# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import os
from collections.abc import Mapping
from typing import Annotated, Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode
from urllib.request import Request, urlopen

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

"""
Xquik Function Tools Example

This sample demonstrates API-key backed function tools for public X/Twitter
research workflows. The agent can search posts, look up a user profile, fetch
recent user posts, and inspect trends through Xquik REST API endpoints.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT - Azure AI Foundry project endpoint
    FOUNDRY_MODEL            - Model deployment name
    XQUIK_API_KEY            - Optional Xquik API key for live API calls
    XQUIK_BASE_URL           - Optional API base URL, defaults to https://xquik.com/api/v1

When XQUIK_API_KEY is not set, the tools return local sample data so this file
can run in sample validation without external Xquik credentials.
"""

XQUIK_API_CONTRACT = "2026-04-29"
XQUIK_BASE_URL = os.environ.get("XQUIK_BASE_URL", "https://xquik.com/api/v1").rstrip("/")
XQUIK_TIMEOUT_SECONDS = 20


def _query_params(values: Mapping[str, object | None]) -> dict[str, str]:
    """Convert optional tool arguments to URL query parameters."""
    params: dict[str, str] = {}
    for key, value in values.items():
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            params[key] = str(value).lower()
        else:
            params[key] = str(value)
    return params


def _int_param(value: object | None, default: int) -> int:
    """Read an integer sample parameter with a stable default."""
    if value is None or value == "":
        return default
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _sample_response(path: str, params: Mapping[str, object | None]) -> dict[str, Any]:
    """Return deterministic sample data when no Xquik API key is configured."""
    note = "Set XQUIK_API_KEY to call the live Xquik API."
    if path == "/x/tweets/search":
        query = str(params.get("q") or "agent framework")
        return {
            "mode": "sample_data",
            "note": note,
            "tweets": [
                {
                    "id": "1900000000000000001",
                    "text": f"Developers are wiring agent function tools to live APIs for {query}.",
                    "createdAt": "2026-05-15T09:00:00Z",
                    "author": {
                        "id": "1000000001",
                        "username": "sample_builder",
                        "name": "Sample Builder",
                        "verified": False,
                    },
                    "likeCount": 24,
                    "retweetCount": 5,
                    "replyCount": 3,
                    "quoteCount": 1,
                }
            ],
            "has_next_page": False,
            "next_cursor": None,
        }

    if path.startswith("/x/users/") and path.endswith("/tweets"):
        user = unquote(path.split("/")[3])
        return {
            "mode": "sample_data",
            "note": note,
            "tweets": [
                {
                    "id": "1900000000000000002",
                    "text": f"{user} shared a product update about API-backed agent tools.",
                    "createdAt": "2026-05-15T08:30:00Z",
                    "author": {
                        "id": "1000000002",
                        "username": user,
                        "name": user,
                        "verified": False,
                    },
                }
            ],
            "has_next_page": False,
            "next_cursor": None,
        }

    if path.startswith("/x/users/"):
        user = unquote(path.split("/")[3])
        return {
            "mode": "sample_data",
            "note": note,
            "id": "1000000002",
            "username": user,
            "name": user,
            "verified": False,
            "description": "Sample profile returned when XQUIK_API_KEY is not set.",
            "followersCount": 1200,
            "followingCount": 180,
        }

    if path == "/x/trends":
        return {
            "mode": "sample_data",
            "note": note,
            "woeid": _int_param(params.get("woeid"), 1),
            "count": _int_param(params.get("count"), 3),
            "trends": [
                {"name": "#AIAgents", "query": "%23AIAgents", "rank": 1},
                {"name": "Agent Framework", "query": "Agent%20Framework", "rank": 2},
                {"name": "Function Tools", "query": "Function%20Tools", "rank": 3},
            ],
        }

    return {"mode": "sample_data", "note": note}


