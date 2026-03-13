# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    Final,
    Literal,
    Protocol,
    TypeAlias,
    runtime_checkable,
)

from ._sessions import BaseContextProvider
from ._types import ChatResponse, Content, Message

if TYPE_CHECKING:
    from ._clients import SupportsChatGetResponse

GroupKind: TypeAlias = Literal["system", "user", "assistant_text", "tool_call"]
GROUP_ANNOTATION_KEY = "_group"
GROUP_ID_KEY = "id"
GROUP_KIND_KEY = "kind"
GROUP_INDEX_KEY = "index"
GROUP_HAS_REASONING_KEY = "has_reasoning"
GROUP_TOKEN_COUNT_KEY = "token_count"  # noqa: S105 # nosec B105 - compaction metadata key, not a credential
EXCLUDED_KEY = "_excluded"
EXCLUDE_REASON_KEY = "_exclude_reason"
SUMMARY_OF_MESSAGE_IDS_KEY = "_summary_of_message_ids"
SUMMARY_OF_GROUP_IDS_KEY = "_summary_of_group_ids"
SUMMARIZED_BY_SUMMARY_ID_KEY = "_summarized_by_summary_id"


logger = logging.getLogger("agent_framework")


@runtime_checkable
class TokenizerProtocol(Protocol):
    """Protocol for token counters used by token-aware compaction strategies."""

    def count_tokens(self, text: str) -> int:
        """Count tokens for a serialized message payload."""
        ...


@runtime_checkable
class CompactionStrategy(Protocol):
    """Protocol for in-place message compaction strategies."""

    async def __call__(self, messages: list[Message]) -> bool:
        """Mutate message annotations and/or list contents in place.

        Assumes caller has already applied grouping annotations (and token
        annotations when required by the strategy).

        Returns:
            True if compaction changed message inclusion or content; otherwise False.
        """
        ...


class CharacterEstimatorTokenizer:
    """Fast heuristic tokenizer using a 4-char/token estimate."""

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)


def _has_content_type(message: Message, content_type: str) -> bool:
    return any(content.type == content_type for content in message.contents)


def _has_function_call(message: Message) -> bool:
    return _has_content_type(message, "function_call")


def _has_reasoning(message: Message) -> bool:
    return _has_content_type(message, "text_reasoning")


def _is_tool_call_assistant(message: Message) -> bool:
    return message.role == "assistant" and _has_function_call(message)


def _is_reasoning_only_assistant(message: Message) -> bool:
    if message.role != "assistant" or not message.contents:
        return False
    return all(content.type == "text_reasoning" for content in message.contents)


def _ensure_message_ids(messages: list[Message]) -> None:
    for index, message in enumerate(messages):
        if not message.message_id:
            message.message_id = f"msg_{index}"


def _group_id_for(message: Message, group_index: int) -> str:
    if message.message_id:
        return f"group_{message.message_id}"
    return f"group_index_{group_index}"


