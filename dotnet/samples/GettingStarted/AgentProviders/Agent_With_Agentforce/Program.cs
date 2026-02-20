// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use an AI agent backed by Salesforce Agentforce.
// The agent connects to a Salesforce org via the Agentforce REST API (OAuth 2.0 client
// credentials flow) and forwards messages to a deployed Agentforce agent.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Agentforce;

// ---------------------------------------------------------------------------
// 1. Read configuration from environment variables
// ---------------------------------------------------------------------------
string myDomainHost = Environment.GetEnvironmentVariable("AGENTFORCE_DOMAIN")
    ?? throw new InvalidOperationException("Set the AGENTFORCE_DOMAIN environment variable to your Salesforce My Domain host (e.g. your-org.my.salesforce.com).");

string consumerKey = Environment.GetEnvironmentVariable("AGENTFORCE_CONSUMER_KEY")
    ?? throw new InvalidOperationException("Set the AGENTFORCE_CONSUMER_KEY environment variable to your Connected App consumer key.");

string consumerSecret = Environment.GetEnvironmentVariable("AGENTFORCE_CONSUMER_SECRET")
    ?? throw new InvalidOperationException("Set the AGENTFORCE_CONSUMER_SECRET environment variable to your Connected App consumer secret.");

string agentId = Environment.GetEnvironmentVariable("AGENTFORCE_AGENT_ID")
    ?? throw new InvalidOperationException("Set the AGENTFORCE_AGENT_ID environment variable to the Agentforce Agent ID.");

// ---------------------------------------------------------------------------
// 2. Create the Agentforce agent
// ---------------------------------------------------------------------------
var config = new AgentforceConfig(myDomainHost, consumerKey, consumerSecret, agentId);
using var agent = new AgentforceAgent(config);

Console.WriteLine("Agentforce agent created. Sending a message...\n");

// ---------------------------------------------------------------------------
// 3. Run a single-turn conversation (non-streaming)
// ---------------------------------------------------------------------------
AgentResponse response = await agent.RunAsync("What can you help me with?");

Console.WriteLine("=== Agent Response (non-streaming) ===");
Console.WriteLine(response);
Console.WriteLine();

// ---------------------------------------------------------------------------
// 4. Run a single-turn conversation (streaming)
// ---------------------------------------------------------------------------
Console.WriteLine("=== Agent Response (streaming) ===");
await foreach (AgentResponseUpdate update in agent.RunStreamingAsync("Tell me more about your capabilities."))
{
    Console.Write(update);
}

Console.WriteLine();
Console.WriteLine("\nDone.");
