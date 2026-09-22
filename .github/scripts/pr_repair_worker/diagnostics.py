"""Bounded, redacted diagnostics shared verbatim with the public repair worker.

This reduces accidental disclosure; arbitrary output can encode secrets in formats
no recognizer can identify. No raw-output fallback is permitted.
"""

from __future__ import annotations

import ipaddress
import re

MAX_INPUT_BYTES = 1_048_576
MAX_OUTPUT_BYTES = 16_384
MAX_LINES = 100
MAX_LINE_CHARS = 1_000
_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)?)")
_ASSIGNMENT = re.compile(r"""(["']?\b[A-Za-z_][A-Za-z0-9_-]*["']?\s*[:=]\s*)""")
_ASSIGNMENT_VALUE = re.compile(r""""[^"\n]*"|'[^'\n]*'|[^\s,;]+""")
_SENSITIVE_NAME = re.compile(
    r"(?:password|passwd|pwd|secret|token|apikey|accesskey|accountkey|connectionstring|authorization|endpoint|hostname|host|signature|sig)$"
)
_ERROR = re.compile(
    r"\berror(?:\[[^\]]+\])?\s*:|\berror\s+(?:CS|MSB|NU|NETSDK)\d+\b|"
    r"\b(?:report[A-Z]\w+|Would reformat|would reformat|FAILED|FAILURES|AssertionError)\b|"
    r"(?:^|\s)(?:[A-Z]{1,4}\d{3,4})\s+\S|^\s*E\s+\S|"
    r"\b(?:fatal error|failed test|tests? failed)\b",
    re.IGNORECASE,
)
_SOURCE = re.compile(r"[A-Za-z0-9_./\\-]+\.(?:py|cs)(?=[:(\s]|$)")


def _bounded(text: str) -> None:
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError("Diagnostic input exceeds byte limit")


def redact(text: str) -> str:
    """Remove common credentials/endpoints without interpreting log instructions."""
    _bounded(text)
    text = _ANSI.sub("", text)
    text = re.sub(
        r"-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?(?:-----END [^-\r\n]*PRIVATE KEY-----|\Z)",
        "[REDACTED PRIVATE KEY]",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(
        r"\b(?:github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9]+|(?:AKIA|ASIA)[A-Z0-9]{16})\b",
        "[REDACTED TOKEN]",
        text,
    )
    text = re.sub(
        r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
        "[REDACTED TOKEN]",
        text,
    )
    text = re.sub(
        r"(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9_.+/=\-]+", "[REDACTED AUTH]", text
    )
    # Connection strings contain multiple secrets and endpoint fields: drop the
    # whole line tail instead of relying on every vendor's key vocabulary.
    text = re.sub(
        r"(?im)\b(?:DefaultEndpointsProtocol|AccountName|Data Source|Server|HostName|SharedAccessSignature)\s*=.*$",
        "[REDACTED CONNECTION]",
        text,
    )
    text = re.sub(r'\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s<>"\']+', "[REDACTED URL]", text)
    parts, position = [], 0
    for match in _ASSIGNMENT.finditer(text):
        key = re.sub(r"[^a-z]", "", re.split(r"[:=]", match[1], maxsplit=1)[0].lower())
        if match.start() >= position and _SENSITIVE_NAME.search(key):
            value = _ASSIGNMENT_VALUE.match(text, match.end())
            if value is not None:
                parts.extend([text[position : match.start()], match[1], "[REDACTED]"])
                position = value.end()
    text = "".join(parts) + text[position:]
    text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b", "[REDACTED ADDRESS]", text)
    text = re.sub(
        r"\[(?:[0-9a-fA-F]*:){2,}[0-9a-fA-F:.]+\](?::\d+)?", "[REDACTED ADDRESS]", text
    )
    text = re.sub(
        r"(?i)\b(?:[a-z0-9_-]+\.)+(?:com|net|org|io|dev|local|internal|lan|cloud|corp|svc|localhost|invalid|test)\b(?::\d+)?",
        "[REDACTED HOST]",
        text,
    )
    text = re.sub(r"(?i)\blocalhost(?::\d+)?\b", "[REDACTED HOST]", text)

    def address(match: re.Match) -> str:
        candidate = match[0]
        if ":" not in candidate:
            return candidate
        try:
            ipaddress.IPv6Address(candidate)
        except ValueError:
            return candidate
        return "[REDACTED ADDRESS]"

    text = re.sub(r"(?i)(?<![\w:])[0-9a-f:]{3,}(?![\w:])", address, text)
    return text


def extract_diagnostics(text: str, *, allowed_paths: list[str] | None = None) -> str:
    """Return recognized diagnostic lines and at most one adjacent context line.

    When supplied, paths constrain relevance; logs cannot expand editable scope.
    An empty path list matches nothing. Wrapped filename headers are supported.
    """
    _bounded(text)
    # Redact before selecting or truncating so multiline secret bodies cannot
    # survive through a neighboring context line or a chopped closing delimiter.
    lines = redact(text).splitlines()
    normalized = [re.sub(r"\s+", "", line.replace("\\", "/")) for line in lines]
    allowed = (
        None if allowed_paths is None else [p.replace("\\", "/") for p in allowed_paths]
    )

    def relevant(index: int) -> bool:
        neighborhood = normalized[max(0, index - 1) : index + 2]
        if allowed is None:
            return True
        for path in allowed:
            basename = path.rsplit("/", 1)[-1]
            for offset, line in enumerate(neighborhood):
                raw_line = lines[max(0, index - 1) + offset].replace("\\", "/")
                if path in line or re.search(
                    r"(?<![\w./-])" + re.escape(basename) + r"(?=[:(\s]|$)", raw_line
                ):
                    return True
        return False

    selected = set()
    for index, line in enumerate(lines):
        if not _ERROR.search(line) or not relevant(index):
            continue
        selected.add(index)
        for neighbor in [index - 1, index + 1]:
            if 0 <= neighbor < len(lines) and (
                _SOURCE.search(lines[neighbor])
                or _ERROR.search(lines[neighbor])
                or lines[neighbor].startswith(("  ", "\t"))
            ):
                selected.add(neighbor)
    output = []
    used = 0
    for index in sorted(selected):
        line = lines[index][:MAX_LINE_CHARS]
        size = len(line.encode("utf-8")) + (1 if output else 0)
        if used + size > MAX_OUTPUT_BYTES or len(output) >= MAX_LINES:
            break
        output.append(line)
        used += size
    return "\n".join(output)
