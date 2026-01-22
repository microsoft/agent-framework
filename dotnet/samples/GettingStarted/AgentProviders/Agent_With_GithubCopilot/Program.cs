// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with GitHub Copilot SDK.

using GitHub.Copilot.SDK;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.GithubCopilot;

// Create a Copilot client with default options
var copilotClientOptions = new CopilotClientOptions
{
    AutoStart = true
};

// Create an instance of the AIAgent using GitHub Copilot SDK
AIAgent agent = new GithubCopilotAgent(copilotClientOptions);

// Invoke the agent and output the text result
AgentResponse response = await agent.RunAsync("Tell me a joke about a pirate.");
Console.WriteLine(response);
