# Copyright (c) Microsoft. All rights reserved.

"""A2UIAgent — wraps an agent with A2UI surface-generation support.

Every run gets a ``generate_a2ui`` tool that delegates UI generation to a render
sub-agent and returns a validated A2UI operations envelope as its tool result, run
through the shared toolkit's validate→retry recovery loop.

Two paths:

* **Non-streaming** advertises a REAL ``generate_a2ui`` tool whose body runs the
  toolkit's synchronous ``run_a2ui_generation_with_recovery``; ordinary automatic
  function invocation executes it.
* **Streaming** advertises ``generate_a2ui`` as a declaration-only tool (``func=None``)
  so the planner's call surfaces on the update stream instead of being auto-invoked.
  An agent-level planner-rounds loop then runs the render sub-agent with a streaming
  chat call, forwards its per-chunk ``render_a2ui`` argument fragments (progressive
  paint), balances the forwarded call with a ``{"status": "rendered"}`` tool result,
  feeds the envelope back to the planner, and continues — the same wire shape the
  LangGraph adapters produce. MAF-python is async-native, so the streaming loop runs
  on one event loop with no worker-thread/queue bridge.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any, cast

from ag_ui_a2ui_toolkit import (
    BASIC_CATALOG_ID,
    GENERATE_A2UI_ARG_DESCRIPTIONS,
    MAX_A2UI_ATTEMPTS,
    RENDER_A2UI_TOOL_DEF,
    A2UIToolParams,
    augment_prompt_with_validation_errors,
    build_a2ui_envelope,
    build_context_prompt,
    prepare_a2ui_request,
    resolve_a2ui_catalog,
    resolve_a2ui_tool_params,
    run_a2ui_generation_with_recovery,
    validate_a2ui_components,
    wrap_error_envelope,
)
from agent_framework import Content, FunctionTool, Message, normalize_messages

from ._state import to_history_messages

logger = logging.getLogger(__name__)


def _recovery_exhausted_envelope(max_attempts: int, attempts: list[dict[str, Any]]) -> str:
    """Build the surface envelope shown when recovery attempts are exhausted.

    Prefers the toolkit's shared implementation so the streaming twin and the
    synchronous loop cannot drift on the exhaustion-envelope shape. That helper is
    private (``_wrap_recovery_exhausted_envelope``) and not part of the toolkit's
    public surface, so a patch release could rename or promote it; fall back to the
    public :func:`wrap_error_envelope` rather than failing hard.
    """
    try:
        from ag_ui_a2ui_toolkit.recovery import _wrap_recovery_exhausted_envelope
    except ImportError:
        return cast(
            str,
            wrap_error_envelope(f"A2UI generation failed after {max_attempts} attempt(s)."),
        )
    return cast(str, _wrap_recovery_exhausted_envelope(max_attempts, attempts))


# Inner render_a2ui tool name (canonical, from the toolkit's tool def).
RENDER_A2UI_TOOL_NAME: str = RENDER_A2UI_TOOL_DEF["function"]["name"]
_RENDER_PARAMETERS: dict[str, Any] = RENDER_A2UI_TOOL_DEF["function"]["parameters"]
_RENDER_DESCRIPTION: str = RENDER_A2UI_TOOL_DEF["function"]["description"]

# Bare acknowledgement returned as the inner render_a2ui tool result; the painted
# surface rides the streamed arguments, so the result only has to balance the call.
RENDER_ACKNOWLEDGEMENT = '{"status": "rendered"}'

# Cap on planner rounds (model turn -> generation -> result fed back) per run,
# guarding against a planner that keeps requesting surfaces without terminating.
MAX_PLANNER_ROUNDS = 8


def _generate_tool_schema() -> dict[str, Any]:
    """JSON schema for the planner-facing generate_a2ui tool (string args)."""
    return {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "description": GENERATE_A2UI_ARG_DESCRIPTIONS["intent"]},
            "target_surface_id": {
                "type": "string",
                "description": GENERATE_A2UI_ARG_DESCRIPTIONS["target_surface_id"],
            },
            "changes": {"type": "string", "description": GENERATE_A2UI_ARG_DESCRIPTIONS["changes"]},
        },
    }


def _as_tool_list(tools: Any) -> list[Any]:
    if tools is None:
        return []
    if isinstance(tools, (list, tuple)):
        return list(tools)
    return [tools]


def _string_arg(args: dict[str, Any], name: str) -> str | None:
    value = args.get(name)
    return value if isinstance(value, str) else None


def _tool_call_index(content: Any) -> int | None:
    """The provider's streaming tool-call index for a function_call fragment, if known.

    OpenAI-compatible chat completions tag each parallel tool call with a stable
    ``index`` and send continuation deltas (empty id + name) that share it. The core
    chat client surfaces it on ``content.additional_properties["tool_call_index"]`` when
    available; return it so nameless deltas can be attributed to the right call even when
    parallel calls interleave. Returns ``None`` when the client does not expose it (the
    caller then falls back to most-recently-opened-call attribution).
    """
    ap = getattr(content, "additional_properties", None)
    if isinstance(ap, dict):
        idx = ap.get("tool_call_index")
        if isinstance(idx, int):
            return idx
    return None


def _normalize_catalog(catalog: dict[str, Any] | None) -> dict[str, Any] | None:
    """Coerce a catalog into the shape ``validate_a2ui_components`` expects.

    The validator reads ``catalog["components"]`` as a NAME→schema MAPPING
    (``catalog_components.get(ctype)``). Frontend catalogs — and the schema the
    A2UI middleware forwards in ``RunAgentInput.context`` — list components as an
    ARRAY of ``{"name": ..., ...}`` definitions instead. Re-key the array by
    component name so catalog-membership / required-prop checks run instead of
    crashing. Returns ``None`` (structural validation only) when there is no usable
    component mapping — matching the toolkit's ``resolve_a2ui_catalog``, which
    surfaces no component schema for the forwarded-catalog path.
    """
    if not isinstance(catalog, dict):
        return None
    comps = catalog.get("components")
    if isinstance(comps, dict):
        return catalog
    if isinstance(comps, list):
        mapping = {c["name"]: c for c in comps if isinstance(c, dict) and isinstance(c.get("name"), str) and c["name"]}
        return {**catalog, "components": mapping} if mapping else None
    return None


def _resolve_catalog(state: dict[str, Any], explicit_catalog: dict[str, Any] | None) -> dict[str, Any] | None:
    """Resolve the structured catalog used for validation.

    An explicit ``params.catalog`` wins (nullish — it is the host's deliberate
    choice). Otherwise the forwarded A2UI schema (``state["ag-ui"]["a2ui_schema"]``,
    a JSON string or dict carrying the component catalog) is used so catalog-membership
    and required-prop checks run, not just structural ones. The result is normalized to
    the validator's name→schema mapping shape (see :func:`_normalize_catalog`). Warns and
    degrades to no catalog (structural checks only) on empty/unparseable/non-object
    schema rather than failing the run.
    """
    if explicit_catalog is not None:
        return _normalize_catalog(explicit_catalog)
    schema = (state.get("ag-ui") or {}).get("a2ui_schema")
    if schema is None or schema == "":
        return None
    if isinstance(schema, dict):
        return _normalize_catalog(schema)
    if isinstance(schema, str):
        try:
            parsed = json.loads(schema)
        except (ValueError, TypeError):
            logger.warning("A2UI schema context is not valid JSON; validating without a catalog.")
            return None
        if isinstance(parsed, dict):
            return _normalize_catalog(parsed)
        logger.warning("A2UI schema context did not parse to an object; validating without a catalog.")
        return None
    logger.warning("A2UI schema context has unexpected type %s; validating without a catalog.", type(schema))
    return None


def _effective_default_catalog_id(configured: str, state: dict[str, Any]) -> str:
    """Prefer the frontend-forwarded catalog id when the host configured none.

    ``resolve_a2ui_tool_params`` fills an unset ``default_catalog_id`` with the basic
    catalog. Zero-config demos rely on the catalog the client registered (forwarded in
    ``RunAgentInput.context``), so when the configured id is the basic fallback and a
    forwarded catalog id is available, bind generated surfaces to that instead. An
    explicitly-configured non-basic id always wins.
    """
    if configured and configured != BASIC_CATALOG_ID:
        return configured
    resolved = resolve_a2ui_catalog(state)
    forwarded_id = resolved[1] if resolved else None
    return forwarded_id or configured


def _first_parsable_object(*candidates: str) -> dict[str, Any] | None:
    """Return the first candidate string that parses to a JSON object.

    Streaming tool-call arguments must be reassembled in a way robust to how the
    provider emits them:

    * MAF's Chat-Completions client emits argument DELTAS (``name=""``,
      ``call_id=""`` after the first fragment) for progressive visibility PLUS a
      FINAL COALESCED fragment repeating the tool name with the FULL arguments
      (verified against gpt-4o: the client yields the args twice, so the all-fragment
      concat is exactly ``2x`` the name-bearing concat). Concatenating only the
      NAME-BEARING fragments (opening ``""`` + coalesced full) yields complete JSON;
      concatenating ALL fragments would append the deltas AND the coalesced copy and
      double the JSON into an unparseable string.
    * A deltas-only provider (no coalesced fragment) yields the full JSON only when
      ALL fragments are concatenated.

    Passing ``(name_bearing_concat, all_fragment_concat)`` is robust to both: the
    name-bearing concat wins when a coalesced fragment is present (no doubling), and
    the all-fragment concat is the fallback otherwise. Empty / non-object / unparsable
    candidates are skipped.
    """
    for cand in candidates:
        if not cand:
            continue
        try:
            obj = json.loads(cand)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _sanitize_unanswered_tool_calls(messages: list[Any]) -> list[Any]:
    """Drop function-call contents whose call id has no matching function-result, and
    drop any message left with no contents.

    A2UI surfaces are rendered as ACTIVITIES, so the runtime persists the assistant's
    ``generate_a2ui`` / ``render_a2ui`` tool calls but NOT their tool results (those
    became the rendered surface, not a tool message). On a later turn — e.g. a surface
    action ("Book") — the replayed history then contains an assistant message whose
    tool calls are unanswered, which OpenAI-family providers reject at the planner call
    ("400: an assistant message with 'tool_calls' must be followed by tool messages
    responding to each 'tool_call_id'"). An unanswered tool call cannot be sent to the
    provider, so strip the dangling calls before the planner runs (keeping any text and
    balanced call/result pairs). The surface itself already rendered client-side.
    """
    answered: set[str] = set()
    for m in messages:
        for c in getattr(m, "contents", None) or []:
            if getattr(c, "type", None) == "function_result":
                cid = getattr(c, "call_id", None)
                if cid:
                    answered.add(cid)

    out: list[Any] = []
    for m in messages:
        contents = getattr(m, "contents", None)
        if not contents:
            out.append(m)
            continue
        kept = [
            c
            for c in contents
            if not (getattr(c, "type", None) == "function_call" and getattr(c, "call_id", None) not in answered)
        ]
        if len(kept) == len(contents):
            out.append(m)
        elif kept:
            out.append(Message(role=getattr(m, "role", "assistant"), contents=kept))
        # else: message had only unanswered calls -> drop it entirely
    return out


def _is_recoverable_error(exc: BaseException) -> bool:
    """Classify a sub-agent error. Programmer errors and cancellation rethrow;
    everything else is a recoverable attempt failure (retry).

    Rethrow cancellation, TypeError, NameError, and any non-Exception BaseException
    (SystemExit/KeyboardInterrupt); treat everything else as recoverable.
    """
    if isinstance(exc, asyncio.CancelledError):
        return False
    if not isinstance(exc, Exception):
        return False
    if isinstance(exc, (TypeError, NameError)):
        return False
    return True


class A2UIAgent:
    """Wraps an agent so each run can generate A2UI surfaces.

    Also the single A2UI runner interface the AG-UI host uses: it carries the render
    tool(s) to strip from the planner's list (:attr:`drop_tool_names`), prepends the
    forwarded component catalog + guidelines as a system message, and is recognized by
    :func:`._factory.is_a2ui_runner` so the host can suppress the terminal message
    snapshot for both the auto-injected and the manual ``enable_a2ui()`` paths.

    Args:
        inner_agent: The agent to wrap (any ``SupportsAgentRun``).
        subagent_chat_client: A raw chat client (NO automatic function invocation)
            used to run the UI-generation sub-agent; the adapter reads the forced
            ``render_a2ui`` call's arguments directly.
        params: Behavior knobs (model is not needed here — the sub-agent client is
            supplied directly); defaults are filled per the shared toolkit rules.
        context_slice: Forwarded AG-UI context (component catalog + guidelines) for the
            run, prepended to the prompt as a system message. Handed in directly rather
            than read back from run-option ``additional_properties``.
        drop_tool_names: Render tool name(s) the runtime injected into the planner's
            tools that should be stripped before the planner call (auto-inject path).
            Empty for the manual ``enable_a2ui()`` path.
    """

    def __init__(
        self,
        inner_agent: Any,
        subagent_chat_client: Any,
        params: A2UIToolParams | None = None,
        context_slice: dict[str, Any] | None = None,
        drop_tool_names: list[str] | None = None,
    ) -> None:
        self.inner_agent = inner_agent
        self.subagent_chat_client = subagent_chat_client
        self.params = resolve_a2ui_tool_params(params or {})
        self._context_slice = context_slice or {}
        self.drop_tool_names: list[str] = list(drop_tool_names or [])
        self.id = getattr(inner_agent, "id", None)
        self.name = getattr(inner_agent, "name", None)
        self.description = getattr(inner_agent, "description", None)

    # Delegate the run-loop-relevant attributes to the wrapped agent so a manually
    # enable_a2ui()-wrapped runner (which the host reads these off of directly) keeps the
    # inner agent's configured tools, provider-owned state protection, and approval /
    # authorization middleware, matching the auto-injected path (which keeps the real
    # agent bound).
    @property
    def client(self) -> Any:
        return getattr(self.inner_agent, "client", None)

    @property
    def default_options(self) -> Any:
        return getattr(self.inner_agent, "default_options", None)

    @property
    def context_providers(self) -> Any:
        return getattr(self.inner_agent, "context_providers", [])

    # -- public run -------------------------------------------------------

    def run(self, messages: Any = None, *, stream: bool = False, **kwargs: Any) -> Any:
        """Run the wrapped agent with A2UI support.

        Prepends the forwarded AG-UI context as a system message, then dispatches to the
        streaming or non-streaming path. The AG-UI context slice is taken per run from an
        ``a2ui_context`` kwarg when the host supplies one (so a reused runner never serves
        stale catalog/guidelines), falling back to the constructor value. Returns an async
        iterator (stream) or an awaitable (non-stream), matching the inner agent's protocol.
        """
        context_slice = kwargs.pop("a2ui_context", None)
        if context_slice is None:
            context_slice = self._context_slice
        messages = self._with_context_prompt(messages, context_slice)
        if stream:
            return self._run_streaming(messages, context_slice, **kwargs)
        return self._run_non_streaming(messages, context_slice, **kwargs)

    def _with_context_prompt(self, messages: Any, context_slice: dict[str, Any]) -> list[Message]:
        """Prepend the forwarded component catalog + guidelines as a system message."""
        normalized = normalize_messages(messages)
        if not context_slice:
            return normalized
        prompt = build_context_prompt({"ag-ui": context_slice})
        if not prompt:
            return normalized
        return [Message(role="system", contents=[Content.from_text(text=prompt)]), *normalized]

    # -- non-streaming ----------------------------------------------------

    async def _run_non_streaming(
        self, messages: Any = None, context_slice: dict[str, Any] | None = None, **kwargs: Any
    ) -> Any:
        """Advertise a real generate_a2ui tool and let auto-invocation run it."""
        normalized = _sanitize_unanswered_tool_calls(normalize_messages(messages))
        tools = _as_tool_list(kwargs.pop("tools", None))
        generate_tool = self._build_generate_tool(normalized, context_slice or {})
        merged = [*[t for t in tools if getattr(t, "name", None) != self.params["tool_name"]], generate_tool]
        return await self.inner_agent.run(normalized, stream=False, tools=merged, **kwargs)

    def _build_generate_tool(self, conversation: list[Any], context_slice: dict[str, Any]) -> FunctionTool:
        """Build an EXECUTABLE generate_a2ui tool whose body runs the recovery loop."""
        state = {"ag-ui": context_slice}
        history = to_history_messages(conversation)
        catalog = _resolve_catalog(state, self.params["catalog"])

        async def _generate_a2ui(
            intent: str | None = None,
            target_surface_id: str | None = None,
            changes: str | None = None,
        ) -> str:
            prep = prepare_a2ui_request(
                intent=intent,
                target_surface_id=target_surface_id,
                changes=changes,
                messages=history,
                state=state,
                guidelines=self.params["guidelines"],
            )
            prep_error = prep.get("error")
            if prep_error:
                return cast(str, wrap_error_envelope(prep_error))

            def _run_recovery() -> dict[str, Any]:
                # The toolkit recovery loop is synchronous and calls invoke_subagent
                # once per attempt. Drive every attempt on ONE dedicated event loop
                # (created here, on the executor thread) rather than a fresh
                # asyncio.run per attempt: a per-attempt loop closes after attempt 1,
                # and a retry then fails with "Event loop is closed" because the
                # sub-agent chat client's async transport stays bound to the first
                # (now-closed) loop.
                worker_loop = asyncio.new_event_loop()
                # Set the worker loop as this executor thread's current loop so a
                # sub-agent client that reaches for asyncio.get_event_loop() binds to it.
                asyncio.set_event_loop(worker_loop)
                try:

                    def _invoke(prompt: str, attempt: int) -> dict[str, Any] | None:
                        # Mirror the streaming path's error handling: a recoverable
                        # (transient) sub-agent error becomes a failed attempt the
                        # toolkit loop retries (the toolkit does NOT catch invoke_subagent
                        # exceptions itself); a programmer error / cancellation propagates.
                        try:
                            return worker_loop.run_until_complete(self._invoke_render_subagent(prompt, conversation))
                        except BaseException as exc:  # noqa: BLE001 — reclassified below
                            if not _is_recoverable_error(exc):
                                raise
                            logger.warning(
                                "A2UI render sub-agent failed (non-streaming attempt %d, recoverable): %s",
                                attempt,
                                exc,
                            )
                            return None

                    recovery_result: dict[str, Any] = run_a2ui_generation_with_recovery(
                        base_prompt=prep.get("prompt", ""),
                        invoke_subagent=_invoke,
                        build_envelope=lambda args: build_a2ui_envelope(
                            args=args,
                            is_update=prep.get("is_update", False),
                            target_surface_id=target_surface_id,
                            prior=prep.get("prior"),
                            default_surface_id=self.params["default_surface_id"],
                            default_catalog_id=_effective_default_catalog_id(self.params["default_catalog_id"], state),
                        ),
                        catalog=catalog,
                        config=self.params["recovery"],
                        on_attempt=self.params["on_a2ui_attempt"],
                    )
                    return recovery_result
                finally:
                    asyncio.set_event_loop(None)
                    worker_loop.close()

            # Run the whole synchronous recovery loop in an executor so we never nest
            # event loops on the agent's running loop.
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, _run_recovery)
            return cast(str, result["envelope"])

        return FunctionTool(
            name=self.params["tool_name"],
            description=self.params["tool_description"],
            func=_generate_a2ui,
            input_model=_generate_tool_schema(),
        )

    def _inner_default_tools(self) -> list[Any]:
        """The inner agent's own configured tools (``default_options["tools"]``).

        ``run_agent_stream`` passes no ``tools=`` when there are no AG-UI client tools, so
        a server tool the developer wired on the agent reaches the streaming loop only
        here — not in ``incoming_tools``. Included in the mixed-batch lookup so such a
        tool still executes instead of being treated as unknown.
        """
        default_options = getattr(self.inner_agent, "default_options", None)
        if isinstance(default_options, dict):
            return _as_tool_list(default_options.get("tools"))
        return []

    async def _execute_server_tools(
        self,
        server_calls: list[Any],
        tools: list[Any],
        session: Any,
        config: Any,
        run_kwargs: dict[str, Any],
    ) -> tuple[list[Any], list[Any], bool]:
        """Execute server tools called alongside generate_a2ui through the shared executor.

        Runs them via the framework's function-invocation helper with the run's ``session``,
        the run ``config``, and a middleware pipeline built from the client's static function
        middleware plus the runtime ``middleware`` (bare objects and MiddlewareBundles
        normalized/expanded via ``categorize_middleware``, so a bundle's function middleware
        is applied, not skipped) — the same helper AG-UI approval resume uses, so
        authorization/audit/policy middleware, the session, and approval controls all apply.
        Kept here in the adapter (not behind a new core abstraction). Returns
        ``(results, control, should_terminate)``; ``control`` are non-result contents (e.g. a
        ``function_approval_request``) that must reach the client. A ``MiddlewareFailure``
        (the fail-closed escape an authorization/guardrail middleware raises) propagates,
        exactly as the core loop treats it, so a denied turn aborts instead of continuing on
        to render a surface. Ordinary execution failures surface as error results — carrying a
        generic, non-leaking message unless ``include_detailed_errors`` is enabled, matching
        the core function-error formatting — rather than aborting the surface generation.
        """
        from agent_framework._middleware import FunctionMiddlewarePipeline, MiddlewareFailure, categorize_middleware
        from agent_framework._tools import _try_execute_function_call_groups

        client = getattr(self.inner_agent, "client", None)
        runtime_middleware = run_kwargs.get("middleware")
        runtime_fn_mw = categorize_middleware(runtime_middleware)["function"] if runtime_middleware is not None else []
        pipeline = FunctionMiddlewarePipeline(*(getattr(client, "function_middleware", None) or ()), *runtime_fn_mw)
        custom_args = {k: v for k, v in run_kwargs.items() if k not in ("options", "middleware")}
        try:
            groups, should_terminate = await _try_execute_function_call_groups(
                custom_args=custom_args,
                function_calls=server_calls,
                tools=tools,
                config=config,
                invocation_session=session,
                middleware_pipeline=pipeline,
            )
        except MiddlewareFailure:
            # Fail-closed escape: an authorization/guardrail abort must propagate, never be
            # folded into an error result, or the denied turn would still go on to render a
            # surface. Core's function loop lets this through the same way.
            raise
        except Exception as exc:  # noqa: BLE001 — other failures surface as tool results, never abort the surface
            logger.warning("A2UI: server tool execution failed during a mixed generate turn: %s", exc)
            # Match core's error formatting: keep the model-visible result generic (a raw
            # ``str(exc)`` can carry credentials, provider payloads, or tenant data); expose
            # detail only when the run explicitly enabled it. The full text still rides the
            # non-model-visible ``exception`` field for logs/telemetry.
            detailed = bool(config.get("include_detailed_errors", False)) if hasattr(config, "get") else False
            message = "Error: Function failed."
            if detailed:
                message = f"{message} Exception: {exc}"
            errors = [
                Content.from_function_result(
                    call_id=getattr(c, "call_id", "") or "", result=message, exception=str(exc)
                )
                for c in server_calls
            ]
            return errors, [], False
        results: list[Any] = []
        control: list[Any] = []
        for group in groups:
            for content in group:
                (results if getattr(content, "type", None) == "function_result" else control).append(content)
        return results, control, should_terminate

    async def _invoke_render_subagent(self, prompt: str, conversation: list[Any]) -> dict[str, Any] | None:
        """Run the render sub-agent (forced render_a2ui) and return its args, or None."""
        response = await self.subagent_chat_client.get_response(
            self._subagent_messages(prompt, conversation),
            stream=False,
            options=self._subagent_options(),
        )
        return self._read_render_args(response)

    # -- streaming --------------------------------------------------------

    async def _run_streaming(
        self, messages: Any = None, context_slice: dict[str, Any] | None = None, **kwargs: Any
    ) -> Any:
        from agent_framework import AgentResponseUpdate
        from agent_framework._tools import normalize_function_invocation_configuration

        history = _sanitize_unanswered_tool_calls(normalize_messages(messages))
        session = kwargs.pop("session", None)
        incoming_tools = [
            t for t in _as_tool_list(kwargs.pop("tools", None)) if getattr(t, "name", None) != self.params["tool_name"]
        ]
        state = {"ag-ui": context_slice or {}}
        generate_decl = FunctionTool(
            name=self.params["tool_name"],
            description=self.params["tool_description"],
            func=None,
            input_model=_generate_tool_schema(),
        )

        # Honor the inner agent's function-invocation configuration locally so this loop
        # behaves like the core loop: the invocation toggle, the cumulative call budget
        # (charged by both server tools and generate_a2ui), the iteration cap on planner
        # rounds, and a tools-off final narration when a limit — not an external pause —
        # ends the run.
        fi_config = normalize_function_invocation_configuration(
            getattr(getattr(self.inner_agent, "client", None), "function_invocation_configuration", None)
        )
        fi_enabled = fi_config.get("enabled", True)
        max_calls = fi_config.get("max_function_calls")
        max_iters = fi_config.get("max_iterations")
        max_rounds = MAX_PLANNER_ROUNDS if max_iters is None else min(MAX_PLANNER_ROUNDS, max_iters)
        calls_used = 0

        pending: list[Any] = history
        pending_session = session
        for _round in range(1, max_rounds + 1):
            text_contents: list[Content] = []
            # Coalesce every streamed function_call fragment by call id — generate_a2ui
            # AND any ordinary tool the planner calls in the same turn. A single call is
            # streamed as MANY fragments: an opening fragment carries id (+name),
            # argument-delta fragments carry name=""/call_id="", and MAF adds a final
            # coalesced fragment repeating id + name + the FULL args. Treating each
            # fragment as its own call would run tools repeatedly and emit duplicate
            # results for one call id (an unbalanced assistant/tool sequence the provider
            # rejects). For each call we keep BOTH the name-bearing concat (opening +
            # coalesced) and the all-fragment concat (name-bearing + deltas), then pick
            # the first that parses — robust whether or not a coalesced fragment arrives,
            # without doubling the args. Nameless continuation deltas are attributed by
            # the provider tool-call index when the chat client exposes it, else by the
            # most recently opened call, so interleaved parallel calls do not cross-
            # contaminate.
            call_order: list[str] = []
            name_by_cid: dict[str, str] = {}
            named_concat: dict[str, str] = {}
            all_concat: dict[str, str] = {}
            cid_by_index: dict[int, str] = {}
            active_cid: str | None = None
            async for update in self.inner_agent.run(
                pending,
                stream=True,
                session=pending_session,
                tools=[*incoming_tools, generate_decl],
                **kwargs,
            ):
                for content in update.contents:
                    ctype = getattr(content, "type", None)
                    if ctype == "text":
                        text_contents.append(content)
                        continue
                    if ctype != "function_call":
                        continue
                    name = getattr(content, "name", None)
                    cid = getattr(content, "call_id", None)
                    raw = getattr(content, "arguments", None)
                    frag = raw if isinstance(raw, str) else (json.dumps(raw) if isinstance(raw, dict) else "")
                    idx = _tool_call_index(content)
                    if cid:
                        # Opening or coalesced fragment of some call.
                        if cid not in all_concat:
                            call_order.append(cid)
                            named_concat[cid] = ""
                            all_concat[cid] = ""
                        if name:
                            name_by_cid[cid] = name
                            named_concat[cid] += frag
                        if idx is not None:
                            cid_by_index[idx] = cid
                        active_cid = cid
                        all_concat[cid] += frag
                    else:
                        # Nameless continuation delta: attribute by index if known, else
                        # to the most recently opened call.
                        target = cid_by_index.get(idx) if idx is not None else None
                        target = target or active_cid
                        if target is not None:
                            all_concat[target] += frag
                yield update

            # Classify the coalesced calls. The declaration-only generate_a2ui poisons
            # the inner agent's batch invocation (a batch with any declaration-only call
            # is paused before execution), so tools called alongside it are NOT run by the
            # inner agent — handle them here by TYPE:
            #   * generate_a2ui -> stream the surface (below).
            #   * server tool (executable FunctionTool, found across incoming_tools OR the
            #     inner agent's default tools) -> execute through the agent's real
            #     function-invocation pipeline so middleware/config are preserved.
            #   * client / declaration-only tool (func=None, browser-side) -> leave as a
            #     user-input request for the frontend to execute and resume; do NOT
            #     synthesize a result (that would break the resumable client-tool flow).
            executable_tools = [*incoming_tools, *self._inner_default_tools()]
            tool_by_name = {getattr(t, "name", None): t for t in executable_tools}
            generate_calls: list[Content] = []
            server_calls: list[Content] = []
            client_calls: list[Content] = []
            for cid in call_order:
                nm = name_by_cid.get(cid, "")
                if not nm:
                    continue
                obj = _first_parsable_object(named_concat[cid], all_concat[cid])
                if nm == self.params["tool_name"]:
                    generate_calls.append(
                        Content.from_function_call(
                            call_id=cid, name=nm, arguments=json.dumps(obj) if obj is not None else ""
                        )
                    )
                    continue
                args_str = json.dumps(obj) if isinstance(obj, dict) else (all_concat[cid] or "{}")
                call = Content.from_function_call(call_id=cid, name=nm, arguments=args_str)
                tool = tool_by_name.get(nm)
                if tool is not None and getattr(tool, "func", None) is not None:
                    server_calls.append(call)
                else:
                    call.user_input_request = True
                    call.id = cid
                    client_calls.append(call)

            if not generate_calls:
                # No surface requested this round. A batch WITHOUT a declaration-only call
                # is not poisoned, so the inner agent already executed/surfaced its calls
                # and looped; nothing more to do here.
                return

            # Execute server tools batched with generate_a2ui, honoring the invocation
            # toggle + the shared per-request call budget locally. Calls we must not run
            # (invocation disabled, or over budget) are deferred (left unexecuted) and force
            # the run to stop below rather than be fabricated.
            server_results: list[Content] = []
            server_control: list[Content] = []
            server_terminated = False
            deferred_calls: list[Content] = []
            if server_calls:
                runnable = server_calls if fi_enabled else []
                if max_calls is not None:
                    runnable = runnable[: max(0, max_calls - calls_used)]
                deferred_calls = server_calls[len(runnable) :]
                if runnable:
                    server_results, server_control, server_terminated = await self._execute_server_tools(
                        runnable, executable_tools, session, fi_config, kwargs
                    )
                    calls_used += len(runnable)

            # generate_a2ui also charges the call budget — each is a render-subagent
            # invocation — so a generate-only planner cannot exceed max_function_calls
            # across rounds. Surfaces over budget are deferred (not rendered) and stop the run.
            deferred_generate: list[Content] = []
            if not fi_enabled:
                deferred_generate = generate_calls
                generate_calls = []
            elif max_calls is not None:
                allowed = max(0, max_calls - calls_used)
                deferred_generate = generate_calls[allowed:]
                generate_calls = generate_calls[:allowed]
            calls_used += len(generate_calls)

            generate_results: list[Content] = []
            for call in generate_calls:
                box: list[Any] = [None]
                async for update in self._run_generate_streaming(call, history, state, box):
                    yield update
                generate_results.append(Content.from_function_result(call_id=call.call_id or "", result=box[0]))

            all_results = [*server_results, *generate_results]
            # Surface tool results on the wire; also surface any executor control contents
            # (e.g. a function_approval_request for a protected tool) so they are not dropped.
            yield AgentResponseUpdate(role="tool", contents=all_results)
            if server_control:
                yield AgentResponseUpdate(role="assistant", contents=server_control)

            # Two ways this turn ends the loop. Calls awaiting EXTERNAL resolution — client
            # tools the frontend must run, deferred server tools, an approval request, an
            # executor termination — end the run right here: a follow-up run resumes them,
            # and re-entering the planner would replay an unbalanced assistant tool_call. But
            # a spent call budget is NOT external: break out and still give the planner the
            # tools-off final narration below, matching the core loop's budget-exhausted
            # final response.
            if client_calls or deferred_calls or deferred_generate or server_control or server_terminated:
                return

            # Record this round's assistant call(s) + results BEFORE deciding to stop, so
            # the tools-off final narration below sees the surface this turn just produced
            # (otherwise it receives only the original user messages and cannot narrate it).
            assistant_contents = [*text_contents, *server_calls, *generate_calls]
            history = [
                *history,
                Message(role="assistant", contents=assistant_contents),
                Message(role="tool", contents=all_results),
            ]

            budget_exhausted = max_calls is not None and calls_used >= max_calls
            if budget_exhausted:
                break

            pending = history
            pending_session = None

        # The planner rounds or the call budget are spent. Give the planner one final turn
        # to consume the last result and narrate, with tools forced off via
        # tool_choice="none" — matching the core loop's budget-exhausted final response.
        # Withholding only generate_a2ui is not enough: a fresh inner_agent.run() would
        # otherwise start a new invocation budget and could execute another full batch of
        # server/default tools past the configured max_function_calls / max_iterations.
        final_kwargs = dict(kwargs)
        final_options = dict(final_kwargs.get("options") or {})
        final_options["tool_choice"] = "none"
        final_kwargs["options"] = final_options
        async for update in self.inner_agent.run(
            history,
            stream=True,
            session=None,
            tools=incoming_tools,
            **final_kwargs,
        ):
            yield update

    async def _run_generate_streaming(
        self,
        call: Any,
        conversation: list[Any],
        state: dict[str, Any],
        box: list[Any],
    ) -> AsyncIterator[Any]:
        """Run one generate_a2ui invocation with the streaming validate-retry loop.

        Forwards the render sub-agent's per-chunk updates (progressive paint) and
        deposits the final envelope into ``box[0]``.
        """
        from agent_framework import AgentResponseUpdate

        args = call.parse_arguments() or {}
        intent = _string_arg(args, "intent")
        target_surface_id = _string_arg(args, "target_surface_id")
        changes = _string_arg(args, "changes")

        prep = prepare_a2ui_request(
            intent=intent,
            target_surface_id=target_surface_id,
            changes=changes,
            messages=to_history_messages(conversation),
            state=state,
            guidelines=self.params["guidelines"],
        )
        prep_error = prep.get("error")
        if prep_error:
            box[0] = wrap_error_envelope(prep_error)
            return

        catalog = _resolve_catalog(state, self.params["catalog"])
        max_attempts = (self.params["recovery"] or {}).get("maxAttempts", MAX_A2UI_ATTEMPTS)
        attempts: list[dict[str, Any]] = []
        last_errors: list[dict[str, str]] = []
        for attempt in range(1, max_attempts + 1):
            prompt = augment_prompt_with_validation_errors(prep.get("prompt", ""), last_errors)
            updates: list[Any] = []
            # Track the live render call id so a mid-stream failure can still close it
            # — an unanswered (unbalanced) tool call is a protocol violation and the
            # retry would open a second one on top.
            live_render_call_id: str | None = None
            try:
                async for cru in self.subagent_chat_client.get_response(
                    self._subagent_messages(prompt, conversation),
                    stream=True,
                    options=self._subagent_options(),
                ):
                    updates.append(cru)
                    if live_render_call_id is None:
                        live_render_call_id = self._first_render_call_id(cru)
                    # Forward each per-chunk update so the hosting loop paints the
                    # render_a2ui argument fragments progressively.
                    yield AgentResponseUpdate(
                        contents=cru.contents,
                        role=getattr(cru, "role", None),
                        message_id=getattr(cru, "message_id", None),
                        response_id=getattr(cru, "response_id", None),
                        raw_representation=cru,
                    )
                render_call_id, render_args = self._extract_render_args(updates)
            except BaseException as exc:
                # Classify BEFORE yielding anything. A non-recoverable exception includes
                # GeneratorExit / CancelledError raised into this async generator when the
                # consumer closes it (client disconnect / aclose): yielding during
                # GeneratorExit raises "async generator ignored GeneratorExit", masking a
                # clean cancellation. Re-raise those immediately, without a balancing yield.
                if not _is_recoverable_error(exc):
                    raise
                # Recoverable provider error mid-stream: close the live render call with a
                # balancing tool result so the retry does not open a second one on top and
                # the next turn's history stays balanced.
                if live_render_call_id is not None:
                    yield AgentResponseUpdate(
                        role="tool",
                        contents=[
                            Content.from_function_result(call_id=live_render_call_id, result=RENDER_ACKNOWLEDGEMENT)
                        ],
                    )
                logger.warning("A2UI render sub-agent failed (attempt %d, recoverable): %s", attempt, exc)
                err = {
                    "code": "subagent_error",
                    "path": "render_a2ui",
                    "message": str(exc) or type(exc).__name__,
                }
                record = {"attempt": attempt, "ok": False, "errors": [err]}
                attempts.append(record)
                self._notify_attempt(record)
                last_errors = [err]
                continue

            # Balance the forwarded render_a2ui call with a tool result so the next
            # turn's history is valid (an unanswered tool call is rejected on replay).
            balance_call_id = render_call_id or live_render_call_id
            if balance_call_id is not None:
                yield AgentResponseUpdate(
                    role="tool",
                    contents=[Content.from_function_result(call_id=balance_call_id, result=RENDER_ACKNOWLEDGEMENT)],
                )

            raw_components = (render_args or {}).get("components")
            components = raw_components if isinstance(raw_components, list) else []
            raw_data = (render_args or {}).get("data")
            data = raw_data if isinstance(raw_data, dict) else {}
            result = validate_a2ui_components(components=components, data=data, catalog=catalog)
            record = {"attempt": attempt, "ok": result["valid"], "errors": result["errors"]}
            attempts.append(record)
            self._notify_attempt(record)

            if result["valid"] and render_args is not None:
                box[0] = build_a2ui_envelope(
                    args=render_args,
                    is_update=prep.get("is_update", False),
                    target_surface_id=target_surface_id,
                    prior=prep.get("prior"),
                    default_surface_id=self.params["default_surface_id"],
                    default_catalog_id=_effective_default_catalog_id(self.params["default_catalog_id"], state),
                )
                return
            last_errors = result["errors"]

        box[0] = _recovery_exhausted_envelope(max_attempts, attempts)

    # -- sub-agent helpers ------------------------------------------------

    def _subagent_messages(self, prompt: str, conversation: list[Any]) -> list[Any]:
        return [Message(role="system", contents=[Content.from_text(text=prompt)]), *conversation]

    def _subagent_options(self) -> dict[str, Any]:
        render_decl = FunctionTool(
            name=RENDER_A2UI_TOOL_NAME,
            description=_RENDER_DESCRIPTION,
            func=None,
            input_model=_RENDER_PARAMETERS,
        )
        return {
            "tools": [render_decl],
            "tool_choice": {"mode": "required", "required_function_name": RENDER_A2UI_TOOL_NAME},
        }

    def _first_render_call_id(self, update: Any) -> str | None:
        for content in getattr(update, "contents", None) or []:
            if (
                getattr(content, "type", None) == "function_call"
                and getattr(content, "name", None) == RENDER_A2UI_TOOL_NAME
                and getattr(content, "call_id", None)
            ):
                return cast("str | None", content.call_id)
        return None

    def _extract_render_args(self, updates: list[Any]) -> tuple[str | None, dict[str, Any] | None]:
        """Reassemble the render_a2ui call id + arguments from streamed updates.

        MAF's ``ChatResponse.from_updates`` coalesces text content but NOT function-call
        argument fragments, so a coalesced render call carries only a partial fragment.
        We concatenate the render_a2ui argument deltas ourselves — the same reassembly
        the AG-UI wire performs — and parse the joined JSON. Returns
        ``(call_id, args)``; ``args`` is ``None`` when the sub-agent produced no render
        call or the accumulated arguments are not valid JSON (→ a failed attempt the
        recovery loop retries).
        """
        call_id: str | None = None
        named_buf = ""  # name == render_a2ui fragments (opening + coalesced-final)
        all_buf = ""  # every function_call fragment (deltas + coalesced)
        parsed_obj: dict[str, Any] | None = None
        for upd in updates:
            for content in getattr(upd, "contents", None) or []:
                if getattr(content, "type", None) != "function_call":
                    continue
                # The sub-agent is forced (tool_choice) to call ONLY render_a2ui, so
                # every function_call fragment belongs to that one call — the
                # name=="" argument-delta fragments included.
                name = getattr(content, "name", None)
                if call_id is None and name == RENDER_A2UI_TOOL_NAME and getattr(content, "call_id", None):
                    call_id = content.call_id
                raw = getattr(content, "arguments", None)
                if isinstance(raw, str):
                    all_buf += raw
                    if name == RENDER_A2UI_TOOL_NAME:
                        named_buf += raw
                elif isinstance(raw, dict):
                    # A provider that already coalesced this fragment to a dict.
                    parsed_obj = raw
        if parsed_obj is not None:
            return call_id, parsed_obj
        # Prefer the name-bearing concat (opening + coalesced full); fall back to the
        # all-fragment concat for a deltas-only provider. See _first_parsable_object.
        obj = _first_parsable_object(named_buf, all_buf)
        if obj is None and (named_buf or all_buf):
            logger.warning(
                "A2UI render_a2ui arguments did not parse as a JSON object "
                "(named=%d chars, all=%d chars); treating attempt as no surface.",
                len(named_buf),
                len(all_buf),
            )
        return call_id, obj

    def _notify_attempt(self, record: dict[str, Any]) -> None:
        """Invoke the host ``on_a2ui_attempt`` callback, isolating its failures.

        The callback is host-supplied observability; a throwing callback must not abort
        an in-flight run (the surface has already streamed to the client by this point).
        """
        callback = self.params["on_a2ui_attempt"]
        if callback is None:
            return
        try:
            callback(record)
        except Exception as exc:  # noqa: BLE001 — host callback must not break the run
            logger.warning("A2UI on_a2ui_attempt callback raised (ignored): %s", exc)

    def _find_render_call(self, response: Any) -> Any:
        for message in getattr(response, "messages", None) or []:
            for content in getattr(message, "contents", None) or []:
                if (
                    getattr(content, "type", None) == "function_call"
                    and getattr(content, "name", None) == RENDER_A2UI_TOOL_NAME
                ):
                    return content
        return None

    def _read_render_args(self, response: Any) -> dict[str, Any] | None:
        call = self._find_render_call(response)
        return (call.parse_arguments() or {}) if call is not None else None
