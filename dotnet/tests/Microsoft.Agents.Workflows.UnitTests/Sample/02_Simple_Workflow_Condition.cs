// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Reflection;

namespace Microsoft.Agents.Workflows.Sample;

internal static class Step2EntryPoint
{
    public static Workflow<string> WorkflowInstance
    {
        get
        {
            string[] spamKeywords = ["spam", "advertisement", "offer"];

            DetectSpamExecutor detectSpam = new(spamKeywords);
            RespondToMessageExecutor respondToMessage = new();
            RemoveSpamExecutor removeSpam = new();

            return new WorkflowBuilder(detectSpam)
                .AddEdge(detectSpam, respondToMessage, (bool isSpam) => !isSpam) // If not spam, respond
                .AddEdge(detectSpam, removeSpam, (bool isSpam) => isSpam) // If spam, remove
                .Build<string>();
        }
    }

    public static async ValueTask<string> RunAsync(TextWriter writer, string input = "This is a spam message.")
    {
        StreamingRun handle = await InProcessExecution.StreamAsync(WorkflowInstance, input).ConfigureAwait(false);
        await foreach (WorkflowEvent evt in handle.WatchStreamAsync().ConfigureAwait(false))
        {
            switch (evt)
            {
                case WorkflowCompletedEvent workflowCompleteEvt:
                    // The workflow has completed successfully, return the result
                    string workflowResult = workflowCompleteEvt.Data!.ToString()!;
                    writer.WriteLine($"Result: {workflowResult}");
                    return workflowResult;
                case ExecutorCompletedEvent executorCompletedEvt:
                    writer.WriteLine($"'{executorCompletedEvt.ExecutorId}: {executorCompletedEvt.Data}");
                    break;
            }
        }

        throw new InvalidOperationException("Workflow failed to yield the completion event.");
    }
}

internal sealed class DetectSpamExecutor : ReflectingExecutor<DetectSpamExecutor>, IMessageHandler<string, bool>
{
    public string[] SpamKeywords { get; }

    public DetectSpamExecutor(params string[] spamKeywords)
    {
        this.SpamKeywords = spamKeywords;
    }

    public async ValueTask<bool> HandleAsync(string message, IWorkflowContext context)
    {
#if NET5_0_OR_GREATER
        bool isSpam = this.SpamKeywords.Any(keyword => message.Contains(keyword, StringComparison.OrdinalIgnoreCase));
#else
        bool isSpam = this.SpamKeywords.Any(keyword => message.IndexOf(keyword, StringComparison.OrdinalIgnoreCase) >= 0);
#endif

        return isSpam;
    }
}

internal sealed class RespondToMessageExecutor : ReflectingExecutor<RespondToMessageExecutor>, IMessageHandler<bool>
{
    public const string ActionResult = "Message processed successfully.";

    public async ValueTask HandleAsync(bool message, IWorkflowContext context)
    {
        if (message)
        {
            // This is SPAM, and should not have been routed here
            throw new InvalidOperationException("Received a spam message that should not be getting a reply.");
        }

        await Task.Delay(1000).ConfigureAwait(false); // Simulate some processing delay

        await context.AddEventAsync(new WorkflowCompletedEvent(ActionResult))
                     .ConfigureAwait(false);
    }
}

internal sealed class RemoveSpamExecutor : ReflectingExecutor<RemoveSpamExecutor>, IMessageHandler<bool>
{
    public const string ActionResult = "Spam message removed.";

    public async ValueTask HandleAsync(bool message, IWorkflowContext context)
    {
        if (!message)
        {
            // This is NOT SPAM, and should not have been routed here
            throw new InvalidOperationException("Received a non-spam message that should not be getting removed.");
        }

        await Task.Delay(1000).ConfigureAwait(false); // Simulate some processing delay

        await context.AddEventAsync(new WorkflowCompletedEvent(ActionResult))
                     .ConfigureAwait(false);
    }
}
