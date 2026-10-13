# Copyright (c) Microsoft. All rights reserved.

import asyncio
import warnings

from agent_framework import AsyncRequestBroker

"""AsyncRequestBroker: pause server-side work until a client responds.

This sample demonstrates how to use `AsyncRequestBroker` to let server-side
code (for example a running agent or tool) stop partway through, ask a
connected client for a decision, and continue once the client answers.

A typical case is a tool that needs human approval before it runs. The server
calls `await broker.request(request_id)` and sends the request ID to the UI
over whatever transport you use (websocket, SSE, HTTP). When the user answers,
the client handler calls `broker.resolve(request_id, value)` or
`broker.reject(request_id, exception)`, and the awaiting coroutine continues.

The sample covers three cases:
1. The server awaits a request and the client resolves it.
2. The server awaits a request, the client rejects it, and the server handles
   the error.
3. The server awaits a request with a timeout that nobody answers.

No LLM or credentials are needed. The "client" is simulated with
`asyncio.create_task` in the same event loop.
"""

# AsyncRequestBroker is experimental; silence the warning to keep output tidy.
warnings.filterwarnings("ignore", message=r"\[HARNESS\]")


class ApprovalDenied(Exception):
    """Raised on the server when the client denies an approval request."""


async def server_delete_files(broker: AsyncRequestBroker[bool], request_id: str, path: str) -> None:
    """Server-side work that pauses for client approval before continuing."""
    print(f"[server] Requesting approval to delete '{path}' (id={request_id})")
    try:
        # Suspends here, without blocking the event loop, until the client answers.
        approved = await broker.request(request_id)
    except ApprovalDenied as ex:
        print(f"[server] Request {request_id} was rejected: {ex}. Skipping.")
        return
    print(f"[server] Request {request_id} answered: approved={approved}. Deleting '{path}'.")


async def client_respond(broker: AsyncRequestBroker[bool], request_id: str, *, approve: bool) -> None:
    """Simulate a client (e.g. a UI) answering the request after a short delay."""
    await asyncio.sleep(0.1)  # The user thinks about it...
    if approve:
        print(f"[client] Approving {request_id}")
        broker.resolve(request_id, True)
    else:
        print(f"[client] Denying {request_id}")
        broker.reject(request_id, ApprovalDenied("user said no"))


async def main() -> None:
    broker: AsyncRequestBroker[bool] = AsyncRequestBroker()

    # 1. Resolve: the client approves and the server continues with the result.
    print("=== Resolve ===")
    await asyncio.gather(
        server_delete_files(broker, "req-1", "./tmp/cache"),
        client_respond(broker, "req-1", approve=True),
    )

    # 2. Reject: the client denies and the server gets the exception.
    print("\n=== Reject ===")
    await asyncio.gather(
        server_delete_files(broker, "req-2", "./important"),
        client_respond(broker, "req-2", approve=False),
    )

    # 3. Timeout: nobody answers, so the server stops waiting.
    print("\n=== Timeout ===")
    try:
        await broker.request("req-3", timeout=0.2)
    except asyncio.TimeoutError:
        print("[server] Request req-3 timed out with no response.")

    # A late reply for a settled request is ignored. resolve() returns True to
    # show the ID is known but already settled.
    print(f"[client] Late reply to req-3 accepted as already settled: {broker.resolve('req-3', True)}")
    print(f"Pending requests: {broker.pending_count}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
=== Resolve ===
[server] Requesting approval to delete './tmp/cache' (id=req-1)
[client] Approving req-1
[server] Request req-1 answered: approved=True. Deleting './tmp/cache'.

=== Reject ===
[server] Requesting approval to delete './important' (id=req-2)
[client] Denying req-2
[server] Request req-2 was rejected: user said no. Skipping.

=== Timeout ===
[server] Request req-3 timed out with no response.
[client] Late reply to req-3 accepted as already settled: True
Pending requests: 0
"""
