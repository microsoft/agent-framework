// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use file-based Agent Skills with a ChatClientAgent.
// Skills are discovered from SKILL.md files on disk and follow the progressive disclosure pattern:
// 1. Advertise — skill names and descriptions in the system prompt
// 2. Load — full instructions loaded on demand via load_skill tool
// 3. Read resources — reference files read via read_skill_resource tool
// 4. Run scripts — scripts executed via run_skill_script tool with a subprocess executor
//
// This sample uses a unit-converter skill that converts between miles, kilometers, pounds, and kilograms.

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
            Instructions = "You are a helpful assistant that can convert units.",
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
