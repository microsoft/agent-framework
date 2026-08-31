// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to configure auto-approval rules for skill tools using the
// UseToolApproval middleware. It builds on the file-based skills pattern from Step01, adding
// ToolApprovalAgent middleware with auto-approval rules so that read-only skill operations
// (load_skill, read_skill_resource) are approved automatically while script execution
// (run_skill_script) still requires explicit user approval.
//
// All tools exposed by AgentSkillsProvider always require approval by default.
// Auto-approval rules let you selectively bypass the approval prompt for safe operations.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

// --- Configuration ---
string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

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
AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential())
    .GetResponsesClient()
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = "UnitConverterAgent",
        ChatOptions = new()
        {
            Instructions = "You are a helpful assistant that can convert units.",
        },
        AIContextProviders = [skillsProvider],
    },
    model: deploymentName)
    .AsBuilder()
    .UseToolApproval(new ToolApprovalAgentOptions
    {
        // Auto-approve read-only skill tools (load_skill, read_skill_resource).
        // run_skill_script will still require explicit user approval.
        AutoApprovalRules = [AgentSkillsProvider.ReadOnlyToolsAutoApprovalRule],
    })
    .Build();

// For other auto-approval options (all tools, custom lambdas, combining providers),
// see the README.md in this sample directory.

// --- Example: Unit conversion with auto-approval ---
Console.WriteLine("Converting units with file-based skills and auto-approval");
Console.WriteLine(new string('-', 60));

AgentSession session = await agent.CreateSessionAsync();
AgentResponse response = await agent.RunAsync(
    "How many kilometers is a marathon (26.2 miles)? And how many pounds is 75 kilograms?",
    session);

// Handle any pending approval requests (only script execution should require approval)
List<ToolApprovalRequestContent> approvalRequests = response.Messages
    .SelectMany(m => m.Contents)
    .OfType<ToolApprovalRequestContent>()
    .ToList();

while (approvalRequests.Count > 0)
{
    List<ChatMessage> userInputResponses = approvalRequests
        .ConvertAll(functionApprovalRequest =>
        {
            var toolCall = (FunctionCallContent)functionApprovalRequest.ToolCall;
            Console.WriteLine($"Approval required for: {toolCall.Name}. Reply Y to approve:");
            bool approved = Console.ReadLine()?.Equals("Y", StringComparison.OrdinalIgnoreCase) ?? false;
            return new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateResponse(approved)]);
        });

    response = await agent.RunAsync(userInputResponses, session);
    approvalRequests = response.Messages
        .SelectMany(m => m.Contents)
        .OfType<ToolApprovalRequestContent>()
        .ToList();
}

Console.WriteLine($"Agent: {response.Text}");
