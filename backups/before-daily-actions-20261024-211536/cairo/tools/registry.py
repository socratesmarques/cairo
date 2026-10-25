"""Useful local tools with consistent JSON results and explicit permissions."""

import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from cairo.sandbox import WorkspacePolicy
from cairo.tools.files import search_files
from cairo.scheduler.reminders import Reminders
from cairo.integrations.desktop_control import DesktopController

MAX_FILE_BYTES = 64 * 1024
MAX_ENTRIES = 200
MAX_NOTE_CHARS = 4000


def _schema(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties,
                           "required": required, "additionalProperties": False}}}


_PATH = {"type": "string", "description": "Workspace-relative path using forward slashes"}
_DESKTOP_TOOLS = frozenset({"desktop_apps", "open_app", "open_site", "search_music", "window_action", "search_web"})
_SCHEMAS = {
    "search_web": _schema("search_web", "Open Google search in the browser. Does NOT read results or research the web.", {"query": {"type": "string"}, "browser": {"type": "string"}}, ["query"]),
    "search_files": _schema("search_files", "Search filenames or UTF-8 text recursively within workspace; bounded scan.", {"query": {"type": "string"}, "path": _PATH, "content": {"type": "boolean"}}, ["query"]),
    "create_directory": _schema("create_directory", "Create workspace directory when writes enabled.", {"path": _PATH}, ["path"]),
    "reminder_create": _schema("reminder_create", "Create user-requested reminder. due is ISO 8601 with timezone. Visible when Cairo UI is open.", {"text": {"type": "string"}, "due": {"type": "string"}}, ["text", "due"]),
    "reminder_list": _schema("reminder_list", "List pending reminders in this conversation.", {}, []),
    "reminder_dismiss": _schema("reminder_dismiss", "Dismiss a reminder in this conversation.", {"id": {"type": "string"}}, ["id"]),
    "desktop_apps": _schema("desktop_apps", "List approved desktop applications and sites.", {}, []),
    "open_app": _schema("open_app", "Open an approved app only at the user request: chrome, edge, notepad, calculator, explorer.", {"app": {"type": "string"}}, ["app"]),
    "open_site": _schema("open_site", "Open approved site youtube_music, youtube or google in chrome or edge.", {"site": {"type": "string"}, "browser": {"type": "string"}}, ["site"]),
    "search_music": _schema("search_music", "Search YouTube Music. Does not automatically play a song.", {"query": {"type": "string"}, "browser": {"type": "string"}}, ["query"]),
    "window_action": _schema("window_action", "Change the topmost matching app window: minimize, maximize, restore, focus.", {"app": {"type": "string"}, "action": {"type": "string"}}, ["app", "action"]),
    "list_files": _schema("list_files", "List at most 200 immediate workspace directory entries.",
                          {"path": _PATH}, []),
    "read_file": _schema("read_file", "Read a UTF-8 text file up to 64 KiB; larger files are rejected.",
                         {"path": _PATH}, ["path"]),
    "write_file": _schema("write_file", "Write UTF-8 text up to 64 KiB, only when workspace writes are enabled.",
                          {"path": _PATH, "content": {"type": "string"},
                           "overwrite": {"type": "boolean", "description": "Explicitly replace an existing file"}},
                          ["path", "content"]),
    "system_info": _schema("system_info", "Read runtime, operating system and CPU count without executing commands.", {}, []),
    "memory_search": _schema("memory_search", "Search persistent notes for this chat session.",
                             {"query": {"type": "string", "maxLength": 500}}, ["query"]),
    "memory_save": _schema("memory_save", "Save a useful note for this chat session (not a workspace file write).",
                           {"content": {"type": "string", "maxLength": MAX_NOTE_CHARS}}, ["content"]),
}
_ALLOW = {
    "MasterAgent": frozenset(_SCHEMAS),
    "DeveloperAgent": frozenset({"list_files", "read_file", "write_file", "search_files", "create_directory"}),
    "ResearchAgent": frozenset({"list_files", "read_file", "memory_search", "memory_save", "search_files"}),
    "SystemAgent": frozenset({"system_info", "list_files", "reminder_create", "reminder_list", "reminder_dismiss"}) | _DESKTOP_TOOLS,
    "Reviewer": frozenset(),
}


