// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Orchestration;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Samples;
using OpenAI;

namespace Orchestration;

/// <summary>
/// Demonstrates how to use the <see cref="SequentialOrchestration"/> for
/// executing multiple heterogeneous agents in sequence.
/// </summary>
public class SequentialOrchestration_Multi_Agent(ITestOutputHelper output) : OrchestrationSample(output)
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RunOrchestrationAsync(bool streamedResponse)
    {
        var openAIClient = new OpenAIClient(TestConfiguration.OpenAI.ApiKey);
        var model = TestConfiguration.OpenAI.ChatModelId;

        // Define the agents
        AIAgent analystAgent =
            openAIClient.GetChatClient(model).CreateAIAgent(
                name: "Analyst",
                instructions:
                """
                You are a marketing analyst. Given a product description, identify:
                - Key features
                - Target audience
                - Unique selling points
                """,
                description: "A agent that extracts key concepts from a product description.");
        AIAgent writerAgent =
            openAIClient.GetOpenAIResponseClient(model).CreateAIAgent(
                name: "copywriter",
                instructions:
                """
                You are a marketing copywriter. Given a block of text describing features, audience, and USPs,
                compose a compelling marketing copy (like a newsletter section) that highlights these points.
                Output should be short (around 150 words), output just the copy as a single text block.
                """,
                description: "An agent that writes a marketing copy based on the extracted concepts.");
        AIAgent editorAgent =
            openAIClient.GetAssistantClient().CreateAIAgent(
                model,
                name: "editor",
                instructions:
                """
                You are an editor. Given the draft copy, correct grammar, improve clarity, ensure consistent tone,
                give format and make it polished. Output the final improved copy as a single text block.
                """,
                description: "An agent that formats and proofreads the marketing copy.");

        // Create a monitor to capturing agent responses (via ResponseCallback)
        // to display at the end of this sample. (optional)
        // NOTE: Create your own callback to capture responses in your application or service.
        OrchestrationMonitor monitor = new();
        // Define the orchestration
        SequentialOrchestration orchestration =
            new(analystAgent, writerAgent, editorAgent)
            {
                LoggerFactory = this.LoggerFactory,
                ResponseCallback = monitor.ResponseCallbackAsync,
                StreamingResponseCallback = streamedResponse ? monitor.StreamingResultCallbackAsync : null,
            };

        // Run the orchestration
        const string Input = "An eco-friendly stainless steel water bottle that keeps drinks cold for 24 hours";
        Console.WriteLine($"\n# INPUT: {Input}\n");
        AgentRunResponse result = await orchestration.RunAsync(Input);
        Console.WriteLine($"\n# RESULT: {result}");

        this.DisplayHistory(monitor.History);

        // Cleanup
        var assistantClient = openAIClient.GetAssistantClient();
        await assistantClient.DeleteAssistantAsync(editorAgent.Id);
        // Need to know how to get the assistant thread ID to delete the thread (issue #260)
    }
}
