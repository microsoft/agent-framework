// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.UnitTests;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Sample;

internal sealed class HandoffTestEchoAgent(string id, string name, string prefix = "")
    : TestEchoAgent(id, name, prefix)
{
    protected override IEnumerable<ChatMessage> GetEpilogueMessages(AgentRunOptions? options = null)
    {
        if (options is ChatClientAgentRunOptions chatClientOptions &&
            chatClientOptions.ChatOptions != null)
        {
            IEnumerable<AITool>? handoffs = chatClientOptions.ChatOptions
                                                             .Tools?
                                                             .Where(tool => tool.Name?.StartsWith(HandoffsWorkflowBuilder.FunctionPrefix,
                                                                                                  StringComparison.OrdinalIgnoreCase) is true);

            if (handoffs != null)
            {
                AITool? handoff = handoffs.FirstOrDefault();
                if (handoff != null)
                {
                    return [new(ChatRole.Assistant, [new FunctionCallContent(Guid.NewGuid().ToString("N"), handoff.Name)])
                    {
                        AuthorName = this.DisplayName,
                        MessageId = Guid.NewGuid().ToString("N"),
                        CreatedAt = DateTime.UtcNow
                    }];
                }
            }
        }

        return base.GetEpilogueMessages(options);
    }
}

internal static class Step12EntryPoint
{
    public const int AgentCount = 2;

    public const string EchoAgentIdPrefix = "echo-";
    public const string EchoAgentNamePrefix = "Echo";

    public static string EchoPrefixForAgent(int agentNumber)
        => $"{agentNumber}:";

    public static Workflow CreateWorkflow()
    {
        TestEchoAgent[] echoAgents = Enumerable.Range(1, AgentCount)
            .Select(i => new HandoffTestEchoAgent($"{EchoAgentIdPrefix}{i}", $"{EchoAgentNamePrefix}{i}", EchoPrefixForAgent(i)))
            .ToArray();

        return new HandoffsWorkflowBuilder(echoAgents[0])
                   .WithHandoff(echoAgents[0], echoAgents[1])
                   .Build();
    }

    public static Workflow WorkflowInstance => CreateWorkflow();

    public static async ValueTask RunAsync(TextWriter writer, IWorkflowExecutionEnvironment executionEnvironment, IEnumerable<string> inputs)
    {
        AIAgent hostAgent = WorkflowInstance.AsAgent("echo-workflow", "EchoW", executionEnvironment: executionEnvironment);

        AgentThread thread = hostAgent.GetNewThread();
        foreach (string input in inputs)
        {
            AgentRunResponse response;
            ResponseContinuationToken? continuationToken = null;
            do
            {
                response = await hostAgent.RunAsync(input, thread, new AgentRunOptions { ContinuationToken = continuationToken });
            } while ((continuationToken = response.ContinuationToken) is { });

            foreach (ChatMessage message in response.Messages)
            {
                writer.WriteLine(message.Text);
            }
        }
    }
}
