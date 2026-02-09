// Copyright (c) Microsoft. All rights reserved.

// Tool Approval (Human-in-the-Loop)
// Require human approval before the agent invokes sensitive function tools.
// Uses ApprovalRequiredAIFunction to gate tool invocation.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/tools

using System.ComponentModel;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

// <approval_tool>
ApprovalRequiredAIFunction approvalTool = new(AIFunctionFactory.Create(GetWeather, name: nameof(GetWeather)));

AIAgent agent = await aiProjectClient.CreateAIAgentAsync(
    name: "WeatherAssistant",
    model: deploymentName,
    instructions: "You are a helpful assistant that can get weather information.",
    tools: [approvalTool]);
// </approval_tool>

// <handle_approval>
AgentSession session = await agent.CreateSessionAsync();
AgentResponse response = await agent.RunAsync("What is the weather like in Amsterdam?", session);

List<FunctionApprovalRequestContent> approvalRequests = response.Messages
    .SelectMany(m => m.Contents).OfType<FunctionApprovalRequestContent>().ToList();

while (approvalRequests.Count > 0)
{
    List<ChatMessage> userInputMessages = approvalRequests
        .ConvertAll(req =>
        {
            Console.WriteLine($"The agent would like to invoke: {req.FunctionCall.Name}. Reply Y to approve:");
            bool approved = Console.ReadLine()?.Equals("Y", StringComparison.OrdinalIgnoreCase) ?? false;
            return new ChatMessage(ChatRole.User, [req.CreateResponse(approved)]);
        });

    response = await agent.RunAsync(userInputMessages, session);
    approvalRequests = response.Messages.SelectMany(m => m.Contents).OfType<FunctionApprovalRequestContent>().ToList();
}

Console.WriteLine($"\nAgent: {response}");
// </handle_approval>

await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
