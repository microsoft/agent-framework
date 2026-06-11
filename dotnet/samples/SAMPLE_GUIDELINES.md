<!-- Copyright (c) Microsoft. All rights reserved. -->

# .NET Samples Guidelines

This document establishes standardized conventions for creating and maintaining samples in the `dotnet/samples/` directory. It complements `AGENTS.md` (which documents structural decisions) with practical guidelines for implementation.

## Environment Variables

All samples use **environment variables** for configuration. Never hardcode credentials, endpoints, or deployment names.

### Foundry Samples Standard

Samples that use Microsoft Foundry must set:

- `FOUNDRY_PROJECT_ENDPOINT` — Your Foundry project endpoint URL
  - Example: `https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project`
- `FOUNDRY_MODEL` — The model name to use
  - Example: `gpt-5.4-mini`

### Azure OpenAI Samples

Samples using Azure OpenAI must set:

- `AZURE_OPENAI_ENDPOINT` — Your Azure OpenAI endpoint
- `AZURE_OPENAI_DEPLOYMENT_NAME` — Your deployment name (defaults to `gpt-5.4-mini` if not set)

### Other Providers

Samples for other providers (OpenAI, Anthropic, Gemini, Ollama, etc.) define their own environment variables in their respective README files.

## Credentials

### DefaultAzureCredential (Recommended)

All canonical samples use `DefaultAzureCredential` from `Azure.Identity`. This credential chain checks multiple credential sources (environment, managed identity, Azure CLI, etc.) and is recommended for production use in Azure environments.

**Important warning**: Always include this comment in sample files using `DefaultAzureCredential`:

```csharp
// WARNING: DefaultAzureCredential is convenient for development but requires careful 
// consideration in production. In production, consider using a specific credential 
// (e.g., ManagedIdentityCredential) to avoid latency issues, unintended credential 
// probing, and potential security risks from fallback mechanisms.
```

**For local development**: Run `az login` before running samples to authenticate with Azure CLI.

### Language-Specific Standards

- **.NET samples**: Use `DefaultAzureCredential` (see section above)
- **Python samples**: Use `AzureCliCredential` (per `python/samples/SAMPLE_GUIDELINES.md`)

## Code Structure

1. **Copyright header** — Start every `.cs` file with:
   ```csharp
   // Copyright (c) Microsoft. All rights reserved.
   ```

2. **Description comment** — Add a brief comment explaining what the sample demonstrates

3. **Using statements** — Group by namespace:
   - System namespaces first
   - Azure/Microsoft namespaces next
   - Project namespaces last

4. **Main code logic** — Keep `Program.cs` focused and linear for readability

5. **Helper methods** — Place at bottom of file

Example structure:

```csharp
// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to create and run a simple agent with the Foundry service.

using Azure.Identity;
using Microsoft.Agents.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful 
// consideration in production. In production, consider using a specific credential 
// (e.g., ManagedIdentityCredential) to avoid latency issues, unintended credential 
// probing, and potential security risks from fallback mechanisms.
FoundryAgent agent = new(
    new Uri(endpoint),
    new DefaultAzureCredential(),
    model: model,
    instructions: "You are a helpful assistant.",
    name: "MyAgent");

Console.WriteLine(await agent.RunAsync("Hello, tell me about yourself."));
```

## README Requirements

Every sample must include a `README.md` that documents:

1. **Title** — Clear, concise description of what the sample demonstrates

2. **Overview** — 1–3 sentences explaining the sample's purpose

3. **Prerequisites** — Required tools, environment variables, and setup steps
   - List required environment variables
   - For local development: "Run `az login` to authenticate with Azure"
   - Other tool requirements (e.g., Docker, Node.js)

4. **How to run** — Step-by-step instructions
   ```bash
   cd path/to/sample
   dotnet run
   ```

5. **Expected output** — Example output or behavior description

6. **Key concepts** — Brief explanation of what the sample teaches

Example README structure:

```markdown
# My Sample Name

This sample demonstrates [what it demonstrates].

## Prerequisites

- .NET 10 SDK or later
- Foundry project endpoint and credentials
- Environment variables:
  - `FOUNDRY_PROJECT_ENDPOINT` — Your Foundry project endpoint
  - `FOUNDRY_MODEL` — Model name (e.g., `gpt-5.4-mini`)
- For local development, run `az login` to authenticate

## How to run

1. Navigate to this directory
2. Run the sample: `dotnet run`

## Expected output

[Describe what output the user should expect]

## Key concepts

- [Concept 1]: [Brief explanation]
- [Concept 2]: [Brief explanation]
```

## Provider Examples

Samples demonstrating specific providers (Azure OpenAI, OpenAI, Anthropic, etc.) should be organized under `02-agents/AgentProviders/[Provider]/` following the pattern:

- `Azure OpenAI/` — Azure OpenAI samples (uses `AzureOpenAIClient`)
- `OpenAI/` — OpenAI samples (uses `OpenAIClient`)
- `Anthropic/` — Anthropic samples
- `Gemini/` — Google Gemini samples
- `Ollama/` — Ollama local inference samples
- `Foundry/` — Microsoft Foundry samples (uses `FoundryAgent` or `AIProjectClient`)

Each provider directory contains focused samples demonstrating provider-specific capabilities and API patterns.

## Testing Samples

Use the built-in verification framework in `dotnet/eng/verify-samples/` to ensure all samples build successfully:

```bash
cd dotnet/eng/verify-samples
dotnet test
```

Before committing sample changes:

1. Build the sample locally: `dotnet build`
2. Run the sample locally (if practical): `dotnet run`
3. Ensure sample-level build succeeds in CI: `dotnet test` from verify-samples directory

## Common Patterns

### Async/Await

All async methods use the `Async` suffix:

```csharp
var response = await agent.RunAsync("prompt");
```

### Error Handling

Use `InvalidOperationException` for missing required configuration:

```csharp
var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
```

### Agent Instantiation

Prefer the extension method pattern for creating agents:

```csharp
// Foundry
FoundryAgent agent = new(
    new Uri(endpoint),
    new DefaultAzureCredential(),
    model: model,
    instructions: "...",
    name: "...");

// Alternative: Using AIProjectClient extensions
AIProjectClient client = new(new Uri(endpoint), new DefaultAzureCredential());
FoundryAgent agent = client.AsAIAgent(model, instructions, name);

// Azure OpenAI
AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(instructions: "...", name: "...");
```

### Multi-Turn Conversations

Use `AgentSession` for managing conversation state:

```csharp
using (AgentSession session = agent.CreateSession())
{
    var response1 = await session.SendAsync("First message");
    var response2 = await session.SendAsync("Follow-up message");
}
```

## See Also

- `AGENTS.md` — Structural decisions and design principles
- `.github/skills/build-and-test/SKILL.md` — Build and test commands
- `python/samples/SAMPLE_GUIDELINES.md` — Python sample conventions
