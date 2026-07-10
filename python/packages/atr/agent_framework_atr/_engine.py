# Copyright (c) Microsoft. All rights reserved.

"""Local, deterministic ATR detection backed by the ``pyatr`` engine.

The engine is loaded once and reused. Detection runs entirely in-process with
no model call, so block/allow decisions are reproducible and auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pyatr

# Severity ranks used to filter matches against ``min_severity`` and to keep the
# highest-severity hit. Mirrors the ATR schema severity enum.
_SEVERITY_ORDER: dict[str, int] = {
    "informational": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


@dataclass(frozen=True)
class ATRDetection:
    """A single ATR rule match.

    Attributes:
        rule_id: The matched rule identifier, e.g. ``ATR-2026-00001``.
        severity: The rule severity (critical, high, medium, low, informational).
        confidence: The rule confidence label reported by the engine.
        title: The human-readable rule title.
    """

    rule_id: str
    severity: str
    confidence: str
    title: str


class ATRDetector:
    """Loads an ATR ruleset once and evaluates agent text against it.

    Detection is delegated to the upstream ``pyatr`` engine and is fully local
    and deterministic. Construct one detector and share it across middleware to
    avoid reloading rules on every call.

    Args:
        rules_dir: Directory of ATR rule YAML files to load. When ``None`` the
            ruleset bundled with ``pyatr`` is used.
        min_severity: Minimum severity a match must have to be reported. One of
            critical, high, medium, low, informational. Defaults to
            ``informational`` (report every match).
    """

    def __init__(self, *, rules_dir: str | None = None, min_severity: str = "informational") -> None:
        engine: Any = pyatr.ATREngine()
        if rules_dir is None:
            engine.load_default_rules()
        else:
            engine.load_rules_from_directory(rules_dir)
        self._engine: Any = engine
        self._min_rank: int = _SEVERITY_ORDER.get(min_severity.lower(), 0)

    def detect(self, text: str, *, event_type: str = "llm_input", field: str = "user_input") -> ATRDetection | None:
        """Evaluate ``text`` and return the highest-severity match, or ``None``.

        Args:
            text: The agent text to scan (user input, tool arguments, ...).
            event_type: The ATR event type to evaluate the text as, e.g.
                ``llm_input`` or ``tool_call``.
            field: The ATR field name the text is exposed under so field-scoped
                rule conditions (e.g. ``tool_args``) can match.

        Returns:
            The highest-severity :class:`ATRDetection` at or above
            ``min_severity``, or ``None`` when nothing matches.
        """
        if not text:
            return None
        event: Any = pyatr.AgentEvent(content=text, event_type=event_type, fields={field: text})
        matches: Any = self._engine.evaluate(event)
        # ``evaluate`` returns matches sorted critical-first.
        for match in matches:
            if _SEVERITY_ORDER.get(str(match.severity).lower(), 0) >= self._min_rank:
                return ATRDetection(
                    rule_id=str(match.rule_id),
                    severity=str(match.severity),
                    confidence=str(match.confidence),
                    title=str(match.title),
                )
        return None
