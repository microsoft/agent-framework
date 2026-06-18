---
status: accepted
contact: bentho
date: 2026-02-27
deciders: bentho, markwallace-microsoft, westey-m
consulted: Pratyush Mishra, Shivam Shrivastava, Manni Arora (Centrica eval scenario)
informed: Agent Framework team, Foundry Evals team
---

# Agent Evaluation Architecture with Azure AI Foundry Integration

## Context and Problem Statement

Azure AI Foundry provides a rich evaluation service for AI agents — built-in evaluators for agent behavior (task adherence, intent resolution), tool usage (tool call accuracy, tool selection), quality (coherence, fluency, relevance), and safety (violence, self-harm, prohibited actions). Results are viewable in the Foundry portal with dashboards and comparison views.

However, using Foundry Evals with an agent-framework agent today requires significant manual effort. Developers must:

1. Transform agent-framework's `Message`/`Content` types into the OpenAI-style agent message schema that Foundry evaluators expect
2. Map tool definitions from agent-framework's `FunctionTool` format to evaluator-compatible schemas
3. Manually wire up the correct Foundry data source type (`azure_ai_traces`, `jsonl`, `azure_ai_target_completions`, etc.) depending on their scenario
4. Handle App Insights trace ID queries, response ID collection, and eval polling

Additionally, evaluation is a concern that extends beyond any single provider. Developers may want to use local evaluators (LLM-as-judge, regex, keyword matching), third-party evaluation libraries, or multiple providers in combination. The architecture must support this without creating a Foundry-specific lock-in at the API level.

### Functional Requirements for Agent Evaluation

- **Single agents and workflows.** Evaluate both individual agent responses and multi-agent workflow results, with per-agent breakdown to pinpoint underperformance.
- **One-shot and multi-turn conversations.** Capture full conversation trajectories — including tool calls and results — not just final query/response pairs.
- **Conversation factoring.** Support splitting conversations into query/response in multiple ways (last turn, full trajectory, per-turn) because different factorings measure different things.
- **Multiple providers, mix and match.** Run Foundry LLM-as-judge evaluators alongside fast local checks and custom evaluators on the same data, without restructuring code.
- **Third-party extensibility.** Any evaluation library can participate by implementing the `Evaluator` protocol (Python) or `IAgentEvaluator` interface (.NET). No predetermined list of supported libraries — the protocol is intentionally simple (`evaluate(items) → results`) so that wrappers for libraries like DeepEval, RAGAS, or Promptfoo are straightforward to write.
- **Bring your own evaluator.** Creating a custom evaluator should be as simple as writing a function.
- **Evaluate without re-running.** Evaluate existing responses from logs or previous runs without invoking the agent again.

## Decision Drivers

- **Zero-friction evaluation**: Developers should go from "I have an agent" to "I have eval results" with minimal code.
- **Provider-agnostic API**: Core evaluation capabilities must not be tied to any specific provider. Provider configuration should be separate from the evaluation call.
- **Lowest concept count**: Introduce the fewest possible new types, abstractions, and APIs for developers to learn.
- **Leverage existing knowledge**: The framework already knows which agents exist, what tools they have, and what conversations occurred. Evals should use this automatically rather than requiring the developer to re-specify it.
- **Foundry-native results**: When using Foundry, results should be viewable in the Foundry portal with dashboards and comparison views.
- **Progressive disclosure**: Simple scenarios should be near-zero code. Advanced scenarios should build on the same primitives.
- **Cross-language parity**: Design must be implementable in both Python and .NET.

## Considered Options

1. **Provider-specific functions** — Build Foundry-specific helper functions (`evaluate_agent()`, etc.) directly in the Azure package. All eval functions take Foundry connection parameters.
2. **Evaluator protocol with shared orchestration** — Define a provider-agnostic `Evaluator` protocol in the base agent library (`agent_framework` in Python, `Microsoft.Agents.AI` in .NET). Orchestration functions live alongside it. Providers implement the protocol.
3. **Full eval framework** — Build comprehensive eval infrastructure including custom evaluator definitions, scoring profiles, and reporting inside agent-framework.

## Decision Outcome

