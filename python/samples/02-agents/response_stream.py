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
- How do you transform or block content at defined stages?
- How do you hold all updates until a final result is approved?

ResponseStream solves all these problems by wrapping an async iterable and providing:
- Multiple consumption patterns (iteration OR direct finalization)
- Ordered gates (checks that return `None` to allow a value or raise to block it) and transforms
- Live or buffered update release
- Cleanup, finalization, and mapping without double-consuming the stream

=== The Content Pipeline ===

Each update follows this pipeline:

```text
source update
  -> before-transform update gates
  -> update transforms
  -> after-transform update gates
  -> stream immediately or buffer
```

Updates stream immediately by default. Set `stream_updates=False` in the
constructor, or call `.buffer_updates()` on an existing stream, to hold every
update until finalization and all configured gates have passed.

The final result follows a matching pipeline:

```text
finalizer
  -> before-transform result gates
  -> result transforms
  -> after-transform result gates
```

The complete lifecycle is:

1. **Pull a source update.**
2. **Run before-transform update gates** from
   `update_gates={"before_transform": [...]}`.
3. **Apply update transforms** from `update_transforms=[]` or
   `.with_update_transform()`, in registration order. A transform returns a
   replacement update, or `None` to keep the current update.
4. **Run after-transform update gates** from
   `update_gates={"after_transform": [...]}`. A gate can block a transformed
   update even when buffered mode will hold rather than immediately emit it.
5. **Emit or hold the transformed update.**
   - Live mode emits it immediately after step 4 passes.
   - Buffered mode holds it until the final result has passed its complete pipeline.
6. **Repeat steps 1-5** until the source is exhausted.
7. **Run cleanup hooks** from `cleanup_hooks=[]` or `.with_cleanup_hook()`.
8. **Run the finalizer** supplied through `finalizer=` over the collected source
   updates.
9. **Run before-transform result gates** from
   `result_gates={"before_transform": [...]}`.
10. **Apply result transforms** from `result_transforms=[]` or
   `.with_result_transform()`, in registration order. A transform returns a
   replacement result, or `None` to keep the current result.
11. **Run after-transform result gates** from
    `result_gates={"after_transform": [...]}`.
12. **Gate and emit buffered updates.** If a result transform returned a
    replacement, `result_to_updates` creates the updates to release. ResponseStream
    runs every after-transform update gate against those replacement updates before
    emitting the first one.

The older `transform_hooks`, `result_hooks`, `.with_transform_hook()`, and
`.with_result_hook()` names remain compatible aliases.

Middleware should register stream transforms, gates, buffering, and conversion
on its `AgentContext` or `ChatContext` before calling `call_next()`. The
middleware pipeline applies that configuration to the eventual ResponseStream
after the chain unwinds, in unwind order: inner middleware post-processing runs
before outer middleware post-processing. Use the fluent ResponseStream helpers
when code outside middleware already owns a concrete stream.

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
- The stream finalizes automatically when iteration reaches the end

**Pattern 2: Direct Finalization**
```python
final = await response_stream.get_final_response()
```
- If the stream hasn't been iterated, it auto-iterates (consuming all updates)
- The finalizer converts collected updates to a final response
- Update and result pipelines run normally
- You get the complete response without ever seeing individual updates

** Pattern 3: Combined Usage **
```python
async for update in response_stream:
    print(update.text)  # See each update
final = await response_stream.get_final_response()  # Get the aggregated result
```
When you first iterate the stream and then call `get_final_response()`, the following occurs:
- Iteration yields updates with transform hooks applied
- Cleanup hooks run after iteration completes
- Calling `get_final_response()` uses the already collected updates to produce the final response
- Note that it does not re-iterate the stream since it's already been consumed

=== Chaining with .map(), .flat_map(), and .with_finalizer() ===

When building an Agent on top of a ChatClient, we face a challenge:
- The ChatClient returns a ResponseStream[ChatResponseUpdate, ChatResponse]
- The Agent needs to return a ResponseStream[AgentResponseUpdate, AgentResponse]
- We can't iterate the ChatClient's stream twice!

