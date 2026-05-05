# Copyright (c) Microsoft. All rights reserved.

r"""Built-in channel: Microsoft Teams (microsoft-teams-apps SDK).

This channel layers Teams-native affordances on top of the Bot Framework
transport that Azure Bot Service exposes. It uses the official
``microsoft-teams-apps`` SDK (microsoft/teams.py) instead of speaking
the Bot Framework Activity Protocol over raw HTTP — the SDK gives us:

- typed activity models (``MessageActivity``, ``MessageSubmitActionInvokeActivity``, ...),
- streaming via :class:`~microsoft_teams.apps.HttpStream` (mid-stream
  ``updateActivity`` edits that Teams renders as live text),
- adaptive cards (``AdaptiveCard`` from ``microsoft_teams.cards``),
- citation entities (``CitationEntity``, ``CitationAppearance``),
- a typed ``on_message_submit_feedback`` invoke handler for thumbs-up /
  thumbs-down feedback.

The SDK normally owns its own HTTP server. Here we replace that with a
custom :class:`~microsoft_teams.apps.HttpServerAdapter` that captures
the route registration synchronously into a Starlette :class:`Route`,
which the host then mounts under ``path``. The SDK's
:class:`~microsoft_teams.apps.HttpServer` registers its route during
:meth:`~microsoft_teams.apps.HttpServer.initialize` (a synchronous call
made from the async :meth:`microsoft_teams.apps.App.initialize` only as
part of plugin/server boot). We invoke that synchronous step ourselves
inside :meth:`TeamsChannel.contribute` so the route is available before
the host starts serving; plugin :py:meth:`on_init` callbacks (which are
async) still run from the channel's startup hook by calling
``app.initialize()`` once more (it is idempotent).

For deployments that just need the channel-neutral Activity Protocol
shape (text in, text out) across every Bot Service connector — Slack,
Webex, Telegram-via-Bot-Service, etc. — see the companion
``agent-framework-hosting-activity-protocol`` package.

Authentication note
-------------------
Teams bots are still reached **through Azure Bot Service** under the
hood. There is currently no way to receive Teams traffic without an
Azure Bot Service registration. This channel does not change that — it
only changes the *programming model* (typed SDK + Teams affordances).

Outbound feature scope
----------------------
The channel returns a plain text reply by default. To customize the
outbound payload (use an Adaptive Card, attach citations, suggest
follow-up actions, …) supply an ``outbound_transform`` callable. The
hook receives a :class:`TeamsOutboundContext` with the inbound
``ActivityContext`` and the agent's :class:`HostedRunResult`, and
returns a :class:`TeamsOutboundPayload`. See the README for examples.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeAlias, cast

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    ResponseStream,
)
from agent_framework_hosting import (
    ChannelContext,
    ChannelContribution,
    ChannelIdentity,
    ChannelRequest,
    ChannelRunHook,
    ChannelSession,
    ChannelStreamTransformHook,
    HostedRunResult,
    apply_run_hook,
    logger,
)
from microsoft_teams.api.activities.invoke.message.submit_action import (
    MessageSubmitActionInvokeActivity,
)
from microsoft_teams.api.activities.message.message import (
    MessageActivity,
    MessageActivityInput,
)
from microsoft_teams.api.models import CitationUsageInfo
from microsoft_teams.api.models.entity.citation_entity import (
    Appearance,
    CitationEntity,
    Claim,
    Image,
)
from microsoft_teams.apps import (
    ActivityContext,
    App,
    HttpServerAdapter,
)
from microsoft_teams.apps.http.adapter import (
    HttpMethod,
    HttpRequest,
    HttpResponse,
    HttpRouteHandler,
)
from microsoft_teams.cards.core import AdaptiveCard
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

# --------------------------------------------------------------------------- #
# Public type aliases                                                         #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TeamsCitation:
    """A single citation to attach to an outbound Teams message.

    Translated to a :class:`Claim` inside a :class:`CitationEntity` on the
    message's ``entities`` array. Teams renders these as numbered
    footnote chips beneath the assistant message; the chip name is shown
    verbatim and the URL is opened when clicked. ``abstract`` is
    required by the SDK schema (Teams shows it on hover); pass an empty
    string when no abstract is available.
    """

    name: str
    abstract: str
    url: str | None = None
    text: str | None = None
    keywords: tuple[str, ...] = ()
    image: Image | None = None
    usage_info: CitationUsageInfo | None = None


@dataclass
class TeamsOutboundPayload:
    """What the channel sends to Teams in response to a message.

    Exactly one of ``text`` or ``card`` is delivered; if both are set the
    card wins and ``text`` is dropped (Teams treats them as alternative
    bodies). ``citations`` are wired in only when ``text`` is used —
    Adaptive Cards have their own citation conventions.
    """

    text: str | None = None
    card: AdaptiveCard | None = None
    citations: Sequence[TeamsCitation] = ()


@dataclass(frozen=True)
class TeamsOutboundContext:
    """Inputs handed to ``outbound_transform``."""

    request: ChannelRequest
    activity_context: ActivityContext[MessageActivity]
    result: HostedRunResult


TeamsOutboundTransform: TypeAlias = Callable[
    [TeamsOutboundContext],
    "TeamsOutboundPayload | Awaitable[TeamsOutboundPayload]",
]


@dataclass(frozen=True)
class TeamsFeedbackContext:
    """Inputs handed to ``feedback_handler`` when a user submits feedback.

    ``rating`` is the SDK-normalized ``"like"`` / ``"dislike"`` string;
    ``feedback`` is the optional free-text message the user typed.
    ``activity_context`` exposes the original feedback invoke activity
    so handlers can inspect ``reply_to_id`` (the assistant message being
    rated), the user identity, etc.
    """

    activity_context: ActivityContext[MessageSubmitActionInvokeActivity]
    rating: str
    feedback: str | None
    reply_to_id: str | None
    identity: ChannelIdentity


TeamsFeedbackHandler: TypeAlias = Callable[
    [TeamsFeedbackContext],
    "Awaitable[None] | None",
]


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def teams_isolation_key(conversation_id: str) -> str:
    """Return the host-wide isolation key used by :class:`TeamsChannel`.

    Mirrors the helper exposed by ``hosting-activity-protocol`` so callers
    that bridge Responses → Teams can construct the same key without
    knowing the channel's internals. Distinct prefix (``teams:``) keeps
    Teams-SDK conversations from colliding with Activity-Protocol
    conversations even though both run on Bot Service.
    """
    return f"teams:{conversation_id}"


# --------------------------------------------------------------------------- #
# Starlette / SDK adapter                                                     #
# --------------------------------------------------------------------------- #


class _StarletteCaptureAdapter(HttpServerAdapter):  # type: ignore[misc]
    """Capture the SDK's route registration into Starlette routes.

    The SDK calls :meth:`register_route` once per endpoint during
    :meth:`microsoft_teams.apps.HttpServer.initialize` (synchronous).
    We hold every (method, path) → handler pairing here so the channel
    can reflect them as :class:`starlette.routing.Route` instances on
    its :class:`ChannelContribution`.

    ``serve_static`` and ``start`` / ``stop`` are intentionally no-ops:
    static files are mounted by the host (not the SDK), and the host
    owns the server lifecycle.
    """

    def __init__(self) -> None:
        self.handlers: dict[tuple[str, str], HttpRouteHandler] = {}

    def register_route(self, method: HttpMethod, path: str, handler: HttpRouteHandler) -> None:
        self.handlers[method.upper(), path] = handler

    def serve_static(self, path: str, directory: str) -> None:  # pragma: no cover - host owns static
        logger.debug("TeamsChannel: ignoring serve_static(%s, %s); host owns static.", path, directory)

    async def start(self, port: int) -> None:  # pragma: no cover - host owns lifecycle
        logger.debug("TeamsChannel: ignoring adapter.start(%s); host owns lifecycle.", port)

    async def stop(self) -> None:  # pragma: no cover - host owns lifecycle
        logger.debug("TeamsChannel: ignoring adapter.stop(); host owns lifecycle.")


def _route_for(handler: HttpRouteHandler, mount_path: str, method: str) -> Route:
    """Wrap a captured SDK handler as a Starlette :class:`Route`.

    The wrapper translates the Starlette request shape (raw bytes +
    headers) to the SDK's :class:`HttpRequest` (parsed body + headers
    dict) and the returned :class:`HttpResponse` back to a Starlette
    response. Bodies are parsed as JSON; non-JSON inbound payloads (rare
    for Bot Framework) result in a 400.
    """

    async def _starlette_handler(request: Request) -> Response:
        raw_body = await request.body()
        body: dict[str, Any] = {}
        if raw_body:
            try:
                parsed = await request.json()
            except Exception:
                return JSONResponse({"error": "invalid json"}, status_code=400)
            if isinstance(parsed, dict):
                body = cast(dict[str, Any], parsed)
        headers = {k.lower(): v for k, v in request.headers.items()}
        result: HttpResponse = await handler(HttpRequest(body=body, headers=headers))
        status = result.get("status", 200)
        result_body = result.get("body")
        if result_body is None:
            return Response(status_code=status)
        return JSONResponse(content=cast(Any, result_body), status_code=status)

    return Route(mount_path, _starlette_handler, methods=[method])


# --------------------------------------------------------------------------- #
# Channel                                                                     #
# --------------------------------------------------------------------------- #


@dataclass
class _TeamsHandlerSet:
    """Bundle of SDK callbacks the channel installs on its :class:`App`."""

    on_message: Callable[[ActivityContext[MessageActivity]], Awaitable[None]]
    on_feedback: Callable[[ActivityContext[MessageSubmitActionInvokeActivity]], Awaitable[None]] | None = None


class TeamsChannel:
    """Microsoft Teams channel built on the ``microsoft-teams-apps`` SDK.

    The channel registers a single ``POST {path}`` webhook (default
    ``/teams/messages``) that hands inbound activities to the SDK. The
    SDK validates JWTs, parses the activity, and dispatches to
    :meth:`_on_message_activity` / :meth:`_on_feedback_activity`.
    """

    name = "teams"

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        tenant_id: str | None = None,
        token: Callable[[Any, str | None], str | Awaitable[str]] | None = None,
        path: str = "/teams/messages",
        skip_auth: bool = False,
        run_hook: ChannelRunHook | None = None,
        outbound_transform: TeamsOutboundTransform | None = None,
        feedback_handler: TeamsFeedbackHandler | None = None,
        stream_transform_hook: ChannelStreamTransformHook | None = None,
        streaming: bool = False,
        app: App | None = None,
    ) -> None:
        """Configure the channel.

        Args:
            client_id: Entra app id of the Bot Service registration.
                Required unless ``skip_auth=True`` or you supply ``app``.
            client_secret: Client secret for the Entra app.
            tenant_id: Tenant id; defaults to the Bot Framework
                multi-tenant authority when omitted.
            token: Optional async/sync token provider, passed straight
                through to the SDK. Use this with managed identity or
                custom credential flows.
            path: Mount path for the messaging endpoint. The SDK's
                default of ``/api/messages`` is replaced with this value.
            skip_auth: Disable inbound JWT validation. **Only** for
                local dev with the Bot Framework Emulator.
            run_hook: Optional channel run hook (mutates the
                :class:`ChannelRequest` before it hits the host). Receives
                ``protocol_request`` set to the inbound :class:`MessageActivity`.
            outbound_transform: Optional callable that turns the
                agent's :class:`HostedRunResult` into a
                :class:`TeamsOutboundPayload`. Default behaviour is to
                send ``result.text`` as a plain text reply.
            feedback_handler: Optional callable invoked when a user
                submits a thumbs-up / thumbs-down rating. When supplied
                the channel registers ``on_message_submit_feedback`` on
                the SDK app.
            stream_transform_hook: Per-update transform hook applied
                during streaming. Returning ``None`` from the hook drops
                the update entirely.
            streaming: When ``True`` the channel calls ``run_stream`` on
                the host and writes deltas through the SDK's
                :class:`HttpStream`. When ``False`` (default) it calls
                ``run`` once and sends a single reply.
            app: Pre-built :class:`microsoft_teams.apps.App` instance.
                Useful for tests and for advanced setups that need to
                register additional handlers (dialogs, message
                extensions, ...) before passing the app to the channel.
                Must have been built with an :class:`HttpServerAdapter`
                that this channel can replace, or none at all (the
                channel will install its own).
        """
        self.path = path
        self._run_hook = run_hook
        self._outbound_transform = outbound_transform
        self._feedback_handler = feedback_handler
        self._stream_transform_hook = stream_transform_hook
        self._streaming = streaming
        self._ctx: ChannelContext | None = None

        self._adapter = _StarletteCaptureAdapter()
        if app is not None:
            self._app = app
            # Replace whatever adapter the user gave the App with our capturing
            # one so the host can mount the routes. The SDK exposes
            # ``server`` directly, so we swap the adapter on the server.
            self._app.server._adapter = self._adapter  # type: ignore[attr-defined]  # pyright: ignore[reportPrivateUsage]
        else:
            options: dict[str, Any] = {
                "http_server_adapter": self._adapter,
                "messaging_endpoint": path,
                "skip_auth": skip_auth,
            }
            if client_id is not None:
                options["client_id"] = client_id
            if client_secret is not None:
                options["client_secret"] = client_secret
            if tenant_id is not None:
                options["tenant_id"] = tenant_id
            if token is not None:
                options["token"] = token
            self._app = App(**options)

        self._handlers = _TeamsHandlerSet(on_message=self._on_message_activity)
        if feedback_handler is not None:
            self._handlers.on_feedback = self._on_feedback_activity

        self._app.on_message(self._handlers.on_message)
        if self._handlers.on_feedback is not None:
            self._app.on_message_submit_feedback(self._handlers.on_feedback)

    # -- public spec API --------------------------------------------------- #

    def contribute(self, context: ChannelContext) -> ChannelContribution:
        """Register the messaging webhook and lifecycle hooks.

        Calls :meth:`microsoft_teams.apps.HttpServer.initialize`
        synchronously so the SDK populates the capturing adapter before
        we hand the host a :class:`ChannelContribution`. Plugin
        ``on_init`` callbacks (async) run from :meth:`_on_startup`.
        """
        self._ctx = context
        # Synchronously register the route on our capturing adapter.
        self._app.server.initialize(
            credentials=self._app.credentials,
            skip_auth=self._app.options.skip_auth or False,
            cloud=self._app.cloud,
        )
        # Wire HttpServer.on_request to App's activity dispatcher (this
        # is normally done inside App.initialize, but we did the
        # synchronous initialization piecewise to obtain routes early).
        self._app.server.on_request = self._app._process_activity_event  # type: ignore[attr-defined]  # pyright: ignore[reportPrivateUsage]

        routes = [
            _route_for(handler, mount_path, method) for (method, mount_path), handler in self._adapter.handlers.items()
        ]
        return ChannelContribution(
            routes=routes,
            on_startup=[self._on_startup],
            on_shutdown=[self._on_shutdown],
        )

    # -- lifecycle --------------------------------------------------------- #

    async def _on_startup(self) -> None:
        """Run plugin :meth:`on_init` callbacks via ``app.initialize``.

        :meth:`microsoft_teams.apps.App.initialize` is idempotent: the
        synchronous server-init step we already ran is short-circuited
        on the second call, but plugin async initialization still runs.
        Logs a warning when ``skip_auth=True`` so users notice the
        auth bypass in their startup output.
        """
        if not self._app._initialized:  # type: ignore[attr-defined]  # pyright: ignore[reportPrivateUsage]
            await self._app.initialize()
        if self._app.options.skip_auth:
            logger.warning(
                "TeamsChannel running with skip_auth=True — inbound "
                "activities are not JWT-validated. Use only with the "
                "Bot Framework Emulator for local development."
            )
        logger.info("TeamsChannel listening on %s", self.path)

    async def _on_shutdown(self) -> None:
        """Best-effort SDK teardown.

        The SDK does not expose a public ``close`` on :class:`App`. The
        underlying HTTP client and token manager hold sockets and a
        background-refresh timer respectively; both are typically reaped
        on process exit. We only invoke any best-effort close hooks the
        SDK exposes today.
        """
        http_client = getattr(self._app, "http_client", None)
        close = getattr(http_client, "close", None) if http_client is not None else None
        if close is not None:
            try:
                result = close()
                if isinstance(result, Awaitable):
                    await result
            except Exception:  # pragma: no cover - best-effort
                logger.exception("TeamsChannel http client close failed")

    # -- inbound: message ------------------------------------------------- #

    async def _on_message_activity(self, activity_context: ActivityContext[MessageActivity]) -> None:
        """Build a :class:`ChannelRequest` from the inbound message and run."""
        if self._ctx is None:  # pragma: no cover - contribute() always called first
            raise RuntimeError("TeamsChannel was not contributed to a host.")

        activity = activity_context.activity
        text = activity.text or ""
        identity = self._identity_from_activity(activity)
        session = ChannelSession(isolation_key=teams_isolation_key(activity.conversation.id))

        request = ChannelRequest(
            channel=self.name,
            operation="message.create",
            input=text,
            session=session,
            stream=self._streaming,
            identity=identity,
            metadata={
                "conversation_id": activity.conversation.id,
                "channel_id": activity.channel_id,
                "service_url": activity.service_url,
                "from_id": activity.from_.id,
                "from_aad_object_id": getattr(activity.from_, "aad_object_id", None),
            },
        )

        if self._run_hook is not None:
            request = await apply_run_hook(
                self._run_hook,
                request,
                target=self._ctx.target,
                protocol_request=activity,
            )

        if self._streaming:
            await self._run_streaming(request, activity_context)
        else:
            result = await self._ctx.run(request)
            await self._ctx.deliver_response(request, result)
            await self._send_outbound(request, activity_context, result)

    async def _run_streaming(
        self,
        request: ChannelRequest,
        activity_context: ActivityContext[MessageActivity],
    ) -> None:
        """Iterate the host stream and emit deltas through ``activity_context.stream``.

        Teams renders ``HttpStream.emit`` calls as live mid-message edits
        (the typing-then-text streaming UI). We close the stream when
        the host stream completes and call ``deliver_response`` with the
        accumulated final result so cross-channel delivery still runs.
        """
        if self._ctx is None:  # pragma: no cover - contribute() ran first
            raise RuntimeError("TeamsChannel was not contributed to a host.")
        stream: ResponseStream[AgentResponseUpdate, AgentResponse] = self._ctx.run_stream(request)
        accumulated: list[str] = []
        async for update in stream:
            transformed: AgentResponseUpdate | None = update
            if self._stream_transform_hook is not None:
                maybe = self._stream_transform_hook(update)
                if isinstance(maybe, Awaitable):
                    transformed = await cast("Awaitable[AgentResponseUpdate | None]", maybe)
                else:
                    transformed = maybe
            if transformed is None:
                continue
            chunk = _update_text(transformed)
            if not chunk:
                continue
            activity_context.stream.emit(chunk)
            accumulated.append(chunk)
        await activity_context.stream.close()
        result = HostedRunResult(text="".join(accumulated))
        await self._ctx.deliver_response(request, result)

    # -- outbound: message ------------------------------------------------- #

    async def _send_outbound(
        self,
        request: ChannelRequest,
        activity_context: ActivityContext[MessageActivity],
        result: HostedRunResult,
    ) -> None:
        """Resolve outbound content and POST to Teams via the SDK."""
        payload = await self._resolve_outbound(request, activity_context, result)

        if payload.card is not None:
            await activity_context.send(payload.card)
            return
        if payload.text is None:
            return
        if not payload.citations:
            await activity_context.send(payload.text)
            return
        message = MessageActivityInput(
            text=payload.text,
            entities=[_citations_entity(payload.citations)],
        )
        await activity_context.send(message)

    async def _resolve_outbound(
        self,
        request: ChannelRequest,
        activity_context: ActivityContext[MessageActivity],
        result: HostedRunResult,
    ) -> TeamsOutboundPayload:
        """Run ``outbound_transform`` (sync or async) and return the payload."""
        if self._outbound_transform is None:
            return TeamsOutboundPayload(text=result.text)
        maybe = self._outbound_transform(
            TeamsOutboundContext(
                request=request,
                activity_context=activity_context,
                result=result,
            )
        )
        if isinstance(maybe, Awaitable):
            return await maybe
        return maybe

    # -- inbound: feedback ------------------------------------------------- #

    async def _on_feedback_activity(self, activity_context: ActivityContext[MessageSubmitActionInvokeActivity]) -> None:
        """Translate a feedback invoke into a :class:`TeamsFeedbackContext`."""
        if self._feedback_handler is None:  # pragma: no cover - guarded at registration
            return
        activity = activity_context.activity
        identity = self._identity_from_activity(activity)
        action_value = getattr(activity.value, "action_value", None)
        rating = str(getattr(action_value, "reaction", "")) if action_value is not None else ""
        feedback = getattr(action_value, "feedback", None) if action_value is not None else None
        ctx = TeamsFeedbackContext(
            activity_context=activity_context,
            rating=rating,
            feedback=feedback,
            reply_to_id=activity.reply_to_id,
            identity=identity,
        )
        outcome = self._feedback_handler(ctx)
        if isinstance(outcome, Awaitable):
            await outcome

    # -- helpers ---------------------------------------------------------- #

    def _identity_from_activity(
        self,
        activity: MessageActivity | MessageSubmitActionInvokeActivity,
    ) -> ChannelIdentity:
        """Build a :class:`ChannelIdentity` from the inbound activity."""
        from_ = activity.from_
        attributes: dict[str, Any] = {
            "name": getattr(from_, "name", None),
            "aad_object_id": getattr(from_, "aad_object_id", None),
            "conversation_id": activity.conversation.id,
            "channel_id": activity.channel_id,
        }
        return ChannelIdentity(
            channel=self.name,
            native_id=from_.id,
            attributes={k: v for k, v in attributes.items() if v is not None},
        )


# --------------------------------------------------------------------------- #
# Update / citation helpers                                                   #
# --------------------------------------------------------------------------- #


def _update_text(update: AgentResponseUpdate) -> str:
    """Extract concatenated text from a single :class:`AgentResponseUpdate`.

    The SDK's stream protocol expects per-chunk strings (it concatenates
    them into the live message). We tolerate updates with no text
    contents by returning an empty string, which the caller skips.
    """
    parts: list[str] = []
    for content in update.contents:
        text = getattr(content, "text", None)
        if isinstance(text, str) and text:
            parts.append(text)
    return "".join(parts)


def _citations_entity(citations: Sequence[TeamsCitation]) -> CitationEntity:
    """Translate a list of :class:`TeamsCitation` into the SDK's wire format.

    All citations on a single message live inside one
    :class:`CitationEntity`'s ``citation`` array. Positions are 1-based
    to match the chip number Teams renders. Optional fields
    (``url`` / ``text`` / ``keywords`` / ``image`` / ``usage_info``)
    are forwarded only when set so the channel does not pin the SDK's
    defaults.
    """
    claims: list[Claim] = []
    for position, citation in enumerate(citations, start=1):
        appearance_kwargs: dict[str, Any] = {
            "name": citation.name,
            "abstract": citation.abstract,
        }
        if citation.text is not None:
            appearance_kwargs["text"] = citation.text
        if citation.url is not None:
            appearance_kwargs["url"] = citation.url
        if citation.keywords:
            appearance_kwargs["keywords"] = list(citation.keywords)
        if citation.image is not None:
            appearance_kwargs["image"] = citation.image
        if citation.usage_info is not None:
            appearance_kwargs["usage_info"] = citation.usage_info
        claims.append(Claim(position=position, appearance=Appearance(**appearance_kwargs)))
    return CitationEntity(citation=claims)
