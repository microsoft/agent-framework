// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.Sample;

internal static class Step2aEntryPoint
{
    public static async ValueTask RunAsync()
    {
        string[] spamKeywords = { "spam", "advertisement", "offer" };

        DetectSpamExecutor detectSpam = new(spamKeywords);
        RespondToMessageExecutor respondToMessage = new();
        RemoveSpamExecutor removeSpam = new();

        Workflow<string> workflow = new WorkflowBuilder(detectSpam)
            .AddEdge(detectSpam, respondToMessage, isSpam => isSpam is true) // If not spam, respond
            .AddEdge(detectSpam, removeSpam, isSpam => isSpam is false) // If spam, remove
            .Build<string>();

        LocalRunner<string> runner = new(workflow);

        StreamingExecutionHandle handle = await runner.StreamAsync("This is a spam message.").ConfigureAwait(false);
        await handle.RunToCompletionAsync().ConfigureAwait(false);
    }
}

internal sealed class DetectSpamExecutor : Executor, IMessageHandler<string, bool>
{
    public string[] SpamKeywords { get; }

    public DetectSpamExecutor(params string[] spamKeywords)
    {
        this.SpamKeywords = spamKeywords;
    }

    public ValueTask<bool> HandleAsync(string message, IWorkflowContext context)
    {
#if NET5_0_OR_GREATER
        bool isSpam = this.SpamKeywords.Any(keyword => message.Contains(keyword, StringComparison.OrdinalIgnoreCase));
#else
        bool isSpam = this.SpamKeywords.Any(keyword => message.IndexOf(keyword, StringComparison.OrdinalIgnoreCase) >= 0);
#endif

        return CompletedValueTaskSource.FromResult(isSpam);
    }
}

internal sealed class RespondToMessageExecutor : Executor, IMessageHandler<bool>
{
    public async ValueTask HandleAsync(bool message, IWorkflowContext context)
    {
        if (message)
        {
            // This is SPAM, and should not have been routed here
            throw new InvalidOperationException("Received a spam message that should not be getting a reply.");
        }

        await Task.Delay(1000).ConfigureAwait(false); // Simulate some processing delay

        await context.AddEventAsync(new WorkflowCompletedEvent { Data = "Message processed successfully." })
                     .ConfigureAwait(false);
    }
}

internal sealed class RemoveSpamExecutor : Executor, IMessageHandler<bool>
{
    public async ValueTask HandleAsync(bool message, IWorkflowContext context)
    {
        if (!message)
        {
            // This is NOT SPAM, and should not have been routed here
            throw new InvalidOperationException("Received a non-spam message that should not be getting removed.");
        }

        await Task.Delay(1000).ConfigureAwait(false); // Simulate some processing delay

        await context.AddEventAsync(new WorkflowCompletedEvent { Data = "Spam message removed." })
                     .ConfigureAwait(false);
    }
}
