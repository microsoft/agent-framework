// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Reflection;

namespace Microsoft.Agents.AI.Workflows.Sample;

internal static class Step2EntryPoint
{
    public static Workflow WorkflowInstance
    {
        get
        {
            string[] spamKeywords = ["spam", "advertisement", "offer"];

            DetectSpamExecutor detectSpam = new("DetectSpam", spamKeywords);
            RespondToMessageExecutor respondToMessage = new("RespondToMessage");
            RemoveSpamExecutor removeSpam = new("RemoveSpam");

            return new WorkflowBuilder(detectSpam)
                .AddEdge(detectSpam, respondToMessage, (bool isSpam) => !isSpam) // If not spam, respond
                .AddEdge(detectSpam, removeSpam, (bool isSpam) => isSpam) // If spam, remove
                .WithOutputFrom(respondToMessage, removeSpam)
                .Build();
        }
    }

    public static async ValueTask<string> RunAsync(TextWriter writer, IWorkflowExecutionEnvironment environment, string input = "This is a spam message.")
    {
        StreamingRun handle = await environment.StreamAsync(WorkflowInstance, input).ConfigureAwait(false);
        await foreach (WorkflowEvent evt in handle.WatchStreamAsync().ConfigureAwait(false))
        {
            switch (evt)
            {
                case WorkflowOutputEvent workflowOutputEvt:
                    // The workflow has completed successfully, return the result
                    string workflowResult = workflowOutputEvt.As<string>()!;
                    writer.WriteLine($"Result: {workflowResult}");
                    return workflowResult;
                case ExecutorCompletedEvent executorCompletedEvt:
                    writer.WriteLine($"'{executorCompletedEvt.ExecutorId}: {executorCompletedEvt.Data}");
                    break;
            }
        }

        throw new InvalidOperationException("Workflow failed to yield an output.");
    }
}

internal sealed class DetectSpamExecutor(string id, params string[] spamKeywords) :
    ReflectingExecutor<DetectSpamExecutor>(id, declareCrossRunShareable: true), IMessageHandler<string, bool>
{
    public async ValueTask<bool> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default) =>
        spamKeywords.Any(keyword => message.IndexOf(keyword, StringComparison.OrdinalIgnoreCase) >= 0);
}

internal sealed class RespondToMessageExecutor(string id) : ReflectingExecutor<RespondToMessageExecutor>(id, declareCrossRunShareable: true), IMessageHandler<bool>
{
    public const string ActionResult = "Message processed successfully.";

    public async ValueTask HandleAsync(bool message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        if (message)
        {
            // This is SPAM, and should not have been routed here
            throw new InvalidOperationException("Received a spam message that should not be getting a reply.");
        }

        await Task.Delay(1000, cancellationToken).ConfigureAwait(false); // Simulate some processing delay

        await context.YieldOutputAsync(ActionResult, cancellationToken)
                     .ConfigureAwait(false);
    }
}

internal sealed class RemoveSpamExecutor(string id) : ReflectingExecutor<RemoveSpamExecutor>(id, declareCrossRunShareable: true), IMessageHandler<bool>
{
    public const string ActionResult = "Spam message removed.";

    public async ValueTask HandleAsync(bool message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        if (!message)
        {
            // This is NOT SPAM, and should not have been routed here
            throw new InvalidOperationException("Received a non-spam message that should not be getting removed.");
        }

        await Task.Delay(1000, cancellationToken).ConfigureAwait(false); // Simulate some processing delay

        await context.YieldOutputAsync(ActionResult, cancellationToken)
                     .ConfigureAwait(false);
    }
}
