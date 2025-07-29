// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;

namespace Microsoft.Agents.Workflows;

internal static class Check
{
    public static T NotNull<T>(T? value, [CallerArgumentExpression(nameof(value))] string? paramExpr = null) where T : class
    {
        if (value is null)
        {
            throw new ArgumentNullException(nameof(value), $"Value cannot be null: {paramExpr}");
        }

        return value;
    }
}

internal enum Activation
{
    WhenAll,
}

internal static class WorkflowBuilderExtensions
{
    public static WorkflowBuilder AddLoop(this WorkflowBuilder builder, ExecutorIsh source, ExecutorIsh loopBody, Func<object?, bool>? condition = null)
    {
        Check.NotNull(builder);
        Check.NotNull(source);
        Check.NotNull(loopBody);

        builder.AddEdge(source, loopBody, condition);
        builder.AddEdge(loopBody, source);

        return builder;
    }

    public static WorkflowBuilder AddChain(this WorkflowBuilder builder, ExecutorIsh source, params ExecutorIsh[] executors)
    {
        Check.NotNull(builder);
        Check.NotNull(source);

        for (int i = 0; i < executors.Length; i++)
        {
            Check.NotNull(executors[i], nameof(executors) + $"[{i}]");
            builder.AddEdge(source, executors[i]);
            source = executors[i];
        }

        return builder;
    }

    private class FanOutMessage(object message)
    {
        public object Content = message ?? throw new ArgumentNullException(nameof(message), "Message cannot be null");
    }

    private class FanInMessage(IEnumerable<object>? message = null)
    {
        public static readonly FanInMessage Pending = new();

        public bool IsCompleted => this.Result is not null;
        public IEnumerable<object>? Result = message;
    }

    private class FanOutExecutor : Executor, IMessageHandler<object, FanOutMessage>
    {
        public ValueTask<FanOutMessage> HandleAsync(object message, IExecutionContext context)
        {
            return new ValueTask<FanOutMessage>(new FanOutMessage(message));
        }
    }

    public static WorkflowBuilder AddFanOut(this WorkflowBuilder builder, ExecutorIsh source, params ExecutorIsh[] targets)
    {
        Check.NotNull(builder);
        Check.NotNull(source);

        FanOutExecutor fanOut = new();
        builder.AddEdge(source, fanOut);

        foreach (var target in targets)
        {
            Check.NotNull(target);
            builder.AddEdge(fanOut, target);
        }

        return builder;
    }

    private class FanInExecutor : Executor,
                                  IMessageHandler<FanOutMessage, FanInMessage>
    {
#if NET9_0_OR_GREATER
        required
#endif
        public int SourceCount
        { get; init; }

        public Activation Activation { get; init; } = Activation.WhenAll;

        private readonly List<object> _messages = [];
        public ValueTask<FanInMessage> HandleAsync(FanOutMessage message, IExecutionContext context)
        {
            this._messages.Add(message.Content);

            if (this._messages.Count >= this.SourceCount)
            {
                return new ValueTask<FanInMessage>(new FanInMessage(this._messages.ToArray()));
            }

            return CompletedValueTaskSource.FromResult(FanInMessage.Pending);
        }
    }

    private class FanInUnwrapper : Executor,
                                  IMessageHandler<FanInMessage, IEnumerable<object>>
    {
        public ValueTask<IEnumerable<object>> HandleAsync(FanInMessage message, IExecutionContext context)
        {
            return CompletedValueTaskSource.FromResult(message.Result!);
        }
    }

    public static WorkflowBuilder AddFanIn(this WorkflowBuilder builder, ExecutorIsh target, Activation activation = Activation.WhenAll, params ExecutorIsh[] sources)
    {
        Check.NotNull(builder);
        Check.NotNull(target);

        FanInExecutor fanIn = new()
        {
            Activation = activation,
            SourceCount = sources.Length
        };
        FanInUnwrapper unwrapper = new();

        builder.AddEdge(fanIn, unwrapper, IsFanInCompleted);
        builder.AddEdge(unwrapper, target);

        foreach (var source in sources)
        {
            Check.NotNull(source);
            builder.AddEdge(source, fanIn);
        }

        return builder;

        static bool IsFanInCompleted(object? message) => message is FanInMessage fanIn && fanIn.IsCompleted;
    }
}
