// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public static partial class AgentWorkflowBuilderTests
{
    public class SequentialTests
    {
        [Fact]
        public void BuildSequential_InvalidArguments_Throws()
        {
            Assert.Throws<ArgumentNullException>("agents", () => AgentWorkflowBuilder.BuildSequential(workflowName: null!, null!));
            Assert.Throws<ArgumentException>("agents", () => AgentWorkflowBuilder.BuildSequential());
        }

        [Theory]
        [InlineData(1)]
        [InlineData(2)]
        [InlineData(3)]
        [InlineData(4)]
        [InlineData(5)]
        public async Task BuildSequential_AgentsRunInOrderAsync(int numAgents)
        {
            var workflow = AgentWorkflowBuilder.BuildSequential(
                from i in Enumerable.Range(1, numAgents)
                select new DoubleEchoAgent($"agent{i}"));

            for (int iter = 0; iter < 3; iter++)
            {
                const string UserInput = "abc";
                (string updateText, List<ChatMessage>? result, _, _) = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, UserInput)]);

                Assert.NotNull(result);
                Assert.Equal(numAgents + 1, result.Count);

                Assert.Equal(ChatRole.User, result[0].Role);
                Assert.Null(result[0].AuthorName);
                Assert.Equal(UserInput, result[0].Text);

                string[] texts = new string[numAgents + 1];
                texts[0] = UserInput;
                string expectedTotal = string.Empty;
                for (int i = 1; i < numAgents + 1; i++)
                {
                    string id = $"agent{((i - 1) % numAgents) + 1}";
                    texts[i] = $"{id}{Double(string.Concat(texts.Take(i)))}";
                    Assert.Equal(ChatRole.Assistant, result[i].Role);
                    Assert.Equal(id, result[i].AuthorName);
                    Assert.Equal(texts[i], result[i].Text);
                    expectedTotal += texts[i];
                }

                Assert.Equal(expectedTotal, updateText);
                Assert.Equal(UserInput + expectedTotal, string.Concat(result));

                static string Double(string s) => s + s;
            }
        }
    }
}
