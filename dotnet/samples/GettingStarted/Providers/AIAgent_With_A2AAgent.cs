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

        AIAgent agent = a2aClient.CreateAIAgent();

        // Run in non-streaming mode.
        AgentRunResponse response = await agent.RunAsync("Tell me a joke about a pirate.");
        Console.WriteLine(response);

        // Run in streaming mode.
        IAsyncEnumerable<AgentRunResponseUpdate> updates = agent.RunStreamingAsync("Tell me a joke about a pirate.");
        await foreach (var update in updates)
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

        AIAgent agent = await agentCardResolver.CreateAIAgentAsync();

        // Run in non-streaming mode.
        AgentRunResponse response = await agent.RunAsync("Tell me a joke about a pirate.");
        Console.WriteLine(response);

        // Run in streaming mode.
        IAsyncEnumerable<AgentRunResponseUpdate> updates = agent.RunStreamingAsync("Tell me a joke about a pirate.");
        await foreach (var update in updates)
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

        AIAgent agent = a2aClient.CreateAIAgent();

        // Run in non-streaming mode.
        AgentThread thread = agent.GetNewThread();
        Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", thread));
        Console.WriteLine(await agent.RunAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", thread));

        // Run in streaming mode.
        thread = agent.GetNewThread();
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
