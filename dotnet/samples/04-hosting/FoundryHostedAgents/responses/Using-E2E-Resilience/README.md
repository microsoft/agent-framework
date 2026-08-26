# Using-E2E-Resilience

A self-contained local E2E demonstration for
[`Hosted-Workflow-Resilient-Long-Running`](../Hosted-Workflow-Resilient-Long-Running/).
It owns both server process lifetimes, consumes their response stream, and prints every countdown
output in one console.

The E2E creates a MAF client agent through `AIProjectClient.AsAIAgent(model, instructions)`. It
enables `AgentRunOptions.AllowBackgroundResponses`, consumes `AgentResponseUpdate` values, saves the
latest non-null `ResponseContinuationToken`, and supplies that token after the replacement server
starts. It does not implement the Responses HTTP or SSE protocol itself.

The demonstration uses one MAF client agent and one agent session for three calls:

1. Starts the hosted workflow server as a child process.
2. Creates a stored background streaming response through the MAF agent.
3. Prints countdown messages as MAF streaming updates arrive.
4. Waits until the matching workflow and response checkpoint is durable.
5. Force-kills the server process tree.
6. Starts a replacement server over the same AgentServer state.
7. The second call reconnects with the sequence-aware continuation token and prints only newly
   recovered messages.
8. The third call uses the same agent and session with the same response ID but no sequence cursor,
   replaying the entire stream from the start.
9. The E2E verifies that the client accumulator and cursor-free replay contain the same complete
   countdown.

## Run

Run from the repository root:

```powershell
dotnet run --project dotnet\samples\04-hosting\FoundryHostedAgents\responses\Using-E2E-Resilience
```

The E2E program starts the first server, ends it abruptly, starts the replacement server with the
same durable state, and ends the replacement when the verification completes. A separately running
local server may remain open: the E2E uses a random port, isolated Debug binaries, and an isolated
AgentServer state directory.

No Azure project, model deployment, credentials, or second terminal is required.
The E2E builds the server in Debug into an isolated temporary directory, so it does not reuse or
overwrite the binaries of a separately running local server.

`AIProjectClient` requires an HTTPS endpoint before its bearer-token policy will run. The shared
`LocalHttpSchemeRewriteHandler` presents HTTPS to that pipeline, then routes the request to the
random loopback HTTP port at transport time. The handler rejects non-loopback targets.

Example:

```text
[1/7] Starting the first server process...
[2/7] Starting the background countdown...
      before    > 20
      before    > 19
      before    > 18
...
[4/7] Force-killing the first server process...
[5/7] Starting a replacement server over the same durable state...
[6/7] Reconnecting to the response stream...
      recovered > 10
      recovered > 9
...
      recovered > Countdown complete.

[7/7] Replaying from the start without a sequence cursor...
      replayed  > 20
      replayed  > 19
...
      replayed  > Countdown complete.

Client retained countdown updates: 20
Replay countdown updates:          20

PASS: crash recovery completed with ordered output and no missing or duplicated items.
```

## Options

```powershell
dotnet run --project dotnet\samples\04-hosting\FoundryHostedAgents\responses\Using-E2E-Resilience -- `
    --target 30 `
    --crash-after-count 12 `
    --delay-seconds 1
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--target` | `20` | First countdown value. Must be at least 2. |
| `--crash-after-count` | Half the target | Number of completed countdown messages before the crash. |
| `--delay-seconds` | `1` | Delay between countdown steps. |

Server output is redirected to a temporary log whose path is printed at startup. Each run uses a
random local port and an isolated AgentServer state directory. Successful runs delete their durable
state. Failed runs retain state and print its path for investigation.

The second call's continuation token resumes after the last update consumed before the crash.
Previously consumed countdown messages are retained in the client accumulator and are not streamed
again. Only work after the durable checkpoint appears as `recovered`.

For the third call, the E2E derives another valid `ChatClientAgent` continuation token whose inner
Responses token contains the same response ID without a sequence number. That call prints every
persisted stream item as `replayed`.
