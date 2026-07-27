# Copyright (c) Microsoft. All rights reserved.

"""Human-in-the-loop (HITL) addressing helper for workflow executors.

When a MAF :class:`~agent_framework.Workflow` runs on the Azure Functions durable
host, an executor can ask a human for input via ``ctx.request_info(...)``. To notify
that human out-of-band (for example by emailing them an approval link), the executor
needs the orchestration's ``instanceId`` and the request's ``requestId`` so it can
build the ``/respond`` URL the reviewer will POST back to.

:class:`WorkflowHitlContext` packages that addressing. It reads the orchestration
metadata the durable host surfaces on the executor's runner context (see
``CapturingRunnerContext.host_metadata``) and builds the canonical respond/status
URLs that :class:`~agent_framework_azurefunctions.AgentFunctionApp` exposes -- so the
executor never has to thread the instance id or base URL by hand.

Typical use, from inside a notify executor reached by an edge from the executor that
called ``request_info``::

    hitl = WorkflowHitlContext.from_context(ctx)
    if hitl is not None:  # None when not on the Azure Functions durable host
        url = hitl.build_respond_url(request_id)
        send_email(to=reviewer, body=f"Approve or reject here: {url}")
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, cast

from agent_framework_durabletask._workflows.runner_context import (
    HOST_METADATA_INSTANCE_ID,
    HOST_METADATA_REQUEST_PATH_PREFIX,
    HOST_METADATA_WORKFLOW_NAME,
)

from ._routes import build_workflow_respond_url, build_workflow_status_url

# App setting carrying the function app's host (e.g. ``myapp.azurewebsites.net``).
# Azure Functions sets this automatically in the cloud; for local ``func start`` runs
# add it to the ``Values`` map in ``local.settings.json`` (e.g. ``localhost:7071``).
WEBSITE_HOSTNAME_ENV = "WEBSITE_HOSTNAME"

# Loopback hosts that resolve to ``http`` (not ``https``) when WEBSITE_HOSTNAME is
# host-only; covers the addresses ``func start`` can bind locally.
_LOOPBACK_HOSTS = frozenset({"localhost", "0.0.0.0", "::1"})  # ruff:ignore[hardcoded-bind-all-interfaces]  # nosec B104


def _is_loopback(host: str) -> bool:
    """Return whether ``host`` (optionally ``host:port``) is a local loopback address.

    Handles ``localhost``, IPv4 ``127.0.0.0/8`` and ``0.0.0.0``, and IPv6 ``::1``
    (including the bracketed ``[::1]:port`` form ``func start`` prints).
    """
    normalized = host.strip().lower()
    if normalized.startswith("["):  # bracketed IPv6 like [::1]:7071
        normalized = normalized[1 : normalized.find("]")] if "]" in normalized else normalized[1:]
    elif normalized.count(":") == 1:  # host:port (bare IPv6 has multiple colons)
        normalized = normalized.split(":", 1)[0]
    return normalized in _LOOPBACK_HOSTS or normalized.startswith("127.")


@dataclass(frozen=True)
class WorkflowHitlContext:
    """Builds Azure Functions HITL respond/status URLs from inside a workflow executor.

    Obtain one with :meth:`from_context`. It exposes the addressable *root*
    orchestration's ``instance_id`` and ``workflow_name`` and builds the URLs an
    external reviewer uses to resume the workflow. When the executor runs inside a
    nested sub-workflow, ``request_path_prefix`` carries the ``{executor}~{ordinal}~``
    hops from the root down to this level, so :meth:`build_respond_url` qualifies a bare
    request id back to the top-level instance automatically. The base URL is resolved
    lazily (see :attr:`base_url`) from an explicit override or the ``WEBSITE_HOSTNAME``
    app setting.
    """

    instance_id: str
    workflow_name: str
    base_url_override: str | None = None
    request_path_prefix: str = ""

    @classmethod
    def from_context(
        cls,
        ctx: Any,
        *,
        base_url: str | None = None,
    ) -> WorkflowHitlContext | None:
        """Build a HITL context from a workflow executor's ``WorkflowContext``.

        Reads the orchestration metadata the durable host attached to the executor's
        runner context. Returns ``None`` when that metadata is absent -- i.e. the same
        executor is running in-process rather than on the Azure Functions durable host
        -- so callers can skip notification and degrade gracefully.

        Args:
            ctx: The ``WorkflowContext`` passed to the executor's handler.
            base_url: Optional explicit base URL (scheme + host, e.g.
                ``https://contoso.example.com``). Use this when the public URL differs
                from ``WEBSITE_HOSTNAME`` -- for example behind a custom domain or API
                Management gateway, where ``WEBSITE_HOSTNAME`` still reports the default
                ``*.azurewebsites.net`` host. When omitted, the base URL is resolved
                from ``WEBSITE_HOSTNAME`` on first use.

        Returns:
            A :class:`WorkflowHitlContext`, or ``None`` if not running on a durable host.
        """
        runner_context = getattr(ctx, "_runner_context", None)
        raw_metadata = getattr(runner_context, "host_metadata", None)
        if not isinstance(raw_metadata, dict):
            return None
        metadata = cast("dict[str, Any]", raw_metadata)

        instance_id = metadata.get(HOST_METADATA_INSTANCE_ID)
        workflow_name = metadata.get(HOST_METADATA_WORKFLOW_NAME)
        if not isinstance(instance_id, str) or not isinstance(workflow_name, str):
            return None

        # Present when the executor runs inside a nested sub-workflow; absent/empty at
        # the top level. Defaults to "" so the request id is used unqualified.
        raw_prefix = metadata.get(HOST_METADATA_REQUEST_PATH_PREFIX)
        request_path_prefix = raw_prefix if isinstance(raw_prefix, str) else ""

        return cls(
            instance_id=instance_id,
            workflow_name=workflow_name,
            base_url_override=base_url,
            request_path_prefix=request_path_prefix,
        )

    @staticmethod
    async def pending_request_id(ctx: Any) -> str | None:
        """Return the id of the most recently emitted ``request_info`` on ``ctx``.

        Call this **immediately after** ``await ctx.request_info(...)`` to recover the
        request id the framework generated, so it can be forwarded (e.g. in a message
        to a downstream notify executor that builds the respond URL) without the caller
        generating an id by hand.

        Why "immediately after" is the rule, and why it is safe on the durable host:
        the returned id is simply the newest entry in the executor's pending
        request-info set, so reading right after a call always yields *that* call's id.
        On the Azure Functions durable host every executor runs in its own activity with
        its own runner context, so that set only ever holds this executor's own
        requests (never another executor's), and the request you just emitted is always
        the latest. If a single executor emits several ``request_info`` calls in one
        turn, read this after **each** call (the only case where reading once at the end
        would lose the earlier ids); or pass an explicit ``request_id`` to
        ``request_info`` to address them directly.

        Returns ``None`` only when no request is pending (or the runner context does not
        track request-info events, e.g. in process off the durable host).
        """
        runner_context = getattr(ctx, "_runner_context", None)
        getter = getattr(runner_context, "get_pending_request_info_events", None)
        if getter is None:
            return None
        events = await getter()
        if not events:
            return None
        # Dicts preserve insertion order, so the last key is the most recent request.
        return next(reversed(events))

    @property
    def base_url(self) -> str:
        """The scheme + host the respond/status URLs are built on (no trailing slash).

        Resolution order: the explicit ``base_url`` passed to :meth:`from_context`, then
        the ``WEBSITE_HOSTNAME`` app setting (``http`` for localhost, otherwise
        ``https``).

        Raises:
            RuntimeError: If neither an override nor ``WEBSITE_HOSTNAME`` is available.
        """
        if self.base_url_override:
            return self.base_url_override.rstrip("/")

        hostname = os.environ.get(WEBSITE_HOSTNAME_ENV)
        if not hostname:
            raise RuntimeError(
                "Cannot build a HITL URL: no base URL is available. Set the "
                f"'{WEBSITE_HOSTNAME_ENV}' app setting (present automatically on Azure "
                "Functions; add it to the 'Values' map in local.settings.json for local "
                "`func start` runs, e.g. 'localhost:7071'), or pass base_url=... to "
                "WorkflowHitlContext.from_context()."
            )

        # WEBSITE_HOSTNAME may include a scheme (unusual but possible); otherwise it is
        # host-only, so infer one (http for local loopback, https otherwise).
        if hostname.startswith(("http://", "https://")):
            return hostname.rstrip("/")
        scheme = "http" if _is_loopback(hostname) else "https"
        return f"{scheme}://{hostname.rstrip('/')}"

    def build_respond_url(self, request_id: str) -> str:
        """Build the URL a reviewer POSTs their response to, resuming the workflow.

        Mirrors the ``respondUrl`` AgentFunctionApp returns from its run/status
        endpoints: ``{base}/{prefix}/workflow/{name}/respond/{instanceId}/{requestId}``
        (``prefix`` is the app's ``routePrefix``, ``api`` by default), always targeting
        the addressable top-level instance.

        Args:
            request_id: The pending request's id -- the id passed to (or generated by)
                ``ctx.request_info``. Pass the **bare** id even from inside a nested
                sub-workflow: any :attr:`request_path_prefix` is prepended for you to
                qualify it (``{executor}~{ordinal}~{requestId}``) back to the root.

        Returns:
            The fully-qualified respond URL.
        """
        qualified_id = f"{self.request_path_prefix}{request_id}"
        return build_workflow_respond_url(self.base_url, self.workflow_name, self.instance_id, qualified_id)

    def build_status_url(self) -> str:
        """Build the workflow status URL for this orchestration instance.

        Returns ``{base}/{prefix}/workflow/{name}/status/{instanceId}`` (``prefix`` is the
        app's ``routePrefix``, ``api`` by default), the same endpoint AgentFunctionApp
        exposes for polling runtime status and pending HITL requests.
        """
        return build_workflow_status_url(self.base_url, self.workflow_name, self.instance_id)
