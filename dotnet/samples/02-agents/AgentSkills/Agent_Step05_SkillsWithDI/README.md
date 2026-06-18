# Agent Skills with Dependency Injection

This sample demonstrates how to use **Dependency Injection (DI)** with Agent Skills. It shows two approaches side-by-side, each handling a different conversion domain:

1. **Code-defined skill** (`AgentInlineSkill`) — converts **distances** (miles ↔ kilometers)
2. **Class-based skill** (`AgentClassSkill`) — converts **weights** (pounds ↔ kilograms)

Both skills resolve the same `ConversionService` from the DI container. When prompted with a question spanning both domains, the agent uses both skills.

## What It Shows

- Registering application services in a `ServiceCollection`
- Defining a **code-defined** skill (distance converter) with resources and scripts that resolve services from `IServiceProvider`
- Defining a **class-based** skill (weight converter) with resources and scripts that resolve services from `IServiceProvider`
- Passing the built `IServiceProvider` to the agent so skills can access DI services at execution time
- Running a single prompt that exercises both skills to show they work together

## How It Works

1. A `ConversionService` is registered as a singleton in the DI container
2. **Code-defined skill**: An `AgentInlineSkill` for distance conversions declares `IServiceProvider` as a parameter in its `AddResource` and `AddScript` delegates — the framework injects it automatically
3. **Class-based skill**: A `WeightConverterSkill` class extends `AgentClassSkill` for weight conversions and uses `CreateResource`/`CreateScript` factory methods with `IServiceProvider` parameters
4. Both skills resolve `ConversionService` from the provider — one for distance tables, the other for weight tables
5. A single agent is created with both skills registered, and the service provider flows through to skill execution

> **Tip:** Class-based skills can also accept dependencies through their **constructor**. Register the skill class in the `ServiceCollection` and resolve it from the container instead of calling `new` directly. This is useful when the skill itself needs injected services beyond what the resource/script delegates use.

## How It Differs from Other Samples

| Sample | Skill Type | DI Support |
|--------|------------|------------|
| [Step02](../Agent_Step02_CodeDefinedSkills/) | Code-defined (`AgentInlineSkill`) | No — static resources |
| [Step03](../Agent_Step03_ClassBasedSkills/) | Class-based (`AgentClassSkill`) | No — static resources |
| **Step05 (this)** | **Both code-defined and class-based** | **Yes — DI via `IServiceProvider`** |

## Prerequisites

- .NET 10
- An Azure OpenAI deployment

## Configuration

Set the following environment variables:

| Variable | Description |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | Your Azure OpenAI endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Model deployment name (defaults to `gpt-5.4-mini`) |

## Running the Sample

```bash
dotnet run
```

### Expected Output

```
Converting units with DI-powered skills
------------------------------------------------------------
Agent: Here are your conversions:

1. **26.2 miles → 42.16 km** (a marathon distance)
2. **75 kg → 165.35 lbs**
```