def _get_xquik_json(path: str, params: Mapping[str, object | None]) -> dict[str, Any]:
    """Call Xquik or return local sample data when credentials are absent."""
    api_key = os.environ.get("XQUIK_API_KEY")
    if not api_key:
        return _sample_response(path, params)

    query_string = urlencode(_query_params(params))
    url = f"{XQUIK_BASE_URL}{path}"
    if query_string:
        url = f"{url}?{query_string}"

    request = Request(
        url,
        headers={
            "x-api-key": api_key,
            "xquik-api-contract": XQUIK_API_CONTRACT,
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=XQUIK_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:240]
        raise RuntimeError(f"Xquik request failed with HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Xquik request failed: {exc.reason}") from exc

    return json.loads(body)


async def _get_xquik(path: str, params: Mapping[str, object | None]) -> dict[str, Any]:
    """Run blocking standard-library HTTP I/O outside the event loop."""
    return await asyncio.to_thread(_get_xquik_json, path, params)


def _limit_items(response: dict[str, Any], key: str, max_items: int) -> dict[str, Any]:
    """Limit large result arrays before returning them to the model."""
    items = response.get(key)
    if not isinstance(items, list):
        return response
    return {**response, key: items[:max_items]}


@tool(approval_mode="never_require")
async def search_x_posts(
    query: Annotated[
        str,
        Field(description='X search query, such as "agent framework" or "from:microsoft".'),
    ],
    limit: Annotated[int, Field(ge=1, le=20, description="Maximum posts to return.")] = 5,
    query_type: Annotated[
        str,
        Field(description='Sort order. Use "Latest" for chronological or "Top" for engagement-ranked.'),
    ] = "Latest",
) -> dict[str, Any]:
    """Search public X/Twitter posts with Xquik."""
    if query_type not in {"Latest", "Top"}:
        raise ValueError('query_type must be "Latest" or "Top".')

    return await _get_xquik(
        "/x/tweets/search",
        {"q": query, "limit": limit, "queryType": query_type},
    )


@tool(approval_mode="never_require")
async def get_x_user(
    user: Annotated[
        str,
        Field(description="X username without @, or a numeric X user ID."),
    ],
) -> dict[str, Any]:
    """Get an X/Twitter user profile with follower counts and verification."""
    identifier = quote(user.lstrip("@"), safe="")
    return await _get_xquik(f"/x/users/{identifier}", {})


@tool(approval_mode="never_require")
async def get_x_user_posts(
    user: Annotated[
        str,
        Field(description="X username without @, or a numeric X user ID."),
    ],
    max_posts: Annotated[int, Field(ge=1, le=20, description="Maximum posts to return to the agent.")] = 5,
    include_replies: Annotated[bool, Field(description="Include reply posts in the result.")] = False,
) -> dict[str, Any]:
    """Fetch recent public posts from an X/Twitter user."""
    identifier = quote(user.lstrip("@"), safe="")
    response = await _get_xquik(
        f"/x/users/{identifier}/tweets",
        {"includeReplies": include_replies},
    )
    return _limit_items(response, "tweets", max_posts)


@tool(approval_mode="never_require")
async def get_x_trends(
    woeid: Annotated[
        int,
        Field(description="Yahoo Where On Earth ID. Use 1 for worldwide trends."),
    ] = 1,
    count: Annotated[int, Field(ge=1, le=20, description="Maximum trends to return.")] = 10,
) -> dict[str, Any]:
    """Get trending topics from X/Twitter by region."""
    return await _get_xquik("/x/trends", {"woeid": woeid, "count": count})


async def main() -> None:
    """Run an agent that uses Xquik tools for a short research brief."""
    agent = Agent(
        client=FoundryChatClient(credential=AzureCliCredential()),
        name="XquikResearchAgent",
        instructions=(
            "You help developers research public X/Twitter activity. Use the Xquik tools for "
            "post search, user lookup, user posts, and trends. Mention when a tool result uses "
            "sample data instead of the live API."
        ),
        tools=[search_x_posts, get_x_user, get_x_user_posts, get_x_trends],
    )

    query = (
        "Search recent public posts about agent frameworks, look up microsoft, "
        "check worldwide trends, and return a short research brief with source IDs."
    )
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}")


"""
Sample output:
User: Search recent public posts about agent frameworks, look up microsoft, check worldwide trends,
and return a short research brief with source IDs.
Agent: Xquik returned sample data because XQUIK_API_KEY is not set. The sample post
1900000000000000001 discusses developers wiring agent function tools to live APIs.
The sample microsoft profile and worldwide trends suggest interest in agent frameworks
and function tools. Set XQUIK_API_KEY to run the same tools against the live Xquik API.
"""


if __name__ == "__main__":
    asyncio.run(main())