The mapping and finalizer methods solve this by creating new ResponseStreams that:
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
    # Example 3: Update transforms - transform updates during iteration
    # =========================================================================
    print("\n=== Example 3: Update Transforms ===\n")

    update_count = {"value": 0}

    def counting_transform(update: ChatResponseUpdate) -> ChatResponseUpdate:
        """Transform that counts each update without replacing it."""
        update_count["value"] += 1
        return update

    def uppercase_transform(update: ChatResponseUpdate) -> ChatResponseUpdate:
        """Transform that converts text to uppercase."""
        if update.text:
            return ChatResponseUpdate(
                contents=[Content.from_text(update.text.upper())], role=None, response_id=update.response_id
            )
        return update

    # Pass update transforms directly to the constructor.
    stream3: ResponseStream[ChatResponseUpdate, ChatResponse] = ResponseStream(
        generate_updates(),
        finalizer=combine_updates,
        update_transforms=[counting_transform, uppercase_transform],
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
    async for update in stream4:
        print(f"  Received: '{update.text}'")
    print(f"Cleanup was performed: {cleanup_performed['value']}")

    # =========================================================================
    # Example 5: Result transforms - transform the final response
    # =========================================================================
    print("\n=== Example 5: Result Transforms ===\n")

    def add_metadata_transform(response: ChatResponse) -> ChatResponse:
        """Result transform that adds metadata to the response."""
        response.additional_properties["processed"] = True
        response.additional_properties["word_count"] = len((response.text or "").split())
        return response

    def wrap_in_quotes_transform(response: ChatResponse) -> ChatResponse:
        """Result transform that wraps the response text in quotes."""
        if response.text:
            return ChatResponse(
                messages=[Message(contents=[f'"{response.text}"'], role="assistant")],
                additional_properties=response.additional_properties,
            )
        return response

    # The finalizer creates a response, then result transforms run in order.
    stream5: ResponseStream[ChatResponseUpdate, ChatResponse] = ResponseStream(
        generate_updates(),
        finalizer=combine_updates,
        result_transforms=[add_metadata_transform, wrap_in_quotes_transform],
    )

    final5 = await stream5.get_final_response()
    print(f"Final text: {final5.text}")
    print(f"Metadata: {final5.additional_properties}")

    # =========================================================================
    # Example 6: Gates before and after transforms
    # =========================================================================
    print("\n=== Example 6: Gates Around Transforms ===\n")

    async def generate_policy_updates() -> AsyncIterable[ChatResponseUpdate]:
        """Produce content that must be transformed before egress."""
        for text in ("Public content. ", "Internal secret."):
            await asyncio.sleep(0.05)
            yield ChatResponseUpdate(contents=[Content.from_text(text)], role="assistant")

    def inspect_source_update(update: ChatResponseUpdate) -> None:
        """A before-transform gate can inspect the provider's original update."""
        print(f"  [Before gate] Saw: '{update.text}'")

    def redact_update(update: ChatResponseUpdate) -> ChatResponseUpdate:
        """Transforms own all content replacement."""
        text = (update.text or "").replace("Internal secret", "[redacted]")
        return ChatResponseUpdate(contents=[Content.from_text(text)], role="assistant")

    def require_safe_update(update: ChatResponseUpdate) -> None:
        """An after-transform gate blocks if unsafe content would egress."""
        if "secret" in (update.text or "").lower():
            raise RuntimeError("Unsafe update was not redacted.")

    def redact_result(response: ChatResponse) -> ChatResponse:
        """Apply the corresponding replacement to the finalized response."""
        text = (response.text or "").replace("Internal secret", "[redacted]")
        return ChatResponse(messages=[Message(role="assistant", contents=[text])])

    def require_safe_result(response: ChatResponse) -> None:
        """Validate the final result after its transforms."""
        if "secret" in (response.text or "").lower():
            raise RuntimeError("Unsafe final result was not redacted.")

    gated_stream: ResponseStream[ChatResponseUpdate, ChatResponse] = ResponseStream(
        generate_policy_updates(),
        finalizer=combine_updates,
        update_gates={
            "before_transform": [inspect_source_update],
            "after_transform": [require_safe_update],
        },
        update_transforms=[redact_update],
        result_gates={"after_transform": [require_safe_result]},
        result_transforms=[redact_result],
    )

    print("Released updates:")
    async for update in gated_stream:
        print(f"  -> '{update.text}'")
    print(f"Final result: '{(await gated_stream.get_final_response()).text}'")

    # =========================================================================
    # Example 7: Buffer updates so a final-result replacement controls egress
    # =========================================================================
    print("\n=== Example 7: Buffered Final Replacement ===\n")

    def log_original_result(response: ChatResponse) -> None:
        """A before-transform result gate sees the original finalized response."""
        print(f"  [Before result gate] Original: '{response.text}'")

    def replace_result(_: ChatResponse) -> ChatResponse:
        """Return a completely different final response."""
        return ChatResponse(messages=[Message(role="assistant", contents=["Approved replacement response."])])

    def response_to_updates(response: ChatResponse) -> Sequence[ChatResponseUpdate]:
        """Convert a replacement final result back into updates for buffered release."""
        return [ChatResponseUpdate(contents=list(message.contents), role="assistant") for message in response.messages]

    buffered_stream: ResponseStream[ChatResponseUpdate, ChatResponse] = ResponseStream(
        generate_policy_updates(),
        finalizer=combine_updates,
    )

    # Fluent methods are convenient when middleware or another layer receives an
    # existing ResponseStream rather than constructing it itself.
    (
        buffered_stream
        .with_result_gate(log_original_result, phase="before_transform")
        .with_result_transform(replace_result)
        .with_result_gate(require_safe_result, phase="after_transform")
        .with_update_transform(redact_update)
        .with_update_gate(require_safe_update, phase="after_transform")
        .buffer_updates(result_to_updates=response_to_updates)
    )

    print("The source is fully consumed and the replacement is approved before the first update is released:")
    async for update in buffered_stream:
        print(f"  -> '{update.text}'")
    print(f"Final replacement: '{(await buffered_stream.get_final_response()).text}'")

    # =========================================================================
    # Example 8: Mapping - layering without double-consumption
    # =========================================================================
    print("\n=== Example 8: Mapping for Layering ===\n")

    # Simulate what ChatClient returns
    inner_stream = ResponseStream(generate_updates(), finalizer=combine_updates)

    # Simulate what Agent does: wrap the inner stream
    def to_agent_format(update: ChatResponseUpdate) -> ChatResponseUpdate:
        """Map ChatResponseUpdate to agent format (simulated transformation)."""
        # In real code, this would convert to AgentResponseUpdate
        return ChatResponseUpdate(
            contents=[Content.from_text(f"[AGENT] {update.text}")], role=None, response_id=update.response_id
        )

    def to_agent_response(updates: Sequence[ChatResponseUpdate]) -> ChatResponse:
        """Finalizer that converts updates to agent response (simulated)."""
        # In real code, this would create an AgentResponse
        text = "".join(u.text or "" for u in updates)
        return ChatResponse(
            messages=[Message(contents=[f"[AGENT FINAL] {text}"], role="assistant")],
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
    # Example 9: Combining lifecycle patterns
    # =========================================================================
    print("\n=== Example 9: Lifecycle Integration ===\n")

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
        """Result transform that includes statistics in the final response."""
        response.additional_properties["stats"] = stats.copy()
        return response

    # Transforms and cleanup hooks can be assembled together in the constructor.
    full_stream: ResponseStream[ChatResponseUpdate, ChatResponse] = ResponseStream(
        generate_updates(),
        finalizer=combine_updates,
        update_transforms=[track_stats],
        result_transforms=[add_stats_to_response],
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

# Expected output includes:
# === Example 6: Gates Around Transforms ===
# Released updates:
#   [Before gate] Saw: 'Public content. '
#   -> 'Public content. '
#   [Before gate] Saw: 'Internal secret.'
#   -> '[redacted].'
# Final result: 'Public content. [redacted].'
#
# === Example 7: Buffered Final Replacement ===
# The source is fully consumed and the replacement is approved before the first update is released:
#   [Before result gate] Original: 'Public content. Internal secret.'
#   -> 'Approved replacement response.'
# Final replacement: 'Approved replacement response.'
