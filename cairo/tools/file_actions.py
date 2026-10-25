"""File operation schemas kept apart from the general tool registry."""

OPERATIONS = {
    "file_read_text": (
        "Read UTF-8 text up to 64 KiB from a root/path or an absolute path allowed by the configured access mode.",
        {"path": "string"},
        ["path"],
    ),
    "file_list": (
        "List up to 200 directory entries from a root/path or an absolute path allowed by the configured access mode.",
        {"path": "string"},
        ["path"],
    ),
    "file_roots": (
        "List configured file roots and their IDs before choosing paths.",
        {},
        [],
    ),
    "file_info": (
        "Read file/folder size and modification timestamp.",
        {"path": "string"},
        ["path"],
    ),
    "file_hash": (
        "Calculate SHA-256 for a file up to 256 MiB.",
        {"path": "string"},
        ["path"],
    ),
    "file_search": (
        "Find filenames recursively, scanning at most 5000 entries with up to 100 results. No file contents.",
        {"path": "string", "query": "string"},
        ["path", "query"],
    ),
    "file_copy": (
        "Copy one file up to 256 MiB; never overwrites. Source/destination use root/path, e.g. downloads/report.pdf and documents/report.pdf.",
        {"source": "string", "destination": "string"},
        ["source", "destination"],
    ),
    "file_move": (
        "Move one file up to 256 MiB; never overwrites, verifies hashes before removing source.",
        {"source": "string", "destination": "string"},
        ["source", "destination"],
    ),
    "file_rename": (
        "Rename one file; new_name is only a filename. Never overwrites.",
        {"path": "string", "new_name": "string"},
        ["path", "new_name"],
    ),
    "file_mkdir": (
        "Create a directory using root/path or an allowed absolute path. Set parents=true to create intermediate folders.",
        {"path": "string", "parents": "boolean"},
        ["path"],
    ),
    "file_write_text": (
        "Create a NEW UTF-8 file up to 64 KiB using root/path or an allowed absolute path anywhere on local drives when full access is enabled. Empty content creates an empty file. Set create_parents=true for missing folders. Never overwrites.",
        {"path": "string", "content": "string", "create_parents": "boolean"},
        ["path", "content"],
    ),
    "file_edit_text": (
        "Replace one exact, unique occurrence of find with replacement in an existing UTF-8 file up to 64 KiB. Keeps a recoverable backup and returns its ID.",
        {"path": "string", "find": "string", "replacement": "string"},
        ["path", "find", "replacement"],
    ),
    "file_trash": (
        "Move one file to Cairo recoverable trash, returning an operation ID. Never permanently deletes.",
        {"path": "string"},
        ["path"],
    ),
    "file_trash_list": (
        "List up to 100 recoverable trash records in this chat.",
        {},
        [],
    ),
    "file_restore": (
        "Restore an item from this chat trash to its original location; never overwrites.",
        {"operation_id": "string"},
        ["operation_id"],
    ),
}
METHODS = {
    "file_read_text": "read_text",
    "file_list": "list_directory",
    "file_roots": "roots_list",
    "file_info": "info",
    "file_hash": "hash_file",
    "file_search": "search",
    "file_copy": "copy",
    "file_move": "move",
    "file_rename": "rename",
    "file_mkdir": "mkdir",
    "file_write_text": "write_text",
    "file_edit_text": "edit_text",
    "file_trash": "trash_file",
    "file_trash_list": "list_trash",
    "file_restore": "restore",
}
MUTATIONS = frozenset(
    {
        "file_copy",
        "file_move",
        "file_rename",
        "file_mkdir",
        "file_write_text",
        "file_edit_text",
        "file_trash",
        "file_restore",
    }
)


def dispatch(manager, name: str, arguments: dict, session_id: str):
    kwargs = dict(arguments)
    if name in {"file_trash", "file_trash_list", "file_restore", "file_edit_text"}:
        kwargs["session_id"] = session_id
    return getattr(manager, METHODS[name])(**kwargs)