Proposed option: "Evaluator protocol with shared orchestration", because it delivers the low-friction developer experience, supports multiple providers without API changes, and keeps the concept count low.

### Usage Examples

#### Evaluate an agent

The agent is invoked once per query by default. For statistically meaningful evaluation, provide multiple diverse queries. For measuring **consistency** (does the same query produce reliable results?), use `num_repetitions` to run each query N times independently:

**Python:**

```python
evals = FoundryEvals(
    project_client=client,
    model_deployment="gpt-4o",
    evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE],
)

results = await evaluate_agent(
    agent=my_agent,
    queries=[
        "What's the weather in Seattle?",
        "Plan a weekend trip to Portland",
        "What restaurants are near Pike Place?",
    ],
    evaluators=evals,
)
for r in results:
    r.assert_passed()
```

**C#:**

```csharp
var evals = new FoundryEvals(chatConfiguration, FoundryEvals.Relevance, FoundryEvals.Coherence);

AgentEvaluationResults results = await agent.EvaluateAsync(
    new[] {
        "What's the weather in Seattle?",
        "Plan a weekend trip to Portland",
        "What restaurants are near Pike Place?",
    },
    evals);

results.AssertAllPassed();
```

`evaluate_agent` returns one `EvalResults` per evaluator. Each result contains per-item scores with the evaluated response for auditing:

```
# results[0] (FoundryEvals)
EvalResults(status="completed", passed=3, failed=0, total=3)
  items[0]: EvalItemResult(
    query="What's the weather in Seattle?",
    response="It's currently 72°F and sunny in Seattle.",
    scores={"relevance": 5, "coherence": 5})
  items[1]: EvalItemResult(
    query="Plan a weekend trip to Portland",
    response="Here's a 2-day Portland itinerary...",
    scores={"relevance": 4, "coherence": 5})
  items[2]: EvalItemResult(
    query="What restaurants are near Pike Place?",
    response="Top restaurants near Pike Place Market: ...",
    scores={"relevance": 5, "coherence": 4})
```

#### Measure consistency with repetitions

Run each query multiple times to detect non-deterministic behavior:

**Python:**

```python
results = await evaluate_agent(
    agent=my_agent,
    queries=["What's the weather in Seattle?"],
    evaluators=evals,
    num_repetitions=3,  # each query runs 3 times independently
)
# results contain 3 items (1 query × 3 repetitions)
```

**C#:**

```csharp
AgentEvaluationResults results = await agent.EvaluateAsync(
    new[] { "What's the weather in Seattle?" },
    evals,
    numRepetitions: 3);  // each query runs 3 times independently
// results contain 3 items (1 query × 3 repetitions)
```

#### Evaluate a response you already have

When you already have agent responses, pass them directly to skip re-running the agent. Each query is paired with its corresponding response:

**Python:**

```python
queries = ["What's the weather?", "What's the capital of France?"]
responses = [await agent.run([Message("user", [q])]) for q in queries]

results = await evaluate_agent(
    responses=responses,
    evaluators=evals,
)
```

**C#:**

```csharp
var queries = new[] { "What's the weather?" };
var responses = new List<AgentResponse>();
foreach (var q in queries)
    responses.Add(await agent.RunAsync(new[] { new ChatMessage(ChatRole.User, q) }));

AgentEvaluationResults results = await agent.EvaluateAsync(
    responses: responses,
    evals);
```

Each `AgentResponse` already contains the conversation (query + response), so the evaluator extracts query/response from the conversation. When you pass `responses` without `queries`, the conversation is the source of truth.

#### Evaluate with conversation split strategies

By default, evaluators see only the last turn (final user message → final assistant response). For multi-turn conversations, you can control how the conversation is factored for evaluation:

**Python:**

```python
results = await evaluate_agent(
    agent=agent,
    queries=["Plan a 3-day trip to Paris"],
    evaluators=evals,
    conversation_split=ConversationSplit.FULL,      # evaluate entire trajectory
)

# Or per-turn: each user→assistant exchange scored independently
results = await evaluate_agent(
    agent=agent,
    queries=["Plan a 3-day trip to Paris"],
    evaluators=evals,
    conversation_split=ConversationSplit.PER_TURN,
)
```

