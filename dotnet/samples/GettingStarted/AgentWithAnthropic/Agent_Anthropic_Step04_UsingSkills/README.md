# Using Anthropic Skills with agents

This sample demonstrates how to use Anthropic-managed Skills with AI agents. Skills are pre-built capabilities provided by Anthropic that can be used with the Claude API.

## What this sample demonstrates

- Listing available Anthropic-managed skills
- Creating an AI agent with Anthropic Claude Skills support using the simplified `AsAITool()` approach
- Using the pptx skill to create PowerPoint presentations
- Downloading and saving generated files to disk
- Handling agent responses with generated content

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10.0 SDK or later
- Anthropic API key configured
- Access to Anthropic Claude models with Skills support

**Note**: This sample uses Anthropic Claude models with Skills. Skills are a beta feature. For more information, see [Anthropic documentation](https://docs.anthropic.com/).

Set the following environment variables:

```powershell
$env:ANTHROPIC_API_KEY="your-anthropic-api-key"  # Replace with your Anthropic API key
$env:ANTHROPIC_MODEL="your-anthropic-model"  # Replace with your Anthropic model (e.g., claude-sonnet-4-5-20250929)
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
- `xlsx` - Create Excel spreadsheets
- `docx` - Create Word documents
- `pdf` - Create and analyze PDF documents

You can list available skills using the Anthropic SDK:

```csharp
SkillListPage skills = await anthropicClient.Beta.Skills.List(
    new SkillListParams { Source = "anthropic", Betas = [AnthropicBeta.Skills2025_10_02] });

foreach (var skill in skills.Items)
{
    Console.WriteLine($"{skill.Source}: {skill.ID} (version: {skill.LatestVersion})");
}
```

## Expected behavior

The sample will:

1. List all available Anthropic-managed skills
2. Create an agent with the pptx skill enabled
3. Run the agent with a request to create a presentation
4. Display the agent's response text
5. Download any generated files and save them to disk
6. Display token usage statistics

## Code highlights

### Simplified skill configuration

The Anthropic SDK handles all beta flags and container configuration automatically when using `AsAITool()`:

```csharp
// Define the pptx skill
BetaSkillParams pptxSkill = new()
{
    Type = BetaSkillParamsType.Anthropic,
    SkillID = "pptx",
    Version = "latest"
};

// Create an agent - the SDK handles beta flags automatically!
ChatClientAgent agent = anthropicClient.Beta.AsAIAgent(
    model: model,
    instructions: "You are a helpful agent for creating PowerPoint presentations.",
    tools: [pptxSkill.AsAITool()]);
```

**Note**: No manual `RawRepresentationFactory`, `Betas`, or `Container` configuration is needed. The SDK automatically adds the required beta headers (`skills-2025-10-02`, `code-execution-2025-08-25`) and configures the container with the skill.

### Handling generated files

Generated files are returned as `HostedFileContent` within `CodeInterpreterToolResultContent`:

```csharp
// Collect generated files from response
List<HostedFileContent> hostedFiles = response.Messages
    .SelectMany(m => m.Contents.OfType<CodeInterpreterToolResultContent>())
    .Where(c => c.Outputs is not null)
    .SelectMany(c => c.Outputs!.OfType<HostedFileContent>())
    .ToList();

// Download and save each file
foreach (HostedFileContent file in hostedFiles)
{
    using HttpResponse fileResponse = await anthropicClient.Beta.Files.Download(
        file.FileId,
        new FileDownloadParams { Betas = ["files-api-2025-04-14"] });

    string fileName = $"presentation_{file.FileId.Substring(0, 8)}.pptx";
    await using FileStream fileStream = File.Create(fileName);
    Stream contentStream = await fileResponse.ReadAsStream();
    await contentStream.CopyToAsync(fileStream);
}
```
