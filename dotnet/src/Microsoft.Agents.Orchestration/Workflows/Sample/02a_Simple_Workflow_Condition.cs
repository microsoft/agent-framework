// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Orchestration.Workflows.Core;

namespace Microsoft.Agents.Orchestration.Workflows.Sample;

internal static class Step2aEntryPoint
{
    public static ValueTask RunAsync()
    {
        string[] spamKeywords = { "spam", "advertisement", "offer" };

        DetectSpamExecutor detectSpam = new(spamKeywords);
        RespondToMessageExecutor respondToMessage = new();
        RemoveSpamExecutor removeSpam = new();

        Workflow<string> workflow = new WorkflowBuilder(detectSpam)
            .AddEdge(detectSpam, respondToMessage, isSpam => isSpam is true) // If not spam, respond
            .AddEdge(detectSpam, removeSpam, isSpam => isSpam is false) // If spam, remove
            .Build<string>();

        // async foreach (var event in workflow.RunAsync("This is a spam message."))
        //     await Console.Out.WriteLineAsync(event);

        return CompletedValueTaskSource.Completed;
    }
}

internal class DetectSpamExecutor : Executor, IMessageHandler<string, bool>
{
    public string[] SpamKeywords { get; }

    public DetectSpamExecutor(params string[] spamKeywords)
    {
        this.SpamKeywords = spamKeywords;
    }

    public ValueTask<bool> HandleAsync(string message, IExecutionContext context)
    {
#if NET5_0_OR_GREATER
        bool isSpam = this.SpamKeywords.Any(keyword => message.Contains(keyword, StringComparison.OrdinalIgnoreCase));
#else
        bool isSpam = this.SpamKeywords.Any(keyword => message.IndexOf(keyword, StringComparison.OrdinalIgnoreCase) >= 0);
#endif

        return CompletedValueTaskSource.FromResult(isSpam);
    }
}

internal class RespondToMessageExecutor : Executor, IMessageHandler<bool>
{
    public async ValueTask HandleAsync(bool message, IExecutionContext context)
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

internal class RemoveSpamExecutor : Executor, IMessageHandler<bool>
{
    public async ValueTask HandleAsync(bool message, IExecutionContext context)
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
