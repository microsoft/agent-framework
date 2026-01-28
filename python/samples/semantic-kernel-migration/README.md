# Semantic Kernel → Microsoft Agent Framework Migration Samples

This gallery helps Semantic Kernel (SK) developers move to the Microsoft Agent Framework (AF) with minimal guesswork. Each script pairs SK code with its AF equivalent so you can compare primitives, tooling, and orchestration patterns side by side while you migrate production workloads.

## What’s Included

## What’s Included

### Chat completion parity
- [01_basic_chat_completion.py](chat_completion/01_basic_chat_completion.py) — Minimal SK `ChatCompletionAgent` and AF `ChatAgent` conversation.
- [02_chat_completion_with_tool.py](chat_completion/02_chat_completion_with_tool.py) — Adds a simple tool/function call in both SDKs.
- [03_chat_completion_thread_and_stream.py](chat_completion/03_chat_completion_thread_and_stream.py) — Demonstrates thread reuse and streaming prompts.

### Azure AI agent parity
- [01_basic_azure_ai_agent.py](azure_ai_agent/01_basic_azure_ai_agent.py) — Create and run an Azure AI agent end to end.
- [02_azure_ai_agent_with_code_interpreter.py](azure_ai_agent/02_azure_ai_agent_with_code_interpreter.py) — Enable hosted code interpreter/tool execution.
- [03_azure_ai_agent_threads_and_followups.py](azure_ai_agent/03_azure_ai_agent_threads_and_followups.py) — Persist threads and follow-ups across invocations.

### OpenAI Assistants API parity
- [01_basic_openai_assistant.py](openai_assistant/01_basic_openai_assistant.py) — Baseline assistant comparison.
- [02_openai_assistant_with_code_interpreter.py](openai_assistant/02_openai_assistant_with_code_interpreter.py) — Code interpreter tool usage.
- [03_openai_assistant_function_tool.py](openai_assistant/03_openai_assistant_function_tool.py) — Custom function tooling.

### OpenAI Responses API parity
- [01_basic_responses_agent.py](openai_responses/01_basic_responses_agent.py) — Basic responses agent migration.
- [02_responses_agent_with_tool.py](openai_responses/02_responses_agent_with_tool.py) — Tool-augmented responses workflows.
- [03_responses_agent_structured_output.py](openai_responses/03_responses_agent_structured_output.py) — Structured JSON output alignment.

### Copilot Studio parity
- [01_basic_copilot_studio_agent.py](copilot_studio/01_basic_copilot_studio_agent.py) — Minimal Copilot Studio agent invocation.
- [02_copilot_studio_streaming.py](copilot_studio/02_copilot_studio_streaming.py) — Streaming responses from Copilot Studio agents.

### Orchestrations
- [sequential.py](orchestrations/sequential.py) — Step-by-step SK Team → AF `SequentialBuilder` migration.
- [concurrent_basic.py](orchestrations/concurrent_basic.py) — Concurrent orchestration parity.
- [group_chat.py](orchestrations/group_chat.py) — Group chat coordination with an LLM-backed manager in both SDKs.
- [handoff.py](orchestrations/handoff.py) - Handoff coordination between agents.
- [magentic.py](orchestrations/magentic.py) — Magentic Team orchestration vs. AF builder wiring.

### Processes
- [fan_out_fan_in_process.py](processes/fan_out_fan_in_process.py) — Fan-out/fan-in comparison between SK Process Framework and AF workflows.
- [nested_process.py](processes/nested_process.py) — Nested process orchestration vs. AF sub-workflows.

Each script is fully async and the `main()` routine runs both implementations back to back so you can observe their outputs in a single execution.

## Prerequisites
- Python 3.10 or later.
- Access to the necessary model endpoints (Azure OpenAI, OpenAI, Azure AI, Copilot Studio, etc.).
- Installed SDKs: `semantic-kernel` and the Microsoft Agent Framework (`pip install semantic-kernel agent-framework`), or the repo’s editable packages if you are developing locally.
- Service credentials exposed through environment variables (for example `OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, or Copilot Studio auth settings).

## Running Single-Agent Samples
From the repository root:
```
python samples/semantic-kernel-migration/chat_completion/01_basic_chat_completion.py
```
Every script accepts no CLI arguments and will first call the SK implementation, followed by the AF version. Adjust the prompt or credentials inside the file as necessary before running.

## Running Orchestration & Workflow Samples
Advanced comparisons are split between `samantic-kernel-migration/orchestrations` (Sequential, Concurrent, Magentic) and `samantic-kernel-migration/processes` (fan-out/fan-in, nested). You can run them directly, or isolate dependencies in a throwaway virtual environment:
```
cd samples/semantic-kernel-migration
uv venv --python 3.10 .venv-migration
source .venv-migration/bin/activate
uv pip install semantic-kernel agent-framework
uv run python orchestrations/sequential.py
uv run python processes/fan_out_fan_in_process.py
```
Swap the script path for any other workflow or process sample. Deactivate the sandbox with `deactivate` when you are finished.

## Tips for Migration
- Keep the original SK sample open while iterating on the AF equivalent; the code is intentionally formatted so you can copy/paste across SDKs.
- Threads/conversation state are explicit in AF. When porting SK code that relies on implicit thread reuse, call `agent.get_new_thread()` and pass it into each `run`/`run_stream` call.
- Tools map cleanly: SK `@kernel_function` plugins translate to AF `@tool` callables. Hosted tools (code interpreter, web search, MCP) are available only in AF—introduce them once parity is achieved.
- For multi-agent orchestration, AF workflows expose checkpoints and resume capabilities that SK Process/Team abstractions do not. Use the workflow samples as a blueprint when modernizing complex agent graphs.
