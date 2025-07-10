﻿// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Orchestration;
using Microsoft.Agents.Orchestration.Concurrent;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime.InProcess;

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
            this.CreateAgent(
                instructions: "You are an expert in physics. You answer questions from a physics perspective.",
                description: "An expert in physics");
        ChatClientAgent chemist =
            this.CreateAgent(
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
                ResponseCallback = monitor.ResponseCallback,
                StreamingResponseCallback = streamedResponse ? monitor.StreamingResultCallback : null,
            };

        // Start the runtime
        await using InProcessRuntime runtime = new();
        await runtime.StartAsync();

        // Run the orchestration
        string input = "What is temperature?";
        Console.WriteLine($"\n# INPUT: {input}\n");
        OrchestrationResult<string[]> result = await orchestration.InvokeAsync(input, runtime);

        string[] output = await result.GetValueAsync(TimeSpan.FromSeconds(ResultTimeoutInSeconds));
        Console.WriteLine($"\n# RESULT:\n{string.Join("\n\n", output.Select(text => $"{text}"))}");

        await runtime.RunUntilIdleAsync();

        this.DisplayHistory(monitor.History);
    }
}
