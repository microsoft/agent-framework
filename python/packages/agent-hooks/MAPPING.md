# Mapping AGENT-HOOKS-0.1 onto Agent Framework middleware

[AGENT-HOOKS-0.1](https://github.com/responsibleai/agent-hooks) defines
eight interception points a host emits around the agent loop, a
three-verdict control contract (`allow` / `deny`, optionally liftable
by an approval seam / `transform`), and fail-closed host obligations.
This package implements that contract on Agent Framework's Python
middleware pipeline.

## Seam mapping

| Interception point | Agent Framework seam | Fit |
| --- | --- | --- |
| `agent_startup` | `AgentMiddleware.process`, before `call_next` | Synthesized: emitted at run start; the run is the session (below) |
| `input` | `AgentMiddleware.process`, before `call_next` (`context.messages`) | Clean |
| `pre_model_call` | `ChatMiddleware.process`, before `call_next` (`context.messages`, `context.options`) | Clean |
| `post_model_call` | `ChatMiddleware.process`, after `call_next` (`context.result`) | Clean (non-streaming) |
| `pre_tool_call` | `FunctionMiddleware.process`, before `call_next` (`context.function`, `context.arguments`) | Clean |
| `post_tool_call` | `FunctionMiddleware.process`, after `call_next` (`context.result`) | Clean |
| `output` | `AgentMiddleware.process`, after `call_next` (`context.result`) | Clean (non-streaming) |
| `agent_shutdown` | `AgentMiddleware.process`, `finally` | Synthesized: emitted at run end with `completed` / `error` |

**Session scope.** Agent Framework middleware wraps *invocations*, not
agent lifecycle: there is no construction/disposal seam. This adapter
therefore scopes one agent-hooks session to one agent run —
`agent_startup` and `agent_shutdown` bracket the run, and `session.id`
is a per-run identifier. Multi-turn state above the run (an
`AgentSession`) has no middleware seam today; a session-scoped bracket
would need a small upstream seam (agent-level `on_session_open/close`
or middleware around `AgentSession`).

**Control semantics.** A block verdict maps to
`MiddlewareTermination`, the framework's documented early-termination
mechanism; the deny reason travels in the exception message and the
interception record. For post-action points (`post_model_call`,
`post_tool_call`, `output`) the adapter clears `context.result` before
terminating, matching the spec's discard-the-result obligation.
Transforms write back through the context (`context.arguments` for
tool calls), so the framework executes exactly the value the
interceptors approved.

**Fail-closed.** Errors inside the emitter, an interceptor, or this
adapter's own marshalling terminate the run; they never fall through
to execution. This is the inverse of observe-only callback surfaces
that log and continue.

## Known gaps (documented, not hidden)

1. **Streaming runs.** For `context.stream == True`, `output` and
   `post_model_call` content is not available until the stream is
   consumed. The adapter enforces all pre-action points on streaming
   runs but does not currently buffer streams to enforce post-action
   points; a finalizer-hook integration (`stream_result_hooks`) is the
   natural follow-up. The spec's `buffered_output: false` declaration
   covers this honestly in a conformance claim.
2. **Session-scoped brackets** (above).
3. **`post_model_call` tool-call extraction** is best-effort across
   client result shapes; unrecognized shapes degrade to an empty
   `tool_calls` list rather than failing the run.
