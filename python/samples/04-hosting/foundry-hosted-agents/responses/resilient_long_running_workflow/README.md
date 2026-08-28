# What this sample demonstrates

A long-running, crash-resilient [Agent Framework](https://github.com/microsoft/agent-framework) workflow
hosted using the **Responses protocol**. The workflow extracts a target number from the user's message and
then counts down from it one step per second, demonstrating how `resilient_background=True` lets a
background response survive a hard crash of the server process and resume from its last checkpoint instead
of restarting from scratch.

## How It Works

### Workflow

The workflow has three executors (see [main.py](main.py)):

- **`StartExecutor`** uses a `FoundryChatClient`-backed agent to extract a positive integer target from the
  user's message. If no valid target is found, the workflow yields an error message instead of counting down.
- **`CountdownExecutor`** decrements the target through a self-loop, sleeping for a second and yielding an
  output on each tick, to simulate a long-running operation.
- **`complete`** yields the workflow's final `"Countdown complete."` output once the countdown reaches zero.

### Agent Hosting

The workflow is hosted as an agent using the [Agent Framework](https://github.com/microsoft/agent-framework)
`ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.
Setting `resilient_background=True` in `ResponsesServerOptions` enables the framework to checkpoint the
workflow's progress and durably persist streamed output, so a background response can be recovered and
resumed after a crash (see "Testing resiliency" below).

## Running the Agent Host

Follow the instructions in the [Running the Agent Host Locally](../../README.md#running-the-agent-host-locally) section of the README in the parent directory to run the agent host.

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. Please refer to the [parent README](../../README.md) for more details. Use this README for sample queries you can send to the agent.

Send a POST request to the server with a JSON body containing an `"input"` field with a positive integer target to count down from. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Count down from 5"}'
```

The server will respond with a JSON object containing the response output (one item per countdown step) and a response ID. You can use this response ID to continue the conversation in subsequent requests.


## Testing resiliency (crash recovery)

This sample enables `resilient_background=True`, so a long-running countdown survives a hard crash of the
server process and resumes from its last checkpoint instead of restarting from scratch. Locally, the
server persists responses, streams, and checkpoints under `${AGENTSERVER_STATE_ROOT:-~/.agentserver}/`, so
this state survives a process restart as long as you run from the same working directory.

On startup, the server's task manager scans that persisted state for any tasks that were still in flight
when the process died and automatically reclaims and resumes each one from its last checkpoint -- this
happens for every incomplete resilient background response, not just the one a client happens to reconnect
to. This is why a stale response from an earlier run can still be found "recovering" in the server logs
long after you've moved on to a new test: every restart re-triggers the same scan, so the stale task keeps
getting resumed until it either reaches a terminal state or the persisted state directory is cleared (as
`verify_resiliency.py` does).

### Automated

[verify_resiliency.py](verify_resiliency.py) runs the whole scenario end to end: it clears any leftover
`${AGENTSERVER_STATE_ROOT:-~/.agentserver}` state from a previous run, starts the server, kicks off a
background+streaming countdown, force-kills the server once half the countdown has completed, restarts the
server, and asserts the recovered response completes with the exact expected output (no lost or duplicated
steps). Progress is printed as each countdown item completes, both before and after the crash, by reading
the response's own `stream=true` SSE feed -- a plain (non-streaming) `GET` only ever reflects the response's
initial or terminal snapshot, never anything in between.

```bash
python verify_resiliency.py --target 20
```

### Manual

To exercise crash recovery by hand:

1. Start the server, then kick off a long background+streaming countdown and note the response `id` from the
   first `response.created` event:

   ```bash
   curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
     -d '{"input": "Count down from 200", "stream": true, "store": true, "background": true}'
   ```

2. While the countdown is still running, kill the server process abruptly — use `kill -9 <pid>`
   (`Stop-Process -Id <pid> -Force` on Windows), not `Ctrl+C`. A `Ctrl+C` triggers a graceful shutdown, which
   is handled differently than a crash; a hard kill is required to exercise crash recovery. The sample server
   prints its PID (`PID: <pid>`) on startup so you don't need to look it up separately.

3. Restart the server (`python main.py`) from the same working directory.

4. Reconnect to the response to observe recovery:

   ```bash
   curl "http://localhost:8088/responses/REPLACE_WITH_RESPONSE_ID?stream=true"
   ```

   The recovered stream emits a fresh `response.in_progress` event first, then resumes the countdown from
   where it left off — the output already produced before the crash is neither lost nor duplicated.
   Alternatively, poll `GET /responses/REPLACE_WITH_RESPONSE_ID` (without `stream`) until `status` is
   `completed` and inspect the `output` array for a contiguous, non-duplicated sequence.

> **Windows note:** the local stream store falls back to a plain lock *file* (no `fcntl`), which isn't
> cleaned up when the process is force-killed. If restart fails with `another process holds the lock-file
> on ...jsonl`, delete the stale `<response-id>.jsonl.lock` file under
> `%USERPROFILE%\.agentserver\streams\` before restarting the server.

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent directory.
