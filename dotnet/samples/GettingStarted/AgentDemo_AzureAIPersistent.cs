// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Samples;

namespace GettingStarted;

public class AgentDemo_AzureAIPersistent(ITestOutputHelper output) : AgentSample(output)
{
    // Simplest case with CreateNew and Existing
    // Add Threads
    // Add RunOptions at construction time (not breaking abstraction)
    // Add sample showing usage of ThreadAndRunOptions

    private const string ExistingAgentId = "asst_Bka3wK4I1scpRvJImnDCdBlk";

    [Fact]
    public async Task AzureAIPersistent_RunWithNewAgent1()
    {
        // Get a client for creating server side agents.
        PersistentAgentsClient persistentAgentsClient = new(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());

        // Create a server side agent.
        var persistentAgentResponse = await persistentAgentsClient.Administration.CreateAgentAsync(
            model: TestConfiguration.AzureAI.DeploymentName,
            name: "Joker",
            instructions: "You are good at telling jokes.");

        // Create a ChatClientAgent from the service call result.
        Agent agent = persistentAgentsClient.GetChatClientAgent(persistentAgentResponse.Value.Id);

        // Create a ChatClientAgent from the service call result.
        // Agent agent = persistentAgentResponse.AsChatClientAgent(TestConfiguration.AzureAI.Endpoint!, new AzureCliCredential());

        // Invoke the agent.
        var response = await agent.RunAsync("Tell me a joke about a pirate.");
        Console.WriteLine(response.Text);

        // Demo cleanup.
        await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
    }

    [Fact]
    public async Task AzureAIPersistent_RunWithNewAgent2()
    {
        // Get a client for creating server side agents.
        PersistentAgentsClient persistentAgentsClient = new(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());

        // Create a server side agent and expose it as a ChatClientAgent.
        Agent agent = await persistentAgentsClient.CreateChatClientAgentAsync(
            model: TestConfiguration.AzureAI.DeploymentName!,
            name: "Joker",
            instructions: "You are good at telling jokes.");

        // Invoke the agent.
        var response = await agent.RunAsync("Tell me a joke about a pirate.");
        Console.WriteLine(response.Text);

        // Demo cleanup.
        await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
    }

    [Fact]
    public async Task AzureAIPersistent_RunWithExistingAgent()
    {
        // Get a client for interacting with server side agents.
        PersistentAgentsClient persistentAgentsClient = new(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());

        // Get an existing agent using its ID.
        Agent agent = persistentAgentsClient.GetChatClientAgent(ExistingAgentId);

        // Invoke the agent.
        var response = await agent.RunAsync("Tell me a joke about a pirate.");
        Console.WriteLine(response.Text);
    }

    [Fact]
    public async Task AzureAIPersistent_RunWithThreadAsync()
    {
        PersistentAgentsClient persistentAgentsClient = new(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());
        Agent agent = persistentAgentsClient.GetChatClientAgent(ExistingAgentId);

        // Create a thread for this agent.
        var thread = agent.GetNewThread();

        // Run with the thread.
        var response = await agent.RunAsync("Tell me a joke about a pirate.", thread);
        Console.WriteLine(response.Text);

        response = await agent.RunAsync("Now tell the same joke like a parrot.", thread);
        Console.WriteLine(response.Text);
    }

    [Fact]
    public async Task AzureAIPersistent_GetAgentWithCustomSettings()
    {
        // Get a client for interacting with server side agents.
        PersistentAgentsClient persistentAgentsClient = new(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());

        // Get an existing agent but set AzureAIPersistent specific options that apply to all runs.
        var options = new ThreadAndRunOptions() { OverrideInstructions = "Always refuse to tell jokes" };
        ChatClientAgent agent = persistentAgentsClient.GetChatClientAgent(ExistingAgentId, chatOptions: new() { RawRepresentationFactory = _ => options });

        // Invoke the agent with AzureAIPersistent specific options.
        var response = await agent.RunAsync("Tell me a joke about a pirate.");
        Console.WriteLine(response.Text);
    }

    [Fact]
    public async Task AzureAIPersistent_RunWithCustomSettings()
    {
        // Get a client for interacting with server side agents.
        PersistentAgentsClient persistentAgentsClient = new(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());

        // Get an existing agent using its ID.
        ChatClientAgent agent = persistentAgentsClient.GetChatClientAgent(ExistingAgentId);

        // Invoke the agent with AzureAIPersistent specific options.
        var options = new ThreadAndRunOptions() { OverrideInstructions = "Always refuse to tell jokes" };
        var response = await agent.RunAsync("Tell me a joke about a pirate.", chatOptions: new() { RawRepresentationFactory = _ => options });
        Console.WriteLine(response.Text);
    }
}
