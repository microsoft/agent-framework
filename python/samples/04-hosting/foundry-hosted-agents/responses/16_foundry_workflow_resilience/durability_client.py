# Copyright (c) Microsoft. All rights reserved.

"""Submit and monitor one durable background response across host replacements."""

# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "azure-identity>=1.25.2",
#   "httpx>=0.28.1",
# ]
# ///

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from azure.identity.aio import AzureCliCredential

TERMINAL_STATUSES = {"completed", "failed", "cancelled", "incomplete"}


def _is_local_endpoint(endpoint: str) -> bool:
    return urlsplit(endpoint).hostname in {"localhost", "127.0.0.1"}


def _response_url(endpoint: str, response_id: str | None = None, session_id: str | None = None) -> str:
    parsed = urlsplit(endpoint)
    path = parsed.path.rstrip("/")
    if response_id:
        path = f"{path}/{response_id}"
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if session_id:
        query["agent_session_id"] = session_id
    return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode(query), parsed.fragment))


def _output_text(response: dict[str, object]) -> str:
    parts: list[str] = []
    output = response.get("output")
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
    return "\n".join(parts)


async def _authorization_headers(endpoint: str) -> dict[str, str]:
    if _is_local_endpoint(endpoint):
        return {}
    credential = AzureCliCredential()
    try:
        token = await credential.get_token("https://ai.azure.com/.default")
        return {"Authorization": f"Bearer {token.token}"}
    finally:
        await credential.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, help="Responses endpoint printed by `azd ai agent show`.")
    parser.add_argument(
        "--session-id",
        help="Hosted session created by `azd ai agent sessions create`; required for remote endpoints.",
    )
    parser.add_argument("--response-id", help="Resume monitoring an existing response instead of creating one.")
    parser.add_argument(
        "--input",
        default="The quick brown fox jumps over the lazy dog.",
        help="English text to send when creating a response.",
    )
    parser.add_argument("--poll-seconds", type=float, default=5)
    parser.add_argument("--state-file", type=Path, default=Path(".durability-response.json"))
    args = parser.parse_args()

    if not _is_local_endpoint(args.endpoint) and not args.session_id:
        parser.error("--session-id is required for remote endpoints")

    headers = await _authorization_headers(args.endpoint)
    headers.update(
        {
            "Content-Type": "application/json",
            "x-agent-user-isolation-key": "durability-demo-user",
            "x-agent-chat-isolation-key": "durability-demo-chat",
        }
    )
    async with httpx.AsyncClient(headers=headers, timeout=60) as client:
        response_id = args.response_id
        if not response_id:
            result = await client.post(
                _response_url(args.endpoint, session_id=args.session_id),
                json={
                    "model": "workflow",
                    "input": args.input,
                    "background": True,
                    "store": True,
                    "stream": False,
                },
            )
            result.raise_for_status()
            body = result.json()
            response_id = body["id"]
            args.state_file.write_text(
                json.dumps(
                    {
                        "endpoint": args.endpoint,
                        "session_id": args.session_id,
                        "response_id": response_id,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            if args.session_id:
                print(f"Hosted session: {args.session_id}")
            print(f"Created durable background response: {response_id}")
            print(f"Recovery state saved to: {args.state_file.resolve()}")
            print("Redeploy or replace the host while this client continues polling.\n")

        last_status: str | None = None
        while True:
            try:
                result = await client.get(_response_url(args.endpoint, response_id, args.session_id))
                result.raise_for_status()
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                print(f"Host temporarily unavailable; retrying: {exc}")
                await asyncio.sleep(args.poll_seconds)
                continue

            body = result.json()
            status = body.get("status")
            if status != last_status:
                print(f"Response status: {status}")
                last_status = status if isinstance(status, str) else None

            if status in TERMINAL_STATUSES:
                text = _output_text(body)
                if text:
                    print("\nPersisted response output\n-------------------------")
                    print(text)
                if status != "completed":
                    raise RuntimeError(json.dumps(body, indent=2))
                print("\nPASS: The original response completed.")
                return

            await asyncio.sleep(args.poll_seconds)


if __name__ == "__main__":
    asyncio.run(main())
