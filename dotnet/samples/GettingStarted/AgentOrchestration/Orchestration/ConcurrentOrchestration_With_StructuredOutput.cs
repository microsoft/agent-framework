// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.Orchestration;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Samples;

namespace Orchestration;

/// <summary>
/// Demonstrates how to use the <see cref="ConcurrentOrchestration"/> with structured output.
/// </summary>
public class ConcurrentOrchestration_With_StructuredOutput(ITestOutputHelper output) : OrchestrationSample(output)
{
    private static readonly JsonSerializerOptions s_options = new() { WriteIndented = true };

    [Fact]
    public async Task RunOrchestrationAsync()
    {
        // Define the agents
        ChatClientAgent agent1 =
            CreateAgent(
                instructions: "You are an expert in identifying themes in articles. Given an article, identify the main themes.",
                description: "An expert in identifying themes in articles");
        ChatClientAgent agent2 =
            CreateAgent(
                instructions: "You are an expert in sentiment analysis. Given an article, identify the sentiment.",
                description: "An expert in sentiment analysis");
        ChatClientAgent agent3 =
            CreateAgent(
                instructions: "You are an expert in entity recognition. Given an article, extract the entities.",
                description: "An expert in entity recognition");

        // Define the orchestration with transform
        ConcurrentOrchestration orchestration = new(agent1, agent2, agent3) { LoggerFactory = this.LoggerFactory };

        // Run the orchestration
        const string ResourceId = "Hamlet_full_play_summary.txt";
        string input = Resources.Read(ResourceId);
        Console.WriteLine($"\n# INPUT: @{ResourceId}\n");

        var output = await orchestration.RunAsync<Analysis>(CreateChatClient(), input);
        Console.WriteLine($"\n# RESULT:\n{JsonSerializer.Serialize(output, s_options)}");
    }

#pragma warning disable CA1812 // Avoid uninstantiated internal classes
    private sealed class Analysis
    {
        public IList<string> Themes { get; set; } = [];
        public IList<string> Sentiments { get; set; } = [];
        public IList<string> Entities { get; set; } = [];
    }
#pragma warning restore CA1812
}
