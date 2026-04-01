---
name: verify-samples-tool
description: How to use the verify-samples tool to run, verify, and manage sample definitions in the Agent Framework repository. Use this when adding, updating, or running sample verification.
---

# verify-samples Tool

The `verify-samples` project (`dotnet/eng/verify-samples/`) is an automated tool that runs sample projects and verifies their output using deterministic checks and AI-powered verification.

## Running verify-samples

```bash
cd dotnet

# Run all samples across all categories
dotnet run --project eng/verify-samples -- --log results.log --csv results.csv

# Run a specific category
dotnet run --project eng/verify-samples -- --category 02-agents --log results.log

# Run specific samples by name
dotnet run --project eng/verify-samples -- Agent_Step02_StructuredOutput Agent_Step09_AsFunctionTool

# Control parallelism (default 8)
dotnet run --project eng/verify-samples -- --parallel 8 --log results.log

# Combine options
dotnet run --project eng/verify-samples -- --category 03-workflows --parallel 4 --log results.log --csv results.csv
```

### Required Environment Variables

The tool itself needs:
- `AZURE_OPENAI_ENDPOINT` — for the AI verification agent
- `AZURE_OPENAI_DEPLOYMENT_NAME` (optional, defaults to `gpt-5-mini`)

Individual samples require their own env vars (e.g., `AZURE_AI_PROJECT_ENDPOINT`). The tool automatically checks and skips samples with missing env vars.

### Output Files

- `--log results.log` — detailed per-sample log with stdout/stderr, AI reasoning, and a summary
- `--csv results.csv` — tabular summary with Sample, ProjectPath, Status, FailedChecks, and Failures columns

## Sample Categories

Definitions are in the `dotnet/eng/verify-samples/` directory:

| Category | Config File | Registered Key |
|----------|-------------|----------------|
| 01-get-started | `GetStartedSamples.cs` | `01-get-started` |
| 02-agents | `AgentsSamples.cs` | `02-agents` |
| 03-workflows | `WorkflowSamples.cs` | `03-workflows` |

Categories are registered in `VerifyOptions.cs` in the `s_sampleSets` dictionary.

## SampleDefinition Properties

Each sample is defined as a `SampleDefinition` in the appropriate config file. Key properties:

```csharp
new SampleDefinition
{
    // Required: Display name for the sample
    Name = "Agent_Step02_StructuredOutput",

    // Required: Relative path from dotnet/ to the sample project directory
    ProjectPath = "samples/02-agents/Agents/Agent_Step02_StructuredOutput",

    // Environment variables the sample requires (throws if missing)
    RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],

    // Environment variables with defaults that would prompt on console if unset
    OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],

    // Skip this sample with a reason (for structural issues only)
    SkipReason = null, // or "Requires external service X."

    // Deterministic checks: substrings that must appear in stdout
    MustContain = ["=== Section Header ==="],

    // Substrings that must NOT appear in stdout
    MustNotContain = [],

    // If true, only MustContain checks are used (no AI verification)
    IsDeterministic = false,

    // AI verification: natural-language descriptions of expected output
    // Each entry describes one aspect to verify independently
    ExpectedOutputDescription =
    [
        "The output should show structured person information with Name, Age, and Occupation fields.",
        "The output should not contain error messages or stack traces.",
    ],

    // Stdin inputs to feed to the sample (for interactive samples)
    Inputs = ["Y", "Y", "Y"],

    // Delay between stdin inputs in ms (default 2000, increase for LLM calls between inputs)
    InputDelayMs = 3000,
}
```

## How to Add a New Sample Definition

1. **Check the sample's Program.cs** to understand:
   - What environment variables it reads (look for `GetEnvironmentVariable`)
   - Whether it needs stdin input (look for `Console.ReadLine`, `Application.GetInput`)
   - Whether it has an external loop (look for `EXIT` patterns in YAML workflows)
   - What output it produces (section headers, markers, expected behavior)
   - Whether it exits on its own or runs as a server

