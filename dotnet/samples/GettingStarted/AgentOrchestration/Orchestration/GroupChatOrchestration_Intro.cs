// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Orchestration;
using Microsoft.Extensions.AI.Agents;

namespace Orchestration;

/// <summary>
/// Demonstrates how to use the <see cref="GroupChatOrchestration"/> ith a default
/// round robin manager for controlling the flow of conversation in a round robin fashion.
/// </summary>
/// <remarks>
/// Think of the group chat manager as a state machine, with the following possible states:
/// - Request for user message
/// - Termination, after which the manager will try to filter a result from the conversation
/// - Continuation, at which the manager will select the next agent to speak.
/// </remarks>
public class GroupChatOrchestration_Intro(ITestOutputHelper output) : OrchestrationSample(output)
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RunOrchestrationAsync(bool streamedResponse)
    {
        // Define the agents
        ChatClientAgent writer =
            CreateAgent(
                name: "CopyWriter",
                description: "A copy writer",
                instructions:
                """
                You are a copywriter with ten years of experience and are known for brevity and a dry humor.
                The goal is to refine and decide on the single best copy as an expert in the field.
                Only provide a single proposal per response.
                You're laser focused on the goal at hand.
                Don't waste time with chit chat.
                Consider suggestions when refining an idea.
                """);
        ChatClientAgent editor =
            CreateAgent(
                name: "Reviewer",
                description: "An editor.",
                instructions:
                """
                You are an art director who has opinions about copywriting born of a love for David Ogilvy.
                The goal is to determine if the given copy is acceptable to print.
                If so, state that it is approved.
                If not, provide insight on how to refine suggested copy without example.
                """);

        // Create a monitor to capturing agent responses (via ResponseCallback)
        // to display at the end of this sample. (optional)
        // NOTE: Create your own callback to capture responses in your application or service.
        OrchestrationMonitor monitor = new();
        // Define the orchestration
        GroupChatOrchestration orchestration =
            new(new RoundRobinGroupChatManager()
            {
                MaximumInvocationCount = 5
            },
            writer,
            editor)
            {
                LoggerFactory = this.LoggerFactory,
                ResponseCallback = monitor.ResponseCallbackAsync,
                StreamingResponseCallback = streamedResponse ? monitor.StreamingResultCallbackAsync : null,
            };

        const string Input = "Create a slogon for a new eletric SUV that is affordable and fun to drive.";
        Console.WriteLine($"\n# INPUT: {Input}\n");
        AgentRunResponse result = await orchestration.RunAsync(Input);
        Console.WriteLine($"\n# RESULT: {result}");

        this.DisplayHistory(monitor.History);
    }
}
