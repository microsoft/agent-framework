# Copyright (c) Microsoft. All rights reserved.
# Semantic Kernel → Microsoft Agent Framework Migration Samples

This gallery helps Semantic Kernel (SK) developers move to the Microsoft Agent Framework (AF) with minimal guesswork. Each script pairs SK code with its AF equivalent so you can compare primitives, tooling, and orchestration patterns side by side while you migrate production workloads.

## What’s Included
- `chat_completion/` – SK `ChatCompletionAgent` scenarios and their AF `ChatAgent` counterparts (basic chat, tooling, threading/streaming).
- `azure_ai_agent/` – Remote Azure AI agent examples, including hosted code interpreter and explicit thread reuse.
- `openai_assistant/` – Assistants API migrations covering basic usage, code interpreter, and custom function tools.
- `openai_responses/` – Responses API parity samples with tooling and structured JSON output.
- `copilot_studio/` – Copilot Studio agent parity, tools, and streaming examples.
- `orchestrations/` – Sequential, Concurrent, and Magentic workflow migrations that mirror SK Team abstractions.
- `processes/` – Fan-out/fan-in and nested process examples that contrast SK’s Process Framework with AF workflows.

Each script is fully async and the `main()` routine runs both implementations back to back so you can observe their outputs in a single execution.

## Prerequisites
- Python 3.10 or later.
- Access to the necessary model endpoints (Azure OpenAI, OpenAI, Azure AI, Copilot Studio, etc.).
- Installed SDKs: `semantic-kernel` and the Microsoft Agent Framework (`pip install semantic-kernel agent-framework`), or the repo’s editable packages if you are developing locally.
- Service credentials exposed through environment variables (for example `OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, or Copilot Studio auth settings).

## Running Single-Agent Samples
From the repository root:
```
python samantic-kernel-migration/chat_completion/01_basic_chat_completion.py
```
Every script accepts no CLI arguments and will first call the SK implementation, followed by the AF version. Adjust the prompt or credentials inside the file as necessary before running.

## Running Orchestration & Workflow Samples
Advanced comparisons are split between `samantic-kernel-migration/orchestrations` (Sequential, Concurrent, Magentic) and `samantic-kernel-migration/processes` (fan-out/fan-in, nested). You can run them directly, or isolate dependencies in a throwaway virtual environment:
```
cd samantic-kernel-migration
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
- Tools map cleanly: SK `@kernel_function` plugins translate to AF `@ai_function` callables. Hosted tools (code interpreter, web search, MCP) are available only in AF—introduce them once parity is achieved.
- For multi-agent orchestration, AF workflows expose checkpoints and resume capabilities that SK Process/Team abstractions do not. Use the workflow samples as a blueprint when modernizing complex agent graphs.