**C#:**

```csharp
// Full conversation as context
AgentEvaluationResults results = await agent.EvaluateAsync(
    new[] { "Plan a 3-day trip to Paris" },
    evals,
    splitter: ConversationSplitters.Full);

// Per-turn splitting
var items = EvalItem.PerTurnItems(conversation);  // one EvalItem per user turn
var results = await evals.EvaluateAsync(items);
```

With `PER_TURN`, a 3-turn conversation produces 3 scored items:

```
EvalResults(status="completed", passed=3, failed=0, total=3)
  items[0]: query="Plan a 3-day trip to Paris"    scores={"relevance": 5}
  items[1]: query="What about restaurants?"        scores={"relevance": 4}
  items[2]: query="Make it budget-friendly"        scores={"relevance": 5}
```

#### Evaluate a multi-agent workflow

**Python:**

```python
result = await workflow.run("Plan a trip to Paris")
eval_results = await evaluate_workflow(
    workflow=workflow,
    workflow_result=result,
    evaluators=evals,
)

for r in eval_results:
    print(f"  overall: {r.passed}/{r.total}")
    for name, sub in r.sub_results.items():
        print(f"    {name}: {sub.passed}/{sub.total}")
```

**C#:**

```csharp
WorkflowRunResult result = await workflow.RunAsync("Plan a trip to Paris");

IReadOnlyList<AgentEvaluationResults> evalResults = await result.EvaluateAsync(evals);

foreach (var r in evalResults)
{
    Console.WriteLine($"  overall: {r.Passed}/{r.Total}");
    foreach (var (name, sub) in r.SubResults)
        Console.WriteLine($"    {name}: {sub.Passed}/{sub.Total}");
}
```

Workflows return one result per evaluator, with sub-results per agent in the workflow:

```
EvalResults(status="completed", passed=2, failed=0, total=2)
  sub_results:
    "planner":  EvalResults(passed=1, total=1)
    "researcher": EvalResults(passed=1, total=1)
```

#### Mix multiple providers

**Python:**

```python
@evaluator
def is_helpful(response: str) -> bool:
    return len(response.split()) > 10

foundry = FoundryEvals(
    project_client=client,
    model_deployment="gpt-4o",
    evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE],
)

results = await evaluate_agent(
    agent=agent,
    queries=queries,
    evaluators=[is_helpful, keyword_check("weather"), foundry],
)
```

**C#:**

```csharp
IReadOnlyList<AgentEvaluationResults> results = await agent.EvaluateAsync(
    queries,
    evaluators: new IAgentEvaluator[]
    {
        new LocalEvaluator(
            EvalChecks.KeywordCheck("weather"),
            FunctionEvaluator.Create("is_helpful", (string r) => r.Split(' ').Length > 10)),
        new FoundryEvals(chatConfiguration, FoundryEvals.Relevance, FoundryEvals.Coherence),
    });
```

Multiple evaluators return one result each — `results[0]` is the local evaluator, `results[1]` is Foundry.

#### Custom function evaluators

**Python:**

```python
@evaluator
def mentions_city(response: str, expected_output: str) -> bool:
    return expected_output.lower() in response.lower()

@evaluator
def used_tools(conversation: list, tools: list) -> float:
    # ... scoring logic
    return score

local = LocalEvaluator(mentions_city, used_tools)
```

`@evaluator` uses **parameter name injection** — the function's parameter names determine what data it receives from the `EvalItem`. Supported names: `query`, `response`, `expected`, `expected_tool_calls`, `conversation`, `tools`, `context`. Any combination is valid.

**C#:**

```csharp
var local = new LocalEvaluator(
    FunctionEvaluator.Create("mentions_city",
        (EvalItem item) => item.ExpectedOutput != null
            && item.Response.Contains(item.ExpectedOutput, StringComparison.OrdinalIgnoreCase)),
    FunctionEvaluator.Create("is_concise",
        (string response) => response.Split(' ').Length < 500));
```

## What To Build

### Core: Evaluator Protocol

