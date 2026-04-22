# Copyright (c) Microsoft. All rights reserved.

"""Output extraction and formatting for Azure Content Understanding results.

Converts CU ``AnalysisResult`` objects into plain Python dicts suitable
for LLM consumption, and formats them as human-readable text.
"""

from __future__ import annotations

import json
from typing import Any, cast

from azure.ai.contentunderstanding.models import AnalysisResult

from ._models import AnalysisSection


def extract_sections(
    result: AnalysisResult,
    output_sections: list[AnalysisSection],
) -> dict[str, object]:
    """Extract configured sections from a CU analysis result.

    For single-segment results (documents, images, short audio), returns a flat
    dict with ``markdown`` and ``fields`` at the top level.

    For multi-segment results (e.g. video split into scenes), fields are kept
    with their respective segments in a ``segments`` list so the LLM can see
    which fields belong to which part of the content:
    - ``segments``: list of per-segment dicts with ``markdown``, ``fields``,
      ``start_time_s``, and ``end_time_s``
    - ``markdown``: still concatenated at top level for file_search uploads
    - ``duration_seconds``: computed from the global time span
    - ``kind`` / ``resolution``: taken from the first segment
    """
    extracted: dict[str, object] = {}
    contents = result.contents
    if not contents:
        return extracted

    # --- Warnings from the CU service (ODataV4Format with code/message/target) ---
    if result.warnings:
        warnings_out: list[dict[str, str]] = []
        for w in result.warnings:
            entry: dict[str, str] = {}
            code = getattr(w, "code", None)
            if code:
                entry["code"] = code
            msg = getattr(w, "message", None)
            entry["message"] = msg if msg else str(w)
            target = getattr(w, "target", None)
            if target:
                entry["target"] = target
            warnings_out.append(entry)
        extracted["warnings"] = warnings_out

    # --- Media metadata (from first segment) ---
    first = contents[0]
    kind = getattr(first, "kind", None)
    if kind:
        extracted["kind"] = kind
    width = getattr(first, "width", None)
    height = getattr(first, "height", None)
    if width and height:
        extracted["resolution"] = f"{width}x{height}"

    # Compute total duration from the global time span of all segments.
    global_start: int | None = None
    global_end: int | None = None
    for content in contents:
        s = getattr(content, "start_time_ms", None)
        if s is None:
            s = getattr(content, "startTimeMs", None)
        e = getattr(content, "end_time_ms", None)
        if e is None:
            e = getattr(content, "endTimeMs", None)
        if s is not None:
            global_start = s if global_start is None else min(global_start, s)
        if e is not None:
            global_end = e if global_end is None else max(global_end, e)
    if global_start is not None and global_end is not None:
        extracted["duration_seconds"] = round((global_end - global_start) / 1000, 1)

    is_multi_segment = len(contents) > 1

    # --- Single-segment: flat output (documents, images, short audio) ---
    if not is_multi_segment:
        if "markdown" in output_sections and contents[0].markdown:
            extracted["markdown"] = contents[0].markdown
        if "fields" in output_sections and contents[0].fields:
            fields: dict[str, object] = {}
            for name, field in contents[0].fields.items():
                entry_dict: dict[str, object] = {
                    "type": getattr(field, "type", None),
                    "value": extract_field_value(field),
                }
                confidence = getattr(field, "confidence", None)
                if confidence is not None:
                    entry_dict["confidence"] = confidence
                fields[name] = entry_dict
            if fields:
                extracted["fields"] = fields
        # Content-level category (e.g. from classifier analyzers)
        category = getattr(contents[0], "category", None)
        if category:
            extracted["category"] = category
        return extracted

    # --- Multi-segment: per-segment output (video scenes, long audio) ---
    # Each segment keeps its own markdown + fields together so the LLM can
    # see which fields (e.g. Summary) belong to which part of the content.
    segments_out: list[dict[str, object]] = []
    md_parts: list[str] = []  # also collect for top-level concatenated markdown

    for content in contents:
        seg: dict[str, object] = {}

        # Time range for this segment
        s = getattr(content, "start_time_ms", None)
        if s is None:
            s = getattr(content, "startTimeMs", None)
        e = getattr(content, "end_time_ms", None)
        if e is None:
            e = getattr(content, "endTimeMs", None)
        if s is not None:
            seg["start_time_s"] = round(s / 1000, 1)
        if e is not None:
            seg["end_time_s"] = round(e / 1000, 1)

        # Per-segment markdown
        if "markdown" in output_sections and content.markdown:
            seg["markdown"] = content.markdown
            md_parts.append(content.markdown)

        # Per-segment fields
        if "fields" in output_sections and content.fields:
            seg_fields: dict[str, object] = {}
            for name, field in content.fields.items():
                seg_entry: dict[str, object] = {
                    "type": getattr(field, "type", None),
                    "value": extract_field_value(field),
                }
                confidence = getattr(field, "confidence", None)
                if confidence is not None:
                    seg_entry["confidence"] = confidence
                seg_fields[name] = seg_entry
            if seg_fields:
                seg["fields"] = seg_fields

        # Per-segment category (e.g. from classifier analyzers)
        category = getattr(content, "category", None)
        if category:
            seg["category"] = category

        segments_out.append(seg)

    extracted["segments"] = segments_out

    # Top-level concatenated markdown (used by file_search for vector store upload)
    if md_parts:
        extracted["markdown"] = "\n\n---\n\n".join(md_parts)

    return extracted