def group_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Compute group spans and metadata for annotation.

    Returns:
        Ordered list of lightweight span dicts with keys:
        ``group_id``, ``kind``, ``start_index``, ``end_index``, ``has_reasoning``.
    """
    _ensure_message_ids(messages)
    spans: list[dict[str, Any]] = []
    i = 0
    group_index = 0

    while i < len(messages):
        current = messages[i]

        if current.role == "system":
            spans.append({
                "group_id": _group_id_for(current, group_index),
                "kind": "system",
                "start_index": i,
                "end_index": i,
                "has_reasoning": _has_reasoning(current),
            })
            i += 1
            group_index += 1
            continue

        if current.role == "user":
            spans.append({
                "group_id": _group_id_for(current, group_index),
                "kind": "user",
                "start_index": i,
                "end_index": i,
                "has_reasoning": _has_reasoning(current),
            })
            i += 1
            group_index += 1
            continue

        # Reasoning prefix before an assistant function_call joins the same tool_call group.
        # This includes the OpenAI Responses shape where reasoning and function_call
        # contents are co-located in the same assistant message.
        if _is_reasoning_only_assistant(current):
            prefix_start = i
            j = i
            while j < len(messages) and _is_reasoning_only_assistant(messages[j]):
                j += 1
            if j < len(messages) and _is_tool_call_assistant(messages[j]):
                k = j + 1
                has_reasoning = True
                while k < len(messages) and _is_reasoning_only_assistant(messages[k]):
                    has_reasoning = True
                    k += 1
                while k < len(messages) and messages[k].role == "tool":
                    k += 1
                spans.append({
                    "group_id": _group_id_for(messages[prefix_start], group_index),
                    "kind": "tool_call",
                    "start_index": prefix_start,
                    "end_index": k - 1,
                    "has_reasoning": has_reasoning or _has_reasoning(messages[j]),
                })
                i = k
                group_index += 1
                continue

        if _is_tool_call_assistant(current):
            has_reasoning = _has_reasoning(current)
            k = i + 1
            while k < len(messages) and _is_reasoning_only_assistant(messages[k]):
                has_reasoning = True
                k += 1
            while k < len(messages) and messages[k].role == "tool":
                k += 1
            spans.append({
                "group_id": _group_id_for(current, group_index),
                "kind": "tool_call",
                "start_index": i,
                "end_index": k - 1,
                "has_reasoning": has_reasoning,
            })
            i = k
            group_index += 1
            continue

        if current.role == "tool":
            k = i + 1
            while k < len(messages) and messages[k].role == "tool":
                k += 1
            spans.append({
                "group_id": _group_id_for(current, group_index),
                "kind": "tool_call",
                "start_index": i,
                "end_index": k - 1,
                "has_reasoning": False,
            })
            i = k
            group_index += 1
            continue

        spans.append({
            "group_id": _group_id_for(current, group_index),
            "kind": "assistant_text",
            "start_index": i,
            "end_index": i,
            "has_reasoning": _has_reasoning(current),
        })
        i += 1
        group_index += 1

    return spans


def _coerce_group_kind(value: object) -> GroupKind | None:
    if value == "system":
        return "system"
    if value == "user":
        return "user"
    if value == "assistant_text":
        return "assistant_text"
    if value == "tool_call":
        return "tool_call"
    return None


def _read_group_annotation(message: Message) -> dict[str, Any] | None:
    raw_annotation = _read_group_annotation_raw(message)
    if raw_annotation is None:
        return None

    group_id = raw_annotation.get(GROUP_ID_KEY)
    group_kind = _coerce_group_kind(raw_annotation.get(GROUP_KIND_KEY))
    group_index = raw_annotation.get(GROUP_INDEX_KEY)
    has_reasoning = raw_annotation.get(GROUP_HAS_REASONING_KEY)
    token_count = raw_annotation.get(GROUP_TOKEN_COUNT_KEY)
    if token_count is not None and not isinstance(token_count, int):
        return None
    if (
        not isinstance(group_id, str)
        or group_kind is None
        or not isinstance(group_index, int)
        or not isinstance(has_reasoning, bool)
    ):
        return None

    return raw_annotation


def _read_group_annotation_raw(message: Message) -> dict[str, Any] | None:
    annotation = message.additional_properties.get(GROUP_ANNOTATION_KEY)
    if isinstance(annotation, Mapping):
        return annotation  # type: ignore[reportUnknownVariableType, return-value]
    return None


def _set_group_summarized_by_summary_id(message: Message, summary_id: str) -> None:
    annotation = _read_group_annotation_raw(message)
    if annotation is None:
        annotation = {}
        message.additional_properties[GROUP_ANNOTATION_KEY] = annotation
    annotation[SUMMARIZED_BY_SUMMARY_ID_KEY] = summary_id


def _write_group_annotation(
    message: Message,
    *,
    group_id: str,
    kind: GroupKind,
    index: int,
    has_reasoning: bool,
) -> None:
    existing_raw_annotation = _read_group_annotation_raw(message)
    unknown_fields: dict[str, Any] = {}
    token_count: int | None = None
    if existing_raw_annotation is not None:
        raw_token_count = existing_raw_annotation.get(GROUP_TOKEN_COUNT_KEY)
        if isinstance(raw_token_count, int) or raw_token_count is None:
            token_count = raw_token_count
        unknown_fields = {
            key: value
            for key, value in existing_raw_annotation.items()
            if key
            not in {
                GROUP_ID_KEY,
                GROUP_KIND_KEY,
                GROUP_INDEX_KEY,
                GROUP_HAS_REASONING_KEY,
                GROUP_TOKEN_COUNT_KEY,
            }
        }

    annotation = {
        GROUP_ID_KEY: group_id,
        GROUP_KIND_KEY: kind,
        GROUP_INDEX_KEY: index,
        GROUP_HAS_REASONING_KEY: has_reasoning,
        GROUP_TOKEN_COUNT_KEY: token_count,
    }
    annotation.update(unknown_fields)
    message.additional_properties[GROUP_ANNOTATION_KEY] = annotation


def _group_id(message: Message) -> str | None:
    annotation = _read_group_annotation(message)
    if annotation is None:
        return None
    group_id = annotation.get(GROUP_ID_KEY)
    return group_id if isinstance(group_id, str) else None


def _group_kind(message: Message) -> GroupKind | None:
    annotation = _read_group_annotation(message)
    if annotation is None:
        return None
    return _coerce_group_kind(annotation.get(GROUP_KIND_KEY))


def _group_index(message: Message) -> int | None:
    annotation = _read_group_annotation(message)
    if annotation is None:
        return None
    group_index = annotation.get(GROUP_INDEX_KEY)
    return group_index if isinstance(group_index, int) else None


def _token_count(message: Message) -> int | None:
    annotation = _read_group_annotation(message)
    if annotation is None:
        return None
    token_count = annotation.get(GROUP_TOKEN_COUNT_KEY)
    return token_count if isinstance(token_count, int) else None


def _write_token_count(message: Message, token_count: int) -> None:
    annotation = _read_group_annotation_raw(message)
    if annotation is None:
        return
    annotation[GROUP_TOKEN_COUNT_KEY] = token_count
    message.additional_properties[GROUP_ANNOTATION_KEY] = annotation


def _ordered_group_ids_from_annotations(messages: Sequence[Message]) -> list[str]:
    ordered_group_ids: list[str] = []
    seen: set[str] = set()
    for message in messages:
        group_id = _group_id(message)
        if group_id is not None and group_id not in seen:
            seen.add(group_id)
            ordered_group_ids.append(group_id)
    return ordered_group_ids


def _first_untokenized_index(messages: Sequence[Message]) -> int | None:
    for index, message in enumerate(messages):
        if _token_count(message) is None:
            return index
    return None


def _first_annotation_gaps(
    messages: Sequence[Message],
    *,
    include_tokens: bool,
) -> tuple[int | None, int | None]:
    first_unannotated: int | None = None
    first_untokenized: int | None = None
    for index, message in enumerate(messages):
        missing_group_annotation = first_unannotated is None and _group_id(message) is None
        missing_token_annotation = include_tokens and first_untokenized is None and _token_count(message) is None

        if missing_group_annotation:
            first_unannotated = index
        if missing_token_annotation:
            first_untokenized = index

        if missing_group_annotation or missing_token_annotation:
            break
    return first_unannotated, first_untokenized


def _reannotation_start(messages: Sequence[Message], index: int) -> int:
    if index <= 0:
        return 0
    previous_index = index - 1
    previous_group_id = _group_id(messages[previous_index])
    if previous_group_id is None:
        return previous_index
    while previous_index > 0:
        prior_group_id = _group_id(messages[previous_index - 1])
        if prior_group_id != previous_group_id:
            break
        previous_index -= 1
    return previous_index


def annotate_message_groups(
    messages: list[Message],
    *,
    from_index: int | None = None,
    force_reannotate: bool = False,
    tokenizer: TokenizerProtocol | None = None,
) -> list[str]:
    """Annotate message groups while reusing existing annotations when possible.

    By default, the function re-annotates only the suffix that contains new
    messages and keeps previously annotated prefixes untouched. When a
    ``tokenizer`` is provided, token-count annotations are also populated
    incrementally.
    """
    if not messages:
        return []

    if force_reannotate:
        start_index = 0
    elif from_index is not None:
        start_index = max(0, min(from_index, len(messages) - 1))
    else:
        first_unannotated_index, first_untokenized_index = _first_annotation_gaps(
            messages,
            include_tokens=tokenizer is not None,
        )
        candidate_starts = [index for index in (first_unannotated_index, first_untokenized_index) if index is not None]
        if not candidate_starts:
            return _ordered_group_ids_from_annotations(messages)
        start_index = min(candidate_starts)

    start_index = _reannotation_start(messages, start_index)

    # Continue group indices from the preserved prefix when only re-annotating a suffix.
    group_index_offset = 0
    if start_index > 0:
        previous_group_index = _group_index(messages[start_index - 1])
        if previous_group_index is not None:
            group_index_offset = previous_group_index + 1

    spans = group_messages(messages[start_index:])
    for span_index, span in enumerate(spans):
        group_id = str(span["group_id"])
        kind = _coerce_group_kind(span["kind"])
        if kind is None:
            raise ValueError(f"Unexpected group kind in span: {span['kind']}")
        local_start_index = int(span["start_index"])
        local_end_index = int(span["end_index"])
        has_reasoning = bool(span["has_reasoning"])
        for idx in range(start_index + local_start_index, start_index + local_end_index + 1):
            message = messages[idx]
            _write_group_annotation(
                message,
                group_id=group_id,
                kind=kind,
                index=group_index_offset + span_index,
                has_reasoning=has_reasoning,
            )
            message.additional_properties.setdefault(EXCLUDED_KEY, False)
            if tokenizer is not None and _token_count(message) is None:
                _write_token_count(message, tokenizer.count_tokens(_serialize_message(message)))
    return _ordered_group_ids_from_annotations(messages)


def _serialize_content(content: Content) -> dict[str, Any]:
    payload = content.to_dict(exclude_none=True)
    payload.pop("raw_representation", None)
    # ``items`` mirrors ``result`` for function_result content; exclude it
    # to avoid double-counting tokens during estimation.
    payload.pop("items", None)
    return payload


def _serialize_message(message: Message) -> str:
    serialized_contents = [_serialize_content(content) for content in message.contents]
    payload = {
        "role": message.role,
        "message_id": message.message_id,
        "contents": serialized_contents,
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str)


def annotate_token_counts(
    messages: list[Message],
    *,
    tokenizer: TokenizerProtocol,
    from_index: int | None = None,
    force_retokenize: bool = False,
) -> None:
    """Annotate token-count metadata, incrementally by default."""
    if not messages:
        return

    # Token counts are stored inside group annotations.
    annotate_message_groups(messages, from_index=from_index)

    if force_retokenize:
        start_index = 0
    elif from_index is not None:
        start_index = max(0, min(from_index, len(messages) - 1))
    else:
        first_untokenized_index = _first_untokenized_index(messages)
        if first_untokenized_index is None:
            return
        start_index = first_untokenized_index

    for message in messages[start_index:]:
        _write_token_count(message, tokenizer.count_tokens(_serialize_message(message)))


def extend_compaction_messages(
    messages: list[Message],
    new_messages: Sequence[Message],
    *,
    tokenizer: TokenizerProtocol | None = None,
) -> None:
    """Append a batch of messages and annotate only the appended tail."""
    if not new_messages:
        return

    start_index = len(messages)
    messages.extend(new_messages)
    annotate_message_groups(
        messages,
        from_index=start_index,
        tokenizer=tokenizer,
    )


def append_compaction_message(
    messages: list[Message],
    message: Message,
    *,
    tokenizer: TokenizerProtocol | None = None,
) -> None:
    """Append a single message and incrementally annotate metadata."""
    extend_compaction_messages(messages, [message], tokenizer=tokenizer)


def included_messages(messages: list[Message]) -> list[Message]:
    return [message for message in messages if not message.additional_properties.get(EXCLUDED_KEY, False)]


def included_token_count(messages: list[Message]) -> int:
    total = 0
    for message in included_messages(messages):
        token_count = _token_count(message)
        if token_count is not None:
            total += token_count
    return total


def set_excluded(message: Message, *, excluded: bool, reason: str | None = None) -> bool:
    changed = bool(message.additional_properties.get(EXCLUDED_KEY, False)) != excluded
    if changed:
        message.additional_properties[EXCLUDED_KEY] = excluded
    if reason is not None:
        message.additional_properties[EXCLUDE_REASON_KEY] = reason
    return changed


def exclude_group_ids(messages: list[Message], group_ids: set[str], *, reason: str) -> bool:
    changed = False
    for message in messages:
        group_id = _group_id(message)
        if group_id is not None and group_id in group_ids:
            changed = set_excluded(message, excluded=True, reason=reason) or changed
    return changed


def project_included_messages(messages: list[Message]) -> list[Message]:
    return included_messages(messages)


def _group_messages_by_id(messages: list[Message]) -> dict[str, list[Message]]:
    grouped: dict[str, list[Message]] = {}
    for message in messages:
        group_id = _group_id(message)
        if group_id is None:
            continue
        grouped.setdefault(group_id, []).append(message)
    return grouped


def _group_kind_map(messages: list[Message]) -> dict[str, GroupKind]:
    kinds: dict[str, GroupKind] = {}
    for message in messages:
        group_id = _group_id(message)
        group_kind = _group_kind(message)
        if group_id is not None and group_kind is not None and group_id not in kinds:
            kinds[group_id] = group_kind
    return kinds


def _group_start_indices(messages: list[Message]) -> dict[str, int]:
    starts: dict[str, int] = {}
    for idx, message in enumerate(messages):
        group_id = _group_id(message)
        if group_id is not None and group_id not in starts:
            starts[group_id] = idx
    return starts


def _included_group_ids(messages: list[Message], ordered_group_ids: list[str]) -> list[str]:
    grouped = _group_messages_by_id(messages)
    included_ids: list[str] = []
    for group_id in ordered_group_ids:
        if any(not m.additional_properties.get(EXCLUDED_KEY, False) for m in grouped.get(group_id, [])):
            included_ids.append(group_id)
    return included_ids


def _count_included_messages(messages: list[Message]) -> int:
    return len(included_messages(messages))


def _count_included_tokens(messages: list[Message]) -> int:
    return included_token_count(messages)


class TruncationStrategy:
    """Oldest-first compaction using a single metric threshold.

    This strategy runs after group annotations are computed and excludes whole
    groups (never partial tool-call groups). The metric is:
    - token count when ``tokenizer`` is provided
    - included message count when ``tokenizer`` is not provided
    Compaction triggers when the metric exceeds ``max_n`` and trims to
    ``compact_to``.
    """

    def __init__(
        self,
        *,
        max_n: int,
        compact_to: int,
        tokenizer: TokenizerProtocol | None = None,
        preserve_system: bool = True,
    ) -> None:
        """Create a truncation strategy.

        Keyword Args:
            max_n: Trigger threshold measured in tokens when ``tokenizer`` is
                provided, otherwise measured in included messages.
            compact_to: Target value for the same metric used by ``max_n``.
                This argument is required and must be explicitly set.
            tokenizer: Optional tokenizer used for token-based truncation.
            preserve_system: When True, system groups remain included and only
                non-system groups are eligible for exclusion.
        """
        if max_n <= 0:
            raise ValueError("max_n must be greater than 0.")
        if compact_to <= 0:
            raise ValueError("compact_to must be greater than 0.")
        if compact_to > max_n:
            raise ValueError("compact_to must be less than or equal to max_n.")
        self.max_n = max_n
        self.compact_to = compact_to
        self.tokenizer = tokenizer
        self.preserve_system = preserve_system

    async def __call__(self, messages: list[Message]) -> bool:
        ordered_group_ids = _ordered_group_ids_from_annotations(messages)
        if self.tokenizer is not None:
            over_limit = _count_included_tokens(messages) > self.max_n
        else:
            over_limit = _count_included_messages(messages) > self.max_n
        if not over_limit:
            return False

        grouped = _group_messages_by_id(messages)
        kinds = _group_kind_map(messages)
        protected_ids: set[str] = set()
        if self.preserve_system:
            protected_ids = {group_id for group_id in ordered_group_ids if kinds.get(group_id) == "system"}

        changed = False
        for group_id in ordered_group_ids:
            if self.tokenizer is not None:
                target_met = _count_included_tokens(messages) <= self.compact_to
            else:
                target_met = _count_included_messages(messages) <= self.compact_to
            if target_met:
                break
            if group_id in protected_ids:
                continue
            for message in grouped.get(group_id, []):
                changed = set_excluded(message, excluded=True, reason="truncation") or changed
        return changed


class SlidingWindowStrategy:
    """Windowed compaction that keeps the most recent non-system groups.

    The strategy preserves recency by retaining only the last
    ``keep_last_groups`` included non-system groups. System groups can be kept
    as stable anchors when ``preserve_system`` is enabled.

    This can remove older user and assistant groups while keeping system
    instructions, which is useful when directives must persist but conversation
    history grows. Use ``SelectiveToolCallCompactionStrategy`` when only tool
    groups should be reduced.
    """

    def __init__(self, *, keep_last_groups: int, preserve_system: bool = True) -> None:
        """Create a sliding-window strategy.

        Args:
            keep_last_groups: Number of most-recent non-system groups to keep.
            preserve_system: Whether system groups should always remain included.
        """
        if keep_last_groups <= 0:
            raise ValueError(f"keep_last_groups must be more than 0, got {keep_last_groups}")
        self.keep_last_groups = keep_last_groups
        self.preserve_system = preserve_system

    async def __call__(self, messages: list[Message]) -> bool:
        ordered_group_ids = _ordered_group_ids_from_annotations(messages)
        grouped = _group_messages_by_id(messages)
        kinds = _group_kind_map(messages)

        included_group_ids = _included_group_ids(messages, ordered_group_ids)
        non_system_group_ids = [group_id for group_id in included_group_ids if kinds.get(group_id) != "system"]
        keep_non_system_ids = set(non_system_group_ids[-self.keep_last_groups :])
        keep_ids = set(keep_non_system_ids)
        if self.preserve_system:
            keep_ids.update(group_id for group_id in ordered_group_ids if kinds.get(group_id) == "system")

        changed = False
        for group_id in included_group_ids:
            if group_id in keep_ids:
                continue
            for message in grouped.get(group_id, []):
                changed = set_excluded(message, excluded=True, reason="sliding_window") or changed
        return changed


class SelectiveToolCallCompactionStrategy:
    """Compaction focused on reducing tool-call history growth.

    This strategy only targets groups annotated as ``tool_call`` and keeps the
    latest ``keep_last_tool_call_groups`` included tool-call groups. It is
    useful when tool chatter dominates token usage.

    It does not change non-tool-call groups, so it can be combined with other
    strategies that target different aspects of the message history.
    """

    def __init__(self, *, keep_last_tool_call_groups: int = 1) -> None:
        """Create a tool-call-focused compaction strategy.

        Args:
            keep_last_tool_call_groups: Number of newest included tool-call
                groups to retain. Set to 0 to remove all included tool-call
                groups.

        Raises:
            ValueError: If ``keep_last_tool_call_groups`` is negative.
        """
        if keep_last_tool_call_groups < 0:
            raise ValueError("keep_last_tool_call_groups must be greater than or equal to 0.")
        self.keep_last_tool_call_groups = keep_last_tool_call_groups

    async def __call__(self, messages: list[Message]) -> bool:
        ordered_group_ids = _ordered_group_ids_from_annotations(messages)
        grouped = _group_messages_by_id(messages)
        kinds = _group_kind_map(messages)

        included_tool_group_ids = [
            group_id
            for group_id in _included_group_ids(messages, ordered_group_ids)
            if kinds.get(group_id) == "tool_call"
        ]
        if len(included_tool_group_ids) <= self.keep_last_tool_call_groups:
            return False

        keep_ids: set[str] = (
            set(included_tool_group_ids[-self.keep_last_tool_call_groups :])
            if self.keep_last_tool_call_groups > 0
            else set()
        )
        changed = False
        for group_id in included_tool_group_ids:
            if group_id in keep_ids:
                continue
            for message in grouped.get(group_id, []):
                changed = set_excluded(message, excluded=True, reason="tool_call_compaction") or changed
        return changed


class ToolResultCompactionStrategy:
    """Collapse older tool-call groups into short summary messages.

    Unlike ``SelectiveToolCallCompactionStrategy`` which fully excludes old
    tool-call groups, this strategy *replaces* them with a compact summary
    message containing the tool results (e.g.
    ``[Tool results: get_weather: sunny, 18°C]``). This preserves a readable
    trace of what tools returned while reclaiming the token overhead of the
    full function-call/result message structure.

    The most recent ``keep_last_tool_call_groups`` tool-call groups are left
    untouched; older ones are collapsed.
    """

    def __init__(self, *, keep_last_tool_call_groups: int = 1) -> None:
        """Create a tool-result compaction strategy.

        Keyword Args:
            keep_last_tool_call_groups: Number of newest included tool-call
                groups to retain verbatim. Older tool-call groups are collapsed
                into summary messages. Set to 0 to collapse all.

        Raises:
            ValueError: If ``keep_last_tool_call_groups`` is negative.
        """
        if keep_last_tool_call_groups < 0:
            raise ValueError("keep_last_tool_call_groups must be greater than or equal to 0.")
        self.keep_last_tool_call_groups = keep_last_tool_call_groups

    async def __call__(self, messages: list[Message]) -> bool:
        ordered_group_ids = _ordered_group_ids_from_annotations(messages)
        grouped = _group_messages_by_id(messages)
        kinds = _group_kind_map(messages)

        included_tool_group_ids = [
            group_id
            for group_id in _included_group_ids(messages, ordered_group_ids)
            if kinds.get(group_id) == "tool_call"
        ]
        if len(included_tool_group_ids) <= self.keep_last_tool_call_groups:
            return False

        keep_ids: set[str] = (
            set(included_tool_group_ids[-self.keep_last_tool_call_groups :])
            if self.keep_last_tool_call_groups > 0
            else set()
        )
        starts = _group_start_indices(messages)
        changed = False
        for group_id in included_tool_group_ids:
            if group_id in keep_ids:
                continue
            group_msgs = grouped.get(group_id, [])
            # Build a call_id → function_name map from function_call contents.
            call_id_to_name: dict[str, str] = {}
            for msg in group_msgs:
                for content in msg.contents:
                    if content.type == "function_call" and content.call_id and content.name:
                        call_id_to_name[content.call_id] = content.name
            # Collect tool results with the function name for context.
            tool_results: list[str] = []
            for msg in group_msgs:
                for content in msg.contents:
                    if content.type == "function_result":
                        result_text = content.result if isinstance(content.result, str) else str(content.result)
                        func_name = call_id_to_name.get(content.call_id or "", "")
                        label = f"{func_name}: {result_text}" if func_name else result_text
                        tool_results.append(label.strip())
            summary_label = "; ".join(tool_results) if tool_results else "no results"
            summary_text = f"[Tool results: {summary_label}]"

            summary_id = f"tool_summary_{group_id}"
            original_message_ids = [msg.message_id for msg in group_msgs if msg.message_id]

            # Mark originals as excluded with back-link to the summary.
            for msg in group_msgs:
                _set_group_summarized_by_summary_id(msg, summary_id)
                changed = set_excluded(msg, excluded=True, reason="tool_result_compaction") or changed

            # Insert summary with forward links to the originals.
            summary_annotation = {
                SUMMARY_OF_MESSAGE_IDS_KEY: original_message_ids,
                SUMMARY_OF_GROUP_IDS_KEY: [group_id],
            }
            insertion_index = starts.get(group_id, 0)
            summary_message = Message(
                role="assistant",
                text=summary_text,
                message_id=summary_id,
                additional_properties={
                    GROUP_ANNOTATION_KEY: summary_annotation,
                },
            )
            messages.insert(insertion_index, summary_message)
            annotate_message_groups(messages, from_index=insertion_index, force_reannotate=False)
            starts = _group_start_indices(messages)
            grouped = _group_messages_by_id(messages)

        return changed


def _format_messages_for_summary(messages: list[Message]) -> str:
    lines: list[str] = []
    for index, message in enumerate(messages, start=1):
        content_text = message.text
        if not content_text:
            content_text = ", ".join(content.type for content in message.contents)
        lines.append(f"{index}. [{message.role}] {content_text}")
    return "\n".join(lines)


DEFAULT_SUMMARIZATION_PROMPT: Final[
    str
] = """**Generate a clear and complete summary of the entire conversation in no more than five sentences.**