A runtime-checkable protocol that any evaluation provider implements:

```python
@runtime_checkable
class Evaluator(Protocol):
    name: str

    async def evaluate(
        self, items: Sequence[EvalItem], *, eval_name: str = "Agent Framework Eval"
    ) -> EvalResults: ...
```

The protocol is minimal — just `name` and `evaluate()`.

### Core: EvalItem

Provider-agnostic data format for items to evaluate:

```python
@dataclass
class ExpectedToolCall:
    name: str                                    # Tool/function name
    arguments: dict[str, Any] | None = None      # None = don't check args

@dataclass
class EvalItem:
    conversation: list[Message]               # Single source of truth
    tools: list[FunctionTool] | None = None   # Agent's available tools
    context: str | None = None
    expected_output: str | None = None          # Ground-truth for comparison
    expected_tool_calls: list[ExpectedToolCall] | None = None
    split_strategy: ConversationSplitter | None = None

    query: str       # property — derived from conversation split
    response: str    # property — derived from conversation split
```

`conversation` is the single source of truth. `query` and `response` are derived properties — splitting the conversation at the last user message (default) and extracting text from each side. Changing the `split_strategy` consistently changes all derived values.

`tools` provides typed `FunctionTool` objects — including MCP tools, which are automatically extracted after agent runs.

### Internal: AgentEvalConverter

Internal class that converts agent-framework types to `EvalItem`. Used by `evaluate_agent()` and `evaluate_workflow()` — not part of the public API:

| Agent Framework | Eval Format |
|---|---|
| `Content.function_call` | `tool_call` in OpenAI chat format |
| `Content.function_result` | `tool_result` in OpenAI chat format |
| `FunctionTool` | `{name, description, parameters}` schema |
| `Message` history | `conversation` list + `query`/`response` extraction |

### Core: EvalResults

Rich result type with convenience properties for CI integration:

```python
results.all_passed          # bool: no failures or errors (recursive for workflow)
results.passed              # int: passing count
results.failed              # int: failure count
results.total               # int: total = passed + failed + errored
results.items               # list[EvalItemResult]: per-item detail with query, response, and scores
results.error               # str | None: error details on failure
results.sub_results         # dict: per-agent breakdown (workflow evals)
results.report_url          # str | None: portal link (Foundry)
results.assert_passed()     # raises AssertionError with details
```

### Core: Orchestration Functions

Provider-agnostic functions that extract data and delegate to evaluators:

| Function | What it does |
|---|---|
| `evaluate_agent()` | Runs agent against test queries (or evaluates pre-existing `responses=`), converts to `EvalItem`s, passes to evaluator. Accepts optional `expected_output=` for ground-truth comparison, `expected_tool_calls=` for tool-correctness evaluation, and `num_repetitions=` for consistency measurement |
| `evaluate_workflow()` | Extracts per-agent data from `WorkflowRunResult`, evaluates each agent and overall output. Per-agent breakdown in `sub_results`. Also accepts `num_repetitions=` |

### Core: Conversation Split Strategies

Multi-turn conversations must be split into query (input) and response (output) halves for evaluation. How you split determines *what you're evaluating*:

**Last-turn split** — split at the last user message. Everything up to and including it is the query context; the agent's subsequent actions are the response:

```
conversation: user1 → assistant1 → user2 → assistant2(tool) → tool_result → assistant3
query_messages:    [user1, assistant1, user2]
response_messages: [assistant2(tool), tool_result, assistant3]
```

This evaluates: "Given all the context so far, did the agent answer the latest question well?" Best for response quality at a specific point in the conversation.

**Full-conversation split** — the first user message is the query; everything after is the response:

```
query_messages:    [user1]
response_messages: [assistant1, user2, assistant2(tool), tool_result, assistant3]
```

This evaluates: "Given the original request, did the entire conversation trajectory serve the user?" Best for task completion and overall conversation quality.

**Per-turn split** — produces N eval items from an N-turn conversation. Each turn is evaluated with its cumulative context:

```
item 1: query = [user1],                        response = [assistant1]
item 2: query = [user1, assistant1, user2],      response = [assistant2(tool), tool_result, assistant3]
```

