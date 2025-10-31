// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.UnitTests;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Sample;

internal static class Step10EntryPoint
{
    public static Workflow CreateWorkflow()
    {
        TestEchoAgent echoAgent = new("echo", "Echo");
        return AgentWorkflowBuilder.BuildSequential(echoAgent);
    }
    public static Workflow WorkflowInstance => CreateWorkflow();

    public static async ValueTask RunAsync(TextWriter writer, IWorkflowExecutionEnvironment executionEnvironment, IEnumerable<string> inputs)
    {
        AIAgent hostAgent = WorkflowInstance.AsAgent("echo-workflow", "EchoW", executionEnvironment: executionEnvironment);

        AgentThread thread = hostAgent.GetNewThread();
        foreach (string input in inputs)
        {
            AgentRunResponse response;
            object? continuationToken = null;
            do
            {
                response = await hostAgent.RunAsync(input, thread, new AgentRunOptions { ContinuationToken = continuationToken });
            } while ((continuationToken = response.ContinuationToken) is { });

            foreach (ChatMessage message in response.Messages)
            {
                writer.WriteLine($"{message.AuthorName}: {message.Text}");
            }
        }
    }
}
