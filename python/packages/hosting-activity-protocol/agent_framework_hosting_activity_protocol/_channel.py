# Copyright (c) Microsoft. All rights reserved.

r"""Built-in channel: Bot Framework Activity Protocol (Azure Bot Service).

Activity Protocol is the Bot Framework messaging shape used by Azure Bot
Service to fan one bot endpoint out across many surfaces (Microsoft
Teams, Slack, Webex, Telegram, …). An incoming ``Activity`` is POSTed to
your bot's ``/messages`` endpoint, and you reply by POSTing one or more
``Activity`` objects back to the conversation URL the inbound activity
carried in ``serviceUrl``. Auth is an OAuth2 client-credentials token
from Entra (the legacy multi-tenant ``botframework.com`` authority for
public Bot Framework channels, or your own tenant for single-tenant
bots).

This is the channel-neutral Activity-Protocol channel — it surfaces what
every Bot-Service-connected channel has in common (text in, text out).
For deeper Microsoft Teams affordances (adaptive cards, message
extensions, dialogs, SSO, …) on the same Bot Service transport, see the
companion ``agent-framework-hosting-teams`` package.

This channel handles:

- inbound ``message`` activities — text and attachments resolved to URIs,
- outbound replies via ``POST /v3/conversations/{id}/activities``,
- streaming via ``PUT /v3/conversations/{id}/activities/{id}`` mid-stream
  edits (Teams supports updateActivity in personal chats and groups),
- typing indicators while the agent works,
- per-conversation isolation key ``activity:<conversation_id>`` so a Responses
  caller can resume a Teams conversation by passing the conversation id,
- two credential modes for the outbound token — **client secret** or
  **certificate** (for tenants that disallow secrets) — both via
  ``azure.identity.aio``,
- dev-mode auth bypass when no credentials are passed so the Bot Framework
  Emulator can hit the endpoint with no credentials.

Out of scope for the prototype: full JWT validation of inbound requests,
adaptive cards, file uploads, OAuth sign-in flows, and the Teams streaming
preview API (``StreamItem``).

Generating a certificate
------------------------
For tenants that disallow client secrets, register a certificate on your
Bot Framework / Entra app instead. Self-signed PEM (private key + cert in
one file) is what ``azure.identity.CertificateCredential`` expects::

    # 1. Generate a 2048-bit RSA key + self-signed cert (10y), single PEM.
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \\
        -subj "/CN=my-teams-bot" \\
        -keyout teams-bot.key -out teams-bot.crt
    cat teams-bot.key teams-bot.crt > teams-bot.pem

    # 2. Upload teams-bot.crt to your Entra app under
    #    "Certificates & secrets" → "Certificates" → "Upload certificate".

    # 3. Point the channel at the combined PEM:
    ActivityProtocolChannel(
        app_id="<app id>",
        tenant_id="<tenant id>",         # or "botframework.com" for legacy bots
        certificate_path="teams-bot.pem",
    )

To encrypt the private key, drop ``-nodes`` from the openssl command and
pass ``certificate_password=<bytes>`` to the channel.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Mapping
from typing import Any

import httpx
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    Content,
    Message,
    ResponseStream,
)
from agent_framework_hosting import (
    ChannelContext,
    ChannelContribution,
    ChannelRequest,
    ChannelRunHook,
    ChannelSession,
    ChannelStreamTransformHook,
    apply_run_hook,
    logger,
)
from azure.core.credentials_async import AsyncTokenCredential
from azure.identity.aio import CertificateCredential, ClientSecretCredential
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

# Bot Framework v4 multi-tenant authority used by the public Bot Framework
# channels (including Microsoft Teams). Single-tenant bots should override
# ``tenant_id`` with their own tenant.
_BOTFRAMEWORK_TENANT = "botframework.com"
_BOTFRAMEWORK_SCOPE = "https://api.botframework.com/.default"


def activity_protocol_isolation_key(conversation_id: Any) -> str:
    """Build the namespaced isolation key the Teams channel writes under.

    Exposed at module scope so other channels' run hooks can opt into the
    same per-conversation session (e.g. a Responses caller resuming a Teams
    conversation by passing the conversation id).
    """
    return f"activity:{conversation_id}"


def _parse_activity(activity: Mapping[str, Any]) -> Message:
    """Translate one Bot Framework ``message`` Activity into an Agent Framework Message.

    Pulls the activity's ``text`` plus any image/file attachments with a
    ``contentType`` and resolvable URL into ``Content`` parts. If the
    activity has no usable parts an empty text part is emitted so the
    caller never sees a content-less message.
    """
    parts: list[Content] = []
    if (text := activity.get("text")) and isinstance(text, str):
        parts.append(Content.from_text(text=text))

    for attachment in activity.get("attachments") or []:
        if not isinstance(attachment, Mapping):
            continue
        url = attachment.get("contentUrl") or attachment.get("content")
        content_type = attachment.get("contentType")
        if isinstance(url, str) and isinstance(content_type, str) and "/" in content_type:
            parts.append(Content.from_uri(uri=url, media_type=content_type))

    if not parts:
        parts.append(Content.from_text(text=""))
    return Message("user", parts)


class ActivityProtocolChannel:
    """Microsoft Teams channel via Bot Framework v4 webhook.

    Streaming
    ---------
    When ``stream=True`` (default), the channel sends an initial placeholder
    activity, then edits it in place as the agent emits ``AgentResponseUpdate``
    chunks (``PUT /v3/conversations/{id}/activities/{id}``). When ``stream=False``
    it just sends the final reply. A ``stream_transform_hook`` can rewrite or
    drop individual updates before they hit the wire.
    """

    name = "activity"

    def __init__(
        self,
        *,
        path: str = "/activity",
        app_id: str | None = None,
        app_password: str | None = None,
        certificate_path: str | None = None,
        certificate_password: bytes | None = None,
        tenant_id: str = _BOTFRAMEWORK_TENANT,
        token_scope: str = _BOTFRAMEWORK_SCOPE,
        credential: AsyncTokenCredential | None = None,
        run_hook: ChannelRunHook | None = None,
        send_typing_action: bool = True,
        stream: bool = True,
        stream_transform_hook: ChannelStreamTransformHook | None = None,
        stream_edit_min_interval: float = 0.7,
    ) -> None:
        """Configure the Teams channel.

        Args:
            path: Mount path. The webhook lives at ``{path}/messages``.
            app_id: Bot Framework / Entra application (client) id. Required
                whenever any credential is supplied.
            app_password: Application secret for OAuth2 client credentials.
                Mutually exclusive with ``certificate_path``.
            certificate_path: Path to a PEM file containing **both** the
                private key and the X.509 certificate. Use this for tenants
                that disallow client secrets. See the module docstring for an
                ``openssl`` recipe.
            certificate_password: Password for the PEM private key, if any.
            tenant_id: Entra tenant. Defaults to ``"botframework.com"`` for
                public Bot Framework channels; pass your tenant id for
                single-tenant bots.
            token_scope: OAuth2 scope to request. Defaults to the Bot
                Framework resource.
            credential: Bring your own ``AsyncTokenCredential`` (e.g. a
                ``DefaultAzureCredential`` configured elsewhere). Overrides
                ``app_password`` / ``certificate_path``.
            run_hook: Optional rewrite of ``ChannelRequest`` before invocation.
            send_typing_action: Whether to send ``typing`` activities while
                the agent runs.
            stream: Whether to stream by default. ``run_hook`` can flip per
                request.
            stream_transform_hook: Optional rewrite of each
                ``AgentResponseUpdate`` before it hits the wire.
            stream_edit_min_interval: Seconds between successive in-place
                edits. Teams is more rate-sensitive than Telegram, so default
                is higher.
        """
        if app_password and certificate_path:
            raise ValueError("ActivityProtocolChannel: pass either app_password or certificate_path, not both.")
        self.path = path
        self._app_id = app_id
        self._token_scope = token_scope
        self._tenant_id = tenant_id
        self._hook = run_hook
        self._send_typing_action = send_typing_action
        self._stream_default = stream
        self._stream_transform_hook = stream_transform_hook
        self._stream_edit_min_interval = stream_edit_min_interval
        self._ctx: ChannelContext | None = None
        self._http: httpx.AsyncClient | None = None

        # Build the credential up front so misconfiguration fails at construction.
        self._credential: AsyncTokenCredential | None
        if credential is not None:
            self._credential = credential
        elif app_id and certificate_path:
            self._credential = CertificateCredential(
                tenant_id=tenant_id,
                client_id=app_id,
                certificate_path=certificate_path,
                password=certificate_password,
            )
        elif app_id and app_password:
            self._credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=app_id,
                client_secret=app_password,
            )
        else:
            self._credential = None  # dev mode

    def contribute(self, context: ChannelContext) -> ChannelContribution:
        """Capture the host context and register the ``POST /messages`` webhook."""
        self._ctx = context
        return ChannelContribution(
            routes=[Route("/messages", self._handle, methods=["POST"])],
            on_startup=[self._on_startup],
            on_shutdown=[self._on_shutdown],
        )

    # -- lifecycle --------------------------------------------------------- #

    async def _on_startup(self) -> None:
        """Open the outbound HTTP client and emit a startup banner.

        When no Bot Framework credential is configured we log a loud warning —
        outbound replies will not authenticate, which is only acceptable
        against the local Bot Framework Emulator.
        """
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=30.0)
        if self._credential is None:
            logger.warning(
                "ActivityProtocolChannel running without credentials — outbound replies "
                "will not authenticate. Use only with the Bot Framework "
                "Emulator for local development."
            )
        else:
            cred_kind = type(self._credential).__name__
            logger.info(
                "ActivityProtocolChannel listening on %s/messages (auth=%s, tenant=%s)",
                self.path,
                cred_kind,
                self._tenant_id,
            )

    async def _on_shutdown(self) -> None:
        """Close the HTTP client and best-effort close the credential.

        Credential ``close`` failures are logged but never raised — shutdown
        must never be allowed to mask the original cause of an app exit.
        """
        if self._http is not None:
            await self._http.aclose()
        if self._credential is not None:
            close = getattr(self._credential, "close", None)
            if close is not None:
                try:
                    await close()
                except Exception:  # pragma: no cover - best-effort
                    logger.exception("ActivityProtocolChannel credential close failed")

    # -- token management -------------------------------------------------- #

    async def _get_token(self) -> str | None:
        """Acquire (and cache) an outbound bearer token.

        ``azure.identity`` credentials cache and refresh internally, so we
        just delegate.
        """
        if self._credential is None:
            return None
        access_token = await self._credential.get_token(self._token_scope)
        return access_token.token

    def _auth_headers(self, token: str | None) -> dict[str, str]:
        """Return Bot Framework auth headers, or an empty dict in dev mode."""
        return {"Authorization": f"Bearer {token}"} if token else {}

    # -- request handling -------------------------------------------------- #

    async def _handle(self, request: Request) -> Response:
        """Bot Framework webhook entry point.

        Only ``message`` activities are processed; ``conversationUpdate``,
        ``invoke``, ``typing`` and other activity types are silently
        acknowledged. The webhook always returns 200 (or 202 for ignored
        types) so Bot Framework can dequeue the activity even if our
        downstream processing fails — failures are logged and re-tried by
        the user, not by Teams.
        """
        try:
            activity = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid json"}, status_code=400)

        # We accept only message activities for now. ``conversationUpdate``,
        # ``invoke``, ``typing`` and friends are silently ack'd.
        if activity.get("type") != "message":
            return JSONResponse({}, status_code=202)

        try:
            await self._process_activity(activity)
        except Exception:
            logger.exception("Teams activity processing failed")
        # Bot Framework expects 200 OK to dequeue the activity.
        return JSONResponse({}, status_code=200)

    async def _process_activity(self, activity: Mapping[str, Any]) -> None:
        """Build a :class:`ChannelRequest` from a message Activity and dispatch.

        The Teams isolation key is per-conversation so all members of a
        group chat share session state. Activity metadata (``reply_to_id``,
        ``recipient``) is preserved so reply-as-reaction style flows can
        reconstruct the original message context.
        """
        if self._ctx is None:  # pragma: no cover - guarded by lifecycle
            raise RuntimeError("activity channel not started")
        conversation = activity.get("conversation") or {}
        conversation_id = conversation.get("id")
        service_url = activity.get("serviceUrl")
        if not isinstance(conversation_id, str) or not isinstance(service_url, str):
            logger.warning("Teams activity missing conversation.id or serviceUrl — dropping")
            return

        parsed = _parse_activity(activity)
        channel_request = ChannelRequest(
            channel=self.name,
            operation="message.create",
            input=[parsed],
            session=ChannelSession(isolation_key=activity_protocol_isolation_key(conversation_id)),
            attributes={
                "conversation_id": conversation_id,
                "service_url": service_url,
                "from_id": (activity.get("from") or {}).get("id"),
                "channel_id": activity.get("channelId"),
            },
            metadata={"reply_to_id": activity.get("id"), "recipient": activity.get("recipient")},
            stream=self._stream_default,
        )
        if self._hook is not None:
            channel_request = await apply_run_hook(
                self._hook,
                channel_request,
                target=self._ctx.target,
                protocol_request=activity,
            )

        await self._dispatch(activity, channel_request)

    # -- outbound helpers -------------------------------------------------- #

    async def _dispatch(self, inbound: Mapping[str, Any], request: ChannelRequest) -> None:
        """Run the target and ship the result back into the originating Teams conversation.

        Optionally fires a typing indicator before non-streaming runs;
        streaming runs route through ``_stream_to_conversation`` which
        progressively edits a single placeholder activity.
        """
        if self._ctx is None:  # pragma: no cover - guarded by lifecycle
            raise RuntimeError("activity channel not started")
        if self._send_typing_action:
            await self._send_typing(inbound)

        if not request.stream:
            result = await self._ctx.run(request)
            text = getattr(result, "text", None) or "(no response)"
            await self._send_message(inbound, text)
            return

        stream = self._ctx.run_stream(request)
        await self._stream_to_conversation(inbound, stream)

    async def _stream_to_conversation(
        self,
        inbound: Mapping[str, Any],
        stream: ResponseStream[AgentResponseUpdate, AgentResponse],
    ) -> None:
        """Iterate the stream and progressively edit a single Teams activity."""
        accumulated = ""
        last_sent = ""
        last_edit_at = 0.0
        activity_id: str | None = None
        worker_done = asyncio.Event()
        wake = asyncio.Event()

        async def send_initial_placeholder() -> None:
            nonlocal activity_id, last_edit_at
            try:
                activity_id = await self._send_message(inbound, "…")
                last_edit_at = time.monotonic()
            except Exception:  # pragma: no cover
                logger.exception("Teams placeholder send failed")

        async def edit_worker() -> None:
            nonlocal last_sent, last_edit_at
            while not (worker_done.is_set() and accumulated == last_sent):
                await wake.wait()
                wake.clear()
                if activity_id is None or accumulated == last_sent:
                    continue
                elapsed = time.monotonic() - last_edit_at
                if elapsed < self._stream_edit_min_interval:
                    try:
                        await asyncio.wait_for(wake.wait(), timeout=self._stream_edit_min_interval - elapsed)
                        wake.clear()
                    except asyncio.TimeoutError:
                        pass
                snapshot = accumulated
                if snapshot == last_sent:
                    continue
                try:
                    await self._update_activity(inbound, activity_id, snapshot)
                except Exception:  # pragma: no cover
                    logger.exception("Teams interim edit failed")
                last_sent = snapshot
                last_edit_at = time.monotonic()

        await send_initial_placeholder()
        edit_task = asyncio.create_task(edit_worker(), name="activity-edit-worker")

        try:
            async for update in stream:
                if self._stream_transform_hook is not None:
                    transformed = self._stream_transform_hook(update)
                    if isinstance(transformed, Awaitable):
                        transformed = await transformed
                    if transformed is None:
                        continue
                    update = transformed
                chunk = getattr(update, "text", None)
                if chunk:
                    accumulated += chunk
                    wake.set()
        except Exception:
            logger.exception("Teams streaming consumption failed")
        finally:
            worker_done.set()
            wake.set()
            try:
                await edit_task
            except Exception:  # pragma: no cover
                logger.exception("Teams edit worker crashed")

        try:
            await stream.get_final_response()
        except Exception:  # pragma: no cover
            logger.exception("Stream finalize failed")

        # Final flush — make sure the user sees everything that arrived after
        # the worker's last edit.
        if activity_id is not None and accumulated and accumulated != last_sent:
            try:
                await self._update_activity(inbound, activity_id, accumulated)
            except Exception:  # pragma: no cover
                logger.exception("Teams final edit failed")
        elif not accumulated and activity_id is not None:
            # No text streamed — replace the placeholder with a stub so the
            # user isn't left staring at "…".
            try:
                await self._update_activity(inbound, activity_id, "(no response)")
            except Exception:  # pragma: no cover
                logger.exception("Teams placeholder replace failed")

    # -- Bot Framework REST helpers --------------------------------------- #

    def _activity_payload(self, inbound: Mapping[str, Any], text: str) -> dict[str, Any]:
        """Build the outbound Activity envelope (text-only message)."""
        recipient = inbound.get("from") or {}
        from_user = inbound.get("recipient") or {}
        return {
            "type": "message",
            "from": from_user,
            "recipient": recipient,
            "conversation": inbound.get("conversation") or {},
            "replyToId": inbound.get("id"),
            "channelId": inbound.get("channelId"),
            "serviceUrl": inbound.get("serviceUrl"),
            "text": text,
            "textFormat": "plain",
        }

    async def _send_message(self, inbound: Mapping[str, Any], text: str) -> str | None:
        """POST a new Activity. Returns the assigned activity id."""
        if self._http is None:  # pragma: no cover - guarded by lifecycle
            raise RuntimeError("activity channel not started")
        service_url = str(inbound.get("serviceUrl") or "").rstrip("/")
        conversation_id = (inbound.get("conversation") or {}).get("id")
        if not service_url or not isinstance(conversation_id, str):
            return None
        url = f"{service_url}/v3/conversations/{conversation_id}/activities"
        token = await self._get_token()
        response = await self._http.post(
            url, json=self._activity_payload(inbound, text), headers=self._auth_headers(token)
        )
        response.raise_for_status()
        payload = response.json() if response.content else {}
        return payload.get("id") if isinstance(payload, dict) else None

    async def _update_activity(self, inbound: Mapping[str, Any], activity_id: str, text: str) -> None:
        """PUT-edit an existing Activity (Teams updateActivity)."""
        if self._http is None:  # pragma: no cover - guarded by lifecycle
            raise RuntimeError("activity channel not started")
        service_url = str(inbound.get("serviceUrl") or "").rstrip("/")
        conversation_id = (inbound.get("conversation") or {}).get("id")
        if not service_url or not isinstance(conversation_id, str):
            return
        url = f"{service_url}/v3/conversations/{conversation_id}/activities/{activity_id}"
        token = await self._get_token()
        response = await self._http.put(
            url, json=self._activity_payload(inbound, text), headers=self._auth_headers(token)
        )
        response.raise_for_status()

    async def _send_typing(self, inbound: Mapping[str, Any]) -> None:
        """Send a Teams typing indicator; failures are logged and swallowed.

        The typing activity is purely a UX nicety — if it fails (token
        expired, transient network issue, channel that doesn't support
        typing) we never surface that to the user or block the actual
        agent run.
        """
        if self._http is None:  # pragma: no cover - guarded by lifecycle
            raise RuntimeError("activity channel not started")
        service_url = str(inbound.get("serviceUrl") or "").rstrip("/")
        conversation_id = (inbound.get("conversation") or {}).get("id")
        if not service_url or not isinstance(conversation_id, str):
            return
        url = f"{service_url}/v3/conversations/{conversation_id}/activities"
        token = await self._get_token()
        try:
            await self._http.post(
                url,
                json={
                    "type": "typing",
                    "from": inbound.get("recipient") or {},
                    "recipient": inbound.get("from") or {},
                    "conversation": inbound.get("conversation") or {},
                    "serviceUrl": inbound.get("serviceUrl"),
                },
                headers=self._auth_headers(token),
            )
        except Exception:  # pragma: no cover - non-critical UX
            logger.exception("Teams typing send failed")


__all__ = ["ActivityProtocolChannel", "activity_protocol_isolation_key"]
