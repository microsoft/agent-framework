// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Reflection;

namespace Microsoft.Agents.Workflows.Sample;

internal static class Step6Switch
{
    public static async ValueTask RunAsync(TextWriter writer)
    {
        ResultExecutor caseExecutor1 = new(1);
        ResultExecutor caseExecutor2 = new(2);
        ResultExecutor caseExecutor3 = new(3);
        DefaultExecutor elseExecutor = new();
        FinalExecutor finalExecutor = new();
        DiscriminatingExecutor choiceExecutor =
            new(caseExecutor1.Id,
                caseExecutor2.Id,
                caseExecutor3.Id);

        WorkflowBuilder builder = new(choiceExecutor);
        builder.AddSwitch(
            choiceExecutor,
            switchBuilder =>
                switchBuilder
                    .AddCase(result => IsMatch(caseExecutor1.Id, result), caseExecutor1)
                    .AddCase(result => IsMatch(caseExecutor2.Id, result), caseExecutor2)
                    .AddCase(result => IsMatch(caseExecutor3.Id, result), caseExecutor3)
                    .WithDefault(elseExecutor));

        builder.AddEdge(caseExecutor1, finalExecutor);
        builder.AddEdge(caseExecutor2, finalExecutor);
        builder.AddEdge(caseExecutor3, finalExecutor);
        builder.AddEdge(elseExecutor, finalExecutor);

        Workflow<string> workflow = builder.Build<string>();
        StreamingRun run = await InProcessExecution.StreamAsync(workflow, "Hello, World!").ConfigureAwait(false);

        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            writer.WriteLine($"{evt}");
        }
    }

    private static bool IsMatch(string executorId, object? result)
    {
        return string.Equals(executorId, result as string, StringComparison.Ordinal);
    }

    private sealed class DiscriminatingExecutor(params string[] options) : ReflectingExecutor<DiscriminatingExecutor>(nameof(DiscriminatingExecutor)), IMessageHandler<string, string>
    {
        public async ValueTask<string> HandleAsync(string message, IWorkflowContext context)
        {
            int index = 0;
            foreach (char c in message)
            {
                index += c;
                index %= (options.Length + 1);
            }
            return options[index];
        }
    }

    private sealed class ResultExecutor(int index) : ReflectingExecutor<ResultExecutor>($"{nameof(ResultExecutor)}{index}"), IMessageHandler<string>
    {
        public async ValueTask HandleAsync(string message, IWorkflowContext context)
        {
            await context.AddEventAsync(new WorkflowEvent($"#{index}: {message}")).ConfigureAwait(false);
            await context.SendMessageAsync(new ExecutorCompleteMessage(this.Id)).ConfigureAwait(false);
        }
    }

    private sealed class DefaultExecutor() : ReflectingExecutor<DefaultExecutor>(nameof(DefaultExecutor)), IMessageHandler<string>
    {
        public async ValueTask HandleAsync(string message, IWorkflowContext context)
        {
            await context.AddEventAsync(new WorkflowEvent($"#else: {message}")).ConfigureAwait(false);
            await context.SendMessageAsync(new ExecutorCompleteMessage(this.Id)).ConfigureAwait(false);
        }
    }

    private sealed class FinalExecutor() : ReflectingExecutor<FinalExecutor>(nameof(FinalExecutor)), IMessageHandler<ExecutorCompleteMessage>
    {
        public async ValueTask HandleAsync(ExecutorCompleteMessage message, IWorkflowContext context)
        {
            await context.AddEventAsync(new WorkflowEvent($"#exit: {message}")).ConfigureAwait(false);
        }
    }

    private sealed record class ExecutorCompleteMessage(string ExecutorId)
    {
        public DateTime TimeStamp { get; } = DateTime.UtcNow;

        public override string ToString() => $"{this.ExecutorId}: {this.TimeStamp.ToShortTimeString()}";
    }
}
