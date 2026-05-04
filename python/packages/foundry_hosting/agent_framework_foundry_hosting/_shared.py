# Copyright (c) Microsoft. All rights reserved.

"""Shared transformation helpers between the agent-server data model and Agent Framework.

This module is the single home for *pure-data* conversions between the
:mod:`azure.ai.agentserver.responses.models` SDK shapes (``Item``,
``OutputItem``, ``MessageContent``, …) and the Agent Framework public types
(:class:`agent_framework.Message`, :class:`agent_framework.Content`, …).

Why this lives in one module
----------------------------
* The :mod:`._responses` channel adapter and the
  :class:`._history_provider.FoundryHostedAgentHistoryProvider` both need the
  exact same OutputItem→Message conversion. Keeping it in one place means we
  only have **one** ``isinstance(item.type, ...)`` dispatch table to keep up
  to date when the agent-server SDK grows new item kinds. If you spot a
  ``type`` value that this module raises ``ValueError`` for, that is the place
  to add support — and **both** consumers benefit immediately.
* The whole module references the agent-server SDK through a single
  ``from azure.ai.agentserver.responses import models`` import. Looking at the
  ``models.X`` references makes it obvious which generated types we already
  consume and which ones (e.g. ``models.A2AToolCall``,
  ``models.AzureFunctionToolCall``, …) are not yet wired into
  :func:`_output_item_to_message`.

``additional_properties`` round-trip
------------------------------------
Both the SDK models and :class:`agent_framework.Message` carry an extensible
extras bag — the agent-server models are
:class:`collections.abc.MutableMapping` instances that round-trip *any* key
through their JSON serialisation, and ``Message`` (and ``Content``) expose a
public ``additional_properties: dict[str, Any]`` slot.

To preserve channel-specific extras across a load/save cycle:

* On **load** (SDK model → Message) :func:`_collect_unknown_keys` extracts
  every key on the source model that is **not** part of its declared schema
  (per ``_attr_to_rest_field``) and stashes it on
  ``Message.additional_properties["foundry"]`` (and per-content the same
  bag is attached onto ``Content.additional_properties["foundry"]``). The
  bag is only attached when at least one extra key is present, so messages
  that didn't have extras stay byte-equal to the previous behaviour.
* On **save** (Message → SDK model) :func:`_inject_extras` writes any
  previously stashed bag back as direct keys on the SDK model — Foundry
  storage will round-trip them as opaque JSON.

This means an app can stash channel-specific bookkeeping (delivery
fingerprints, `hosting` envelope from the host, AG-UI ``client_state``
snapshots, …) under a known top-level key and rely on it surviving a
write/read cycle through the Foundry response store.
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any, cast

from agent_framework import Content, Message
from azure.ai.agentserver.responses import models

logger = logging.getLogger(__name__)

# Top-level key under which round-tripped SDK extras live on
# ``Message.additional_properties`` and ``Content.additional_properties``.
# Stable on purpose: write-paths look it up by name to re-inject extras into
# outbound SDK models.
EXTRAS_KEY = "foundry"

# Sub-key (under ``additional_properties[EXTRAS_KEY]``) that stores a
# verbatim snapshot of the original SDK ``OutputItem`` mapping captured at
# read time. The write path re-emits the SDK item from this snapshot when
# present, giving lossless audit/replay semantics: every declared field
# (item id, type discriminator, content array, status, …) AND every undeclared
# extra Foundry handed us survive the AF round-trip. Without this, a
# message synthesised back from ``Message.text`` alone would discard the
# original item shape.
RAW_KEY = "__raw__"

# Top-level key on the SDK ``OutputItem`` mapping under which we round-trip
# *every* :class:`agent_framework.Message` ``additional_properties`` namespace
# **other than** :data:`EXTRAS_KEY` (the foundry-internal namespace, handled
# separately by :func:`_inject_extras`).
#
# Why a single container key instead of writing each namespace as a top-level
# extra on the SDK item: Foundry's storage backend round-trips arbitrary
# unknown keys, but on **load** :func:`_collect_unknown_keys` cannot tell
# which unknowns were AF-written namespaces (``hosting``, ``agui_state``,
# ...) vs Foundry-runtime additions. Funnelling AF namespaces under a single
# sentinel key removes that ambiguity: anything inside ``agent_framework``
# is restored under its original namespace; anything else stays under
# :data:`EXTRAS_KEY` (preserving today's behaviour for Foundry-side extras).
#
# Concretely, this is the mechanism that gives the Hosting spec's
# ``Message.additional_properties["hosting"]`` envelope (channel /
# identity / response_target / initial-write ``deliveries[]``) durable
# round-trip semantics through the Foundry response store — see
# ``docs/specs/002-python-hosting-channels.md`` §"Channel metadata
# persisted onto stored messages".
AF_EXTRAS_KEY = "agent_framework"

# Re-exports — these helpers are consumed by sibling modules
# (``_responses.py`` and ``_history_provider.py``); declaring them in
# ``__all__`` quiets pyright's ``reportUnusedFunction`` for module-private
# names that are intentionally part of the package-internal API.
__all__ = (
    "AF_EXTRAS_KEY",
    "EXTRAS_KEY",
    "RAW_KEY",
    "_arguments_to_str",
    "_attach_content_extras",
    "_attach_extras",
    "_capture_raw",
    "_collect_af_extras",
    "_collect_unknown_keys",
    "_convert_message_content",
    "_convert_output_message_content",
    "_inject_af_extras",
    "_inject_extras",
    "_item_to_message",
    "_items_to_messages",
    "_message_text",
    "_message_to_output_item",
    "_messages_to_output_items",
    "_output_item_to_message",
    "_output_items_to_messages",
)


# region Extras helpers


def _collect_unknown_keys(model: Mapping[str, Any]) -> dict[str, Any]:
    """Return any keys present on the SDK model that are not part of its declared schema.

    The agent-server SDK models are
    :class:`collections.abc.MutableMapping` instances generated from the
    Foundry REST contract; declared fields are exposed via the class-level
    ``_attr_to_rest_field`` map. Any extra key on the instance therefore
    represents data the Foundry runtime stored that the SDK doesn't model
    explicitly — typically channel-specific extras a previous write-path
    deliberately stashed there via :func:`_inject_extras`.

    Args:
        model: A model instance (or any mapping) to inspect.

    Returns:
        A new ``dict`` containing only the keys on ``model`` that are not
        declared in the model's REST schema. Empty when the model only
        carries declared fields.
    """
    if not isinstance(model, Mapping):
        return {}
    known = set(getattr(type(model), "_attr_to_rest_field", {}).keys())
    return {key: value for key, value in model.items() if key not in known}


def _attach_extras(message: Message, model: Mapping[str, Any]) -> Message:
    """Attach SDK extras (if any) to ``message.additional_properties``.

    Two-tier restoration so the Hosting spec's namespaced envelopes
    (``hosting``, ``agui_state``, …) come back under their **original**
    keys while Foundry-side extras (anything the runtime layered on the
    SDK item) stay under the foundry-internal :data:`EXTRAS_KEY`
    namespace:

    1. Pop :data:`AF_EXTRAS_KEY` from the unknown-keys bag and merge each
       sub-key directly onto ``message.additional_properties`` — this is
       how the inbound ``hosting`` envelope (channel/identity/
       response_target) and the initial-write ``deliveries[]`` snapshot
       round-trip through Foundry storage.
    2. Anything remaining (Foundry-runtime extras the SDK doesn't model
       explicitly) is stashed under
       ``additional_properties[EXTRAS_KEY]`` for backward compatibility
       and audit/replay.

    No-op when the model carries no extras — ``additional_properties`` is left
    alone so callers and tests that compare ``Message`` instances for equality
    by ``role``/``contents`` only continue to pass.

    Args:
        message: The message to enrich.
        model: The SDK model whose extras should be preserved.

    Returns:
        The same ``message`` instance (returned for fluent chaining).
    """
    extras = _collect_unknown_keys(model)
    if not extras:
        return message
    af_extras = extras.pop(AF_EXTRAS_KEY, None)
    if isinstance(af_extras, Mapping):
        af_extras_typed = cast("Mapping[str, Any]", af_extras)
        for ns_key, ns_val in af_extras_typed.items():
            # Per-namespace overwrite: a fresh load is the source of
            # truth for the message we're rebuilding.
            message.additional_properties[ns_key] = ns_val
    if extras:
        message.additional_properties.setdefault(EXTRAS_KEY, {}).update(extras)
    return message


def _capture_raw(message: Message, item: Mapping[str, Any]) -> Message:
    """Snapshot the SDK item's full mapping onto the message for replay.

    Stored under ``message.additional_properties[EXTRAS_KEY][RAW_KEY]`` so
    :func:`_message_to_output_item` can re-emit the byte-for-byte original
    SDK shape on the write side. This is what lets the AF →
    Foundry-storage round-trip preserve item ids, content variants
    (citations, reasoning, tool results, …) and any extras Foundry
    layered on top of the declared schema.

    A best-effort ``dict(...)`` is used so failure to snapshot (e.g. a
    non-mapping subclass surfacing in the future) degrades gracefully to
    the lossy-but-functional synthesise-from-text path rather than
    crashing the read.
    """
    try:
        raw = dict(item)
    except Exception:
        return message
    message.additional_properties.setdefault(EXTRAS_KEY, {})[RAW_KEY] = raw
    return message


def _inject_extras(model: Any, source: Mapping[str, Any] | None) -> Any:
    """Inject previously-stashed extras back onto an outbound SDK model.

    The SDK models are :class:`collections.abc.MutableMapping`; setting
    arbitrary keys on them is supported and round-trips through serialisation.
    Use this when **emitting** SDK shapes (e.g. when ``save_messages`` decides
    to write back through the Foundry storage API).

    Args:
        model: The SDK model instance to enrich. Must be mapping-like.
        source: The extras bag previously read from
            ``Message.additional_properties[EXTRAS_KEY]`` (or any equivalent).
            ``None`` is treated as an empty bag.

    Returns:
        The same ``model`` instance (returned for fluent chaining).
    """
    if not source:
        return model
    for key, value in source.items():
        # Internal sentinel — never write the raw-snapshot back as a
        # storage field; it lives only inside ``additional_properties``.
        if key == RAW_KEY:
            continue
        # Avoid clobbering declared fields — extras are never allowed to
        # overwrite the schema-defined contract on the model.
        model_type: Any = type(model)  # pyright: ignore[reportUnknownVariableType]
        known: set[str] = set(getattr(model_type, "_attr_to_rest_field", {}))
        if key in known:
            continue
        model[key] = value
    return model


def _collect_af_extras(message: Message) -> dict[str, Any]:
    """Gather every AF-side ``additional_properties`` namespace except :data:`EXTRAS_KEY`.

    Returns the namespaces (``hosting``, ``agui_state``, …) that should
    round-trip through Foundry storage as a single opaque container under
    :data:`AF_EXTRAS_KEY` on the SDK item. The foundry-internal namespace
    is excluded because :func:`_inject_extras` handles it separately and
    its contents are AF-specific bookkeeping (raw snapshots, Foundry
    runtime extras) that don't belong inside the AF container.
    """
    props = message.additional_properties or {}
    return {key: value for key, value in props.items() if key != EXTRAS_KEY}


def _inject_af_extras(model: Any, source: Mapping[str, Any] | None) -> Any:
    """Write AF-side namespaces onto the SDK model under :data:`AF_EXTRAS_KEY`.

    This is the save-side counterpart to :func:`_attach_extras`'s
    AF-namespace restoration. The container key collides with declared
    schema fields only if Foundry decides to add an
    ``agent_framework`` field to its REST contract — at which point we
    rename the constant.

    A non-empty ``source`` overwrites any value already at
    :data:`AF_EXTRAS_KEY` on the model (e.g. a stale value baked into a
    raw-snapshot replay) so the in-process :class:`Message` remains the
    source of truth at write time.
    """
    if not source:
        return model
    model[AF_EXTRAS_KEY] = dict(source)
    return model


# endregion


# region Small utilities


def _arguments_to_str(arguments: str | Mapping[str, Any] | None) -> str:
    """Convert a tool-call ``arguments`` payload to its on-the-wire JSON string form.

    Args:
        arguments: The arguments to serialise. ``None`` becomes an empty
            string, an existing string is returned verbatim, and any mapping
            is JSON-encoded.

    Returns:
        The arguments as a JSON string.
    """
    if arguments is None:
        return ""
    if isinstance(arguments, str):
        return arguments
    return json.dumps(arguments)


# endregion


# region Content conversion


def _convert_file_data(data_uri: str, filename: str | None = None) -> Content:
    """Convert a ``file_data`` data URI to a :class:`Content`.

    For ``text/*`` MIME types the base64 payload is decoded and returned as
    plain text (with a ``[File: <name>]`` prefix when a filename is known);
    other media types fall through to a URI-based content with the
    filename preserved as an additional property.
    """
    if data_uri.startswith("data:") and ";base64," in data_uri:
        header, encoded = data_uri.split(";base64,", 1)
        media_type = header[len("data:") :]
        if media_type.startswith("text/"):
            try:
                decoded_text = base64.b64decode(encoded).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                logger.warning(
                    "Failed to decode text/* file_data as UTF-8, falling through to URI passthrough.",
                    exc_info=True,
                )
            else:
                prefix = f"[File: {filename}]\n" if filename else ""
                return Content.from_text(f"{prefix}{decoded_text}")
    additional_properties = {"filename": filename} if filename else None
    return Content.from_uri(data_uri, additional_properties=additional_properties)


def _convert_message_content(content: models.MessageContent) -> Content:
    """Convert an SDK ``MessageContent`` (input-side) into a framework ``Content``.

    Handles all input/output content variants currently understood by the
    Responses channel — text, output text, summary, refusal, reasoning text,
    input images, input files, computer screenshot.

    Args:
        content: The SDK content node to convert.

    Returns:
        The corresponding :class:`agent_framework.Content`.

    Raises:
        ValueError: If the SDK content ``type`` is not yet supported by this
            adapter.
    """
    if content.type == "input_text":
        return _attach_content_extras(
            Content.from_text(cast(models.MessageContentInputTextContent, content).text), content
        )
    if content.type == "output_text":
        return _attach_content_extras(
            Content.from_text(cast(models.MessageContentOutputTextContent, content).text), content
        )
    if content.type == "text":
        return _attach_content_extras(Content.from_text(cast(models.TextContent, content).text), content)
    if content.type == "summary_text":
        return _attach_content_extras(Content.from_text(cast(models.SummaryTextContent, content).text), content)
    if content.type == "refusal":
        return _attach_content_extras(
            Content.from_text(cast(models.MessageContentRefusalContent, content).refusal), content
        )
    if content.type == "reasoning_text":
        return _attach_content_extras(
            Content.from_text_reasoning(text=cast(models.MessageContentReasoningTextContent, content).text),
            content,
        )
    if content.type == "input_image":
        image = cast(models.MessageContentInputImageContent, content)
        if image.image_url:
            return _attach_content_extras(Content.from_uri(image.image_url), content)
        if image.file_id:
            return _attach_content_extras(Content.from_hosted_file(image.file_id), content)
    if content.type == "input_file":
        file = cast(models.MessageContentInputFileContent, content)
        if file.file_url:
            return _attach_content_extras(Content.from_uri(file.file_url), content)
        if file.file_id:
            return _attach_content_extras(Content.from_hosted_file(file.file_id, name=file.filename), content)
        if file.file_data:
            return _attach_content_extras(_convert_file_data(file.file_data, file.filename), content)
    if content.type == "computer_screenshot":
        return _attach_content_extras(
            Content.from_uri(cast(models.ComputerScreenshotContent, content).image_url), content
        )

    raise ValueError(f"Unsupported MessageContent type: {content.type}")


def _convert_output_message_content(content: models.OutputMessageContent) -> Content:
    """Convert an SDK ``OutputMessageContent`` (assistant output side) into a framework ``Content``.

    Handles assistant-output variants: ``output_text`` and ``refusal``.

    Args:
        content: The SDK content node to convert.

    Returns:
        The corresponding :class:`agent_framework.Content`.

    Raises:
        ValueError: If the SDK content ``type`` is not yet supported.
    """
    if content.type == "output_text":
        return _attach_content_extras(
            Content.from_text(cast(models.OutputMessageContentOutputTextContent, content).text), content
        )
    if content.type == "refusal":
        return _attach_content_extras(
            Content.from_text(cast(models.OutputMessageContentRefusalContent, content).refusal), content
        )

    raise ValueError(f"Unsupported OutputMessageContent type: {content.type}")


def _attach_content_extras(content: Content, model: Mapping[str, Any]) -> Content:
    """Round-trip SDK content extras onto :attr:`Content.additional_properties`.

    Mirror of :func:`_attach_extras` but for individual content nodes. Only
    attaches the bag when at least one extra key is present, so the produced
    ``Content`` stays byte-equivalent to a non-extras conversion when there is
    nothing to preserve.

    Args:
        content: The framework content to enrich.
        model: The SDK content node whose extras should be preserved.

    Returns:
        The same ``content`` instance.
    """
    extras = _collect_unknown_keys(model)
    if extras:
        content.additional_properties.setdefault(EXTRAS_KEY, {}).update(extras)
    return content


# endregion


# region Item → Message (input side)


def _items_to_messages(input_items: Sequence[models.Item]) -> list[Message]:
    """Convert a sequence of input ``Item`` SDK objects to framework ``Message`` objects.

    One :class:`agent_framework.Message` per input item — fan-out is the
    caller's responsibility.

    Args:
        input_items: The input items to convert.

    Returns:
        A list of messages in the same order as the input.
    """
    return [_item_to_message(item) for item in input_items]


def _item_to_message(item: models.Item) -> Message:
    """Convert a single input ``Item`` SDK object to a framework ``Message``.

    Wraps :func:`_item_to_message_inner` and stamps a :data:`RAW_KEY`
    snapshot of the SDK item so the write path can rebuild the original
    shape losslessly. See :func:`_capture_raw`.
    """
    return _capture_raw(_item_to_message_inner(item), item)


def _item_to_message_inner(item: models.Item) -> Message:
    """Convert a single input ``Item`` SDK object to a framework ``Message``.

    The conversion table is intentionally explicit (no auto-discovery) so it
    is easy to scan for missing variants. To add support for a new item kind:

    1. Add an ``elif item.type == "...":`` branch here.
    2. Reference the corresponding ``models.ItemX`` (or
       ``models.XItemParam``) type via ``cast(...)``.
    3. Map its fields onto :class:`agent_framework.Content` factory methods.
    4. Add an ``isinstance(...)`` branch in :func:`_output_item_to_message`
       if the same kind also appears on the output side.

    Args:
        item: The SDK item to convert.

    Returns:
        The converted message, with any unknown extras round-tripped under
        ``message.additional_properties[EXTRAS_KEY]``.

    Raises:
        ValueError: If the SDK item ``type`` is not yet supported by this
            adapter.
    """
    if item.type == "message":
        msg = cast(models.ItemMessage, item)
        if isinstance(msg.content, str):
            message = Message(role=msg.role, contents=[Content.from_text(msg.content)])
        else:
            message = Message(role=msg.role, contents=[_convert_message_content(part) for part in msg.content])
        return _attach_extras(message, item)

    if item.type == "output_message":
        output_msg = cast(models.ItemOutputMessage, item)
        return _attach_extras(
            Message(
                role=output_msg.role,
                contents=[_convert_output_message_content(part) for part in output_msg.content],
            ),
            item,
        )

    if item.type == "function_call":
        fc = cast(models.ItemFunctionToolCall, item)
        return _attach_extras(
            Message(
                role="assistant",
                contents=[Content.from_function_call(fc.call_id, fc.name, arguments=fc.arguments)],
            ),
            item,
        )

    if item.type == "function_call_output":
        fco = cast(models.FunctionCallOutputItemParam, item)
        output = fco.output if isinstance(fco.output, str) else str(fco.output)
        return _attach_extras(
            Message(role="tool", contents=[Content.from_function_result(fco.call_id, result=output)]),
            item,
        )

    if item.type == "reasoning":
        reasoning = cast(models.ItemReasoningItem, item)
        reason_contents: list[Content] = []
        if reasoning.summary:
            for summary in reasoning.summary:
                reason_contents.append(Content.from_text(summary.text))
        return _attach_extras(Message(role="assistant", contents=reason_contents), item)

    if item.type == "mcp_call":
        mcp = cast(models.ItemMcpToolCall, item)
        return _attach_extras(
            Message(
                role="assistant",
                contents=[
                    Content.from_mcp_server_tool_call(
                        mcp.id,
                        mcp.name,
                        server_name=mcp.server_label,
                        arguments=mcp.arguments,
                    )
                ],
            ),
            item,
        )

    if item.type == "mcp_approval_request":
        mcp_req = cast(models.ItemMcpApprovalRequest, item)
        mcp_call_content = Content.from_mcp_server_tool_call(
            mcp_req.id,
            mcp_req.name,
            server_name=mcp_req.server_label,
            arguments=mcp_req.arguments,
        )
        return _attach_extras(
            Message(
                role="assistant",
                contents=[Content.from_function_approval_request(mcp_req.id, mcp_call_content)],
            ),
            item,
        )

    if item.type == "mcp_approval_response":
        mcp_resp = cast(models.MCPApprovalResponse, item)
        placeholder_content = Content.from_function_call(mcp_resp.approval_request_id, "mcp_approval")
        return _attach_extras(
            Message(
                role="user",
                contents=[
                    Content.from_function_approval_response(
                        mcp_resp.approve, mcp_resp.approval_request_id, placeholder_content
                    )
                ],
            ),
            item,
        )

    if item.type == "code_interpreter_call":
        ci = cast(models.ItemCodeInterpreterToolCall, item)
        return _attach_extras(
            Message(role="assistant", contents=[Content.from_code_interpreter_tool_call(call_id=ci.id)]),
            item,
        )

    if item.type == "image_generation_call":
        ig = cast(models.ItemImageGenToolCall, item)
        return _attach_extras(
            Message(role="assistant", contents=[Content.from_image_generation_tool_call(image_id=ig.id)]),
            item,
        )

    if item.type == "shell_call":
        sc = cast(models.FunctionShellCallItemParam, item)
        return _attach_extras(
            Message(
                role="assistant",
                contents=[
                    Content.from_shell_tool_call(
                        call_id=sc.call_id,
                        commands=sc.action.commands,
                        status=str(sc.status),
                    )
                ],
            ),
            item,
        )

    if item.type == "shell_call_output":
        sco = cast(models.FunctionShellCallOutputItemParam, item)
        outputs = [
            Content.from_shell_command_output(
                stdout=out.stdout or "",
                stderr=out.stderr or "",
                exit_code=getattr(out.outcome, "exit_code", None) if hasattr(out, "outcome") else None,
            )
            for out in (sco.output or [])
        ]
        return _attach_extras(
            Message(
                role="tool",
                contents=[
                    Content.from_shell_tool_result(
                        call_id=sco.call_id,
                        outputs=outputs,
                        max_output_length=sco.max_output_length,
                    )
                ],
            ),
            item,
        )

    if item.type == "local_shell_call":
        lsc = cast(models.ItemLocalShellToolCall, item)
        commands = lsc.action.command if hasattr(lsc.action, "command") and lsc.action.command else []
        return _attach_extras(
            Message(
                role="assistant",
                contents=[
                    Content.from_shell_tool_call(
                        call_id=lsc.call_id,
                        commands=commands,
                        status=str(lsc.status),
                    )
                ],
            ),
            item,
        )

    if item.type == "local_shell_call_output":
        lsco = cast(models.ItemLocalShellToolCallOutput, item)
        return _attach_extras(
            Message(
                role="tool",
                contents=[
                    Content.from_shell_tool_result(
                        call_id=lsco.id,
                        outputs=[Content.from_shell_command_output(stdout=lsco.output)],
                    )
                ],
            ),
            item,
        )

    if item.type == "file_search_call":
        fs = cast(models.ItemFileSearchToolCall, item)
        return _attach_extras(
            Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        fs.id,
                        "file_search",
                        arguments=json.dumps({"queries": fs.queries}),
                    )
                ],
            ),
            item,
        )

    if item.type == "web_search_call":
        ws = cast(models.ItemWebSearchToolCall, item)
        return _attach_extras(
            Message(role="assistant", contents=[Content.from_function_call(ws.id, "web_search")]),
            item,
        )

    if item.type == "computer_call":
        cc = cast(models.ItemComputerToolCall, item)
        return _attach_extras(
            Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        cc.call_id,
                        "computer_use",
                        arguments=str(cc.action),
                    )
                ],
            ),
            item,
        )

    if item.type == "computer_call_output":
        cco = cast(models.ComputerCallOutputItemParam, item)
        return _attach_extras(
            Message(role="tool", contents=[Content.from_function_result(cco.call_id, result=str(cco.output))]),
            item,
        )

    if item.type == "custom_tool_call":
        ct = cast(models.ItemCustomToolCall, item)
        return _attach_extras(
            Message(
                role="assistant",
                contents=[Content.from_function_call(ct.call_id, ct.name, arguments=ct.input)],
            ),
            item,
        )

    if item.type == "custom_tool_call_output":
        cto = cast(models.ItemCustomToolCallOutput, item)
        output = cto.output if isinstance(cto.output, str) else str(cto.output)
        # Hosted-MCP results land here because the host writes them via
        # ``aoutput_item_custom_tool_call_output`` (see ``_to_outputs`` for
        # ``mcp_server_tool_result``). The persisted ``call_id`` keeps its
        # ``mcp_*`` prefix; on read, route those back to a hosted-MCP
        # result Content so the chat-client serialize layer can coalesce
        # them onto a single ``mcp_call`` input item with ``output``
        # populated. Issue #5546.
        if cto.call_id and cto.call_id.startswith("mcp_"):
            return _attach_extras(
                Message(
                    role="tool",
                    contents=[Content.from_mcp_server_tool_result(call_id=cto.call_id, output=output)],
                ),
                item,
            )
        return _attach_extras(
            Message(role="tool", contents=[Content.from_function_result(cto.call_id, result=output)]),
            item,
        )

    if item.type == "apply_patch_call":
        ap = cast(models.ApplyPatchToolCallItemParam, item)
        return _attach_extras(
            Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        ap.call_id,
                        "apply_patch",
                        arguments=str(ap.operation),
                    )
                ],
            ),
            item,
        )

    if item.type == "apply_patch_call_output":
        apo = cast(models.ApplyPatchToolCallOutputItemParam, item)
        return _attach_extras(
            Message(role="tool", contents=[Content.from_function_result(apo.call_id, result=apo.output or "")]),
            item,
        )

    raise ValueError(f"Unsupported Item type: {item.type}")


# endregion


# region OutputItem → Message (output / history side)


def _output_items_to_messages(history: Sequence[models.OutputItem]) -> list[Message]:
    """Convert a sequence of ``OutputItem`` SDK objects to framework ``Message`` objects.

    This is the function the :class:`._history_provider.FoundryHostedAgentHistoryProvider`
    calls to materialise stored Foundry response items into the message
    history the agent will see on its next turn.

    Args:
        history: The output items to convert, oldest-first.

    Returns:
        A list of messages, one per supported item, in the same order.
    """
    return [_output_item_to_message(item) for item in history]


def _output_item_to_message(item: models.OutputItem) -> Message:
    """Convert a single ``OutputItem`` SDK object to a framework ``Message``.

    Wraps :func:`_output_item_to_message_inner` and stamps a
    :data:`RAW_KEY` snapshot of the SDK item onto
    ``Message.additional_properties[EXTRAS_KEY]`` so the write path can
    re-emit byte-for-byte. See :func:`_capture_raw` for the rationale.
    """
    return _capture_raw(_output_item_to_message_inner(item), item)


def _output_item_to_message_inner(item: models.OutputItem) -> Message:
    """Convert a single ``OutputItem`` SDK object to a framework ``Message``.

    Variant table — keep in sync with :func:`_item_to_message` when both
    sides exist for the same item kind. To add a new variant:

    1. Add a ``elif item.type == "...":`` branch here.
    2. Reference the corresponding ``models.OutputItemX`` type.
    3. Map its fields to :class:`agent_framework.Content` factory methods.

    Variants currently **missing** from this dispatch (visible by scanning
    ``models.OutputItem*`` and comparing against the branches below):

    * ``models.OutputItemCompactionBody`` — context compaction summaries
    * ``models.OutputItemMcpListTools`` — MCP server ``list_tools`` results
    * ``models.WorkflowActionOutputItem`` — workflow-channel actions
    * Any tool-call variant produced by Azure-specific tools
      (Azure Search, Bing Grounding, SharePoint, Fabric, OpenAPI, A2A,
      browser automation, memory search, …) — the ``models.*ToolCall``
      / ``models.*ToolCallOutput`` family.

    Args:
        item: The SDK item to convert.

    Returns:
        The converted message, with any unknown extras round-tripped under
        ``message.additional_properties[EXTRAS_KEY]``.

    Raises:
        ValueError: If the SDK item ``type`` is not yet supported.
    """
    if item.type == "output_message":
        output_msg = cast(models.OutputItemOutputMessage, item)
        return _attach_extras(
            Message(
                role=output_msg.role,
                contents=[_convert_output_message_content(part) for part in output_msg.content],
            ),
            item,
        )

    if item.type == "message":
        msg = cast(models.OutputItemMessage, item)
        return _attach_extras(
            Message(role=msg.role, contents=[_convert_message_content(part) for part in msg.content]),
            item,
        )

    if item.type == "function_call":
        fc = cast(models.OutputItemFunctionToolCall, item)
        return _attach_extras(
            Message(
                role="assistant",
                contents=[Content.from_function_call(fc.call_id, fc.name, arguments=fc.arguments)],
            ),
            item,
        )

    if item.type == "function_call_output":
        fco = cast(models.FunctionCallOutputItemParam, item)
        output = fco.output if isinstance(fco.output, str) else str(fco.output)
        return _attach_extras(
            Message(role="tool", contents=[Content.from_function_result(fco.call_id, result=output)]),
            item,
        )

    if item.type == "reasoning":
        reasoning = cast(models.OutputItemReasoningItem, item)
        contents: list[Content] = []
        if reasoning.summary:
            for summary in reasoning.summary:
                contents.append(Content.from_text(summary.text))
        return _attach_extras(Message(role="assistant", contents=contents), item)

    if item.type == "mcp_call":
        mcp = cast(models.OutputItemMcpToolCall, item)
        return _attach_extras(
            Message(
                role="assistant",
                contents=[
                    Content.from_mcp_server_tool_call(
                        mcp.id,
                        mcp.name,
                        server_name=mcp.server_label,
                        arguments=mcp.arguments,
                    )
                ],
            ),
            item,
        )

    if item.type == "mcp_approval_request":
        mcp_req = cast(models.OutputItemMcpApprovalRequest, item)
        mcp_call_content = Content.from_mcp_server_tool_call(
            mcp_req.id,
            mcp_req.name,
            server_name=mcp_req.server_label,
            arguments=mcp_req.arguments,
        )
        return _attach_extras(
            Message(
                role="assistant",
                contents=[Content.from_function_approval_request(mcp_req.id, mcp_call_content)],
            ),
            item,
        )

    if item.type == "mcp_approval_response":
        mcp_resp = cast(models.OutputItemMcpApprovalResponseResource, item)
        # Build a placeholder function_call Content since the original call details are not available here.
        placeholder_content = Content.from_function_call(mcp_resp.approval_request_id, "mcp_approval")
        return _attach_extras(
            Message(
                role="user",
                contents=[Content.from_function_approval_response(mcp_resp.approve, mcp_resp.id, placeholder_content)],
            ),
            item,
        )

    if item.type == "code_interpreter_call":
        ci = cast(models.OutputItemCodeInterpreterToolCall, item)
        return _attach_extras(
            Message(role="assistant", contents=[Content.from_code_interpreter_tool_call(call_id=ci.id)]),
            item,
        )

    if item.type == "image_generation_call":
        ig = cast(models.OutputItemImageGenToolCall, item)
        return _attach_extras(
            Message(role="assistant", contents=[Content.from_image_generation_tool_call(image_id=ig.id)]),
            item,
        )

    if item.type == "shell_call":
        sc = cast(models.OutputItemFunctionShellCall, item)
        return _attach_extras(
            Message(
                role="assistant",
                contents=[
                    Content.from_shell_tool_call(
                        call_id=sc.call_id,
                        commands=sc.action.commands,
                        status=str(sc.status),
                    )
                ],
            ),
            item,
        )

    if item.type == "shell_call_output":
        sco = cast(models.OutputItemFunctionShellCallOutput, item)
        outputs = [
            Content.from_shell_command_output(
                stdout=out.stdout or "",
                stderr=out.stderr or "",
                exit_code=getattr(out.outcome, "exit_code", None) if hasattr(out, "outcome") else None,
            )
            for out in (sco.output or [])
        ]
        return _attach_extras(
            Message(
                role="tool",
                contents=[
                    Content.from_shell_tool_result(
                        call_id=sco.call_id,
                        outputs=outputs,
                        max_output_length=sco.max_output_length,
                    )
                ],
            ),
            item,
        )

    if item.type == "local_shell_call":
        lsc = cast(models.OutputItemLocalShellToolCall, item)
        commands = lsc.action.command if hasattr(lsc.action, "command") and lsc.action.command else []
        return _attach_extras(
            Message(
                role="assistant",
                contents=[
                    Content.from_shell_tool_call(
                        call_id=lsc.call_id,
                        commands=commands,
                        status=str(lsc.status),
                    )
                ],
            ),
            item,
        )

    if item.type == "local_shell_call_output":
        lsco = cast(models.OutputItemLocalShellToolCallOutput, item)
        return _attach_extras(
            Message(
                role="tool",
                contents=[
                    Content.from_shell_tool_result(
                        call_id=lsco.id,
                        outputs=[Content.from_shell_command_output(stdout=lsco.output)],
                    )
                ],
            ),
            item,
        )

    if item.type == "file_search_call":
        fs = cast(models.OutputItemFileSearchToolCall, item)
        return _attach_extras(
            Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        fs.id,
                        "file_search",
                        arguments=json.dumps({"queries": fs.queries}),
                    )
                ],
            ),
            item,
        )

    if item.type == "web_search_call":
        ws = cast(models.OutputItemWebSearchToolCall, item)
        return _attach_extras(
            Message(role="assistant", contents=[Content.from_function_call(ws.id, "web_search")]),
            item,
        )

    if item.type == "computer_call":
        cc = cast(models.OutputItemComputerToolCall, item)
        return _attach_extras(
            Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        cc.call_id,
                        "computer_use",
                        arguments=str(cc.action),
                    )
                ],
            ),
            item,
        )

    if item.type == "computer_call_output":
        cco = cast(models.OutputItemComputerToolCallOutputResource, item)
        return _attach_extras(
            Message(role="tool", contents=[Content.from_function_result(cco.call_id, result=str(cco.output))]),
            item,
        )

    if item.type == "custom_tool_call":
        ct = cast(models.OutputItemCustomToolCall, item)
        return _attach_extras(
            Message(
                role="assistant",
                contents=[Content.from_function_call(ct.call_id, ct.name, arguments=ct.input)],
            ),
            item,
        )

    if item.type == "custom_tool_call_output":
        cto = cast(models.OutputItemCustomToolCallOutput, item)
        output = cto.output if isinstance(cto.output, str) else str(cto.output)
        # Hosted-MCP results land here because the host writes them via
        # ``aoutput_item_custom_tool_call_output``. Route ``mcp_*``
        # call_ids back to a hosted-MCP result Content so the chat-client
        # serialize layer can coalesce onto the matching ``mcp_call``
        # input item. Issue #5546.
        if cto.call_id and cto.call_id.startswith("mcp_"):
            return _attach_extras(
                Message(
                    role="tool",
                    contents=[Content.from_mcp_server_tool_result(call_id=cto.call_id, output=output)],
                ),
                item,
            )
        return _attach_extras(
            Message(role="tool", contents=[Content.from_function_result(cto.call_id, result=output)]),
            item,
        )

    if item.type == "apply_patch_call":
        ap = cast(models.OutputItemApplyPatchToolCall, item)
        return _attach_extras(
            Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        ap.call_id,
                        "apply_patch",
                        arguments=str(ap.operation),
                    )
                ],
            ),
            item,
        )

    if item.type == "apply_patch_call_output":
        apo = cast(models.OutputItemApplyPatchToolCallOutput, item)
        return _attach_extras(
            Message(role="tool", contents=[Content.from_function_result(apo.call_id, result=apo.output or "")]),
            item,
        )

    if item.type == "oauth_consent_request":
        oauth = cast(models.OAuthConsentRequestOutputItem, item)
        return _attach_extras(
            Message(role="assistant", contents=[Content.from_oauth_consent_request(oauth.consent_link)]),
            item,
        )

    if item.type == "structured_outputs":
        so = cast(models.StructuredOutputsOutputItem, item)
        text = json.dumps(so.output) if not isinstance(so.output, str) else so.output
        return _attach_extras(Message(role="assistant", contents=[Content.from_text(text)]), item)

    raise ValueError(f"Unsupported OutputItem type: {item.type}")


# endregion


# region AF Message → SDK OutputItem (write path)


def _message_text(message: Message) -> str:
    """Collapse a :class:`Message` into a single text blob.

    The Foundry storage write path only persists the user-visible text — the
    same compression the Responses runtime applies on its own write side. We
    walk ``contents`` rather than relying on ``Message.text`` so we get a
    consistent ordering and can drop non-text parts cleanly.
    """
    chunks: list[str] = []
    for content in message.contents:
        text = getattr(content, "text", None)
        if isinstance(text, str) and text:
            chunks.append(text)
    if chunks:
        return "".join(chunks)
    # Fallback: surface ``Message.text`` if the framework knows how to
    # render the contents (covers structured contents that synthesise text).
    return message.text or ""


def _message_to_output_item(message: Message, item_id: str) -> models.OutputItem:
    """Convert a single :class:`Message` to a Foundry SDK :class:`OutputItem`.

    Two-tier strategy:

    1. **Lossless replay** — if the message carries a previously-captured
       raw SDK snapshot under ``additional_properties[EXTRAS_KEY][RAW_KEY]``
       (set by :func:`_capture_raw` on the read path), rebuild the SDK
       item from that snapshot via the model registry's discriminator
       dispatch (:meth:`models.OutputItem._deserialize`). The snapshot's
       ``id`` is rewritten to ``item_id`` so each write turn gets a
       unique storage row, but every other declared field — content
       variants (citations, reasoning, tool calls, function results,
       …) AND any undeclared extras Foundry layered on top — survives
       intact. This is the auditable round-trip the Foundry storage
       backend relies on.

    2. **Synthesise from text** — for messages constructed in user code
       (no raw snapshot), fall back to the text-only path. ``assistant``
       maps to :class:`OutputItemOutputMessage` (output_text content,
       ``status="completed"``); anything else maps to
       :class:`OutputItemMessage` with the role normalised onto the
       enum's three accepted values (``user`` / ``system`` /
       ``developer`` — ``tool`` collapses to ``user`` because the
       discriminator forbids it).

    In both branches:

    * ``additional_properties[EXTRAS_KEY]`` extras other than the raw
      snapshot are layered onto the emitted model via
      :func:`_inject_extras` so message-level Foundry annotations
      round-trip.
    * **Every other ``additional_properties`` namespace** (notably the
      Hosting spec's ``hosting`` envelope — channel, identity,
      response_target, initial-write ``deliveries[]`` — plus any future
      AF namespaces) is funneled into a single
      :data:`AF_EXTRAS_KEY` container key on the SDK item via
      :func:`_inject_af_extras`. Foundry storage round-trips that key
      as opaque JSON, and :func:`_attach_extras` peels each sub-key
      back onto its original namespace on load. This is what makes the
      audit/replay envelope from the Hosting spec durable across
      Foundry-storage save/load cycles.
    """
    extras_raw: Any = (message.additional_properties or {}).get(EXTRAS_KEY) or {}
    extras: dict[str, Any] = dict(cast("Mapping[str, Any]", extras_raw)) if isinstance(extras_raw, Mapping) else {}
    raw_snapshot: Any = extras.get(RAW_KEY)
    af_extras = _collect_af_extras(message)

    if isinstance(raw_snapshot, Mapping):
        # ``_deserialize`` does discriminator dispatch and tolerates
        # extras-bearing mappings; bypassing it (constructing the
        # concrete class directly) would lose the discriminator wiring
        # and break round-trip for tool-call / reasoning / ... variants.
        snapshot: dict[str, Any] = dict(cast("Mapping[str, Any]", raw_snapshot))
        snapshot["id"] = item_id
        deserialize = cast(Any, models.OutputItem)._deserialize
        item = cast("models.OutputItem", deserialize(snapshot, []))
        return cast(
            "models.OutputItem",
            _inject_af_extras(_inject_extras(item, extras), af_extras),
        )

    text = _message_text(message)
    # ``Message.role`` is an unconstrained ``str | enum`` slot — the
    # framework keeps whatever the constructor was handed (str literals
    # round-trip as ``str``; converters that pass the SDK's
    # ``MessageRole`` enum store the enum). Normalise to the enum's
    # ``value`` (or the bare string) so we don't end up writing
    # ``"MessageRole.USER"`` to storage.
    role_str = getattr(message.role, "value", message.role)

    # Construct via the mapping overload — the SDK's keyword overload tags
    # ``content`` with the abstract base type and rejects our concrete list.
    if role_str == "assistant":
        item = models.OutputItemOutputMessage({
            "id": item_id,
            "type": "output_message",
            "role": "assistant",
            "status": "completed",
            "content": [
                {"type": "output_text", "text": text, "annotations": [], "logprobs": []},
            ],
        })
    else:
        # OutputItemMessage's role enum admits "user" / "system" /
        # "developer". Anything outside that set (e.g. "tool") collapses to
        # "user" so we don't crash on the SDK's discriminator validation.
        role_value = role_str if role_str in ("user", "system", "developer") else "user"
        item = models.OutputItemMessage({
            "id": item_id,
            "type": "message",
            "role": role_value,
            "status": "completed",
            "content": [
                {"type": "input_text", "text": text},
            ],
        })
    return cast("models.OutputItem", _inject_af_extras(_inject_extras(item, extras), af_extras))


def _messages_to_output_items(messages: Sequence[Message], *, id_prefix: str) -> list[models.OutputItem]:
    """Convert a batch of messages to Foundry SDK items with stable IDs.

    Each message gets a deterministic id of the form ``{id_prefix}_itm_{i}``.
    Callers (typically :meth:`FoundryHostedAgentHistoryProvider.save_messages`)
    derive ``id_prefix`` from the response id they're persisting under so
    the per-item ids are unique across a conversation.
    """
    return [_message_to_output_item(msg, f"{id_prefix}_itm_{i}") for i, msg in enumerate(messages)]


# endregion
