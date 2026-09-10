// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use Agent Skills with a FoundryAgent backed by a
// server-side versioned agent.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Extensions.AI;

// --- Configuration ---
string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

const string AgentName = "AgentSkillsAgent";

// --- Define an Agent Skill ---
var supportSkill = new AgentInlineSkill(
    name: "support-policy",
    description: "Example support response-time policy.",
    instructions: """
        Use this skill when answering questions about support response times or escalation.

        Read the response-times resource before answering the user.
        """)
    .AddResource(
        "response-times",
        """
        # Example Support Response Times

        - Severity 1: Initial response within 15 minutes.
        - Severity 2: Initial response within 1 hour.
        - Severity 3: Initial response within 4 hours.

        These values are illustrative, used only by this sample.
        """);

var skillsProvider = new AgentSkillsProvider(supportSkill);

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// --- Create a server-side versioned Foundry agent ---
ProjectsAgentVersion agentVersion = await aiProjectClient.AgentAdministrationClient.CreateAgentVersionAsync(
    AgentName,
    new ProjectsAgentVersionCreationOptions(
        new DeclarativeAgentDefinition(model: deploymentName)
        {
            Instructions = "You are a helpful support assistant. Use available skills when relevant.",
        }));

try
{
    FoundryAgent foundryAgent = aiProjectClient.AsAIAgent(
        agentVersion,
        tools: null,
        clientFactory: inner => inner
            .AsBuilder()
            .UseAIContextProviders(skillsProvider)
            .Build());

    AIAgent agent = foundryAgent
        .AsBuilder()
        .UseToolApproval(new ToolApprovalAgentOptions
        {
            AutoApprovalRules = [AgentSkillsProvider.ReadOnlyToolsAutoApprovalRule],
        })
        .Build();

    Console.WriteLine(await agent.RunAsync(
        "According to the support policy, how quickly should a Severity 1 incident receive an initial response?"));
}
finally
{
    // Cleanup: deletes the agent and all its versions.
    await aiProjectClient.AgentAdministrationClient.DeleteAgentAsync(AgentName);
}
