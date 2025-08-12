// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Specialized;

internal interface IOutputSink<TResult>
{
    TResult? Result { get; }
}

internal class OutputCollectorExecutor<TInput, TResult> :
    Executor<OutputCollectorExecutor<TInput, TResult>>,
    IMessageHandler<TInput>,
    IOutputSink<TResult>
{
    private readonly StreamingAggregator<TInput, TResult> _aggregator;
    private readonly Func<TInput, TResult?, bool>? _completionCondition;

    public TResult? Result { get; private set; }

    public OutputCollectorExecutor(StreamingAggregator<TInput, TResult> aggregator, Func<TInput, TResult?, bool>? completionCondition = null, string? id = null) : base(id)
    {
        this._aggregator = Throw.IfNull(aggregator);
        this._completionCondition = completionCondition;
    }

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
