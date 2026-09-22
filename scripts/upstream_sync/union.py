"""Union merge: keep every line from both sides, in fork-first order."""

from __future__ import annotations


def union_merge(ours: str, theirs: str) -> str:
    """Concatenate both sides, dropping content lines already present.

    Blank lines and comments repeat freely, because each side's sections may
    legitimately end with one.
    """
    out: list[str] = []
    seen: set[str] = set()

    for text in (ours, theirs):
        for line in text.splitlines():
            meaningful = line.strip() and not line.lstrip().startswith("#")
            if meaningful:
                if line in seen:
                    continue
                seen.add(line)
            out.append(line)

    if not out:
        return ""
    return "\n".join(out) + "\n"
