"""Render JavaScript in an ephemeral browser; fetch resources through pinned TLS."""

import asyncio
import http.client
import threading
from urllib.parse import quote

from cairo.integrations.web_reader import PublicHTTPS, public_address, validate_url

MAX_RESOURCE = 2 * 1024 * 1024
MAX_TOTAL = 12 * 1024 * 1024
MAX_REQUESTS = 100
MAX_TEXT = 12000
RENDER_TIMEOUT = 45
_SLOTS = threading.BoundedSemaphore(2)


def fetch_resource(
    url: str, method: str, headers: dict, body: bytes | None
) -> tuple[int, dict, bytes]:
    parsed, host = validate_url(url)
    if method not in {"GET", "HEAD", "POST"} or len(body or b"") > 256000:
        raise ValueError("Método ou corpo da página não permitido")
    connection = PublicHTTPS(host, public_address(host))
    try:
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        allowed = {
            k: v
            for k, v in headers.items()
            if k.lower()
            in {
                "accept",
                "content-type",
                "origin",
                "referer",
                "cookie",
                "authorization",
                "user-agent",
            }
        }
        allowed["Accept-Encoding"] = "identity"
        connection.request(
            method, quote(path, safe="/%?=&:+,;@!$'()*~-._"), body=body, headers=allowed
        )
        response = connection.getresponse()
        raw = response.read(MAX_RESOURCE + 1)
        if len(raw) > MAX_RESOURCE:
            raise ValueError("Um recurso da página excedeu 2 MiB")
        response_headers = {
            k.lower(): v
            for k, v in response.getheaders()
            if k.lower()
            not in {
                "connection",
                "transfer-encoding",
                "content-length",
                "keep-alive",
                "proxy-authenticate",
                "proxy-authorization",
                "upgrade",
            }
        }
        return response.status, response_headers, raw
    except http.client.HTTPException:
        raise OSError("O site retornou HTTP inválido durante a renderização") from None
    finally:
        connection.close()


async def _render(url: str, channel: str, wait_for: str = "") -> dict:
    try:
        from playwright.async_api import TimeoutError as BrowserTimeout
        from playwright.async_api import async_playwright
    except ImportError:
        raise OSError(
            'Navegação JavaScript requer Playwright. Execute python -m pip install "cairo-assistant[browser]" ou instale o extra browser a partir da pasta do projeto.'
        ) from None
    counts = {"requests": 0, "bytes": 0, "blocked": 0}
    semaphore = asyncio.Semaphore(4)
    async with async_playwright() as driver:
        options = {"headless": True}
        if channel != "chromium":
            options["channel"] = channel
        browser = await driver.chromium.launch(**options)
        try:
            context = await browser.new_context(
                java_script_enabled=True,
                accept_downloads=False,
                service_workers="block",
                permissions=[],
                locale="pt-BR",
            )

            async def route_request(route):
                request = route.request
                counts["requests"] += 1
                if counts["requests"] > MAX_REQUESTS or request.resource_type in {
                    "media",
                    "font",
                    "image",
                }:
                    counts["blocked"] += 1
                    await route.abort()
                    return
                try:
                    async with semaphore:
                        status, headers, body = await asyncio.to_thread(
                            fetch_resource,
                            request.url,
                            request.method,
                            await request.all_headers(),
                            request.post_data_buffer,
                        )
                    counts["bytes"] += len(body)
                    if counts["bytes"] > MAX_TOTAL:
                        raise ValueError("Página excede o limite total de recursos")
                    await route.fulfill(status=status, headers=headers, body=body)
                except (OSError, ValueError):
                    counts["blocked"] += 1
                    await route.abort()

            await context.route("**/*", route_request)
            # No WebSockets are needed for bounded page reading.
            if hasattr(context, "route_web_socket"):
                await context.route_web_socket("**/*", lambda socket: socket.close())
            page = await context.new_page()
            context.on(
                "page",
                lambda popup: (
                    asyncio.create_task(popup.close()) if popup != page else None
                ),
            )
            page.on("dialog", lambda dialog: asyncio.create_task(dialog.dismiss()))
            page.set_default_timeout(10000)
            response = await page.goto(
                url, wait_until="domcontentloaded", timeout=20000
            )
            if response is None or response.status >= 400:
                raise OSError(
                    "A página não pôde ser carregada; pode exigir login ou bloquear automação"
                )
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except BrowserTimeout:
                pass
            if wait_for:
                await page.locator(wait_for).first.wait_for(
                    state="visible", timeout=10000
                )
            validate_url(page.url)
            content = await page.locator("body").inner_text()
            title = await page.title()
            links = await page.locator("a[href]").evaluate_all(
                "els => els.slice(0, 40).map(a => ({text: a.innerText.slice(0, 120), url: a.href})).filter(a => a.url.startsWith('https://'))"
            )
            if not content.strip():
                raise ValueError(
                    "A página não forneceu texto visível após executar JavaScript"
                )
            return {
                "url": page.url,
                "title": title[:300],
                "content": content[:MAX_TEXT],
                "links": links,
                "javascript": True,
                "truncated": len(content) > MAX_TEXT,
                "blocked_resources": counts["blocked"],
                "untrusted_content": True,
                "message": f"Fonte: {page.url}\n{title[:300]}\n" + content[:MAX_TEXT],
            }
        finally:
            await browser.close()


def render_page(url: str, *, channel: str = "chrome", wait_for: str = "") -> dict:
    validate_url(url)
    if channel not in {"chrome", "msedge", "chromium"} or len(wait_for) > 200:
        raise ValueError("Canal do navegador ou seletor inválido")
    if not _SLOTS.acquire(blocking=False):
        raise OSError(
            "Há duas leituras JavaScript em andamento; tente novamente depois"
        )

    async def bounded():
        return await asyncio.wait_for(
            _render(url, channel, wait_for), timeout=RENDER_TIMEOUT
        )

    try:
        try:
            return asyncio.run(bounded())
        except ImportError:
            raise OSError("Instale o extra browser para habilitar Playwright") from None
        except TimeoutError:
            raise OSError(
                "A página excedeu o limite de 45 segundos de renderização"
            ) from None
        except Exception as exc:
            if exc.__class__.__module__.startswith("playwright"):
                raise OSError(
                    "O navegador não conseguiu renderizar a página. Confira a instalação de Chrome/Edge ou Chromium e tente novamente; login, CAPTCHA e bloqueios do site podem impedir a leitura."
                ) from None
            raise
    finally:
        _SLOTS.release()
