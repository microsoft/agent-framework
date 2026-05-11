// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to handle user input requests from an A2A agent. When an A2A agent
// needs additional information from the user to complete a task, it returns an "input-required" state
// with a message describing what it needs. This sample shows how to detect those requests, gather
// responses from the user, and send them back to the agent.

using A2A;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.A2A;
using Microsoft.Extensions.AI;

var a2aAgentHost = Environment.GetEnvironmentVariable("A2A_AGENT_HOST")
    ?? throw new InvalidOperationException("A2A_AGENT_HOST is not set.");

A2ACardResolver agentCardResolver = new(new Uri(a2aAgentHost));
AIAgent agent = await agentCardResolver.GetAIAgentAsync();

AgentSession session = await agent.CreateSessionAsync();

// AllowBackgroundResponses enables the polling pattern - the server returns immediately
// with a continuation token instead of blocking until the task is complete.
AgentRunOptions options = new() { AllowBackgroundResponses = true };

// Step 1: Send a vague request to trigger an input request from the agent.
Console.WriteLine("Sending initial request...");
AgentResponse response = await agent.RunAsync("I'd like to book a flight.", session, options);

// Step 2: Poll until the agent completes or requests user input.
while (response.ContinuationToken is { } token)
{
    await Task.Delay(TimeSpan.FromSeconds(2));
    response = await agent.RunAsync(session, options: new AgentRunOptions { ContinuationToken = token, AllowBackgroundResponses = true });
}

// Step 3: Check for user input requests and respond to each one interactively.
var userInputRequests = response.Messages
    .SelectMany(m => m.Contents.OfType<A2AInputRequestContent>())
    .ToList();

List<ChatMessage> responseMessages = [];

foreach (var inputRequest in userInputRequests)
{
    string requestText = inputRequest.Request is TextContent textContent ? textContent.Text : inputRequest.Request.ToString() ?? "";
    Console.WriteLine($"Agent asks: {requestText}");
    Console.Write("Your response: ");
    string userResponse = Console.ReadLine() ?? "";
    responseMessages.Add(new ChatMessage(ChatRole.User, [inputRequest.CreateResponse(userResponse)]));
}

// Step 4: Send all user responses back to the agent.
if (responseMessages.Count > 0)
{
    Console.WriteLine("\nSending user responses...");
    response = await agent.RunAsync(responseMessages, session, options: new AgentRunOptions { AllowBackgroundResponses = true });
}

// Step 5: Poll until the task completes.
while (response.ContinuationToken is { } token)
{
    await Task.Delay(TimeSpan.FromSeconds(2));
    response = await agent.RunAsync(session, options: new AgentRunOptions { ContinuationToken = token, AllowBackgroundResponses = true });
}

Console.WriteLine("\nFinal response:");
Console.WriteLine(response);
