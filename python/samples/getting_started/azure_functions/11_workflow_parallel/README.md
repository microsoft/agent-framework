# Parallel Workflow Execution Sample

This sample demonstrates **parallel execution** of executors and agents in Azure Durable Functions workflows.

## Overview

This sample showcases three different parallel execution patterns:

1. **Two Executors in Parallel** - Fan-out to multiple activities
2. **Two Agents in Parallel** - Fan-out to multiple entities  
3. **Mixed Execution** - Agents and executors can run concurrently

## Workflow Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PARALLEL WORKFLOW                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Pattern 1: Two Executors in Parallel (Activities)                       │
│  ─────────────────────────────────────────────────                       │
│                                                                          │
│     input_router ──┬──> [word_count_processor] ────┐                     │
│                    │                               │                     │
│                    └──> [format_analyzer_processor]┴──> [aggregator]     │
│                                                                          │
│  Pattern 2: Two Agents in Parallel (Entities)                            │
│  ─────────────────────────────────────────────                           │
│                                                                          │
│     [prepare_for_agents] ──┬──> [SentimentAgent] ──────┐                 │
│                            │                           │                 │
│                            └──> [KeywordAgent] ────────┴──> [prepare_for_│
│                                                              mixed]      │
│                                                                          │
│  Pattern 3: Mixed Agent + Executor in Parallel                           │
│  ────────────────────────────────────────────────                        │
│                                                                          │
│     [prepare_for_mixed] ──┬──> [SummaryAgent] ─────────┐                 │
│                           │                            │                 │
│                           └──> [statistics_processor] ─┴──> [final_report│
│                                                              _executor]  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## How Parallel Execution Works

### Activities (Executors)
When multiple executors are pending in the same iteration (e.g., after a fan-out edge), they are batched and executed using `task_all()`:

```python
# In _workflow.py - activities execute in parallel
activity_tasks = [context.call_activity("ExecuteExecutor", input) for ...]
results = yield context.task_all(activity_tasks)  # All run concurrently!
```

### Agents (Entities)
Different agents can also run in parallel when they're pending in the same iteration:

```python
# Different agents run in parallel
agent_tasks = [agent_a.run(...), agent_b.run(...)]
responses = yield context.task_all(agent_tasks)  # Both agents run concurrently!
```

**Note:** Multiple messages to the *same* agent are processed sequentially to maintain conversation coherence.

## Components

| Component | Type | Description |
|-----------|------|-------------|
| `input_router` | Executor | Routes input JSON to parallel processors |
| `word_count_processor` | Executor | Counts words and characters |
| `format_analyzer_processor` | Executor | Analyzes document format |
| `aggregator` | Executor | Combines results from parallel processors |
| `prepare_for_agents` | Executor | Prepares content for agent analysis |
| `SentimentAnalysisAgent` | AI Agent | Analyzes text sentiment |
| `KeywordExtractionAgent` | AI Agent | Extracts keywords and categories |
| `prepare_for_mixed` | Executor | Prepares content for mixed parallel execution |
| `SummaryAgent` | AI Agent | Summarizes the document |
| `statistics_processor` | Executor | Computes document statistics |
| `FinalReportExecutor` | Executor | Compiles final report from all analyses |

## Prerequisites

1. **Azure OpenAI** - Endpoint and deployment configured
2. **DTS Emulator** - For durable task scheduling (recommended)
3. **Azurite** - For Azure Functions internal storage

## Setup

### Option 1: DevUI Mode (Local Development - No Durable Functions)

The sample can run locally without Azure Functions infrastructure using DevUI:

1. Copy the environment template:
   ```bash
   cp .env.template .env
   ```

2. Configure `.env` with your Azure OpenAI credentials

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run in DevUI mode (set `durable=False` in `function_app.py`):
   ```bash
   python function_app.py
   ```

5. Open `http://localhost:8095` and provide input:
   ```json
   {
     "document_id": "doc-001",
     "content": "Your document text here..."
   }
   ```

### Option 2: Durable Functions Mode (Full Azure Functions)

1. Copy configuration files:
   ```bash
   cp .env.template .env
   cp local.settings.json.sample local.settings.json
   ```

2. Configure `local.settings.json` with your Azure OpenAI credentials

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Start DTS Emulator:
   ```bash
   docker run -d --name dts-emulator -p 8080:8080 -p 8082:8082 mcr.microsoft.com/dts/dts-emulator:latest
   ```

5. Start Azurite (or use VS Code extension):
   ```bash
   azurite --silent
   ```

6. Run the function app (ensure `durable=True` in `function_app.py`):
   ```bash
   func start
   ```

## Testing

Use the `demo.http` file with REST Client extension or curl:

### Analyze a Document
```bash
curl -X POST http://localhost:7071/api/workflow/run \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "doc-001",
    "content": "The quarterly earnings report shows strong growth in cloud services. Revenue increased by 25%."
  }'
```

### Check Status
```bash
curl http://localhost:7071/api/workflow/status/{instanceId}
```

## Observing Parallel Execution

Open the DTS Dashboard at `http://localhost:8082` to observe:

1. **Activity Execution Timeline** - You'll see `word_count_processor` and `format_analyzer_processor` starting at approximately the same time
2. **Agent Execution Timeline** - `SentimentAnalysisAgent` and `KeywordExtractionAgent` also start concurrently
3. **Sequential vs Parallel** - Compare with non-parallel samples to see the time savings

## Expected Output

```json
{
  "output": [
    "=== Document Analysis Report ===\n\n--- SentimentAnalysisAgent ---\n{\"sentiment\": \"positive\", \"confidence\": 0.85, \"explanation\": \"...\"}\n\n--- KeywordExtractionAgent ---\n{\"keywords\": [\"earnings\", \"growth\", \"cloud\"], \"categories\": [\"finance\", \"technology\"]}"
  ]
}
```

## Key Takeaways

1. **Parallel execution is automatic** - When multiple executors/agents are pending in the same iteration, they run in parallel
2. **Workflow graph determines parallelism** - Fan-out edges create parallel execution opportunities
3. **Mixed parallelism** - Agents and executors can run concurrently if they're in the same iteration
4. **Same-agent messages are sequential** - To maintain conversation coherence
