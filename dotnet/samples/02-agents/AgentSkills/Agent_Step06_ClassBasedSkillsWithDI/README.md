# Class-Based Agent Skills with Dependency Injection

This sample demonstrates how to use **Dependency Injection (DI)** with **class-based Agent Skills** (`AgentClassSkill`).

## What It Shows

- Defining a skill as a class that extends `AgentClassSkill`
- Using `IServiceProvider` in skill resource delegates to resolve services from the DI container
- Using `IServiceProvider` in skill script delegates to resolve services from the DI container
- Registering application services in a `ServiceCollection` and passing the built provider to the agent

## How It Works

1. A `ConversionRateService` is registered as a singleton in the DI container
2. `UnitConverterSkill` extends `AgentClassSkill` and declares its resources and scripts using `CreateResource` and `CreateScript` factory methods
3. The resource delegate declares `IServiceProvider` as a parameter — the framework injects it automatically
4. The resource resolves `ConversionRateService` from the provider to build a supported-conversions table dynamically
5. The script delegate also declares `IServiceProvider` as a parameter to look up conversion factors at runtime
6. The agent is created with the service provider, which flows through to skill resource and script execution

## How It Differs from Other Samples

| Sample | Skill Type | DI Support |
|--------|-----------|------------|
| [Step03](../Agent_Step03_ClassBasedSkills/) | Class-based (`AgentClassSkill`) | No — static resources |
| [Step05](../Agent_Step05_CodeDefinedSkillsWithDI/) | Code-defined (`AgentInlineSkill`) | Yes — inline delegates |
| **Step06 (this)** | **Class-based (`AgentClassSkill`)** | **Yes — class delegates** |

## Prerequisites

- .NET 10
- An Azure OpenAI deployment

## Configuration

Set the following environment variables:

| Variable | Description |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | Your Azure OpenAI endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Model deployment name (defaults to `gpt-4o-mini`) |

## Running the Sample

```bash
dotnet run
```

### Expected Output

```
Converting units with DI-powered class-based skills
------------------------------------------------------------
Agent: Here are your conversions:

1. **26.2 miles → 42.16 km** (a marathon distance)
2. **75 kg → 165.35 lbs**
```
