"""Resolve public video metadata and dispatch the documented YTMDesktop URI."""
import json
import os
import re
import unicodedata
import urllib.error
import urllib.request
from urllib.parse import urlencode

MAX_SEARCH_BYTES = 4 * 1024 * 1024
SEARCH_TIMEOUT = 20
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")


def _fold(value):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", value.casefold())
                            if not unicodedata.combining(c)).split())


def search_track(query):
    from cairo.models import NoRedirect

    request = urllib.request.Request(
        "https://www.youtube.com/results?" + urlencode({"search_query": query}),
        headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"},
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=SEARCH_TIMEOUT) as response:
            raw = response.read(MAX_SEARCH_BYTES + 1)
    except (OSError, urllib.error.URLError):
        raise OSError("Não consegui pesquisar a faixa no YouTube. Confira a conexão e tente novamente.") from None
    if len(raw) > MAX_SEARCH_BYTES:
        raise ValueError("A pesquisa de música excedeu o limite de dados")
    html = raw.decode("utf-8", errors="replace")
    match = re.search(r"(?:var\s+)?ytInitialData\s*=\s*", html)
    if not match:
        raise ValueError("O YouTube não disponibilizou os resultados. A pesquisa pode exigir consentimento ou verificação no site.")
    try:
        data, _ = json.JSONDecoder().raw_decode(html[match.end():])
    except (ValueError, RecursionError):
        raise ValueError("A pesquisa do YouTube retornou dados inválidos") from None
    stack, candidates, visited = [data], [], 0
    while stack and visited < 50000 and len(candidates) < 100:
        item = stack.pop()
        visited += 1
        if isinstance(item, dict):
            video = item.get("videoRenderer")
            if isinstance(video, dict) and isinstance(video.get("videoId"), str) and VIDEO_ID.fullmatch(video["videoId"]):
                title = video.get("title", {})
                if not isinstance(title, dict):
                    continue
                runs = title.get("runs", [])
                text = title.get("simpleText") or "".join(run.get("text", "") for run in runs if isinstance(run, dict) and isinstance(run.get("text", ""), str))
                if isinstance(text, str) and text:
                    candidates.append({"id": video["videoId"], "title": text[:500]})
            else:
                stack.extend(reversed(list(item.values())))
        elif isinstance(item, list):
            stack.extend(reversed(item))
    if not candidates:
        raise ValueError("Não encontrei uma faixa reproduzível para essa pesquisa")
    target = set(re.findall(r"\w+", _fold(query)))
    variants = {"extended", "remix", "cover", "slowed", "sped", "nightcore", "loop", "remastered", "version", "instrumental", "karaoke"}
    ordinary = [item for item in candidates if not ((set(re.findall(r"\w+", _fold(item["title"]))) & variants) - target)]
    matching = [item for item in ordinary if target <= set(re.findall(r"\w+", _fold(item["title"])))]
    return (matching or ordinary or candidates)[0]


def play_music(query):
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 300 or any(ord(c) < 32 for c in query):
        raise ValueError("Informe uma música ou artista com até 300 caracteres")
    if os.name != "nt":
        raise OSError("YouTube Music Desktop requer Windows nesta integração")
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"ytmd\shell\open\command"):
            pass
    except OSError:
        raise FileNotFoundError("YouTube Music Desktop não está registrado no Windows. Abra ou reinstale o aplicativo para registrar o protocolo ytmd.") from None
    track = search_track(query.strip())
    if not VIDEO_ID.fullmatch(track["id"]):
        raise ValueError("Identificador de faixa inválido")
    os.startfile("ytmd://play/" + track["id"], "open")
    return {"requested": True, "playing": None, "track": track,
            "message": "Solicitei a reprodução de ‘" + track["title"] + "’ no YouTube Music Desktop. O comando foi enviado ao aplicativo; a reprodução não foi verificada."}
