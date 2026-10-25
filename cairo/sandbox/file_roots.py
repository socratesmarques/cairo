"""Named file roots sharing the workspace's traversal and reparse-point checks."""

import ctypes
import os
import re
from pathlib import Path

from cairo.integrations.folders import FOLDERS, known_folder
from cairo.sandbox.policy import WorkspacePolicy


class FileRoots:
    def __init__(
        self,
        workspace: Path,
        data_dir: Path,
        extra: dict[str, str] | None = None,
        *,
        full_access: bool = False,
    ):
        self.workspace = workspace.resolve()
        self.data_dir = data_dir.resolve()
        self.application = Path(__file__).resolve().parents[2]
        self.extra = extra or {}
        self.full_access = full_access
        for alias, value in self.extra.items():
            if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", alias) or alias in {
                *FOLDERS,
                "workspace",
            }:
                raise ValueError("Alias de pasta extra inválido ou reservado")
            path = Path(value)
            if not path.is_absolute() or path == Path(path.anchor):
                raise ValueError(
                    "Cadastre uma pasta absoluta específica, não a raiz de uma unidade"
                )

    def root(self, name: str) -> Path:
        if name == "workspace":
            root = self.workspace
        elif self.full_access and re.fullmatch(r"drive_[a-z]", name):
            root = Path(name[-1].upper() + ":/")
        elif name in self.extra:
            root = Path(self.extra[name]).resolve(strict=True)
        else:
            root = known_folder(name)
        if not root.is_dir():
            raise NotADirectoryError("Pasta cadastrada indisponível")
        return root

    def catalog(self) -> list[dict]:
        result = []
        drives = []
        if self.full_access and os.name == "nt":
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetLogicalDrives.restype = ctypes.c_uint32
            mask = kernel.GetLogicalDrives()
            drives = ["drive_" + chr(97 + i) for i in range(26) if mask & (1 << i)]
        for name in ["workspace", *FOLDERS, *self.extra, *drives]:
            try:
                result.append(
                    {"id": name, "path": str(self.root(name)), "available": True}
                )
            except OSError:
                result.append({"id": name, "available": False})
        return result

    def resolve(self, value: str, *, write: bool = False) -> Path:
        if not isinstance(value, str) or not 1 <= len(value) <= 2048 or "\x00" in value:
            raise ValueError("Informe uma referência como downloads/arquivo.txt")
        value = value.replace("\\", "/")
        if value.startswith("//"):
            raise PermissionError(
                "Use uma unidade local ou montada; caminhos de dispositivo/UNC não são aceitos"
            )
        candidate = Path(value)
        if candidate.is_absolute():
            if self.full_access:
                root = Path(candidate.anchor)
                relative = candidate.relative_to(root).as_posix()
                path = WorkspacePolicy(root, allow_write=True).resolve(relative)
                return self._checked(path, root, write)
            matches = []
            for item in self.catalog():
                if item["available"]:
                    root = Path(item["path"])
                    if candidate.is_relative_to(root):
                        matches.append((root, candidate.relative_to(root).as_posix()))
            if not matches:
                raise PermissionError("Caminho fora das pastas cadastradas")
            root, relative = max(matches, key=lambda pair: len(pair[0].parts))
        else:
            name, _, relative = value.partition("/")
            root = self.root(name)
            relative = relative or "."
        path = WorkspacePolicy(root, allow_write=True).resolve(relative)
        return self._checked(path, root, write)

    def _checked(self, path: Path, root: Path, write: bool) -> Path:
        protected = path.is_relative_to(self.data_dir) or (
            path.is_relative_to(self.application)
            and not path.is_relative_to(self.workspace)
        )
        if protected and (write or not self.full_access):
            raise PermissionError(
                "Arquivos internos do Cairo e armazenamento são protegidos"
            )
        if write and path == root:
            raise PermissionError("A própria pasta raiz não pode ser alterada")
        return path
