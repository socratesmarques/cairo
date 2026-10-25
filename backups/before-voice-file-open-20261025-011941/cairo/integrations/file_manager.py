"""Bounded file mutations with exclusive destinations and recoverable trash."""

import hashlib
import json
import os
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cairo.sandbox.file_roots import FileRoots

MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_TEXT_BYTES = 64 * 1024
MAX_SCAN = 5000


class FileManager:
    def __init__(self, roots: FileRoots, enabled: bool = False):
        self.roots, self.enabled = roots, enabled
        self.lock = threading.RLock()
        self.trash = roots.data_dir / "file-trash"

    def require(self):
        if not self.enabled:
            raise PermissionError(
                "Operações pessoais desativadas; configure CAIRO_ALLOW_FILE_OPERATIONS=true"
            )

    @staticmethod
    def digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            total = 0
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                total += len(block)
                if total > MAX_FILE_BYTES:
                    raise ValueError("Arquivo excede o limite de 256 MiB")
                digest.update(block)
        return digest.hexdigest()

    def source(self, value: str) -> Path:
        source = self.roots.resolve(value)
        if not source.is_file():
            raise ValueError(
                "Esta operação requer um arquivo; pastas não são movidas ou apagadas em lote"
            )
        if source.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("Arquivo excede o limite de 256 MiB por operação")
        return source

    @staticmethod
    def copy_exclusive(source: Path, destination: Path):
        # Exclusive creation never overwrites an existing file, including races.
        with destination.open("xb") as output:
            try:
                with source.open("rb") as handle:
                    copied = 0
                    while block := handle.read(1024 * 1024):
                        copied += len(block)
                        if copied > MAX_FILE_BYTES:
                            raise ValueError(
                                "Arquivo cresceu além do limite durante a cópia"
                            )
                        output.write(block)
                output.flush()
                os.fsync(output.fileno())
            except Exception:
                output.close()
                destination.unlink(missing_ok=True)
                raise
        shutil.copystat(source, destination, follow_symlinks=False)

    def roots_list(self) -> dict:
        self.require()
        roots = self.roots.catalog()
        return {
            "roots": roots,
            "message": "Pastas disponíveis:\n"
            + "\n".join(
                item["id"] + ": " + item.get("path", "indisponível") for item in roots
            ),
        }

    def info(self, path: str) -> dict:
        self.require()
        item = self.roots.resolve(path)
        stat = item.stat()
        result = {
            "path": str(item),
            "name": item.name,
            "kind": "directory" if item.is_dir() else "file",
            "bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(
                stat.st_mtime, timezone.utc
            ).isoformat(),
        }
        result["message"] = (
            f"{result['name']}: {result['kind']}, {stat.st_size} bytes; modificado em {result['modified_at']}."
        )
        return result

    def read_text(self, path: str) -> dict:
        self.require()
        target = self.source(path)
        with target.open("rb") as handle:
            data = handle.read(MAX_TEXT_BYTES + 1)
        if len(data) > MAX_TEXT_BYTES:
            raise ValueError("Leitura de texto limitada a 64 KiB")
        text = data.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError("O arquivo não é texto UTF-8")
        return {"path": str(target), "content": text, "message": text}

    def list_directory(self, path: str) -> dict:
        self.require()
        target = self.roots.resolve(path)
        if not target.is_dir():
            raise NotADirectoryError("Escolha uma pasta para listar")
        entries = []
        with os.scandir(target) as listing:
            for item in listing:
                if len(entries) >= 200:
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
            "path": str(target),
            "entries": entries,
            "possibly_truncated": len(entries) == 200,
            "message": "\n".join(item["name"] for item in entries) or "(pasta vazia)",
        }

    def hash_file(self, path: str) -> dict:
        self.require()
        digest = self.digest(self.source(path))
        return {"sha256": digest, "message": "SHA-256: " + digest}

    def copy(self, source: str, destination: str) -> dict:
        self.require()
        with self.lock:
            original = self.source(source)
            target = self.roots.resolve(destination, write=True)
            if not target.parent.is_dir():
                raise FileNotFoundError(
                    "A pasta de destino não existe; crie-a primeiro"
                )
            self.copy_exclusive(original, target)
            return {
                "source": source,
                "destination": destination,
                "message": f"Copiei {source} para {destination}.",
            }

    def move(self, source: str, destination: str) -> dict:
        self.require()
        with self.lock:
            original = self.source(source)
            self.roots.resolve(source, write=True)
            digest = self.digest(original)
            self.copy(source, destination)
            target = self.roots.resolve(destination)
            if self.digest(target) != digest or self.digest(original) != digest:
                raise OSError(
                    "O arquivo mudou durante a movimentação. A origem foi preservada; confira também a cópia de destino."
                )
            original.unlink()
            return {
                "source": source,
                "destination": destination,
                "message": f"Movi {source} para {destination}.",
            }

    def rename(self, path: str, new_name: str) -> dict:
        self.require()
        if (
            not new_name
            or any(c in new_name for c in "/\\:")
            or new_name in {".", ".."}
        ):
            raise ValueError("Informe somente o novo nome do arquivo")
        normalized = path.replace("\\", "/")
        destination = normalized.rsplit("/", 1)[0] + "/" + new_name
        return self.move(path, destination)

    def mkdir(self, path: str, parents: bool = False) -> dict:
        self.require()
        with self.lock:
            target = self.roots.resolve(path, write=True)
            target.mkdir(parents=parents, exist_ok=False)
            return {"path": path, "message": "Criei a pasta " + path + "."}

    def write_text(self, path: str, content: str, create_parents: bool = False) -> dict:
        self.require()
        data = content.encode("utf-8")
        if len(data) > MAX_TEXT_BYTES:
            raise ValueError("Texto excede o limite de 64 KiB")
        with self.lock:
            target = self.roots.resolve(path, write=True)
            if create_parents:
                target.parent.mkdir(parents=True, exist_ok=True)
                target = self.roots.resolve(path, write=True)
            with target.open("xb") as output:
                try:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
                except Exception:
                    output.close()
                    target.unlink(missing_ok=True)
                    raise
            return {
                "path": path,
                "bytes": len(data),
                "message": "Criei o arquivo "
                + path
                + ". Arquivos existentes não são sobrescritos.",
            }

    def edit_text(
        self, path: str, find: str, replacement: str, session_id: str
    ) -> dict:
        self.require()
        if not find:
            raise ValueError("Informe um trecho existente e não vazio para substituir")
        with self.lock:
            original = self.source(path)
            self.roots.resolve(path, write=True)
            with original.open("rb") as handle:
                data = handle.read(MAX_TEXT_BYTES + 1)
            if len(data) > MAX_TEXT_BYTES:
                raise ValueError("Edição limitada a arquivos de texto de 64 KiB")
            text = data.decode("utf-8")
            if "\x00" in text or text.count(find) != 1:
                raise ValueError(
                    "O trecho deve ocorrer exatamente uma vez em um arquivo de texto UTF-8"
                )
            updated = text.replace(find, replacement, 1).encode("utf-8")
            if len(updated) > MAX_TEXT_BYTES:
                raise ValueError("Texto resultante excede 64 KiB")
            record = {
                "id": uuid.uuid4().hex,
                "session_id": session_id,
                "source": path,
                "sha256": hashlib.sha256(data).hexdigest(),
                "after_sha256": hashlib.sha256(updated).hexdigest(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "pending_edit",
            }
            self._record(record)
            self.copy_exclusive(original, self.trash / (record["id"] + ".payload"))
            temporary = original.parent / (".cairo-edit-" + record["id"] + ".tmp")
            try:
                with temporary.open("xb") as handle:
                    handle.write(updated)
                    handle.flush()
                    os.fsync(handle.fileno())
                if self.digest(original) != record["sha256"]:
                    raise OSError(
                        "O arquivo mudou durante a edição; operação cancelada"
                    )
                os.replace(temporary, original)
            finally:
                temporary.unlink(missing_ok=True)
            record["status"] = "edited"
            self._record(record)
            return {
                "path": path,
                "operation_id": record["id"],
                "message": "Editei " + path + ". Backup recuperável: " + record["id"],
            }

    def _record(self, record: dict):
        self.trash.mkdir(parents=True, exist_ok=True)
        target = self.trash / (record["id"] + ".json")
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, target)

    def trash_file(self, path: str, session_id: str) -> dict:
        self.require()
        with self.lock:
            original = self.source(path)
            self.roots.resolve(path, write=True)
            record = {
                "id": uuid.uuid4().hex,
                "session_id": session_id,
                "source": path,
                "sha256": self.digest(original),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "pending",
            }
            self._record(record)
            payload = self.trash / (record["id"] + ".payload")
            self.copy_exclusive(original, payload)
            if (
                self.digest(payload) != record["sha256"]
                or self.digest(original) != record["sha256"]
            ):
                raise OSError(
                    "Arquivo mudou durante a operação; a origem foi preservada"
                )
            original.unlink()
            record["status"] = "trashed"
            self._record(record)
            return {
                "operation_id": record["id"],
                "message": "Enviei "
                + path
                + " à lixeira recuperável do Cairo. Código: "
                + record["id"],
            }

    def list_trash(self, session_id: str) -> dict:
        self.require()
        items = []
        with self.lock:
            for file in sorted(self.trash.glob("*.json"), key=lambda p: p.name):
                record = json.loads(file.read_text(encoding="utf-8"))
                if record["session_id"] == session_id and record["status"] in {
                    "trashed",
                    "pending",
                    "edited",
                    "pending_edit",
                }:
                    items.append(
                        {k: record[k] for k in ("id", "source", "status", "created_at")}
                    )
        items = items[-100:]
        return {
            "items": items,
            "message": "\n".join(
                item["id"] + " — " + item["source"] + " (" + item["status"] + ")"
                for item in items
            )
            or "Lixeira desta conversa vazia.",
        }

    def restore(self, operation_id: str, session_id: str) -> dict:
        self.require()
        if len(operation_id) != 32 or any(
            c not in "0123456789abcdef" for c in operation_id
        ):
            raise ValueError("Código da lixeira inválido")
        with self.lock:
            record = json.loads(
                (self.trash / (operation_id + ".json")).read_text(encoding="utf-8")
            )
            if record["session_id"] != session_id:
                raise PermissionError("O item pertence a outra conversa")
            if record["status"] not in {"trashed", "pending", "edited", "pending_edit"}:
                raise ValueError("O item já foi restaurado")
            original = self.roots.resolve(record["source"], write=True)
            payload = self.trash / (operation_id + ".payload")
            if self.digest(payload) != record["sha256"]:
                raise OSError("A cópia da lixeira está incompleta ou foi alterada")
            if record["status"] in {"edited", "pending_edit"}:
                current = self.digest(original)
                if current == record["sha256"]:
                    record["status"] = "restored"
                    self._record(record)
                    return {
                        "path": record["source"],
                        "message": "O arquivo original já está preservado.",
                    }
                if current != record["after_sha256"]:
                    raise ValueError(
                        "O arquivo foi alterado novamente; restauração recusada para não perder mudanças"
                    )
                temporary = original.parent / (
                    ".cairo-restore-" + operation_id + ".tmp"
                )
                try:
                    self.copy_exclusive(payload, temporary)
                    if self.digest(original) != current:
                        raise OSError("O arquivo mudou durante a restauração")
                    os.replace(temporary, original)
                finally:
                    temporary.unlink(missing_ok=True)
            else:
                self.copy_exclusive(payload, original)
            record["status"] = "restored"
            self._record(record)
            return {
                "path": record["source"],
                "message": "Restaurei " + record["source"] + ".",
            }

    def search(self, path: str, query: str) -> dict:
        self.require()
        if not 1 <= len(query.strip()) <= 120:
            raise ValueError("A pesquisa precisa de 1 a 120 caracteres")
        root = self.roots.resolve(path)
        if not root.is_dir():
            raise ValueError("Escolha uma pasta para pesquisar")
        results = []
        scanned = 0
        stopped = False
        for directory, subdirs, files in os.walk(root, followlinks=False):
            valid = []
            for name in subdirs:
                item = Path(directory) / name
                try:
                    self.roots.resolve(str(item))
                    valid.append(name)
                except (ValueError, OSError):
                    pass
            subdirs[:] = valid
            scanned += 1 + len(files)
            if scanned > MAX_SCAN:
                stopped = True
                break
            for name in files:
                if query.casefold() in name.casefold():
                    try:
                        item = self.roots.resolve(str(Path(directory) / name))
                        results.append(str(item))
                    except (ValueError, OSError):
                        continue
                    if len(results) >= 100:
                        stopped = True
                        break
            if stopped:
                break
        return {
            "matches": results,
            "truncated": stopped,
            "message": "\n".join(results)
            or "Nenhum arquivo encontrado dentro do limite de busca.",
        }
