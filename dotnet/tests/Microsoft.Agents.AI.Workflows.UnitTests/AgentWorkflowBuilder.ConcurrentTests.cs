// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

#pragma warning disable SYSLIB1045 // Use GeneratedRegex
#pragma warning disable RCS1186 // Use Regex instance instead of static method

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public static partial class AgentWorkflowBuilderTests
{
    public class ConcurrentTests
    {
        [Fact]
        public void BuildConcurrent_InvalidArguments_Throws()
        {
            Assert.Throws<ArgumentNullException>("agents", () => AgentWorkflowBuilder.BuildConcurrent(null!));
        }

        [Fact]
        public async Task BuildConcurrent_AgentsRunInParallelAsync()
        {
            StrongBox<TaskCompletionSource<bool>> barrier = new();
            StrongBox<int> remaining = new();

            var workflow = AgentWorkflowBuilder.BuildConcurrent(
            [
                new DoubleEchoAgentWithBarrier("agent1", barrier, remaining),
                new DoubleEchoAgentWithBarrier("agent2", barrier, remaining),
            ]);

            for (int iter = 0; iter < 3; iter++)
            {
                barrier.Value = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                remaining.Value = 2;

                (string updateText, List<ChatMessage>? result, _, _) = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "abc")]);
                Assert.NotEmpty(updateText);
                Assert.NotNull(result);

                // TODO: https://github.com/microsoft/agent-framework/issues/784
                // These asserts are flaky until we guarantee message delivery order.
                Assert.Single(Regex.Matches(updateText, "agent1"));
                Assert.Single(Regex.Matches(updateText, "agent2"));
                Assert.Equal(4, Regex.Matches(updateText, "abc").Count);
                Assert.Equal(2, result.Count);
            }
        }
    }
}