2. **Choose the right verification strategy:**
   - **Deterministic** (`IsDeterministic = true`): Use `MustContain` for samples with fixed output strings. No AI verification.
   - **AI-verified** (default): Use `ExpectedOutputDescription` with semantic descriptions. Write expectations that are flexible enough for non-deterministic LLM output.
   - **Both**: Use `MustContain` for fixed markers AND `ExpectedOutputDescription` for LLM-generated content.

3. **Set `SkipReason` only for structural issues:**
   - Web servers that don't exit
   - Multi-process client/server architectures
   - Samples requiring external infrastructure (MCP servers you can't reach, Docker, etc.)
   - Do NOT skip for missing env vars — the tool checks those dynamically.

4. **For interactive samples, provide `Inputs`:**
   - Samples using `Application.GetInput(args)` need one initial input
   - Samples with `Console.ReadLine()` approval loops need `"Y"` inputs
   - YAML workflows with `externalLoop` need `"EXIT"` as the last input
   - Set `InputDelayMs` to 3000-8000ms for samples with LLM calls between inputs

5. **Add the definition** to the appropriate config file (e.g., `AgentsSamples.cs`) in the `All` list.

6. **Register new categories** (if needed) in `VerifyOptions.cs` `s_sampleSets` dictionary.

### Writing Good ExpectedOutputDescription

- Write descriptions that are **semantically flexible** — LLM output varies between runs
- Each array entry should describe **one independent aspect** to verify
- Always include `"The output should not contain error messages or stack traces."` as the last entry
- Avoid exact wording expectations — use "should mention", "should contain information about", "should show"
- Bad: `"The output should say 'The weather in Amsterdam is cloudy with a high of 15°C'"`
- Good: `"The output should contain weather information about Amsterdam mentioning cloudy weather with a high of 15°C."`

### Example: Simple LLM Sample

```csharp
new SampleDefinition
{
    Name = "Agent_With_AzureOpenAIChatCompletion",
    ProjectPath = "samples/02-agents/AgentProviders/Agent_With_AzureOpenAIChatCompletion",
    RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
    OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
    ExpectedOutputDescription =
    [
        "The output should contain a joke about a pirate.",
        "The output should not contain error messages or stack traces.",
    ],
},
```

### Example: Deterministic Sample

```csharp
new SampleDefinition
{
    Name = "Workflow_Declarative_GenerateCode",
    ProjectPath = "samples/03-workflows/Declarative/GenerateCode",
    IsDeterministic = true,
    MustContain = ["WORKFLOW: Parsing", "WORKFLOW: Defined"],
    ExpectedOutputDescription = ["The output should show a YAML workflow being parsed and C# code being generated from it."],
},
```

### Example: Interactive Sample with Approval Loop

```csharp
new SampleDefinition
{
    Name = "FoundryAgent_Hosted_MCP",
    ProjectPath = "samples/02-agents/ModelContextProtocol/FoundryAgent_Hosted_MCP",
    RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
    OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
    Inputs = ["Y", "Y", "Y", "Y", "Y"],
    InputDelayMs = 5000,
    ExpectedOutputDescription = ["The output should show an agent using the Microsoft Learn MCP tool with approval prompts."],
},
```

### Example: Declarative Workflow with External Loop

```csharp
new SampleDefinition
{
    Name = "Workflow_Declarative_FunctionTools",
    ProjectPath = "samples/03-workflows/Declarative/FunctionTools",
    RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
    OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
    Inputs = ["What are today's specials?", "EXIT"],
    InputDelayMs = 8000,
    ExpectedOutputDescription = ["The output should show a workflow calling function tools to answer a question about restaurant specials."],
},
```

### Example: Skipped Sample

```csharp
new SampleDefinition
{
    Name = "Agent_MCP_Server",
    ProjectPath = "samples/02-agents/ModelContextProtocol/Agent_MCP_Server",
    RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
    OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
    SkipReason = "Runs as an MCP stdio server that does not exit on its own.",
},
```
