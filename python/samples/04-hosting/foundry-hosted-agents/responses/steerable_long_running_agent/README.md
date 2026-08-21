# What this sample demonstrates

A steerable multi-turn [Agent Framework](https://github.com/microsoft/agent-framework) agent hosted using the
**Responses protocol**. The agent is asked to count down from a target number, pacing its own output with a short
remark before each number so a real response takes a while to fully generate. With `steerable_conversations=True`,
sending a new turn on the same conversation while the countdown is still streaming **cancels the in-progress turn**
and drains the new turn next.

Steering is only supported for non-workflow agents. Steering a workflow is conceptually undefined: a workflow's
graph may have loops or parallel branches with no single well-defined "current point" to cancel and resume from,
unlike an agent's strictly linear execution. `ResponsesHostServer` rejects `steerable_conversations=True` for a
workflow agent with `RuntimeError`.

## How It Works

### Agent

The agent (see [main.py](main.py)) is a single `Agent` backed by `FoundryChatClient`, with no workflow and no custom
agent class. Its instructions ask it to count down one integer per line, prefacing each with a brief remark, so a
real streamed generation takes long enough for a second turn to arrive mid-stream. Compared to the
[Basic](../basic/) sample, the only differences are the instructions and passing
`ResponsesServerOptions(steerable_conversations=True)` -- steering needs no special agent-side code.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) `ResponsesHostServer`.
Setting `steerable_conversations=True` in `ResponsesServerOptions` lets a new turn on the same conversation chain
preempt a still-running one:

- The framework signals the in-progress turn's handler via the 3rd positional `cancellation_signal` argument.
- The handler (here, the Agent Framework agent-hosting layer) checks that signal between streamed model updates and
  winds the turn down promptly, letting it complete with whatever partial output it had already produced.
- The new turn is then drained with `context.is_steered_turn == True` and `context.pending_input_count` reflecting
  how many further turns are still queued behind it.
- **A single, linear chain**: every turn after the first must reference the immediately preceding turn's `id` via
  `previous_response_id`, and a `previous_response_id` that doesn't point at the latest turn is rejected with HTTP
  409 (`conversation_fork_not_supported`). Chain identity in turn also depends on session continuity: without an
  explicit `conversation`, the server derives a session id per request, and it's only deterministic across turns
  when a client forwards the `x-agent-session-id` header from a prior response back as `agent_session_id` on the
  next one (see the `curl` walkthrough below) -- otherwise a later turn resolves to a different session and starts
  a brand new response instead of steering the earlier one. Sending the same explicit `conversation` value on every
  turn sidesteps this entirely: it makes the derived session id (and the chain itself) a deterministic function of
  that id, so no header needs to be echoed back, and `previous_response_id` becomes unnecessary for continuity.

## Running the Agent Host

Follow the instructions in the [Running the Agent Host Locally](../../README.md#running-the-agent-host-locally) section
of the README in the parent directory to run the agent host.

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or
> `azd`. Please refer to the [parent README](../../README.md) for more details. Use this README for sample queries you
> can send to the agent.

Start a long background countdown and note the response `id` from the JSON body and the `x-agent-session-id`
response header:

```bash
curl -i -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "Count down from 30, slowly and with commentary.", "store": true, "background": true}'
```

While it is still generating, send a second turn on the same conversation with `previous_response_id` set to steer
it to a new target. Without an explicit `conversation_id`, also forward the `x-agent-session-id` value from the
first response as `agent_session_id` -- otherwise this turn resolves to a different session and starts a brand new
response instead of steering the first one:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "Actually, count down from 3 instead.", "store": true, "background": true, "previous_response_id": "REPLACE_WITH_FIRST_RESPONSE_ID", "agent_session_id": "REPLACE_WITH_X-AGENT-SESSION-ID_HEADER"}'
```

This second request returns immediately with `"status": "queued"`. Polling the *first* response's id will show it
completed early, with fewer tokens than a full 30-count run. Polling the *second* response's id will show a fresh
countdown from 3.

Alternatively, send an explicit `conversation` id on every turn instead of forwarding `x-agent-session-id`. This is
simpler and also works without `previous_response_id` at all, since the `conversation` id alone identifies the chain:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "Count down from 30, slowly and with commentary.", "store": true, "background": true, "conversation": "my-conversation-id"}'

curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "Actually, count down from 3 instead.", "store": true, "background": true, "conversation": "my-conversation-id"}'
```

## Testing steering

[verify_steering.py](verify_steering.py) runs the whole scenario end to end: it starts the server, kicks off a
background streaming countdown, waits for it to stream a minimum number of tokens, sends a second turn with a new
target via `previous_response_id`, and asserts that the second turn is accepted immediately as `"queued"`, that the
first turn completes early, and that the second (steered) turn's output contains the new target's countdown in
order. Because this sample calls a real model, the assertions here are intentionally loose rather than an exact
output match.

```bash
python verify_steering.py --first-target 30 --second-target 3
```

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the
[Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent
directory.
