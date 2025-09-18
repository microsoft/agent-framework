// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Orchestration;
using Microsoft.Extensions.AI.Agents;

namespace Orchestration;

/// <summary>
/// Demonstrates how to use the <see cref="ConcurrentOrchestration"/>
/// for executing multiple agents on the same task in parallel.
/// </summary>
public class ConcurrentOrchestration_Intro(ITestOutputHelper output) : OrchestrationSample(output)
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RunOrchestrationAsync(bool streamedResponse)
    {
        // Define the agents
        ChatClientAgent physicist =
            CreateAgent(
                instructions: "You are an expert in physics. You answer questions from a physics perspective.",
                description: "An expert in physics");
        ChatClientAgent chemist =
            CreateAgent(
                instructions: "You are an expert in chemistry. You answer questions from a chemistry perspective.",
                description: "An expert in chemistry");

        // Create a monitor to capturing agent responses (via ResponseCallback)
        // to display at the end of this sample. (optional)
        // NOTE: Create your own callback to capture responses in your application or service.
        OrchestrationMonitor monitor = new();

        // Define the orchestration
        ConcurrentOrchestration orchestration =
            new(physicist, chemist)
            {
                LoggerFactory = this.LoggerFactory,
                ResponseCallback = monitor.ResponseCallbackAsync,
                StreamingResponseCallback = streamedResponse ? monitor.StreamingResultCallbackAsync : null,
            };

        // Run the orchestration
        const string Input = "What is temperature?";
        Console.WriteLine($"\n# INPUT: {Input}\n");
        AgentRunResponse result = await orchestration.RunAsync(Input);

        Console.WriteLine($"\n# RESULT:\n{string.Join("\n\n", result.Messages.Select(r => $"{r.Text}"))}");

        this.DisplayHistory(monitor.History);
    }
}
