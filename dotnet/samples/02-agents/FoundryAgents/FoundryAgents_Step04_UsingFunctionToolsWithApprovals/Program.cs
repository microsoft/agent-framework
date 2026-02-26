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

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create a sample function tool that the agent can use.
[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

const string AssistantInstructions = "You are a helpful assistant that can get weather information.";
const string AssistantName = "WeatherAssistant";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

ApprovalRequiredAIFunction approvalTool = new(AIFunctionFactory.Create(GetWeather, name: nameof(GetWeather)));

// Create AIAgent directly
AIAgent agent = await aiProjectClient.CreateAIAgentAsync(name: AssistantName, model: deploymentName, instructions: AssistantInstructions, tools: [approvalTool]);

// Call the agent with approval-required function tools.
// The agent will request approval before invoking the function.
AgentSession session = await agent.CreateSessionAsync();
AgentResponse response = await agent.RunAsync("What is the weather like in Amsterdam?", session);

// Check if there are any approval requests.
// For simplicity, we are assuming here that only function approvals are pending.
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

    // Pass the user input responses back to the agent for further processing.
    response = await agent.RunAsync(userInputMessages, session);

    approvalRequests = response.Messages.SelectMany(m => m.Contents).OfType<FunctionApprovalRequestContent>().ToList();
}

Console.WriteLine($"\nAgent: {response}");

// Cleanup by agent name removes the agent version created.
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
