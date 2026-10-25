"""Interactive JavaScript contexts isolated per Cairo chat, owned by one event loop."""

import asyncio
import threading
import uuid
from concurrent.futures import TimeoutError as FutureTimeout

from cairo.integrations.browser_reader import fetch_resource
from cairo.integrations.web_reader import validate_url

KEYS = {
    "enter": "Enter",
    "tab": "Tab",
    "escape": "Escape",
    "ctrl+a": "Control+a",
    "ctrl+f": "Control+f",
    "ctrl+l": "Control+l",
    "up": "ArrowUp",
    "down": "ArrowDown",
    "left": "ArrowLeft",
    "right": "ArrowRight",
}
MAX_SESSIONS = 3


class BrowserControl:
    def __init__(self, channel: str = "chrome", *, headless: bool = False):
        self.channel, self.headless = channel, headless
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(
            target=self.loop.run_forever, daemon=True, name="cairo-browser"
        )
        self.thread.start()
        self.driver = None
        self.browser = None
        self.sessions = {}
        self.serial = None
        self.closed = False
        self.lock = threading.Lock()

    async def _start(self):
        if self.serial is None:
            self.serial = asyncio.Lock()
        if self.browser is None:
            from playwright.async_api import async_playwright

            self.driver = await async_playwright().start()
            options = {"headless": self.headless}
            if self.channel != "chromium":
                options["channel"] = self.channel
            self.browser = await self.driver.chromium.launch(**options)

    async def _new_session(self, sid):
        if len(self.sessions) >= MAX_SESSIONS:
            oldest = next(iter(self.sessions))
            await self.sessions.pop(oldest)["context"].close()
        context = await self.browser.new_context(
            java_script_enabled=True,
            accept_downloads=False,
            service_workers="block",
            permissions=[],
            locale="pt-BR",
        )
        state = {
            "context": context,
            "page": None,
            "elements": {},
            "requests": 0,
            "bytes": 0,
            "closing": False,
        }
        parallel = asyncio.Semaphore(4)

        async def route_request(route):
            request = route.request
            state["requests"] += 1
            try:
                if state["requests"] > 100 or request.resource_type in {
                    "media",
                    "font",
                }:
                    await route.abort()
                    return
                async with parallel:
                    status, headers, body = await asyncio.to_thread(
                        fetch_resource,
                        request.url,
                        request.method,
                        await request.all_headers(),
                        request.post_data_buffer,
                    )
                state["bytes"] += len(body)
                if state["bytes"] > 12 * 1024 * 1024:
                    await route.abort()
                    return
                await route.fulfill(status=status, headers=headers, body=body)
            except (OSError, ValueError):
                if not state["closing"]:
                    await route.abort()
            except Exception as exc:
                if not exc.__class__.__module__.startswith("playwright"):
                    raise

        await context.route("**/*", route_request)
        if hasattr(context, "route_web_socket"):
            await context.route_web_socket("**/*", lambda socket: socket.close())
        page = await context.new_page()
        state["page"] = page
        page.set_default_timeout(10000)
        context.on(
            "page",
            lambda popup: asyncio.create_task(popup.close()) if popup != page else None,
        )
        page.on("dialog", lambda dialog: asyncio.create_task(dialog.dismiss()))
        self.sessions[sid] = state
        return state

    async def _snapshot(self, state):
        page = state["page"]
        for handle in state["elements"].values():
            try:
                await handle.dispose()
            except Exception:
                pass
        state["elements"] = {}
        elements = []
        locator = page.locator(
            'button,a[href],input,textarea,select,[role="button"],[role="link"]'
        )
        for index in range(min(100, await locator.count())):
            handle = await locator.nth(index).element_handle()
            if handle is None:
                continue
            if not await handle.is_visible():
                await handle.dispose()
                continue
            metadata = await handle.evaluate(
                "e => ({tag:e.tagName.toLowerCase(), type:e.getAttribute('type') || '', name:(e.getAttribute('aria-label') || e.getAttribute('placeholder') || e.innerText || e.getAttribute('name') || '').slice(0,160), options:e.tagName==='SELECT' ? Array.from(e.options).slice(0,20).map(o=>({value:o.value,label:o.label})) : undefined})"
            )
            token = "dom:" + uuid.uuid4().hex
            state["elements"][token] = handle
            metadata["id"] = token
            elements.append(metadata)
        url = page.url
        validate_url(url)
        text = (await page.locator("body").inner_text())[:10000]
        title = (await page.title())[:300]
        return {
            "url": url,
            "title": title,
            "content": text,
            "elements": elements,
            "untrusted_content": True,
            "message": f"Página: {title}\n{url}\n{text}\n\nControles:\n"
            + "\n".join(
                item["id"] + " — " + item["tag"] + " — " + item["name"]
                for item in elements
            ),
        }

    async def _call(self, action, args, sid):
        if self.serial is None:
            self.serial = asyncio.Lock()
        async with self.serial:
            await self._start()
            state = self.sessions.get(sid)
            if action == "open":
                validate_url(args["url"])
                if state is None or state["page"].is_closed():
                    state = await self._new_session(sid)
                state["requests"], state["bytes"] = 0, 0
                response = await state["page"].goto(
                    args["url"], wait_until="domcontentloaded", timeout=20000
                )
                if response is None or response.status >= 400:
                    raise OSError(
                        "O site retornou um erro; confira a janela do navegador"
                    )
                try:
                    await state["page"].wait_for_load_state("networkidle", timeout=3000)
                except Exception as exc:
                    if exc.__class__.__name__ != "TimeoutError":
                        raise
            elif state is None or state["page"].is_closed():
                raise ValueError("Abra uma página nesta conversa antes de interagir")
            else:
                state["requests"], state["bytes"] = 0, 0
                page = state["page"]
                if action in {"click", "fill", "select"}:
                    handle = state["elements"].get(args["element"])
                    if handle is None or not await handle.is_visible():
                        raise ValueError(
                            "Controle inválido ou antigo; leia a página para obter IDs novos"
                        )
                    if action == "click":
                        await handle.click()
                    elif action == "fill":
                        if len(args["text"]) > 4000:
                            raise ValueError("Texto limitado a 4 mil caracteres")
                        await handle.fill(args["text"])
                    else:
                        await handle.select_option(value=args["value"])
                    await asyncio.sleep(0.2)
                elif action == "keys":
                    key = args["keys"].lower()
                    if key not in KEYS:
                        raise ValueError("Atalho não suportado pelo navegador")
                    await page.keyboard.press(KEYS[key])
                elif action == "scroll":
                    if args["direction"] not in {"up", "down"}:
                        raise ValueError("Direção deve ser up ou down")
                    await page.mouse.wheel(
                        0, 650 if args["direction"] == "down" else -650
                    )
                    await asyncio.sleep(0.2)
                elif action == "wait":
                    if len(args["selector"]) > 200:
                        raise ValueError("Seletor limitado a 200 caracteres")
                    await page.locator(args["selector"]).first.wait_for(
                        state="visible", timeout=10000
                    )
                elif action == "close":
                    state["closing"] = True
                    await state["context"].close()
                    self.sessions.pop(sid, None)
                    return {"message": "Fechei o navegador desta conversa."}
                elif action != "read":
                    raise ValueError("Ação de navegador inválida")
            return await self._snapshot(state)

    def call(self, action, args, sid):
        with self.lock:
            if self.closed:
                raise OSError("Navegador encerrado")
            future = asyncio.run_coroutine_threadsafe(
                self._call(action, args, sid), self.loop
            )
        try:
            return future.result(timeout=45)
        except FutureTimeout:
            future.cancel()
            raise OSError("A interação no navegador excedeu 45 segundos") from None
        except ImportError:
            raise OSError(
                "Automação do navegador requer Playwright e o extra browser"
            ) from None
        except Exception as exc:
            if exc.__class__.__module__.startswith("playwright"):
                raise OSError(
                    "A página ou controle não respondeu. Leia a página novamente; login, CAPTCHA, navegação ou elementos removidos podem exigir interação."
                ) from None
            raise

    async def _shutdown(self):
        for state in self.sessions.values():
            state["closing"] = True
        if self.browser:
            await self.browser.close()
        if self.driver:
            await self.driver.stop()
        self.sessions.clear()

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
        try:
            asyncio.run_coroutine_threadsafe(self._shutdown(), self.loop).result(
                timeout=15
            )
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=3)
            if not self.thread.is_alive():
                self.loop.close()
