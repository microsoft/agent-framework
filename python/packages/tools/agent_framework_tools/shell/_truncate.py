# Copyright (c) Microsoft. All rights reserved.

"""Head/tail UTF-8 byte truncation shared by the local and Docker shell tools."""

from __future__ import annotations


def truncate_head_tail(data: bytes, cap: int) -> tuple[str, bool]:
    """Truncate ``data`` to ``cap`` bytes, keeping a head and a tail slice.

    Distributes the budget so head receives ``cap // 2`` bytes and tail
    receives ``cap - cap // 2`` bytes — for an odd ``cap`` the tail keeps
    the extra byte so no input bytes are silently dropped on the boundary.

    Returns the joined (head, marker, tail) string and a boolean indicating
    whether truncation occurred.
    """
    if cap <= 0 or len(data) <= cap:
        return data.decode("utf-8", errors="replace"), False
    head_cap = cap // 2
    tail_cap = cap - head_cap
    head = data[:head_cap].decode("utf-8", errors="replace")
    tail = data[len(data) - tail_cap:].decode("utf-8", errors="replace")
    dropped = len(data) - cap
    return f"{head}\n[... truncated {dropped} bytes ...]\n{tail}", True


def truncate_text_head_tail(text: str, cap: int) -> tuple[str, bool]:
    """``truncate_head_tail`` for already-decoded text.

    Encodes ``text`` as UTF-8, applies the byte-budgeted head/tail split,
    and returns a string. UTF-8 decode with ``errors="replace"`` ensures
    truncation that lands mid-codepoint cannot raise.
    """
    return truncate_head_tail(text.encode("utf-8"), cap)
