// Copyright (c) Microsoft. All rights reserved.

using System.IO;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Sample;

internal static class Step7EntryPoint
{
    public static string EchoAgentId => Step6EntryPoint.EchoAgentId;
    public static string EchoPrefix => Step6EntryPoint.EchoPrefix;

    public static async ValueTask RunAsync(TextWriter writer, IWorkflowExecutionEnvironment environment, int maxSteps = 2, int numIterations = 2)
    {
        Workflow workflow = Step6EntryPoint.CreateWorkflow(maxSteps);

        AIAgent agent = workflow.AsAgent("group-chat-agent", "Group Chat Agent");

        for (int i = 0; i < numIterations; i++)
        {
            AgentThread thread = agent.GetNewThread();
            await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(thread).ConfigureAwait(false))
            {
                if (update.RawRepresentation is WorkflowEvent)
                {
                    // Skip workflow status updates
                    continue;
                }
                string updateText = $"{update.AuthorName
                                       ?? update.AgentId
                                       ?? update.Role.ToString()
                                       ?? ChatRole.Assistant.ToString()}: {update.Text}";
                writer.WriteLine(updateText);
            }
        }
    }
}
