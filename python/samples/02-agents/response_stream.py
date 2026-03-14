# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import AsyncIterable, Sequence

from agent_framework import ChatResponse, ChatResponseUpdate, Content, Message, ResponseStream

"""ResponseStream: A Deep Dive

This sample explores the ResponseStream class - a powerful abstraction for working with
streaming responses in the Agent Framework.

=== Why ResponseStream Exists ===

When working with AI models, responses can be delivered in two ways:
1. **Non-streaming**: Wait for the complete response, then return it all at once
2. **Streaming**: Receive incremental updates as they're generated

Streaming provides a better user experience (faster time-to-first-token, progressive rendering)
but introduces complexity:
- How do you process updates as they arrive?
- How do you also get a final, complete response?
- How do you ensure the underlying stream is only consumed once?
- How do you add custom logic (hooks) at different stages?

ResponseStream solves all these problems by wrapping an async iterable and providing:
- Multiple consumption patterns (iteration OR direct finalization)
- Hook points for transformation, cleanup, finalization, and result processing
- The `wrap()` API to layer behavior without double-consuming the stream

=== The Four Hook Types ===

ResponseStream provides four ways to inject custom logic. All can be passed via constructor
or added later via fluent methods:

1. **Transform Hooks** (`transform_hooks=[]` or `.with_transform_hook()`)
   - Called for EACH update as it's yielded during iteration
   - Can transform updates before they're returned to the consumer
   - Multiple hooks are called in order, each receiving the previous hook's output
   - Only triggered during iteration (not when calling get_final_response directly)

2. **Cleanup Hooks** (`cleanup_hooks=[]` or `.with_cleanup_hook()`)
   - Called ONCE when iteration completes (stream fully consumed), BEFORE finalizer
   - Used for cleanup: closing connections, releasing resources, logging
   - Cannot modify the stream or response
   - Triggered regardless of how the stream ends (normal completion or exception)

3. **Finalizer** (`finalizer=` constructor parameter)
   - Called ONCE when `get_final_response()` is invoked
   - Receives the list of collected updates and converts to the final type
   - There is only ONE finalizer per stream (set at construction)

4. **Result Hooks** (`result_hooks=[]` or `.with_result_hook()`)
   - Called ONCE after the finalizer produces its result
   - Transform the final response before returning
   - Multiple result hooks are called in order, each receiving the previous result
   - Can return None to keep the previous value unchanged

=== Two Consumption Patterns ===

**Pattern 1: Async Iteration**
```python
async for update in response_stream:
    print(update.text)  # Process each update
# Stream is now consumed; updates are stored internally
```
- Transform hooks are called for each yielded item
- Cleanup hooks are called after the last item
- The stream collects all updates internally for later finalization
- Does not run the finalizer automatically

**Pattern 2: Direct Finalization**
```python
final = await response_stream.get_final_response()
```
- If the stream hasn't been iterated, it auto-iterates (consuming all updates)
- The finalizer converts collected updates to a final response
- Result hooks transform the response
- You get the complete response without ever seeing individual updates

** Pattern 3: Combined Usage **

When you first iterate the stream and then call `get_final_response()`, the following occurs:
- Iteration yields updates with transform hooks applied
- Cleanup hooks run after iteration completes
- Calling `get_final_response()` uses the already collected updates to produce the final response
- Note that it does not re-iterate the stream since it's already been consumed

```python
async for update in response_stream:
    print(update.text)  # See each update
final = await response_stream.get_final_response()  # Get the aggregated result
```

=== Chaining with .map() and .with_finalizer() ===

When building a Agent on top of a ChatClient, we face a challenge:
- The ChatClient returns a ResponseStream[ChatResponseUpdate, ChatResponse]
- The Agent needs to return a ResponseStream[AgentResponseUpdate, AgentResponse]
- We can't iterate the ChatClient's stream twice!

The `.map()` and `.with_finalizer()` methods solve this by creating new ResponseStreams that:
- Delegate iteration to the inner stream (only consuming it once)
- Maintain their OWN separate transform hooks, result hooks, and cleanup hooks
- Allow type-safe transformation of updates and final responses

**`.map(transform)`**: Creates a new stream that transforms each update.
- Returns a new ResponseStream with the transformed update type
- Falls back to the inner stream's finalizer if no new finalizer is set

**`.with_finalizer(finalizer)`**: Creates a new stream with a different finalizer.
- Returns a new ResponseStream with the new final type
- The inner stream's finalizer and result_hooks ARE still called (see below)

**IMPORTANT**: When chaining these methods via `get_final_response()`:
1. The inner stream's finalizer runs first (on the original updates)
2. The inner stream's result_hooks run (on the inner final result)
3. The outer stream's finalizer runs (on the transformed updates)
4. The outer stream's result_hooks run (on the outer final result)

This ensures that post-processing hooks registered on the inner stream (e.g., context
provider notifications, telemetry, thread updates) are still executed even when the
stream is wrapped/mapped.

```python
# Agent does something like this internally:
chat_stream = client.get_response(messages, stream=True)
agent_stream = (
    chat_stream
    .map(_to_agent_update, _to_agent_response)
    .with_result_hook(_notify_thread)  # Outer hook runs AFTER inner hooks
)
```

This ensures:
- The underlying ChatClient stream is only consumed once
- The agent can add its own transform hooks, result hooks, and cleanup logic
- Each layer (ChatClient, Agent, middleware) can add independent behavior
- Inner stream post-processing (like context provider notification) still runs
- Types flow naturally through the chain
"""


