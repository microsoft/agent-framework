## Microsoft Agent Framework – ATR Integration (Python)

`agent-framework-atr` adds deterministic [Agent Threat Rules (ATR)](https://github.com/Agent-Threat-Rule/agent-threat-rules) validation to the Microsoft Agent Framework. It lets you block malicious tool calls and user inputs using an open, MIT-licensed detection ruleset for AI-agent threats — prompt injection, tool-argument tampering, credential exfiltration, and more.

> Status: **Preview**

ATR is an independent, open standard. This package is a thin integration that runs the upstream [`pyatr`](https://pypi.org/project/pyatr/) engine inside the Agent Framework middleware pipeline. Detection is fully local and deterministic — there is no model call in the enforcement path, so block/allow decisions are reproducible and auditable.

### Key Features

- Deterministic enforcement at the tool-execution boundary (`ATRFunctionMiddleware`) — the pattern recommended in issue #5366: the check runs before the tool executes, so a matched call never fires.
- Inbound input scanning at the agent boundary (`ATRAgentMiddleware`) — blocks a run when a user message matches a rule.
- Works with any `Agent` using the standard Agent Framework middleware pipeline.
- No external service, credentials, or network calls — the ruleset ships with `pyatr` and runs in-process.
- `audit_only` (shadow) mode: record and log matches without blocking.

### When to Use

Add ATR when you want a deterministic, auditable guard that:

- Blocks prompt-injection or exfiltration payloads that land in tool arguments before the tool runs.
- Rejects malicious user input before it reaches the model.
- Applies a maintained, community-driven ruleset without hand-rolling deny-lists.

---

## Quick Start

```python
import asyncio

from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework_atr import ATRFunctionMiddleware


async def main() -> None:
    client = OpenAIChatCompletionClient()

    agent = Agent(
        client=client,
        instructions="You are a helpful assistant.",
        tools=[...],
        middleware=[ATRFunctionMiddleware()],
    )

    # A tool call whose arguments match an ATR rule is blocked before the tool runs;
    # the middleware raises MiddlewareTermination with the matched rule id.
    result = await agent.run("What's the weather in Tokyo?")
    print(result)


asyncio.run(main())
```

To guard the inbound user message instead of (or in addition to) tool arguments:

```python
from agent_framework_atr import ATRAgentMiddleware

agent = Agent(client=client, instructions="...", middleware=[ATRAgentMiddleware()])
```

---

## Configuration

Both middleware share the same options:

```python
from agent_framework_atr import ATRDetector, ATRFunctionMiddleware

# Share a single detector so the ruleset is loaded once.
detector = ATRDetector(
    rules_dir=None,              # None: use the ruleset bundled with pyatr; or a path to your own ATR rules
    min_severity="informational",  # only act on matches at or above this severity
)

middleware = ATRFunctionMiddleware(
    detector=detector,
    audit_only=False,            # True: record + log matches without blocking (shadow mode)
)
```

On a block, the matched detection is recorded on `context.metadata["atr_detection"]` (an `ATRDetection` with `rule_id`, `severity`, `confidence`, and `title`) for later inspection by downstream middleware or logging.

---

## Notes

- **Deterministic**: detection runs the ATR engine locally over the text; no model is called to make the block/allow decision.
- **Severity threshold**: `min_severity` filters weaker matches; the highest-severity match is the one reported.
- **Audit mode**: use `audit_only=True` to measure what would be blocked before enforcing.
- **Ruleset**: `pyatr` ships the published ATR ruleset; point `rules_dir` at your own directory to run a custom or pinned set.
