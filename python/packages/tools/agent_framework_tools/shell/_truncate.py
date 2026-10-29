# Copyright (c) Microsoft. All rights reserved.

"""Head/tail UTF-8 byte truncation shared by the local and Docker shell tools."""

from __future__ import annotations

import codecs


def _validate_output_limit(cap: int, *, name: str = "cap") -> None:
    if cap <= 0:
        raise ValueError(f"{name} must be positive; got {cap}")


class _OutputBuffer:
    """Keep only the beginning and end of a stream, counting omitted bytes."""

    def __init__(self, cap: int) -> None:
        _validate_output_limit(cap)
        self._cap = cap
        self._head = bytearray()
        self._tail = bytearray()
        self.total_bytes = 0

    def append(self, data: bytes) -> None:
        self.total_bytes += len(data)
        head_remaining = self._cap // 2 - len(self._head)
        if head_remaining:
            self._head.extend(data[:head_remaining])
            data = data[head_remaining:]
        tail_cap = self._cap - self._cap // 2
        self._tail.extend(data[-tail_cap:])
        if len(self._tail) > tail_cap:
            del self._tail[:-tail_cap]

    def append_buffer(self, other: _OutputBuffer) -> None:
        """Append another equally sized capture without reconstructing its gaps."""
        self.append(bytes(other._head))
        self.total_bytes += other.total_bytes - len(other._head) - len(other._tail)
        self.append(bytes(other._tail))

    def format(self) -> tuple[str, bool]:
        if self.total_bytes <= self._cap:
            return (self._head + self._tail).decode("utf-8", errors="replace"), False
        head = self._head.decode("utf-8", errors="replace")
        tail = self._tail.decode("utf-8", errors="replace")
        dropped = self.total_bytes - self._cap
        return f"{head}\n[... truncated {dropped} bytes ...]\n{tail}", True


class _TextOutputBuffer:  # pyright: ignore[reportUnusedClass] - used by persistent sessions
    """Incrementally preserve persistent-session decoding and newline stripping."""

    def __init__(self, cap: int, *, strip_newlines: bool = False) -> None:
        self._cap = cap
        self._output = _OutputBuffer(cap)
        self._pending_newlines = _OutputBuffer(cap)
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._strip_newlines = strip_newlines

    def append(self, data: bytes, *, final: bool = False) -> None:
        text = self._decoder.decode(data, final=final)
        if not self._strip_newlines:
            self._output.append(text.encode("utf-8"))
            return
        stripped = text.rstrip("\r\n")
        if stripped:
            self._output.append_buffer(self._pending_newlines)
            self._pending_newlines = _OutputBuffer(self._cap)
            self._output.append(stripped.encode("utf-8"))
        self._pending_newlines.append(text[len(stripped) :].encode("utf-8"))

    def format(self) -> tuple[str, bool]:
        return self._output.format()


def truncate_head_tail(data: bytes, cap: int) -> tuple[str, bool]:
    """Truncate ``data`` to ``cap`` bytes, keeping a head and a tail slice.

    Distributes the budget so head receives ``cap // 2`` bytes and tail
    receives ``cap - cap // 2`` bytes — for an odd ``cap`` the tail keeps
    the extra byte so no input bytes are silently dropped on the boundary.

    Returns the joined (head, marker, tail) string and a boolean indicating
    whether truncation occurred.

    Raises ``ValueError`` if ``cap`` is not positive — a non-positive
    cap has no consistent meaning here and silently treating it as
    "unlimited" would defeat output-capping assumptions in callers.
    """
    output = _OutputBuffer(cap)
    output.append(data)
    return output.format()


def truncate_text_head_tail(text: str, cap: int) -> tuple[str, bool]:
    """``truncate_head_tail`` for already-decoded text.

    Encodes ``text`` as UTF-8, applies the byte-budgeted head/tail split,
    and returns a string. UTF-8 decode with ``errors="replace"`` ensures
    truncation that lands mid-codepoint cannot raise.
    """
    return truncate_head_tail(text.encode("utf-8"), cap)
