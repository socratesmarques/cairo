"""Bounded HTTPS text retrieval with DNS pinning and public-address validation."""

import http.client
import ipaddress
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

MAX_BYTES = 1_000_000
MAX_TEXT = 12000
TIMEOUT = 10


def validate_url(url: str):
    try:
        parsed = urlsplit(url)
        if (
            len(url) > 2048
            or any(ord(c) <= 32 for c in url)
            or "\\" in url
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise ValueError
        host = parsed.hostname.encode("idna").decode("ascii")
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError
        try:
            if not ipaddress.ip_address(host).is_global:
                raise ValueError
        except ValueError as exc:
            # A non-IP hostname is resolved and checked before network access.
            if ":" in host or host.replace(".", "").isdigit():
                raise ValueError from exc
        return parsed, host
    except (ValueError, UnicodeError, AttributeError):
        raise ValueError(
            "Use uma URL HTTPS pública, sem credenciais ou porta alternativa"
        ) from None


def public_address(host: str) -> str:
    try:
        addresses = list(
            dict.fromkeys(
                item[4][0]
                for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            )
        )
    except OSError:
        raise OSError("Não foi possível localizar o site na internet") from None
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise PermissionError(
            "Endereços locais, privados e reservados não podem ser consultados"
        )
    return addresses[0]


class PublicHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=TIMEOUT, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # TLS validates the original hostname, while the socket uses the checked IP.
        raw = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []
        self.title = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg", "template"}:
            self.hidden += 1
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg", "template"} and self.hidden:
            self.hidden -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())
            if self.in_title:
                self.title.append(data.strip())


def read_webpage(url: str) -> dict:
    original = url
    try:
        for _ in range(4):
            parsed, host = validate_url(url)
            connection = PublicHTTPS(host, public_address(host))
            try:
                path = parsed.path or "/"
                if parsed.query:
                    path += "?" + parsed.query
                # Quote non-ASCII URL paths before passing to HTTPConnection.
                from urllib.parse import quote

                connection.request(
                    "GET",
                    quote(path, safe="/%?=&:+,;@!$'()*~-._"),
                    headers={
                        "User-Agent": "Cairo/0.4",
                        "Accept": "text/html,text/plain",
                        "Accept-Encoding": "identity",
                    },
                )
                response = connection.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.getheader("Location")
                    if not location:
                        raise ValueError("Redirecionamento sem destino")
                    url = urljoin(url, location)
                    continue
                if response.status != 200:
                    raise OSError(
                        f"O site respondeu HTTP {response.status}; não foi possível ler a página"
                    )
                content_type = response.getheader("Content-Type", "").lower()
                if (
                    not content_type.startswith(("text/html", "text/plain"))
                    or response.getheader("Content-Encoding", "identity") != "identity"
                ):
                    raise ValueError(
                        "A página precisa fornecer texto/HTML sem compressão"
                    )
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError("Página excede o limite de 1 MB")
                encoding = response.headers.get_content_charset() or "utf-8"
            finally:
                connection.close()
            text = raw.decode(encoding, errors="replace")
            title = ""
            if content_type.startswith("text/html"):
                parser = TextExtractor()
                parser.feed(text)
                text, title = "\n".join(parser.parts), " ".join(parser.title)
            if not text.strip():
                raise ValueError(
                    "A página não forneceu texto; ela pode depender de JavaScript ou login"
                )
            return {
                "url": url,
                "requested_url": original,
                "title": title[:300],
                "content": text[:MAX_TEXT],
                "truncated": len(text) > MAX_TEXT,
                "untrusted_content": True,
                "message": f"Fonte: {url}\n{title[:300]}\n" + text[:MAX_TEXT],
            }
        raise ValueError("A página excedeu o limite de redirecionamentos")
    except (TimeoutError, http.client.HTTPException, ssl.SSLError):
        raise OSError("A leitura do site falhou ou excedeu o tempo limite") from None
    except (LookupError, UnicodeError):
        raise ValueError("A página utiliza um formato de texto não suportado") from None
