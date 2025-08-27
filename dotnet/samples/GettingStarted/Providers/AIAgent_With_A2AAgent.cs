// Copyright (c) Microsoft. All rights reserved.

using A2A;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.A2A;
using Microsoft.Shared.Samples;

namespace Providers;

/// <summary>
/// Shows how to use the <inheritdoc cref="A2AAgent"/>.
/// </summary>
/// <remarks>
/// These samples need to be run against a valid A2A server. If no A2A server is available,
/// they can be run against the echo-agent that can be spun up locally by following the guidelines at:
/// https://github.com/a2aproject/a2a-dotnet/blob/main/samples/AgentServer/README.md
/// </remarks>
public sealed class AIAgent_With_A2AAgent(ITestOutputHelper output) : AgentSample(output)
{
    /// <summary>
    /// This sample shows how to create an <see cref="AIAgent"/> from an <see cref="A2AClient"/>
    /// and run it in non-streaming and streaming modes.
    /// </summary>
    [Fact]
    public async Task CreateFromA2AClientAndRun()
    {
        A2AClient a2aClient = new(TestConfiguration.A2A.AgentEndpoint!);

        // Create the agent
        AIAgent agent = a2aClient.CreateAIAgent();

        // Invoke the agent and output the text result.
        Console.WriteLine("--- Run the agent ---\n");
        Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));

        // Invoke the agent with streaming support.
        Console.WriteLine("\n--- Run the agent with streaming ---\n");
        await foreach (var update in agent.RunStreamingAsync("Tell me a joke about a pirate."))
        {
            Console.Write(update);
        }
    }

    /// <summary>
    /// This sample shows how to create an <see cref="AIAgent"/> from an <see cref="A2ACardResolver"/>
    /// and run it in non-streaming and streaming modes.
    /// </summary>
    [Fact]
    public async Task CreateFromAgentCardResolverAndRun()
    {
        A2ACardResolver agentCardResolver = new(TestConfiguration.A2A.AgentHost!);

        // Create the agent
        AIAgent agent = await agentCardResolver.CreateAIAgentAsync();

        // Invoke the agent and output the text result.
        Console.WriteLine("--- Run the agent ---\n");
        Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));

        // Invoke the agent with streaming support.
        Console.WriteLine("\n--- Run the agent with streaming ---\n");
        await foreach (var update in agent.RunStreamingAsync("Tell me a joke about a pirate."))
        {
            Console.Write(update);
        }
    }

    /// <summary>
    /// This sample shows how to run a multi-turn conversation with an <see cref="AIAgent"/>
    /// by using an <see cref="AgentThread"/> to preserve context across turns.
    /// </summary>
    [Fact]
    public async Task RunMultiturnConversation()
    {
        A2AClient a2aClient = new(TestConfiguration.A2A.AgentEndpoint!);

        // Create the agent
        AIAgent agent = a2aClient.CreateAIAgent();

        // Create a thread and use it for multiple turns to preserve context by passing it to each call to RunAsync method.
        AgentThread thread = agent.GetNewThread();
        Console.WriteLine("--- Run the agent ---\n");
        Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", thread));
        Console.WriteLine(await agent.RunAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", thread));

        // Create a thread and use it for multiple turns to preserve context in streaming mode by passing it to each call to RunStreamingAsync method.
        thread = agent.GetNewThread();
        Console.WriteLine("\n--- Run the agent with streaming ---\n");
        await foreach (var update in agent.RunStreamingAsync("Tell me a joke about a pirate.", thread))
        {
            Console.Write(update);
        }
        await foreach (var update in agent.RunStreamingAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", thread))
        {
            Console.Write(update);
        }
    }
}
