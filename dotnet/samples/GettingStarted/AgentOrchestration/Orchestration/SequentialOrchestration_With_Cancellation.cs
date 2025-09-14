// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Orchestration;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Orchestration;

/// <summary>
/// Demonstrates how to use cancel a <see cref="SequentialOrchestration"/> while its running.
/// </summary>
public class SequentialOrchestration_With_Cancellation(ITestOutputHelper output) : OrchestrationSample(output)
{
    [Fact]
    public async Task RunOrchestrationAsync()
    {
        // Define the agents
        ChatClientAgent agent =
            CreateAgent(
                """
                If the input message is a number, return the number incremented by one.
                """,
                description: "A agent that increments numbers.");

        // Define the orchestration
        SequentialOrchestration orchestration = new(agent) { LoggerFactory = this.LoggerFactory };

        // Run the orchestration
        const string Input = "42";
        Console.WriteLine($"\n# INPUT: {Input}\n");

        OrchestratingAgentResponse result = await orchestration.RunAsync([new ChatMessage(ChatRole.User, Input)]);

        result.Cancel();
        await Task.Delay(TimeSpan.FromSeconds(3));

        try
        {
            Console.WriteLine($"\n# RESULT: {await result}");
        }
        catch (TimeoutException exception)
        {
            Console.WriteLine($"\n# CANCELED: {exception.Message}");
        }
    }
}
