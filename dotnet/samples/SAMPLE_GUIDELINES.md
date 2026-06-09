# Sample Guidelines

Samples are the fastest way for developers to understand Agent Framework. Keep them small, consistent, and easy to run. This document captures the authoring guidance that complements [AGENTS.md](./AGENTS.md).

## File structure

Each sample should follow this shape:

1. Copyright header: `// Copyright (c) Microsoft. All rights reserved.`
2. Summary comment block explaining what the sample demonstrates
3. Required `using` statements
4. Environment variable setup
5. Agent, tool, or workflow definitions
6. Main execution flow
7. Supporting types or helper methods at the bottom

When you change a sample, update the relevant `README.md` in the same folder or a parent folder.

## Project structure

Each sample is a standalone .NET project with its own `.csproj` file and inherits shared build settings from `Directory.Build.props`.

```text
dotnet/samples/
├── 01-get-started/          # Progressive tutorial steps 01–06
├── 02-agents/               # Deep-dive agent scenarios
├── 03-workflows/            # Workflow patterns
├── 04-hosting/              # Hosting and deployment
└── 05-end-to-end/           # Complete applications
```

## Naming conventions

- Keep the existing top-level sample folder names exactly as they are in this repo.
- Sample project folders use descriptive PascalCase names with step prefixes when helpful, such as `Agent_Step01_Basics`.
- README titles should describe the scenario first, then the specific API or provider if needed.

## Credentials and environment variables

Use `DefaultAzureCredential` for Azure-backed samples unless the sample is explicitly demonstrating a credential-specific flow.

```csharp
using Azure.Identity;

var credential = new DefaultAzureCredential();
```

### Canonical samples

For `01-get-started`, use Azure OpenAI with:

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT_NAME`

### Provider-specific or advanced samples

Use environment variables that match the provider or service being demonstrated. For example, Foundry samples use:

- `FOUNDRY_PROJECT_ENDPOINT`
- `FOUNDRY_MODEL`

If a sample needs additional variables, document them in its README.

## Documentation expectations

- Keep each sample focused on one concept or one clear progression step.
- Add section comments that explain the purpose of each block.
- Include README setup instructions and the exact `dotnet run --project ...` command.
- Add expected output when it helps users verify success.

## Snippet tags

Use named snippet markers when code is likely to be referenced from docs:

```csharp
// <create_agent>
AIAgent agent = new AzureOpenAIClient(...)
    .GetChatClient(deploymentName)
    .AsAIAgent(instructions: "...", name: "...");
// </create_agent>
```

## Cross-language alignment

Align concepts and progression with the Python samples where it improves discoverability, but preserve current .NET-specific repo conventions and folder names.
