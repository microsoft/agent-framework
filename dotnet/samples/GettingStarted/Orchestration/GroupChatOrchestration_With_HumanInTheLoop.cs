﻿// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Orchestration;
using Microsoft.Agents.Orchestration.GroupChat;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime.InProcess;

namespace Orchestration;

/// <summary>
/// Demonstrates how to use the <see cref="GroupChatOrchestration"/> with human in the loop
/// </summary>
public class GroupChatOrchestration_With_HumanInTheLoop(ITestOutputHelper output) : OrchestrationSample(output)
{
    [Fact]
    public async Task RunOrchestrationAsync()
    {
        // Define the agents
        ChatClientAgent writer =
            this.CreateAgent(
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
            this.CreateAgent(
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
            new(
                new CustomRoundRobinGroupChatManager()
                {
                    MaximumInvocationCount = 5,
                    InteractiveCallback = () =>
                    {
                        ChatMessage input = new(ChatRole.User, "I like it");
                        monitor.History.Add(input);
                        Console.WriteLine($"\n# INPUT: {input.Text}\n");
                        return new ValueTask<ChatMessage>(input);
                    }
                },
                writer,
                editor)
            {
                LoggerFactory = this.LoggerFactory,
                ResponseCallback = monitor.ResponseCallback,
            };

        // Start the runtime
        await using InProcessRuntime runtime = new();
        await runtime.StartAsync();

        // Run the orchestration
        string input = "Create a slogon for a new eletric SUV that is affordable and fun to drive.";
        Console.WriteLine($"\n# INPUT: {input}\n");
        OrchestrationResult<string> result = await orchestration.InvokeAsync(input, runtime);
        string text = await result.GetValueAsync(TimeSpan.FromSeconds(ResultTimeoutInSeconds * 3));
        Console.WriteLine($"\n# RESULT: {text}");

        await runtime.RunUntilIdleAsync();

        this.DisplayHistory(monitor.History);
    }

    /// <summary>
    /// Define a custom group chat manager that enables user input.
    /// </summary>
    /// <remarks>
    /// User input is achieved by overriding the default round robin manager
    /// to allow user input after the reviewer agent's message.
    /// </remarks>
    private sealed class CustomRoundRobinGroupChatManager : RoundRobinGroupChatManager
    {
        public override ValueTask<GroupChatManagerResult<bool>> ShouldRequestUserInput(IReadOnlyCollection<ChatMessage> history, CancellationToken cancellationToken = default)
        {
            string? lastAgent = history.LastOrDefault()?.AuthorName;

            GroupChatManagerResult<bool> result;

            if (lastAgent is null)
            {
                result = new GroupChatManagerResult<bool>(false) { Reason = "No agents have spoken yet." };
            }

            if (lastAgent == "Reviewer")
            {
                result = new GroupChatManagerResult<bool>(true) { Reason = "User input is needed after the reviewer's message." };
            }
            else
            {
                result = new GroupChatManagerResult<bool>(false) { Reason = "User input is not needed until the reviewer's message." };
            }

            return new ValueTask<GroupChatManagerResult<bool>>(result);
        }
    }
}
