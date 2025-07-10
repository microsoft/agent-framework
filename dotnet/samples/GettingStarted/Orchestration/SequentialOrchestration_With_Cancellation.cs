// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Orchestration;
using Microsoft.Agents.Orchestration.Sequential;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime.InProcess;

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
            this.CreateAgent(
                """
                If the input message is a number, return the number incremented by one.
                """,
                description: "A agent that increments numbers.");

        // Define the orchestration
        SequentialOrchestration orchestration = new(agent) { LoggerFactory = this.LoggerFactory };

        // Start the runtime
        await using InProcessRuntime runtime = new();
        await runtime.StartAsync();

        // Run the orchestration
        string input = "42";
        Console.WriteLine($"\n# INPUT: {input}\n");

        OrchestrationResult<string> result = await orchestration.InvokeAsync(input, runtime);

        result.Cancel();
        await Task.Delay(TimeSpan.FromSeconds(3));

        try
        {
            string text = await result.GetValueAsync(TimeSpan.FromSeconds(ResultTimeoutInSeconds));
            Console.WriteLine($"\n# RESULT: {text}");
        }
        catch (AggregateException exception)
        {
            Console.WriteLine($"\n# CANCELLED: {exception.InnerException?.Message}");
        }

        await runtime.RunUntilIdleAsync();
    }
}
