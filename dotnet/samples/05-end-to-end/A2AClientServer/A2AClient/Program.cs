// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to discover and invoke an agent hosted by an A2A server.

using A2A;
using Microsoft.Agents.AI;

// Initialize an A2ACardResolver to discover the policy agent.
var agentUrl = Environment.GetEnvironmentVariable("A2A_AGENT_URL") ?? "http://localhost:5000/";
var agentCardResolver = new A2ACardResolver(new Uri(agentUrl));

// Create an AIAgent from the A2A agent card.
AIAgent policyAgent = await agentCardResolver.GetAIAgentAsync();

// Create a session so requests share the same A2A protocol context.
AgentSession session = await policyAgent.CreateSessionAsync();

while (true)
{
    // Read the next request from the console.
    Console.Write("\nUser (:q or quit to exit): ");
    string? message = Console.ReadLine();

    if (string.IsNullOrWhiteSpace(message))
    {
        Console.WriteLine("Request cannot be empty.");
        continue;
    }

    if (message is ":q" or "quit")
    {
        break;
    }

    // Invoke the remote policy agent over A2A and display its response.
    AgentResponse response = await policyAgent.RunAsync(message, session);

    Console.ForegroundColor = ConsoleColor.Cyan;
    Console.WriteLine($"\nPolicy agent: {response.Text}");
    Console.ResetColor();
}