class ToolRegistry:
    def __init__(self, workspace: Path, memory: object, allow_write: bool = False, allow_desktop: bool = False) -> None:
        self.policy = WorkspacePolicy(workspace, allow_write)
        self.memory = memory
        self.desktop = DesktopController(allow_desktop)

    def schemas(self, agent: str) -> list[dict]:
        names = _ALLOW.get(agent, frozenset())
        # Return copies so callers cannot mutate the registry's schema contract.
        return json.loads(json.dumps([schema for name, schema in _SCHEMAS.items()
                                    if name in names and (name not in _DESKTOP_TOOLS or self.desktop.enabled) and (name not in {"write_file", "create_directory"} or self.policy.allow_write)]))

    def execute(self, name: str, arguments: dict, agent: str, session_id: str) -> str:
        try:
            if name not in _ALLOW.get(agent, frozenset()):
                raise PermissionError(f"Tool {name!r} is not permitted for {agent}")
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be an object")
            specification = _SCHEMAS[name]["function"]["parameters"]
            if set(arguments) - set(specification["properties"]):
                raise ValueError("Unexpected tool arguments")
            if any(key not in arguments for key in specification["required"]):
                raise ValueError("Required tool argument is missing")
            for key, value in arguments.items():
                expected = specification["properties"][key]["type"]
                if not isinstance(value, str if expected == "string" else bool):
                    raise ValueError(f"Invalid type for {key}")
            result = self._dispatch(name, arguments, session_id)
            return json.dumps({"ok": True, "result": result}, ensure_ascii=False)
        except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
            return json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}, ensure_ascii=False)

    def _dispatch(self, name: str, args: dict[str, Any], session_id: str) -> Any:
        if name in _DESKTOP_TOOLS:
            method = "list_apps" if name == "desktop_apps" else name
            return getattr(self.desktop, method)(**args)
        if name == "search_files":
            return search_files(self.policy, **args)
        if name == "create_directory":
            directory = self.policy.resolve(args["path"], write=True)
            directory.mkdir(parents=True, exist_ok=True)
            return {"created": True, "path": args["path"]}
        if name.startswith("reminder_"):
            reminders = Reminders(self.memory)
            if name == "reminder_create":
                item = reminders.create(session_id, args["text"], args["due"])
                return {**item, "message": "Lembrete salvo para " + item["due"] + ". Aparece com Cairo aberto."}
            if name == "reminder_list":
                items = reminders.list(session_id)
                return {"reminders": items, "message": "\n".join(item["due"] + " — " + item["text"] for item in items) or "Nenhum lembrete pendente."}
            return reminders.dismiss(args["id"], session_id)
        if name == "list_files":
            directory = self.policy.resolve(args.get("path", "."))
            if not directory.is_dir():
                raise ValueError("Path is not a directory")
            entries = []
            truncated = False
            with os.scandir(directory) as listing:
                for entry in listing:
                    if len(entries) >= MAX_ENTRIES:
                        truncated = True
                        break
                    item = {"path": Path(entry.path).relative_to(self.policy.root).as_posix()}
                    if entry.is_symlink() or getattr(Path(entry.path), "is_junction", lambda: False)():
                        item["kind"] = "link (blocked)"
                    else:
                        item["kind"] = "directory" if entry.is_dir(follow_symlinks=False) else "file"
                    entries.append(item)
            return {"entries": sorted(entries, key=lambda item: item["path"]), "truncated": truncated}
        if name == "read_file":
            path = self.policy.resolve(args["path"])
            if not path.is_file():
                raise ValueError("Path is not a regular file")
            with path.open("rb") as handle:
                data = handle.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                raise ValueError("File exceeds the 64 KiB read limit")
            return {"path": args["path"], "content": data.decode("utf-8"), "bytes": len(data)}
        if name == "write_file":
            return self._write(args)
        if name == "system_info":
            release = str(sys.getwindowsversion().build) if sys.platform == "win32" else os.uname().release
            architecture = os.environ.get("PROCESSOR_ARCHITECTURE", "unknown") if sys.platform == "win32" else os.uname().machine
            return {"os": "Windows" if sys.platform == "win32" else sys.platform, "release": release,
                    "architecture": architecture, "python": sys.version.split()[0],
                    "cpu_count": os.cpu_count(), "workspace": str(self.policy.root),
                    "workspace_writes_enabled": self.policy.allow_write, "shell_execution": False}
        if name == "memory_search":
            query = args["query"].strip()
            if not query or len(query) > 500:
                raise ValueError("query must contain 1 to 500 characters")
            results = self.memory.search(query, session_id)  # type: ignore[attr-defined]
            return {"notes": results[:20]}
        if name == "memory_save":
            content = args["content"].strip()
            if not content or len(content) > MAX_NOTE_CHARS:
                raise ValueError("Note must contain 1 to 4000 characters")
            self.memory.save_note(session_id, content)  # type: ignore[attr-defined]
            return {"saved": True}
        raise ValueError("Unknown tool")

    def _write(self, args: dict[str, Any]) -> dict:
        path = self.policy.resolve(args["path"], write=True)
        data = args["content"].encode("utf-8")
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("Content exceeds the 64 KiB write limit")
        if path.exists() and not args.get("overwrite", False):
            raise FileExistsError("File exists; overwrite=true is required to replace it")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.policy.resolve(args["path"], write=True)
        if not args.get("overwrite", False):
            # Exclusive creation protects existing files even if another caller wins.
            with path.open("xb") as handle:
                handle.write(data)
        else:
            temporary: str | None = None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".cairo-", delete=False) as handle:
                    temporary = handle.name
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                self.policy.resolve(args["path"], write=True)
                os.replace(temporary, path)
                temporary = None
            finally:
                if temporary is not None:
                    Path(temporary).unlink(missing_ok=True)
        return {"path": args["path"], "bytes": len(data), "written": True}
