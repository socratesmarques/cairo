"""Bounded recursive search without following junctions or symbolic links."""
import os

MAX_SCAN = 2000
MAX_RESULTS = 100
MAX_BYTES = 65536


def search_files(policy, query, path=".", content=False):
    if not query.strip() or len(query) > 200:
        raise ValueError("Pesquisa deve conter 1 a 200 caracteres")
    root = policy.resolve(path)
    if not root.is_dir():
        raise ValueError("Caminho não é uma pasta")
    results, skipped, scanned = [], 0, 0
    pending = [root]
    needle = query.casefold()
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                scanned += 1
                if scanned > MAX_SCAN:
                    return dict(matches=results, truncated=True, skipped=skipped)
                relative = os.path.relpath(entry.path, policy.root).replace(os.sep, "/")
                try:
                    candidate = policy.resolve(relative)
                    if candidate.is_dir():
                        pending.append(candidate)
                        continue
                    if not candidate.is_file():
                        continue
                    if content:
                        with candidate.open("rb") as file:
                            data = file.read(MAX_BYTES + 1)
                        if len(data) > MAX_BYTES or b"\x00" in data:
                            skipped += 1
                            continue
                        lines = data.decode("utf-8").splitlines()
                        for number, line in enumerate(lines, 1):
                            if needle in line.casefold():
                                results.append(dict(path=relative, line=number, preview=line[:300]))
                                break
                    elif needle in candidate.name.casefold():
                        results.append(dict(path=relative))
                except (OSError, ValueError, UnicodeError):
                    skipped += 1
                if len(results) >= MAX_RESULTS:
                    return dict(matches=results, truncated=True, skipped=skipped)
    return dict(matches=results, truncated=False, skipped=skipped)
