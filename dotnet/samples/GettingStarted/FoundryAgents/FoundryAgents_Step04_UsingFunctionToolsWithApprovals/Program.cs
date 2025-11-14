// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use an agent with function tools that require a human in the loop for approvals.
// It shows both non-streaming and streaming agent interactions using weather-related tools.
// If the agent is hosted in a service, with a remote user, combine this sample with the Persisted Conversations sample to persist the chat history
// while the agent is waiting for user input.

using System.ComponentModel;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create a sample function tool that the agent can use.
[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

const string AssistantInstructions = "You are a helpful assistant that can get weather information.";
const string AssistantName = "WeatherAssistant";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

ApprovalRequiredAIFunction approvalTool = new(AIFunctionFactory.Create(GetWeather));

// Create AIAgent directly
AIAgent agent = await aiProjectClient.CreateAIAgentAsync(name: AssistantName, model: deploymentName, instructions: AssistantInstructions, tools: [approvalTool]);

// Call the agent with approval-required function tools.
// The agent will request approval before invoking the function.
AgentThread thread = agent.GetNewThread();
AgentRunResponse response = await agent.RunAsync("What is the weather like in Amsterdam?", thread);

// Check if there are any user input requests (approvals needed).
List<UserInputRequestContent> userInputRequests = response.UserInputRequests.ToList();

while (userInputRequests.Count > 0)
{
    // Ask the user to approve each function call request.
    // For simplicity, we are assuming here that only function approval requests are being made.
    List<ChatMessage> userInputMessages = userInputRequests
        .OfType<FunctionApprovalRequestContent>()
        .Select(functionApprovalRequest =>
        {
            Console.WriteLine($"The agent would like to invoke the following function, please reply Y to approve: Name {functionApprovalRequest.FunctionCall.Name}");
            bool approved = Console.ReadLine()?.Equals("Y", StringComparison.OrdinalIgnoreCase) ?? false;
            return new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateResponse(approved)]);
        })
        .ToList();

    // Pass the user input responses back to the agent for further processing.
    response = await agent.RunAsync(userInputMessages, thread);

    userInputRequests = response.UserInputRequests.ToList();
}

Console.WriteLine($"\nAgent: {response}");

// Cleanup by agent name removes the agent version created.
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
