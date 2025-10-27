# AutoGen → Microsoft Agent Framework Migration Samples

This gallery helps AutoGen developers move to the Microsoft Agent Framework (AF) with minimal guesswork. Each script pairs AutoGen code with its AF equivalent so you can compare primitives, tooling, and orchestration patterns side by side while you migrate production workloads.

## What's Included

### Single-Agent Parity

- [01_basic_assistant_agent.py](single_agent/01_basic_assistant_agent.py) — Minimal AutoGen `AssistantAgent` and AF `ChatAgent` comparison.
- [02_assistant_agent_with_tool.py](single_agent/02_assistant_agent_with_tool.py) — Function tool integration in both SDKs.
- [03_assistant_agent_thread_and_stream.py](single_agent/03_assistant_agent_thread_and_stream.py) — Thread management and streaming responses.
- [04_agent_as_tool.py](single_agent/04_agent_as_tool.py) — Using agents as tools (hierarchical agent pattern) and streaming with tools.

### Multi-Agent Orchestration

- [01_round_robin_group_chat.py](orchestrations/01_round_robin_group_chat.py) — AutoGen `RoundRobinGroupChat` → AF `GroupChatBuilder`/`SequentialBuilder`.
- [02_selector_group_chat.py](orchestrations/02_selector_group_chat.py) — AutoGen `SelectorGroupChat` → AF `GroupChatBuilder`.
- [03_swarm.py](orchestrations/03_swarm.py) — AutoGen Swarm pattern → AF `HandoffBuilder`.
- [04_magentic_one.py](orchestrations/04_magentic_one.py) — AutoGen `MagenticOneGroupChat` → AF `MagenticBuilder`.

Each script is fully async and the `main()` routine runs both implementations back to back so you can observe their outputs in a single execution.

## Prerequisites

- Python 3.10 or later.
- Access to the necessary model endpoints (Azure OpenAI, OpenAI, etc.).
- Installed SDKs: Install AutoGen and the Microsoft Agent Framework with:
  ```bash
  pip install "autogen-agentchat autogen-ext[openai] agent-framework"
  ```
- Service credentials exposed through environment variables (e.g., `OPENAI_API_KEY`).

## Running Single-Agent Samples

From the repository root:

```bash
python samples/autogen-migration/single_agent/01_basic_assistant_agent.py
```

Every script accepts no CLI arguments and will first call the AutoGen implementation, followed by the AF version. Adjust the prompt or credentials inside the file as necessary before running.

## Running Orchestration Samples

Advanced comparisons are in `autogen-migration/orchestrations` (RoundRobin, Selector, Swarm, Magentic). You can run them directly:

```bash
python samples/autogen-migration/orchestrations/01_round_robin_group_chat.py
python samples/autogen-migration/orchestrations/04_magentic_one.py
```

## Tips for Migration

- **Default behavior differences**: AutoGen's `AssistantAgent` is single-turn by default (`max_tool_iterations=1`), while AF's `ChatAgent` is multi-turn and continues tool execution automatically.
- **Thread management**: AF agents are stateless by default. Use `agent.get_new_thread()` and pass it to `run()`/`run_stream()` to maintain conversation state, similar to AutoGen's conversation context.
- **Tools**: AutoGen uses `FunctionTool` wrappers; AF uses `@ai_function` decorators with automatic schema inference.
- **Orchestration patterns**:
  - `RoundRobinGroupChat` → `SequentialBuilder` or `WorkflowBuilder`
  - `SelectorGroupChat` → `GroupChatBuilder` with LLM-based speaker selection
  - `Swarm` → `HandoffBuilder` for agent handoff coordination
  - `MagenticOneGroupChat` → `MagenticBuilder` for orchestrated multi-agent workflows
