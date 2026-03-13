// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use an agent with function tools that require a human in the loop for approvals.
// It shows both non-streaming and streaming agent interactions using weather-related tools.
// If the agent is hosted in a service, with a remote user, combine this sample with the Persisted Conversations sample to persist the chat history
// while the agent is waiting for user input.

using System.ComponentModel;
using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

// Create a sample function tool that the agent can use.
[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string AssistantInstructions = "You are a helpful assistant that can get weather information.";
const string AssistantName = "WeatherAssistant";
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

ApprovalRequiredAIFunction approvalTool = new(AIFunctionFactory.Create(GetWeather, name: nameof(GetWeather)));

PromptAgentDefinition agentDefinition = new(model: deploymentName)
{
    Instructions = AssistantInstructions,
    Tools = { approvalTool.GetService<ResponseTool>() ?? approvalTool.AsOpenAIResponseTool() ?? throw new InvalidOperationException("Unable to convert approval tool to a ResponseTool.") }
};
AgentVersion agentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(AssistantName, new AgentVersionCreationOptions(agentDefinition));
ChatClientAgent agent = aiProjectClient.AsAIAgent(agentVersion, [approvalTool]);

// Call the agent with approval-required function tools.
// The agent will request approval before invoking the function.
AgentSession session = await agent.CreateSessionAsync();
AgentResponse response = await agent.RunAsync("What is the weather like in Amsterdam?", session);

// Check if there are any approval requests.
// For simplicity, we are assuming here that only function approvals are pending.
List<ToolApprovalRequestContent> approvalRequests = response.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().ToList();

while (approvalRequests.Count > 0)
{
    // Ask the user to approve each function call request.
    List<ChatMessage> userInputMessages = approvalRequests
        .ConvertAll(functionApprovalRequest =>
        {
            Console.WriteLine($"The agent would like to invoke the following function, please reply Y to approve: Name {((FunctionCallContent)functionApprovalRequest.ToolCall).Name}");
            bool approved = Console.ReadLine()?.Equals("Y", StringComparison.OrdinalIgnoreCase) ?? false;
            return new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateResponse(approved)]);
        });

    // Pass the user input responses back to the agent for further processing.
    response = await agent.RunAsync(userInputMessages, session);

    approvalRequests = response.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().ToList();
}

Console.WriteLine($"\nAgent: {response}");

// Cleanup: deletes the agent and all its versions.
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
