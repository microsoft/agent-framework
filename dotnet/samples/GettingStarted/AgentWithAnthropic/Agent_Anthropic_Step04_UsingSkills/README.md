# Using Anthropic Skills with agents

This sample demonstrates how to use Anthropic-managed Skills with AI agents. Skills are pre-built capabilities provided by Anthropic that can be used with the Claude API.

## What this sample demonstrates

- Creating an AI agent with Anthropic Claude Skills support
- Using the `BetaSkillParams.AsAITool()` extension method to add skills as tools
- Configuring beta flags required for skills
- Using the pptx skill to create PowerPoint presentations
- Handling agent responses with generated content

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10.0 SDK or later
- Anthropic API key configured
- Access to Anthropic Claude models with Skills support

**Note**: This sample uses Anthropic Claude models with Skills. Skills are a beta feature and require specific beta flags. For more information, see [Anthropic documentation](https://docs.anthropic.com/).

Set the following environment variables:

```powershell
$env:ANTHROPIC_API_KEY="your-anthropic-api-key"  # Replace with your Anthropic API key
$env:ANTHROPIC_MODEL="your-anthropic-model"  # Replace with your Anthropic model (e.g., claude-sonnet-4-20250514)
```

## Run the sample

Navigate to the AgentWithAnthropic sample directory and run:

```powershell
cd dotnet\samples\GettingStarted\AgentWithAnthropic
dotnet run --project .\Agent_Anthropic_Step04_UsingSkills
```

## Available Anthropic Skills

Anthropic provides several managed skills that can be used with the Claude API:

- `pptx` - Create PowerPoint presentations
- Other skills may be available depending on your API access

You can list available skills using the Anthropic SDK:

```csharp
var skills = await client.Beta.Skills.List(
    new SkillListParams { Source = "anthropic", Betas = [AnthropicBeta.Skills2025_10_02] });
foreach (var skill in skills.Data)
{
    Console.WriteLine($"{skill.Source}: {skill.ID} (version: {skill.LatestVersion})");
}
```

## Expected behavior

The sample will:

1. Create an agent with Anthropic Claude Skills enabled (pptx skill)
2. Run the agent with a request to create a presentation
3. Display the agent's response text
4. Display any reasoning/thinking content
5. Display information about any generated files
6. Display token usage statistics

## Code highlights

The key part of this sample is defining the skill configuration and adding it as an AI tool:

```csharp
// Define the pptx skill configuration once to avoid duplication
BetaSkillParams pptxSkill = new()
{
    Type = BetaSkillParamsType.Anthropic,
    SkillID = "pptx",
    Version = "latest"
};

// Add to tools array
tools: [pptxSkill.AsAITool()]
```

And configuring the container with skills in the raw representation:

```csharp
Container = new BetaContainerParams() { Skills = [pptxSkill] }
```
