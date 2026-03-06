// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use an agent with function tools that require a human in the loop for approvals.

using System.ComponentModel;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

ApprovalRequiredAIFunction approvalTool = new(AIFunctionFactory.Create(GetWeather, name: nameof(GetWeather)));

FoundryResponsesAgent agent = new(
    endpoint: new Uri(endpoint),
    tokenProvider: new DefaultAzureCredential(),
    model: deploymentName,
    instructions: "You are a helpful assistant that can get weather information.",
    name: "WeatherAssistant",
    tools: [approvalTool]);

// Call the agent with approval-required function tools.
AgentSession session = await agent.CreateSessionAsync();
AgentResponse response = await agent.RunAsync("What is the weather like in Amsterdam?", session);

// Check if there are any approval requests.
List<FunctionApprovalRequestContent> approvalRequests = response.Messages.SelectMany(m => m.Contents).OfType<FunctionApprovalRequestContent>().ToList();

while (approvalRequests.Count > 0)
{
    // Ask the user to approve each function call request.
    List<ChatMessage> userInputMessages = approvalRequests
        .ConvertAll(functionApprovalRequest =>
        {
            Console.WriteLine($"The agent would like to invoke the following function, please reply Y to approve: Name {functionApprovalRequest.FunctionCall.Name}");
            bool approved = Console.ReadLine()?.Equals("Y", StringComparison.OrdinalIgnoreCase) ?? false;
            return new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateResponse(approved)]);
        });

    response = await agent.RunAsync(userInputMessages, session);
    approvalRequests = response.Messages.SelectMany(m => m.Contents).OfType<FunctionApprovalRequestContent>().ToList();
}

Console.WriteLine($"\nAgent: {response}");
