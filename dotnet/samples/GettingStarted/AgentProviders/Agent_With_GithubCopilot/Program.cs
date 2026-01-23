// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with GitHub Copilot SDK.

using GitHub.Copilot.SDK;
using Microsoft.Agents.AI;

// Create and start a Copilot client
await using CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = true });
await copilotClient.StartAsync();

// Create an instance of the AIAgent using the extension method
AIAgent agent = copilotClient.AsAIAgent(ownsClient: true);

// Ask Copilot to write code for us - demonstrate its code generation capabilities
AgentResponse response = await agent.RunAsync("Write a small .NET 10 C# hello world single file application");
Console.WriteLine(response);
