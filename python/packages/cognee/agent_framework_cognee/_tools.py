# Copyright (c) Microsoft. All rights reserved.

import asyncio
import uuid
from typing import Annotated, Any

import cognee
from agent_framework import AIFunction, ai_function
from cognee.modules.engine.models import NodeSet

_add_lock = asyncio.Lock()
_add_queue: asyncio.Queue[tuple[tuple[Any, ...], dict[str, Any]]] = asyncio.Queue()


async def _enqueue_add(*args: Any, **kwargs: Any) -> None:
    """Queue-based batching for cognee add operations.

    Uses a lock to batch multiple add operations together before calling cognify.
    This prevents race conditions during database initialization and improves performance.
    """
    global _add_lock
    if _add_lock.locked():
        await _add_queue.put((args, kwargs))
        return
    async with _add_lock:
        await _add_queue.put((args, kwargs))
        while True:
            try:
                next_args, next_kwargs = await asyncio.wait_for(_add_queue.get(), timeout=2)
                _add_queue.task_done()
            except asyncio.TimeoutError:
                break
            await cognee.add(*next_args, **next_kwargs)  # type: ignore[reportUnknownMemberType]
        await cognee.cognify()  # type: ignore[reportUnknownMemberType]


async def _cognee_add_impl(
    data: str,
    node_set: list[str] | None = None,
) -> str:
    """Internal implementation of cognee_add."""
    await _enqueue_add(data, node_set=node_set)
    return "Item added to cognee and processed"


async def _cognee_search_impl(
    query_text: str,
    node_name: list[str] | None = None,
) -> list[Any]:
    """Internal implementation of cognee_search."""
    await _add_queue.join()
    return await cognee.search(query_text, node_type=NodeSet, node_name=node_name, top_k=100)  # type: ignore[no-any-return]


@ai_function
async def cognee_add(
    data: Annotated[str, "The text or information to store in the knowledge base"],
    node_set: Annotated[list[str] | None, "Session identifiers for scoping"] = None,
) -> str:
    """Store information in the knowledge base for later retrieval.

    Use this tool whenever you need to remember, store, or save information.
    This is essential for building up a knowledge base that can be searched later.

    Args:
        data: The text or information to store and remember.
        node_set: Optional session identifiers for scoping the data.

    Returns:
        A confirmation message indicating that the item was added.
    """
    return await _cognee_add_impl(data, node_set)


@ai_function
async def cognee_search(
    query_text: Annotated[str, "Natural language search query"],
    node_name: Annotated[list[str] | None, "Node names to filter results"] = None,
) -> list[Any]:
    """Search and retrieve previously stored information from the knowledge base.

    Use this tool to find and recall information that was previously stored.

    Args:
        query_text: What you're looking for, as a natural language query.
        node_name: Optional node names to filter search results.

    Returns:
        A list of search results matching the query.
    """
    return await _cognee_search_impl(query_text, node_name)


def get_cognee_tools(session_id: str | None = None) -> tuple[AIFunction[Any, Any], AIFunction[Any, Any]]:
    """Get cognee tools scoped to a session.

    Returns sessionized versions of cognee_add and cognee_search that automatically
    scope all operations to the specified session ID.

    Args:
        session_id: Session identifier for data isolation. If not provided,
            a unique session ID will be generated.

    Returns:
        A tuple of (cognee_add, cognee_search) AIFunction instances scoped to the session.

    Example:
        ```python
        add_tool, search_tool = get_cognee_tools("user-123")
        agent = ChatAgent(client, tools=[add_tool, search_tool])
        ```
    """
    if session_id is None:
        session_id = f"session-{uuid.uuid4()}"

    @ai_function(name="cognee_add", description="Store information in the knowledge base.")
    async def sessionized_add(
        data: Annotated[str, "The text or information to store"],
    ) -> str:
        """Store information in the knowledge base for this session."""
        return await _cognee_add_impl(data, node_set=[session_id])

    @ai_function(name="cognee_search", description="Search the knowledge base.")
    async def sessionized_search(
        query_text: Annotated[str, "Natural language search query"],
    ) -> list[Any]:
        """Search for information in this session's knowledge base."""
        return await _cognee_search_impl(query_text, node_name=[session_id])

    return sessionized_add, sessionized_search