The summary must always:
- Reflect contributions from both the user and the assistant
- Preserve context to support ongoing dialogue
- Incorporate any previously provided summary
- Emphasize the most relevant and meaningful points

The summary must never:
- Offer critique, correction, interpretation, or speculation
- Highlight errors, misunderstandings, or judgments of accuracy
- Comment on events or ideas not present in the conversation
- Omit any details included in an earlier summary
"""


class SummarizationStrategy:
    """Summarize older included groups and replace them with linked summary text.

    The strategy monitors included non-system message count and triggers when
    that count grows beyond ``target_count + threshold``. When triggered, it
    summarizes the oldest groups and retains the newest content near
    ``target_count`` (subject to atomic group boundaries). It writes trace
    metadata in both directions: summary -> original message/group IDs and
    original -> summary ID.
    """

    def __init__(
        self,
        *,
        client: SupportsChatGetResponse[Any],
        target_count: int = 4,
        threshold: int | None = 2,
        prompt: str | None = None,
    ) -> None:
        """Create a summarization strategy.

        Keyword Args:
            client: A chat client compatible with ``SupportsChatGetResponse``
                used to generate summary text.
            target_count: Target number of included non-system messages to
                retain after summarization. Must be greater than 0.
            threshold: Extra included non-system messages allowed above
                ``target_count`` before summarization triggers. Must be greater
                than or equal to 0 when provided.
            prompt: Optional summarization instruction. If omitted, a default
                prompt that preserves goals, decisions, and unresolved items is
                used.

        Raises:
            ValueError: If ``target_count`` is less than 1.
            ValueError: If ``threshold`` is provided and is negative.
        """
        if target_count <= 0:
            raise ValueError("target_count must be greater than 0.")
        if threshold is not None and threshold < 0:
            raise ValueError("threshold must be greater than or equal to 0.")
        self.client = client
        self.target_count = target_count
        self.threshold = threshold if threshold is not None else 0
        self.prompt = prompt or DEFAULT_SUMMARIZATION_PROMPT

    async def __call__(self, messages: list[Message]) -> bool:
        ordered_group_ids = _ordered_group_ids_from_annotations(messages)
        grouped = _group_messages_by_id(messages)
        kinds = _group_kind_map(messages)
        starts = _group_start_indices(messages)

        included_non_system_groups: list[tuple[str, list[Message]]] = []
        included_non_system_message_count = 0
        for group_id in _included_group_ids(messages, ordered_group_ids):
            if kinds.get(group_id) == "system":
                continue
            group_messages = [
                message
                for message in grouped.get(group_id, [])
                if not message.additional_properties.get(EXCLUDED_KEY, False)
            ]
            if not group_messages:
                continue
            included_non_system_groups.append((group_id, group_messages))
            included_non_system_message_count += len(group_messages)

        if included_non_system_message_count <= self.target_count + self.threshold:
            return False

        keep_group_ids: list[str] = []
        retained_message_count = 0
        for group_id, group_messages in reversed(included_non_system_groups):
            if retained_message_count >= self.target_count and keep_group_ids:
                break
            keep_group_ids.append(group_id)
            retained_message_count += len(group_messages)
        keep_group_id_set = set(keep_group_ids)

        group_ids_to_summarize = [
            group_id for group_id, _ in included_non_system_groups if group_id not in keep_group_id_set
        ]
        if not group_ids_to_summarize:
            return False

        messages_to_summarize: list[Message] = []
        for group_id, group_messages in included_non_system_groups:
            if group_id in keep_group_id_set:
                continue
            messages_to_summarize.extend(group_messages)
        if not messages_to_summarize:
            return False

        try:
            summary_response: ChatResponse[None] = await self.client.get_response(
                [
                    Message(role="system", text=self.prompt),
                    Message(
                        role="user",
                        text=_format_messages_for_summary(messages_to_summarize),
                    ),
                ],
                stream=False,
            )
        except Exception as exc:
            logger.warning(
                "Skipping summarization compaction: summary generation failed (%s).",
                exc,
            )
            return False

        summary_text = summary_response.text.strip() if summary_response.text else ""
        if not summary_text:
            logger.warning("Skipping summarization compaction: summarizer returned no text.")
            return False
        summary_id = f"summary_{len(messages)}"
        original_message_ids = [message.message_id for message in messages_to_summarize if message.message_id]
        summary_of_group_ids = list(group_ids_to_summarize)
        summary_annotation = {
            SUMMARY_OF_MESSAGE_IDS_KEY: original_message_ids,
            SUMMARY_OF_GROUP_IDS_KEY: summary_of_group_ids,
        }

        summary_message = Message(
            role="assistant",
            text=summary_text,
            message_id=summary_id,
            additional_properties={
                GROUP_ANNOTATION_KEY: summary_annotation,
            },
        )

        for message in messages_to_summarize:
            _set_group_summarized_by_summary_id(message, summary_id)
            set_excluded(message, excluded=True, reason="summarized")

        insertion_index = min(starts[group_id] for group_id in group_ids_to_summarize if group_id in starts)
        messages.insert(insertion_index, summary_message)
        annotate_message_groups(messages, from_index=insertion_index, force_reannotate=False)
        return True


class TokenBudgetComposedStrategy:
    """Compose multiple strategies until an included-token budget is satisfied.

    Strategies run in the provided order over shared message annotations. After
    each step, token counts are refreshed. If no strategy reaches budget, a
    deterministic fallback excludes oldest groups (and finally anchors when
    necessary) to enforce the limit.
    """

    def __init__(
        self,
        *,
        token_budget: int,
        tokenizer: TokenizerProtocol,
        strategies: Sequence[CompactionStrategy],
        early_stop: bool = True,
    ) -> None:
        """Create a composed token-budget strategy.

        Args:
            token_budget: Maximum included token count allowed after compaction.
            tokenizer: Tokenizer implementation used for per-message token
                annotation.
            strategies: Ordered strategy sequence to execute before fallback.
            early_stop: When True, stop as soon as budget is satisfied.
        """
        self.token_budget = token_budget
        self.tokenizer = tokenizer
        self.strategies = list(strategies)
        self.early_stop = early_stop

    async def __call__(self, messages: list[Message]) -> bool:
        annotate_message_groups(messages)
        annotate_token_counts(messages, tokenizer=self.tokenizer)
        if included_token_count(messages) <= self.token_budget:
            return False

        changed = False
        for strategy in self.strategies:
            changed = (await strategy(messages)) or changed
            annotate_message_groups(messages)
            annotate_token_counts(messages, tokenizer=self.tokenizer)
            if self.early_stop and included_token_count(messages) <= self.token_budget:
                return changed

        if included_token_count(messages) <= self.token_budget:
            return changed

        ordered_group_ids = annotate_message_groups(messages)
        grouped = _group_messages_by_id(messages)
        kinds = _group_kind_map(messages)
        for group_id in ordered_group_ids:
            if kinds.get(group_id) == "system":
                continue
            for message in grouped.get(group_id, []):
                changed = set_excluded(message, excluded=True, reason="token_budget_fallback") or changed
            if included_token_count(messages) <= self.token_budget:
                break
        if included_token_count(messages) <= self.token_budget:
            return changed

        # Strict budget enforcement fallback: if anchors alone exceed budget, exclude remaining groups.
        for group_id in ordered_group_ids:
            if kinds.get(group_id) != "system":
                continue
            for message in grouped.get(group_id, []):
                changed = set_excluded(message, excluded=True, reason="token_budget_fallback_strict") or changed
            if included_token_count(messages) <= self.token_budget:
                break
        return changed


async def apply_compaction(
    messages: list[Message],
    *,
    strategy: CompactionStrategy | None,
    tokenizer: TokenizerProtocol | None = None,
) -> list[Message]:
    """Apply configured compaction and return projected model-input messages."""
    if strategy is None:
        return messages
    annotate_message_groups(messages)
    if tokenizer is not None:
        annotate_token_counts(messages, tokenizer=tokenizer)
    await strategy(messages)
    return project_included_messages(messages)


COMPACTION_STATE_KEY: Final[str] = "_compaction_messages"


class CompactionProvider(BaseContextProvider):
    """Context provider that compacts messages before and after agent runs.

    This provider accepts two separate strategies:

    - ``before_strategy``: Runs in ``before_run`` on messages already in the
      context (loaded by earlier providers such as a history provider).
      Compacts the loaded history before it reaches the model.
    - ``after_strategy``: Runs in ``after_run`` on the accumulated messages
      stored by a history provider in session state. This compacts the
      persisted history so the next turn starts with a smaller context.

    Either strategy may be ``None`` to skip that phase.

    Examples:
        .. code-block:: python

            from agent_framework import Agent, CompactionProvider, InMemoryHistoryProvider
            from agent_framework._compaction import (
                SlidingWindowStrategy,
                ToolResultCompactionStrategy,
            )

            history = InMemoryHistoryProvider()
            compaction = CompactionProvider(
                before_strategy=SlidingWindowStrategy(keep_last_groups=20),
                after_strategy=ToolResultCompactionStrategy(keep_last_tool_call_groups=1),
                history_source_id=history.source_id,
            )
            agent = Agent(
                client=client,
                name="assistant",
                context_providers=[history, compaction],
            )
            session = agent.create_session()
            await agent.run("Hello", session=session)
    """

    def __init__(
        self,
        *,
        before_strategy: CompactionStrategy | None = None,
        after_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        source_id: str = "compaction",
        history_source_id: str = "in_memory",
    ) -> None:
        """Create a compaction provider.

        Keyword Args:
            before_strategy: Strategy applied to loaded context messages before
                the model runs. ``None`` to skip pre-run compaction.
            after_strategy: Strategy applied to stored history messages after
                the model runs. Requires ``history_source_id`` to locate the
                messages in session state. ``None`` to skip post-run compaction.
            tokenizer: Optional tokenizer for token-aware strategies.
            source_id: Provider source id (default ``"compaction"``).
            history_source_id: The ``source_id`` of the history provider whose
                stored messages the ``after_strategy`` should compact
                (default ``"in_memory"``).
        """
        super().__init__(source_id)
        self.before_strategy = before_strategy
        self.after_strategy = after_strategy
        self.tokenizer = tokenizer
        self.history_source_id = history_source_id

    async def before_run(
        self,
        *,
        agent: Any,
        session: Any,
        context: Any,
        state: dict[str, Any],
    ) -> None:
        """Compact messages already present in the context from earlier providers."""
        if self.before_strategy is None:
            return

        all_messages: list[Message] = context.get_messages()
        if not all_messages:
            return

        annotate_message_groups(all_messages)
        if self.tokenizer is not None:
            annotate_token_counts(all_messages, tokenizer=self.tokenizer)
        await self.before_strategy(all_messages)

        projected = project_included_messages(all_messages)
        projected_set = {id(m) for m in projected}
        for sid in list(context.context_messages):
            context.context_messages[sid] = [m for m in context.context_messages[sid] if id(m) in projected_set]

    async def after_run(
        self,
        *,
        agent: Any,
        session: Any,
        context: Any,
        state: dict[str, Any],
    ) -> None:
        """Compact stored history messages after the model runs."""
        if self.after_strategy is None:
            return

        # Access the history provider's stored messages from session state.
        history_state_raw = session.state.get(self.history_source_id) if session else None
        if not isinstance(history_state_raw, dict):
            return
        history_state: dict[str, Any] = history_state_raw  # type: ignore[assignment]
        raw_messages = history_state.get("messages")
        if not isinstance(raw_messages, list) or not raw_messages:
            return
        stored_messages: list[Message] = raw_messages  # type: ignore[assignment]

        annotate_message_groups(stored_messages)
        if self.tokenizer is not None:
            annotate_token_counts(stored_messages, tokenizer=self.tokenizer)
        await self.after_strategy(stored_messages)

        # Keep all messages (including excluded) in storage so annotations are
        # preserved. The history provider's ``skip_excluded`` flag controls
        # whether excluded messages are loaded on the next turn.


__all__ = [
    "COMPACTION_STATE_KEY",
    "EXCLUDED_KEY",
    "EXCLUDE_REASON_KEY",
    "GROUP_ANNOTATION_KEY",
    "GROUP_HAS_REASONING_KEY",
    "GROUP_ID_KEY",
    "GROUP_INDEX_KEY",
    "GROUP_KIND_KEY",
    "GROUP_TOKEN_COUNT_KEY",
    "SUMMARIZED_BY_SUMMARY_ID_KEY",
    "SUMMARY_OF_GROUP_IDS_KEY",
    "SUMMARY_OF_MESSAGE_IDS_KEY",
    "CharacterEstimatorTokenizer",
    "CompactionProvider",
    "CompactionStrategy",
    "GroupKind",
    "SelectiveToolCallCompactionStrategy",
    "SlidingWindowStrategy",
    "SummarizationStrategy",
    "TokenBudgetComposedStrategy",
    "TokenizerProtocol",
    "ToolResultCompactionStrategy",
    "TruncationStrategy",
    "annotate_message_groups",
    "annotate_token_counts",
    "append_compaction_message",
    "apply_compaction",
    "extend_compaction_messages",
    "group_messages",
    "included_messages",
    "included_token_count",
    "project_included_messages",
]