def extract_field_value(field: Any) -> object:
    """Extract the plain Python value from a CU ``ContentField``.

    Uses the SDK's ``.value`` convenience property, which dynamically
    reads the correct ``value_*`` attribute for each field type.
    Object and array types are recursively flattened so that the
    output contains only plain Python primitives (str, int, float,
    date, dict, list) -- no SDK model objects or raw wire format
    (``valueNumber``, ``spans``, ``source``, etc.).
    """
    field_type = getattr(field, "type", None)
    raw = getattr(field, "value", None)

    # Object fields -> recursively resolve nested sub-fields
    if field_type == "object" and raw is not None and isinstance(raw, dict):
        return {str(k): flatten_field(v) for k, v in cast(dict[str, Any], raw).items()}

    # Array fields -> list of flattened items (each with value + optional confidence)
    if field_type == "array" and raw is not None and isinstance(raw, list):
        return [flatten_field(item) for item in cast(list[Any], raw)]

    # Scalar fields (string, number, date, etc.) -- .value returns native Python type
    return raw


def flatten_field(field: Any) -> object:
    """Flatten a CU ``ContentField`` into a ``{type, value, confidence}`` dict.

    Used for sub-fields inside object and array types to preserve
    per-field confidence scores. Confidence is omitted when ``None``
    to reduce token usage.
    """
    field_type = getattr(field, "type", None)
    value = extract_field_value(field)
    confidence = getattr(field, "confidence", None)

    result: dict[str, object] = {"type": field_type, "value": value}
    if confidence is not None:
        result["confidence"] = confidence
    return result


def format_result(filename: str, result: dict[str, object]) -> str:
    """Format extracted CU result for LLM consumption.

    For multi-segment results (video/audio with ``segments``), each segment's
    markdown and fields are grouped together so the LLM can see which fields
    belong to which part of the content.
    """
    kind = result.get("kind")
    is_video = kind == "audioVisual"
    is_audio = kind == "audio"

    # Header -- media-aware label
    if is_video:
        label = "Video analysis"
    elif is_audio:
        label = "Audio analysis"
    else:
        label = "Document analysis"
    parts: list[str] = [f'{label} of "{filename}":']

    # Media metadata line (duration, resolution)
    meta_items: list[str] = []
    duration = result.get("duration_seconds")
    if duration is not None:
        mins, secs = divmod(int(duration), 60)  # type: ignore[call-overload]
        meta_items.append(f"Duration: {mins}:{secs:02d}")
    resolution = result.get("resolution")
    if resolution:
        meta_items.append(f"Resolution: {resolution}")
    if meta_items:
        parts.append(" | ".join(meta_items))

    # --- Multi-segment: format each segment with its own content + fields ---
    raw_segments = result.get("segments")
    segments: list[dict[str, object]] = (
        cast(list[dict[str, object]], raw_segments) if isinstance(raw_segments, list) else []
    )
    if segments:
        for i, seg in enumerate(segments):
            # Segment header with time range
            start = seg.get("start_time_s")
            end = seg.get("end_time_s")
            if start is not None and end is not None:
                s_min, s_sec = divmod(int(start), 60)  # type: ignore[call-overload]
                e_min, e_sec = divmod(int(end), 60)  # type: ignore[call-overload]
                parts.append(f"\n### Segment {i + 1} ({s_min}:{s_sec:02d} - {e_min}:{e_sec:02d})")
            else:
                parts.append(f"\n### Segment {i + 1}")

            # Segment markdown
            seg_md = seg.get("markdown")
            if seg_md:
                parts.append(f"\n```markdown\n{seg_md}\n```")

            # Segment fields
            seg_fields = seg.get("fields")
            if isinstance(seg_fields, dict) and seg_fields:
                fields_json = json.dumps(seg_fields, indent=2, default=str)
                parts.append(f"\n**Fields:**\n```json\n{fields_json}\n```")

        return "\n".join(parts)

    # --- Single-segment: flat format ---
    fields_raw = result.get("fields")
    fields: dict[str, object] = cast(dict[str, object], fields_raw) if isinstance(fields_raw, dict) else {}

    # For audio: promote Summary field as prose before markdown
    if is_audio and fields:
        summary_field = fields.get("Summary")
        if isinstance(summary_field, dict):
            sf = cast(dict[str, object], summary_field)
            if sf.get("value"):
                parts.append(f"\n## Summary\n\n{sf['value']}")

    # Markdown content
    markdown = result.get("markdown")
    if markdown:
        parts.append(f"\n## Content\n\n```markdown\n{markdown}\n```")

    # Fields section
    if fields:
        remaining = dict(fields)
        if is_audio:
            remaining = {k: v for k, v in remaining.items() if k != "Summary"}
        if remaining:
            fields_json = json.dumps(remaining, indent=2, default=str)
            parts.append(f"\n## Extracted Fields\n\n```json\n{fields_json}\n```")

    return "\n".join(parts)