This evaluates each response independently. Best for fine-grained analysis and pinpointing where a conversation goes wrong.

These factorings produce different scores for the same conversation. The framework ships all three as built-in strategies, defaulting to last-turn. Developers can also provide a custom splitter — a function (Python) or `IConversationSplitter` implementation (.NET) — and override the strategy at the call site or per evaluator.

### Azure AI: FoundryEvals

`Evaluator` implementation backed by Azure AI Foundry:

```python
class FoundryEvals:
    def __init__(self, *, project_client=None, openai_client=None,
                 model_deployment: str, evaluators=None, ...)
    async def evaluate(self, items, *, eval_name) -> EvalResults
```

**Smart auto-detection in `evaluate()`:**
- Default evaluators: relevance, coherence, task_adherence
- Auto-adds `tool_call_accuracy` when items have tools/`tool_definitions`
- Filters out tool evaluators for items without tools

### Azure AI: FoundryEvals Constants

```python
from agent_framework.foundry import FoundryEvals

evaluators = [FoundryEvals.RELEVANCE, FoundryEvals.TOOL_CALL_ACCURACY]
```

Categories: Agent behavior, Tool usage, Quality, Safety.

### Azure AI: Foundry-Specific Functions

| Function | What it does |
|---|---|
| `evaluate_traces()` | Evaluate from stored response IDs or OTel traces |
| `evaluate_foundry_target()` | Evaluate a Foundry-registered agent or deployment |

### Core: LocalEvaluator and Function Evaluators

`LocalEvaluator` implements the `Evaluator` protocol for fast, API-free evaluation. It runs check functions locally — useful for inner-loop development, CI smoke tests, and combining with cloud-based evaluators.

Built-in checks:
- `keyword_check(*keywords)` — response must contain specified keywords
- `tool_called_check(*tool_names)` — agent must have called specified tools
- `tool_calls_present` — all `expected_tool_calls` names appear in conversation (unordered, extras OK)
- `tool_call_args_match` — expected tool calls match on name + arguments (subset match on args)

Custom function evaluators use `@evaluator` to wrap plain Python functions. The function's **parameter names** determine what data it receives from the `EvalItem`:

```python
from agent_framework import evaluator, LocalEvaluator

# Tier 1: Simple check — just query + response
@evaluator
def is_concise(response: str) -> bool:
    return len(response.split()) < 500

# Tier 2: Ground truth — compare against expected output
@evaluator
def mentions_city(response: str, expected_output: str) -> bool:
    return expected_output.lower() in response.lower()

# Tier 3: Full context — inspect conversation and tools
@evaluator
def used_tools(conversation: list, tools: list) -> float:
    # ... scoring logic
    return score

local = LocalEvaluator(is_concise, mentions_city, used_tools)
```

Supported parameters: `query`, `response`, `expected`, `expected_tool_calls`, `conversation`, `tools`, `context`.
Return types: `bool`, `float` (≥0.5 = pass), `dict` with `score` or `passed` key, or `CheckResult`.

Async functions are handled automatically — `@evaluator` detects `async def` and produces the right wrapper.

### Example: GAIA Benchmark

