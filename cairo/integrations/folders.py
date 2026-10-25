"""Resolve Windows known folders, including redirected OneDrive locations."""

import ctypes
import os
import sys
import uuid
from ctypes import wintypes
from pathlib import Path

FOLDERS = {
    "downloads": ("374DE290-123F-4565-9164-39C4925E467B", "Downloads"),
    "documents": ("FDD39AD0-238F-46AF-ADB4-6C85480369C7", "Documentos"),
    "desktop": ("B4BFCC3A-DB2C-424C-B029-7FE99A87C641", "Área de Trabalho"),
    "pictures": ("33E28130-4E1E-4676-835A-98395C3BC3BB", "Imagens"),
    "music": ("4BD8D571-6D19-48D3-BE97-422220080E43", "Músicas"),
    "videos": ("18989B1D-99B5-455B-841C-AB7C74E4DDFC", "Vídeos"),
}
ALIASES = {
    "download": "downloads",
    "downloads": "downloads",
    "documentos": "documents",
    "documents": "documents",
    "area de trabalho": "desktop",
    "desktop": "desktop",
    "imagens": "pictures",
    "fotos": "pictures",
    "pictures": "pictures",
    "musicas": "music",
    "music": "music",
    "videos": "videos",
}


def known_folder(folder: str) -> Path:
    if folder not in FOLDERS:
        raise ValueError("Pasta pessoal não cadastrada")
    if sys.platform != "win32":
        raise OSError("Pastas pessoais requerem Windows nesta versão")
    guid = (ctypes.c_ubyte * 16).from_buffer_copy(
        uuid.UUID(FOLDERS[folder][0]).bytes_le
    )
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    ole = ctypes.WinDLL("ole32")
    shell.SHGetKnownFolderPath.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole.CoTaskMemFree.restype = None
    pointer = ctypes.c_void_p()
    result = shell.SHGetKnownFolderPath(
        ctypes.byref(guid), 0, None, ctypes.byref(pointer)
    )
    try:
        if result < 0 or not pointer.value:
            raise OSError("Windows não conseguiu localizar " + FOLDERS[folder][1])
        path = Path(ctypes.wstring_at(pointer)).resolve(strict=True)
        if not path.is_dir():
            raise NotADirectoryError("Pasta pessoal indisponível")
        return path
    finally:
        if pointer.value:
            ole.CoTaskMemFree(pointer)


def folder_path(folder: str, path: str = ".") -> Path:
    root = known_folder(folder)
    relative = Path(path)
    if (
        relative.is_absolute()
        or relative.drive
        or ".." in relative.parts
        or ":" in path
    ):
        raise PermissionError("Use um caminho relativo dentro da pasta pessoal")
    candidate = root
    for part in relative.parts:
        candidate /= part
        if candidate.is_symlink() or getattr(candidate, "is_junction", lambda: False)():
            raise PermissionError("Links e junções não são permitidos")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise PermissionError("Caminho fora da pasta pessoal")
    return resolved


def list_personal_files(folder: str, path: str = ".") -> dict:
    directory = folder_path(folder, path)
    if not directory.is_dir():
        raise ValueError("O caminho precisa ser uma pasta")
    entries = []
    with os.scandir(directory) as listing:
        for item in listing:
            if len(entries) == 200:
                break
            blocked = (
                item.is_symlink()
                or getattr(Path(item.path), "is_junction", lambda: False)()
            )
            entries.append(
                {
                    "name": item.name,
                    "kind": "link (blocked)"
                    if blocked
                    else "directory"
                    if item.is_dir(follow_symlinks=False)
                    else "file",
                }
            )
    return {
        "folder": folder,
        "path": path,
        "entries": entries,
        "possibly_truncated": len(entries) == 200,
        "message": FOLDERS[folder][1]
        + ":\n"
        + ("\n".join(e["name"] for e in entries) or "(pasta vazia)"),
    }


def read_personal_file(folder: str, path: str) -> dict:
    target = folder_path(folder, path)
    if not target.is_file():
        raise ValueError("Escolha um arquivo de texto")
    with target.open("rb") as handle:
        data = handle.read(65537)
    if len(data) > 65536:
        raise ValueError("Arquivo excede o limite de leitura de 64 KiB")
    text = data.decode("utf-8-sig")
    if "\x00" in text:
        raise ValueError("O arquivo não é texto UTF-8")
    return {"folder": folder, "path": path, "content": text, "message": text}
