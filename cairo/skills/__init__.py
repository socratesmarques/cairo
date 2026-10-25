"""Small declarative skill registry; skills never grant additional permissions."""

from pathlib import Path

_BUNDLED = ("development", "local_research", "system_check")


def load_skills() -> str:
    """Load bounded, packaged Markdown playbooks in a deterministic order."""
    directory = Path(__file__).parent
    return "\n\n".join(
        f"## {name}\n{(directory / (name + '.md')).read_text(encoding='utf-8')[:12000]}"
        for name in _BUNDLED
    )


__all__ = ["load_skills"]