async def main() -> None:
    """Demonstrate the various ResponseStream patterns and capabilities."""

    # =========================================================================
    # Example 1: Basic ResponseStream with iteration
    # =========================================================================
    print("=== Example 1: Basic Iteration ===\n")

    async def generate_updates() -> AsyncIterable[ChatResponseUpdate]:
        """Simulate a streaming response from an AI model."""
        words = ["Hello", " ", "from", " ", "the", " ", "streaming", " ", "response", "!"]
        for word in words:
            await asyncio.sleep(0.05)  # Simulate network delay
            yield ChatResponseUpdate(contents=[Content.from_text(word)], role="assistant")

    def combine_updates(updates: Sequence[ChatResponseUpdate]) -> ChatResponse:
        """Finalizer that combines all updates into a single response."""
        return ChatResponse.from_updates(updates)

    stream = ResponseStream(generate_updates(), finalizer=combine_updates)

    print("Iterating through updates:")
    async for update in stream:
        print(f"  Update: '{update.text}'")

    # After iteration, we can still get the final response
    final = await stream.get_final_response()
    print(f"\nFinal response: '{final.text}'")

    # =========================================================================
    # Example 2: Using get_final_response() without iteration
    # =========================================================================
    print("\n=== Example 2: Direct Finalization (No Iteration) ===\n")

    # Create a fresh stream (streams can only be consumed once)
    stream2 = ResponseStream(generate_updates(), finalizer=combine_updates)

    # Skip iteration entirely - get_final_response() auto-consumes the stream
    final2 = await stream2.get_final_response()
    print(f"Got final response directly: '{final2.text}'")
    print(f"Number of updates collected internally: {len(stream2.updates)}")

    # =========================================================================
    # Example 3: Transform hooks - transform updates during iteration
    # =========================================================================
    print("\n=== Example 3: Transform Hooks ===\n")

    update_count = {"value": 0}

    def counting_hook(update: ChatResponseUpdate) -> ChatResponseUpdate:
        """Hook that counts and annotates each update."""
        update_count["value"] += 1
        # Return the update (or a modified version)
        return update

    def uppercase_hook(update: ChatResponseUpdate) -> ChatResponseUpdate:
        """Hook that converts text to uppercase."""
        if update.text:
            return ChatResponseUpdate(
                contents=[Content.from_text(update.text.upper())], role=update.role, response_id=update.response_id
            )
        return update

    # Pass transform_hooks directly to constructor
    stream3 = ResponseStream(
        generate_updates(),
        finalizer=combine_updates,
        transform_hooks=[counting_hook, uppercase_hook],  # First counts, then uppercases
    )

    print("Iterating with hooks applied:")
    async for update in stream3:
        print(f"  Received: '{update.text}'")  # Will be uppercase

    print(f"\nTotal updates processed: {update_count['value']}")

    # =========================================================================
    # Example 4: Cleanup hooks - cleanup after stream consumption
    # =========================================================================
    print("\n=== Example 4: Cleanup Hooks ===\n")

    cleanup_performed = {"value": False}

    async def cleanup_hook() -> None:
        """Cleanup hook for releasing resources after stream consumption."""
        print("  [Cleanup] Cleaning up resources...")
        cleanup_performed["value"] = True

    # Pass cleanup_hooks directly to constructor
    stream4 = ResponseStream(
        generate_updates(),
        finalizer=combine_updates,
        cleanup_hooks=[cleanup_hook],
    )

    print("Starting iteration (cleanup happens after):")
    async for _update in stream4:
        pass  # Just consume the stream
    print(f"Cleanup was performed: {cleanup_performed['value']}")

    # =========================================================================
    # Example 5: Result hooks - transform the final response
    # =========================================================================
    print("\n=== Example 5: Result Hooks ===\n")

    def add_metadata_hook(response: ChatResponse) -> ChatResponse:
        """Result hook that adds metadata to the response."""
        response.additional_properties["processed"] = True
        response.additional_properties["word_count"] = len((response.text or "").split())
        return response

    def wrap_in_quotes_hook(response: ChatResponse) -> ChatResponse:
        """Result hook that wraps the response text in quotes."""
        if response.text:
            return ChatResponse(
                messages=[Message(text=f'"{response.text}"', role="assistant")],
                additional_properties=response.additional_properties,
            )
        return response

    # Finalizer converts updates to response, then result hooks transform it
    stream5 = ResponseStream(
        generate_updates(),
        finalizer=combine_updates,
        result_hooks=[add_metadata_hook, wrap_in_quotes_hook],  # First adds metadata, then wraps in quotes
    )

    final5 = await stream5.get_final_response()
    print(f"Final text: {final5.text}")
    print(f"Metadata: {final5.additional_properties}")

    # =========================================================================
    # Example 6: The wrap() API - layering without double-consumption
    # =========================================================================
    print("\n=== Example 6: wrap() API for Layering ===\n")

    # Simulate what ChatClient returns
    inner_stream = ResponseStream(generate_updates(), finalizer=combine_updates)

    # Simulate what Agent does: wrap the inner stream
    def to_agent_format(update: ChatResponseUpdate) -> ChatResponseUpdate:
        """Map ChatResponseUpdate to agent format (simulated transformation)."""
        # In real code, this would convert to AgentResponseUpdate
        return ChatResponseUpdate(
            contents=[Content.from_text(f"[AGENT] {update.text}")], role=update.role, response_id=update.response_id
        )

    def to_agent_response(updates: Sequence[ChatResponseUpdate]) -> ChatResponse:
        """Finalizer that converts updates to agent response (simulated)."""
        # In real code, this would create an AgentResponse
        text = "".join(u.text or "" for u in updates)
        return ChatResponse(
            messages=[Message(text=f"[AGENT FINAL] {text}", role="assistant")],
            additional_properties={"layer": "agent"},
        )

    # .map() creates a new stream that:
    # 1. Delegates iteration to inner_stream (only consuming it once)
    # 2. Transforms each update via the transform function
    # 3. Uses the provided finalizer (required since update type may change)
    outer_stream = inner_stream.map(to_agent_format, to_agent_response)

    print("Iterating the mapped stream:")
    async for update in outer_stream:
        print(f"  {update.text}")

    final_outer = await outer_stream.get_final_response()
    print(f"\nMapped final: {final_outer.text}")
    print(f"Mapped metadata: {final_outer.additional_properties}")

    # Important: the inner stream was only consumed once!
    print(f"Inner stream consumed: {inner_stream._consumed}")

    # =========================================================================
    # Example 7: Combining all patterns
    # =========================================================================
    print("\n=== Example 7: Full Integration ===\n")

    stats = {"updates": 0, "characters": 0}

    def track_stats(update: ChatResponseUpdate) -> ChatResponseUpdate:
        """Track statistics as updates flow through."""
        stats["updates"] += 1
        stats["characters"] += len(update.text or "")
        return update

    def log_cleanup() -> None:
        """Log when stream consumption completes."""
        print(f"  [Cleanup] Stream complete: {stats['updates']} updates, {stats['characters']} chars")

    def add_stats_to_response(response: ChatResponse) -> ChatResponse:
        """Result hook to include the statistics in the final response."""
        response.additional_properties["stats"] = stats.copy()
        return response

    # All hooks can be passed via constructor
    full_stream = ResponseStream(
        generate_updates(),
        finalizer=combine_updates,
        transform_hooks=[track_stats],
        result_hooks=[add_stats_to_response],
        cleanup_hooks=[log_cleanup],
    )

    print("Processing with all hooks active:")
    async for update in full_stream:
        print(f"  -> '{update.text}'")

    final_full = await full_stream.get_final_response()
    print(f"\nFinal: '{final_full.text}'")
    print(f"Stats: {final_full.additional_properties['stats']}")


if __name__ == "__main__":
    asyncio.run(main())
