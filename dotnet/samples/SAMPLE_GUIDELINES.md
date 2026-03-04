# Sample Guidelines — .NET

Samples are extremely important for developers to get started with Agent Framework. We strive to provide a wide range of samples that demonstrate the capabilities of Agent Framework with consistency and quality. This document outlines the guidelines for creating .NET samples.

## Project Structure

Every sample is a standalone C# project with the following structure:

```
<sample_name>/
├── <sample_name>.csproj    # Project file
├── Program.cs              # Main entry point
└── README.md               # (optional) Sample-specific docs
```

### Getting Started Samples (01-get-started)

Named as `NN_snake_case/` (e.g., `01_hello_agent/`, `02_add_tools/`). Each step builds on the previous and demonstrates exactly one concept.

### Concept Samples (02-agents through 05-end-to-end)

Named as `Category_StepNN_PascalCase/` (e.g., `Agent_Step01_UsingFunctionToolsWithApprovals/`).

## .csproj Conventions

- Target `net10.0`
- Use central package management (`Directory.Build.props` / `Directory.Packages.props`)
- Use `ProjectReference` to framework source (not NuGet packages)
- Do not add `<PackageVersion>` attributes — versions are centrally managed

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFrameworks>net10.0</TargetFrameworks>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Azure.AI.Projects.OpenAI" />
    <PackageReference Include="Azure.Identity" />
    <PackageReference Include="Microsoft.Extensions.AI.OpenAI" />
  </ItemGroup>
  <ItemGroup>
    <ProjectReference Include="..\..\..\src\Microsoft.Agents.AI\Microsoft.Agents.AI.csproj" />
  </ItemGroup>
</Project>
```

## Default Provider Pattern

All get-started samples use **Azure AI Foundry** via `ProjectResponsesClient`:

```csharp
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

IChatClient chatClient = new ProjectResponsesClient(
    projectEndpoint: new Uri(endpoint),
    tokenProvider: new DefaultAzureCredential())
    .AsIChatClient();

ChatClientAgent agent = new(chatClient, new ChatClientAgentOptions
{
    Name = "...",
    ChatOptions = new() { ModelId = deploymentName, Instructions = "..." },
});
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AZURE_AI_PROJECT_ENDPOINT` | Azure AI Foundry project endpoint | _(required)_ |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Model deployment name | `gpt-4o-mini` |

For authentication, run `az login` before running samples.

## Snippet Tags

All get-started samples must include named snippet regions for `:::code` doc integration:

```csharp
// <snippet_name>
code here
// </snippet_name>
```

Standard snippet IDs by sample:

| Sample | Snippet IDs |
|--------|-------------|
| 01_hello_agent | `create_agent`, `run_agent`, `run_agent_streaming` |
| 02_add_tools | `define_tool`, `create_agent_with_tools`, `run_agent` |
| 03_multi_turn | `create_agent`, `multi_turn` |
| 04_memory | `context_provider`, `create_agent`, `run_with_memory` |
| 05_first_workflow | `create_workflow`, `run_workflow` |
| 06_host_your_agent | `create_agent`, `host_agent` |

## General Guidelines

- **Clear and Concise**: Demonstrate a specific feature or capability. The fewer concepts per sample, the better.
- **Consistent Structure**: Follow naming conventions and project layout.
- **Incremental Complexity**: Start simple and gradually increase. Each getting-started step should build on the previous.
- **Prefer explicit construction**: Use `new ChatClientAgent(chatClient, ...)` rather than `.AsAIAgent(...)` extension methods for clarity.
- **Documentation**: Include a copyright header, descriptive comments, and a file-level comment explaining the sample's purpose.

## Building and Running

All samples use project references to the framework source:

```bash
cd dotnet/samples/01-get-started/01_hello_agent
dotnet run
```
