"""Read Google results using a dedicated, visible browser profile on one thread."""

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from cairo.integrations.web_reader import public_address

EXTRACT_RESULTS = """() => Array.from(document.querySelectorAll('a')).filter(a => a.querySelector('h3')).slice(0, 20).map(a => {
 const container = a.closest('div.MjjYud') || a.closest('div.g') || a.parentElement;
 return {title: a.querySelector('h3').innerText, url: a.href, snippet: container ? container.innerText.slice(0, 1400) : ''};
})"""


def clean_results(items: list) -> list[dict]:
    results = []
    seen = set()
    for item in items:
        url = item.get("url", "")
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if host in {"www.google.com", "google.com"} and parsed.path == "/url":
            query = parse_qs(parsed.query)
            url = (query.get("q") or query.get("url") or [""])[0]
            parsed = urlsplit(url)
            host = parsed.hostname or ""
        if (
            parsed.scheme not in {"https", "http"}
            or not host
            or (
                host in {"google.com", "www.google.com"}
                and parsed.path.startswith(
                    ("/search", "/preferences", "/setprefs", "/advanced_search")
                )
            )
        ):
            continue
        if not item.get("title", "").strip() or url in seen:
            continue
        seen.add(url)
        results.append(
            {
                "title": item["title"].strip()[:300],
                "url": url[:2048],
                "snippet": item.get("snippet", "")[:1400],
            }
        )
        if len(results) == 5:
            break
    return results


class GoogleSearch:
    def __init__(self, data_dir: Path, channel: str = "chrome"):
        self.profile = data_dir / "google-profile"
        self.channel = channel
        self.worker = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="cairo-google"
        )
        self.driver = None
        self.context = None
        self.page = None
        self.lock = threading.Lock()
        self.closed = False
        self.busy = False

    def _start(self):
        from playwright.sync_api import sync_playwright

        if self.context and self.page and not self.page.is_closed():
            return
        self._shutdown()
        self.profile.mkdir(parents=True, exist_ok=True)
        self.driver = sync_playwright().start()
        options = {
            "headless": False,
            "accept_downloads": False,
            "service_workers": "block",
            "permissions": [],
            "locale": "pt-BR",
        }
        if self.channel != "chromium":
            options["channel"] = self.channel
        self.context = self.driver.chromium.launch_persistent_context(
            str(self.profile), **options
        )

        def guard(route):
            parsed = urlsplit(route.request.url)
            host = parsed.hostname or ""
            allowed = any(
                host == domain or host.endswith("." + domain)
                for domain in (
                    "google.com",
                    "google.com.br",
                    "gstatic.com",
                    "googleusercontent.com",
                    "recaptcha.net",
                )
            )
            if (
                parsed.scheme != "https"
                or not allowed
                or parsed.port not in (None, 443)
            ):
                route.abort()
                return
            try:
                public_address(host)
            except OSError:
                route.abort()
                return
            route.continue_()

        self.context.route("**/*", guard)
        self.page = (
            self.context.pages[0] if self.context.pages else self.context.new_page()
        )
        self.page.set_default_timeout(5000)
        self.page.on("dialog", lambda dialog: dialog.dismiss())

    def _search(self, query: str) -> dict:
        self._start()
        url = "https://www.google.com/search?" + urlencode(
            {"q": query, "num": 5, "hl": "pt-BR"}
        )
        self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
        self.page.bring_to_front()
        body = self.page.locator("body").inner_text()[:16000]
        location = self.page.url
        if "/sorry/" in location or (
            self.page.locator('iframe[src*="recaptcha"]').count()
            and not self.page.locator("h3").count()
        ):
            return {
                "status": "verification_required",
                "query": query,
                "url": url,
                "results": [],
                "message": "O Google pediu uma verificação humana nesta rede. A janela de pesquisa do Cairo está aberta; conclua a verificação nela e repita a pesquisa. Ainda não li resultados desta busca.",
            }
        if (urlsplit(location).hostname or "").startswith("consent."):
            return {
                "status": "consent_required",
                "query": query,
                "url": location,
                "results": [],
                "message": "O Google pediu uma escolha de privacidade na janela de pesquisa do Cairo. Escolha nela e repita a pesquisa.",
            }
        try:
            self.page.locator("h3").first.wait_for(state="visible", timeout=5000)
        except Exception as exc:
            if exc.__class__.__name__ != "TimeoutError":
                raise
        results = clean_results(self.page.evaluate(EXTRACT_RESULTS))
        if not results:
            no_results = any(
                phrase in body.casefold()
                for phrase in (
                    "não encontrou nenhum documento",
                    "nenhum resultado encontrado",
                    "did not match any documents",
                )
            )
            return {
                "status": "no_results" if no_results else "unavailable",
                "query": query,
                "url": location,
                "results": [],
                "message": "O Google não retornou resultados para esta pesquisa."
                if no_results
                else "Não consegui extrair resultados do Google. Confira a janela de pesquisa; a página pode exigir interação ou ter mudado de formato.",
            }
        message = "Resultados do Google para " + query + ":\n"
        message += "\n\n".join(
            f"{i}. {item['title']}\n{item['url']}\n{item['snippet']}"
            for i, item in enumerate(results, 1)
        )
        return {
            "status": "ok",
            "query": query,
            "url": location,
            "results": results,
            "untrusted_content": True,
            "message": message,
        }

    def search(self, query: str) -> dict:
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 500:
            raise ValueError("A pesquisa precisa ter de 1 a 500 caracteres")
        with self.lock:
            if self.closed:
                raise OSError("O leitor Google está encerrado")
            if self.busy:
                raise OSError(
                    "Uma pesquisa Google já está em andamento; aguarde antes de pesquisar novamente"
                )
            self.busy = True
            future = self.worker.submit(self._search, query.strip())

        def finished(_):
            with self.lock:
                self.busy = False

        future.add_done_callback(finished)
        try:
            return future.result(timeout=45)
        except TimeoutError:
            raise OSError(
                "A pesquisa Google excedeu 45 segundos; confira a janela e tente novamente depois"
            ) from None
        except ImportError:
            raise OSError(
                "Leitura Google requer Playwright e Chrome/Edge instalados"
            ) from None
        except Exception as exc:
            if exc.__class__.__module__.startswith("playwright"):
                raise OSError(
                    "Não foi possível pesquisar no Google. Confira a janela do Cairo, a conexão e eventuais verificações do site."
                ) from None
            raise

    def _shutdown(self):
        try:
            if self.context:
                self.context.close()
        finally:
            self.context = None
            self.page = None
            if self.driver:
                self.driver.stop()
                self.driver = None

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            self.worker.submit(self._shutdown)
        self.worker.shutdown(wait=True)
