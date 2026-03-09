// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use an agent with function tools that require a human in the loop for approvals.
// It shows both non-streaming and streaming agent interactions using weather-related tools.
// If the agent is hosted in a service, with a remote user, combine this sample with the Persisted Conversations sample to persist the chat history
// while the agent is waiting for user input.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;

// Create a sample function tool that the agent can use.
[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

const string AssistantInstructions = "You are a helpful assistant that can get weather information.";
const string AssistantName = "WeatherAssistant";

ApprovalRequiredAIFunction approvalTool = new(AIFunctionFactory.Create(GetWeather, name: nameof(GetWeather)));

// Create AIAgent directly
FoundryVersionedAgent agent = await FoundryVersionedAgent.CreateAIAgentAsync(name: AssistantName, instructions: AssistantInstructions, tools: [approvalTool]);

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
await FoundryVersionedAgent.DeleteAIAgentAsync(agent);
