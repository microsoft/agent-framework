// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use a ChatClientAgent with function tools that require a human in the loop for approvals.
// It shows both non-streaming and streaming agent interactions using menu-related tools.
// If the agent is hosted in a service, with a remote user, combine this sample with the Persisted Conversations sample to persist the chat history
// while the agent is waiting for user input.

using System.ComponentModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create a sample function tool that the agent can use.
[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

// Create the chat client and agent.
// Note that we are wrapping the function tool with ApprovalRequiredAIFunction to require user approval before invoking it.
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetChatClient(deploymentName)
    .CreateAIAgent(instructions: "You are a helpful assistant", tools: [new ApprovalRequiredAIFunction(AIFunctionFactory.Create(GetWeather))]);

// Call the agent and check if there are any user input requests to handle.
AgentThread thread = agent.GetNewThread();
var response = await agent.RunAsync("What is the weather like in Amsterdam?", thread);
var userInputRequests = response.UserInputRequests.ToList();

// For streaming use:
// var updates = await agent.RunStreamingAsync("What is the weather like in Amsterdam?", thread).ToListAsync();
// userInputRequests = updates.SelectMany(x => x.UserInputRequests).ToList();

while (userInputRequests.Count > 0)
{
    // Ask the user to approve each function call request.
    // For simplicity, we are assuming here that only function approval requests are being made.
    var userInputResponses = userInputRequests
        .OfType<FunctionApprovalRequestContent>()
        .Select(functionApprovalRequest =>
        {
            Console.WriteLine($"The agent would like to invoke the following function, please reply Y to approve: Name {functionApprovalRequest.FunctionCall.Name}");
            return new ChatMessage(ChatRole.User, [functionApprovalRequest.CreateResponse(Console.ReadLine()?.Equals("Y", StringComparison.OrdinalIgnoreCase) ?? false)]);
        })
        .ToList();

    // Pass the user input responses back to the agent for further processing.
    response = await agent.RunAsync(userInputResponses, thread);

    userInputRequests = response.UserInputRequests.ToList();

    // For streaming use:
    // updates = await agent.RunStreamingAsync(userInputResponses, thread).ToListAsync();
    // userInputRequests = updates.SelectMany(x => x.UserInputRequests).ToList();
}

Console.WriteLine($"\nAgent: {response}");

// For streaming use:
// Console.WriteLine($"\nAgent: {updates.ToAgentRunResponse()}");
