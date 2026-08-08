// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use file-based Agent Skills with a ChatClientAgent.
// Skills are discovered from SKILL.md files on disk and follow the progressive disclosure pattern:
// 1. Advertise — skill names and descriptions in the system prompt
// 2. Load — full instructions loaded on demand via load_skill tool
// 3. Read resources — reference files read via read_skill_resource tool
// 4. Run scripts — scripts executed via run_skill_script tool with a subprocess executor
//
// This sample uses two skills:
// - unit-converter: converts between miles, kilometers, pounds, and kilograms.
// - temperature-converter: marked with 'advertise: false' in its frontmatter, so it is NOT listed
//   in the system prompt. It remains loadable by name via the load_skill tool, which the agent's
//   own instructions point it to. Use this to keep the system prompt small or to reserve skills
//   for explicit invocation.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;

// --- Configuration ---
string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

// --- Skills Provider ---
// Discovers skills from the 'skills' directory containing SKILL.md files.
// The script runner runs file-based scripts (e.g. Python) as local subprocesses.
var skillsProvider = new AgentSkillsProvider(
    Path.Combine(AppContext.BaseDirectory, "skills"),
    SubprocessScriptRunner.RunAsync);

// --- Agent Setup ---
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = "UnitConverterAgent",
        ChatOptions = new()
        {
            ModelId = deploymentName,
            // The temperature-converter skill is not advertised (advertise: false), so the model
            // only knows about it because these instructions reference it by name.
            Instructions = "You are a helpful assistant that can convert units. For temperature conversions, load the 'temperature-converter' skill.",
        },
        AIContextProviders = [skillsProvider],
    })
    .AsBuilder()
    .UseToolApproval(new ToolApprovalAgentOptions
    {
        // NOTE: Auto-approving all skill tools is done here for simplicity in
        // this demonstration. In production, you should prompt the user before
        // allowing script execution. See Agent_Step07_SkillsAutoApproval for a
        // walkthrough of the full approval flow.
        AutoApprovalRules = [AgentSkillsProvider.AllToolsAutoApprovalRule],
    })
    .Build();

// --- Example: Unit conversion ---
Console.WriteLine("Converting units with file-based skills");
Console.WriteLine(new string('-', 60));

AgentResponse response = await agent.RunAsync(
    "How many kilometers is a marathon (26.2 miles)? And how many pounds is 75 kilograms?");

Console.WriteLine($"Agent: {response.Text}");

// --- Example: Unadvertised skill ---
// The temperature-converter skill is excluded from the system prompt's skill listing
// (advertise: false), but the agent can still load it because its instructions mention it.
Console.WriteLine();
Console.WriteLine("Converting temperatures with an unadvertised skill");
Console.WriteLine(new string('-', 60));

response = await agent.RunAsync("What is 100 degrees Fahrenheit in Celsius?");

Console.WriteLine($"Agent: {response.Text}");