[GAIA](https://huggingface.co/gaia-benchmark) tests real-world multi-step tasks with known expected answers. Each task has a question and a ground-truth answer, with optional file attachments. The framework accommodates GAIA's knobs (difficulty levels, file inputs, multi-step tool use) through the existing `EvalItem` fields:

```python
from datasets import load_dataset
from agent_framework import evaluate_agent, evaluator, LocalEvaluator

gaia = load_dataset("gaia-benchmark/GAIA", "2023_level1", split="test")

@evaluator
def exact_match(response: str, expected_output: str) -> bool:
    return expected_output.strip().lower() in response.strip().lower()

# Simple path — evaluate_agent handles running + expected_output stamping
results = await evaluate_agent(
    agent=agent,
    queries=[task["Question"] for task in gaia],
    expected_output=[task["Final answer"] for task in gaia],
    evaluators=LocalEvaluator(exact_match),
)
```

### Package Location

- Core types and orchestration: `agent_framework._eval`, `agent_framework._local_eval` (Python), `Microsoft.Agents.AI` (.NET)
- Foundry provider: `agent_framework_azure_ai._foundry_evals` (Python), `Microsoft.Agents.AI.AzureAI` (.NET)
- Azure-AI re-exports core types for convenience (Python)

## Known Limitations

1. **Tool evaluators require query + agent**: Tool evaluators need tool definition schemas. When using these evaluators with `evaluate_agent(responses=...)`, provide `queries=` and pass an agent with tool definitions.
2. **`model_deployment` always required**: Could potentially be inferred from the Foundry project configuration.

## Open Questions

1. **Red teaming non-registered agents**: Requires Foundry API support for callback-based flows.
2. **Datasets with expected outputs**: A dataset abstraction for pre-populating `expected_output` values across eval runs is a natural next step but not yet designed.
3. **Multi-modal evaluation**: The `conversation` field on `EvalItem` already stores full `Message`/`Content` (Python) and `ChatMessage` (.NET) objects, which can represent multi-modal content (images, audio, structured data). Evaluators that accept the full `EvalItem` or `conversation` parameter can access this content today. However, the convenience shortcuts — `query`/`response` string projections and the `FunctionEvaluator` string overloads — are text-only. Multi-modal-aware evaluators should use the full-item path (`Func<EvalItem, CheckResult>` in .NET, `conversation: list` parameter in Python).

## .NET Implementation Design

### Key Difference: MEAI Ecosystem

Unlike Python, the .NET ecosystem already has `Microsoft.Extensions.AI.Evaluation` (v10.3.0) providing:

- `IEvaluator` — per-item evaluation of `(messages, chatResponse) → EvaluationResult`
- `CompositeEvaluator` — combines multiple evaluators
- Quality evaluators — `RelevanceEvaluator`, `CoherenceEvaluator`, `GroundednessEvaluator`
- Safety evaluators — `ContentHarmEvaluator`, `ProtectedMaterialEvaluator`
- Metric types — `NumericMetric`, `BooleanMetric`, `StringMetric`

The .NET integration uses MEAI's `IEvaluator` directly — no new evaluator interface. Our contribution is the **orchestration layer**: extension methods that run agents, extract data, call `IEvaluator` per item, and aggregate results.

### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Developer Code                                              │
│  agent.EvaluateAsync(queries, evaluator)                     │
│  run.EvaluateAsync(evaluator)                                │
└────────────────┬─────────────────────────────────────────────┘
                 │
┌────────────────▼─────────────────────────────────────────────┐
│  Orchestration Layer (Microsoft.Agents.AI)                   │
│  AgentEvaluationExtensions — runs agents, extracts data,     │
│  calls IEvaluator per item, aggregates into                  │
│  AgentEvaluationResults                                      │
└────────────────┬─────────────────────────────────────────────┘
                 │ IEvaluator (MEAI)
                 │
     ┌───────────┼────────────┐
     │           │            │
 ┌───▼───-┐  ┌───▼────┐  ┌────▼──────────┐
 │ MEAI   │  │ Local  │  │ Foundry       │
 │ Quality│  │ Checks │  │ (cloud batch) │
 │ Safety │  │ Lambdas│  │               │
 └────────┘  └────────┘  └───────────────┘
```

All evaluators implement MEAI's `IEvaluator`. The orchestration layer doesn't need to know which kind — it calls `EvaluateAsync(messages, chatResponse)` per item on all of them. `FoundryEvals` handles batching internally (buffers items, submits once, returns per-item results).

### .NET Core Types

**No new evaluator interface.** Use MEAI's `IEvaluator` directly.

**`AgentEvaluationResults`** — The only new type. Aggregates per-item MEAI `EvaluationResult`s across a batch of queries:

```csharp
public class AgentEvaluationResults
{
    public string Provider { get; init; }
    public string? ReportUrl { get; init; }

    // Per-item — standard MEAI EvaluationResult, unchanged
    public IReadOnlyList<EvaluationResult> Items { get; init; }

    // Aggregate pass/fail derived from metric interpretations
    public int Passed { get; }
    public int Failed { get; }
    public int Total { get; }
    public bool AllPassed { get; }

    // Workflow: per-agent breakdown
    public IReadOnlyDictionary<string, AgentEvaluationResults>? SubResults { get; init; }

    public void AssertAllPassed(string? message = null);
}
```

### .NET Evaluator Implementations

All implement MEAI's `IEvaluator`:

**`LocalEvaluator`** — Runs lambda checks locally, returns `BooleanMetric` per check:

```csharp
var local = new LocalEvaluator(
    FunctionEvaluator.Create("is_concise",
        (string response) => response.Split().Length < 500),
    EvalChecks.KeywordCheck("weather"),
    EvalChecks.ToolCalledCheck("get_weather"));
```

**MEAI evaluators** — Used directly, no adapter needed:

```csharp
var quality = new CompositeEvaluator(
    new RelevanceEvaluator(),
    new CoherenceEvaluator());
```

**`FoundryEvals`** — Implements `IEvaluator` but batches internally. On first call, buffers the item. On the last item (or when explicitly flushed), submits the batch to Foundry and distributes per-item results:

```csharp
var foundry = new FoundryEvals(projectClient, "gpt-4o");
```

### .NET Orchestration: Extension Methods

```csharp
public static class AgentEvaluationExtensions
{
    // Evaluate an agent against test queries
    public static Task<AgentEvaluationResults> EvaluateAsync(
        this AIAgent agent,
        IEnumerable<string> queries,
        IEvaluator evaluator,
        ChatConfiguration? chatConfiguration = null,
        IEnumerable<string>? expectedOutput = null,
        CancellationToken cancellationToken = default);

    // Evaluate pre-existing responses (without re-running the agent)
    public static Task<AgentEvaluationResults> EvaluateAsync(
        this AIAgent agent,
        AgentResponse responses,
        IEvaluator evaluator,
        IEnumerable<string>? queries = null,
        ChatConfiguration? chatConfiguration = null,
        IEnumerable<string>? expectedOutput = null,
        CancellationToken cancellationToken = default);

    // Evaluate with multiple evaluators (one result per evaluator)
    public static Task<IReadOnlyList<AgentEvaluationResults>> EvaluateAsync(
        this AIAgent agent,
        IEnumerable<string> queries,
        IEnumerable<IEvaluator> evaluators,
        ChatConfiguration? chatConfiguration = null,
        IEnumerable<string>? expectedOutput = null,
        CancellationToken cancellationToken = default);

    // Evaluate a workflow run with per-agent breakdown
    public static Task<AgentEvaluationResults> EvaluateAsync(
        this Run run,
        IEvaluator evaluator,
        ChatConfiguration? chatConfiguration = null,
        bool includeOverall = true,
        bool includePerAgent = true,
        CancellationToken cancellationToken = default);
}
```

**Usage:**

```csharp
// MEAI evaluators — just works
var results = await agent.EvaluateAsync(
    queries: ["What's the weather?"],
    evaluator: new RelevanceEvaluator(),
    chatConfiguration: new ChatConfiguration(evalClient));

// Local checks
var results = await agent.EvaluateAsync(
    queries: ["What's the weather?"],
    evaluator: new LocalEvaluator(
        EvalChecks.KeywordCheck("weather")));

// Foundry cloud
var results = await agent.EvaluateAsync(
    queries: ["What's the weather?"],
    evaluator: new FoundryEvals(projectClient, "gpt-4o"));

// Evaluate existing response (without re-running the agent)
var response = await agent.RunAsync("What's the weather?");
var results = await agent.EvaluateAsync(
    responses: response,
    queries: ["What's the weather?"],
    evaluator: new FoundryEvals(projectClient, "gpt-4o"));

// Mixed — one result per evaluator
var results = await agent.EvaluateAsync(
    queries: ["What's the weather?"],
    evaluators: [
        new LocalEvaluator(EvalChecks.KeywordCheck("weather")),
        new RelevanceEvaluator(),
        new FoundryEvals(projectClient, "gpt-4o")
    ],
    chatConfiguration: new ChatConfiguration(evalClient));

// Workflow with per-agent breakdown
Run run = await workflowRunner.RunAsync(workflow, "Plan a trip");
var results = await run.EvaluateAsync(
    evaluator: new FoundryEvals(projectClient, "gpt-4o"));
```

### .NET Function Evaluators

Typed factory overloads (C# equivalent of Python's `@evaluator`):

```csharp
public static class FunctionEvaluator
{
    public static EvalCheck Create(string name, Func<string, bool> check);           // response only
    public static EvalCheck Create(string name, Func<string, string?, bool> check);  // expectedOutput
    public static EvalCheck Create(string name, Func<EvalItem, bool> check);         // full item
    public static EvalCheck Create(string name, Func<EvalItem, CheckResult> check);  // full control
    public static EvalCheck Create(string name, Func<string, Task<bool>> check);     // async
}
```

`EvalItem` is a lightweight record used only by `FunctionEvaluator` and `LocalEvaluator` to pass context to check functions. It is not part of the `IEvaluator` interface:

```csharp
public record ExpectedToolCall(string Name, IReadOnlyDictionary<string, object>? Arguments = null);

public sealed class EvalItem
{
    public EvalItem(string query, string response, IReadOnlyList<ChatMessage> conversation);

    public string Query { get; }
    public string Response { get; }
    public IReadOnlyList<ChatMessage> Conversation { get; }
    public IReadOnlyList<AITool>? Tools { get; set; }
    public string? ExpectedOutput { get; set; }
    public IReadOnlyList<ExpectedToolCall>? ExpectedToolCalls { get; set; }
    public string? Context { get; set; }
    public IConversationSplitter? Splitter { get; set; }
}
```

### Workflow Data Extraction (.NET)

`run.EvaluateAsync()` walks `Run.OutgoingEvents` via LINQ:

1. Pair `ExecutorInvokedEvent` / `ExecutorCompletedEvent` by `ExecutorId`
2. Extract `AgentResponseEvent` for per-agent `ChatResponse`
3. Call `evaluator.EvaluateAsync()` per invocation
4. Group by `ExecutorId` for per-agent `SubResults`
5. Use final workflow output for overall eval

### .NET Package Structure

| Package | Contents |
|---------|----------|
| `Microsoft.Agents.AI` | `IAgentEvaluator`, `AgentEvaluationResults`, `LocalEvaluator`, `FunctionEvaluator`, `EvalChecks`, `EvalItem`, `ExpectedToolCall`, `AgentEvaluationExtensions` |
| `Microsoft.Agents.AI.AzureAI` | `FoundryEvals` (provider + constants) |

### Python ↔ .NET Mapping

| Python | .NET |
|--------|------|
| `Evaluator` protocol | `IAgentEvaluator` (our interface; MEAI provides `IEvaluator` for per-item scoring) |
| `EvalItem` dataclass | `EvalItem` class |
| `EvalResults` | `AgentEvaluationResults` |
| `EvalItemResult` / `EvalScoreResult` | MEAI `EvaluationResult` / `EvaluationMetric` (reused) |
| `LocalEvaluator` | `LocalEvaluator` (implements `IAgentEvaluator`) |
| `@evaluator` | `FunctionEvaluator.Create()` overloads |
| `keyword_check()` / `tool_called_check()` | `EvalChecks.KeywordCheck()` / `EvalChecks.ToolCalledCheck()` |
| `tool_calls_present` / `tool_call_args_match` | (custom `FunctionEvaluator` — same pattern) |
| `ExpectedToolCall` dataclass | `ExpectedToolCall` record |
| `FoundryEvals` | `FoundryEvals` (implements `IAgentEvaluator`, includes evaluator name constants) |
| `evaluate_agent()` | `agent.EvaluateAsync(queries, evaluator)` extension method |
| `evaluate_agent(responses=)` | `agent.EvaluateAsync(responses, evaluator)` extension method |
| `evaluate_workflow()` | `run.EvaluateAsync()` extension method |

## More Information

- [Foundry Evals documentation](https://learn.microsoft.com/azure/ai-foundry/concepts/evaluation-approach-gen-ai) — Azure AI Foundry evaluation overview
