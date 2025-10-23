// Copyright (c) Microsoft. All rights reserved.

using System.IO;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Sample;

internal static class Step7EntryPoint
{
    public static async ValueTask RunAsync(TextWriter writer, int maxSteps = 2)
    {
        Workflow workflow = Step6EntryPoint.CreateWorkflow(maxSteps);

        AIAgent agent = workflow.AsAgent("group-chat-agent", "Group Chat Agent");

        AgentThread thread = agent.GetNewThread();

        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(thread).ConfigureAwait(false))
        {
            string updateText = $"{update.AuthorName
                                   ?? update.AgentId
                                   ?? update.Role.ToString()
                                   ?? ChatRole.Assistant.ToString()}: {update.Text}";
            writer.WriteLine(updateText);
        }
    }
}
