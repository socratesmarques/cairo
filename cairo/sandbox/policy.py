"""Bound all file tool operations to a configured workspace."""

from pathlib import Path


class WorkspacePolicy:
    """Reject traversal, link traversal and Windows alternate data streams.

    This guards model-requested paths. A hostile local process changing directories
    concurrently requires OS-level isolation, which this application does not supply.
    """

    def __init__(self, workspace: Path, allow_write: bool = False) -> None:
        self.root = Path(workspace).resolve()
        if not self.root.is_dir():
            raise ValueError("Workspace must be an existing directory")
        self.allow_write = allow_write

    def resolve(self, value: str, *, write: bool = False) -> Path:
        if write and not self.allow_write:
            raise PermissionError("Workspace writes are disabled; enable CAIRO_ALLOW_WRITE explicitly")
        if not isinstance(value, str) or not value or len(value) > 2048:
            raise ValueError("path must be a non-empty string of at most 2048 characters")
        # Reject either platform's separators and device/stream syntax consistently.
        if "\x00" in value or ":" in value or "\\" in value:
            raise ValueError("Use workspace-relative paths with forward slashes")
        relative = Path(value)
        if relative.is_absolute() or any(part == ".." for part in relative.parts):
            raise PermissionError("Path must stay within the workspace")
        reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
        cursor = self.root
        for part in relative.parts:
            if part.endswith((" ", ".")) or part.split(".")[0].upper() in reserved:
                raise ValueError("Ambiguous or reserved path component")
            cursor = cursor / part
            if cursor.is_symlink() or getattr(cursor, "is_junction", lambda: False)():
                raise PermissionError("Symbolic links and directory junctions are not allowed")
        resolved = cursor.resolve()
        if not resolved.is_relative_to(self.root):
            raise PermissionError("Path escapes the workspace")
        return resolved
