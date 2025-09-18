// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Specialized;

internal sealed class OutputCollectorExecutor<TInput, TResult> : Executor, IOutputSink<TResult>
{
    private readonly StreamingAggregator<TInput, TResult> _aggregator;
    private readonly Func<TInput, TResult?, bool>? _completionCondition;

    public TResult? Result { get; private set; }

    public OutputCollectorExecutor(StreamingAggregator<TInput, TResult> aggregator, Func<TInput, TResult?, bool>? completionCondition = null, string? id = null) : base(id)
    {
        this._aggregator = Throw.IfNull(aggregator);
        this._completionCondition = completionCondition;
    }

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
        routeBuilder.AddHandler<TInput>(this.HandleAsync);

    public ValueTask HandleAsync(TInput message, IWorkflowContext context)
    {
        this.Result = this._aggregator(message, this.Result);

        if (this._completionCondition is not null &&
            this._completionCondition!(message, this.Result))
        {
            return context.AddEventAsync(new WorkflowCompletedEvent(this.Result));
        }

        return default;
    }
}
