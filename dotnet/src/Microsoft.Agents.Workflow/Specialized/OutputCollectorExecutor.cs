// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Specialized;

internal class OutputSink<TResult> : Executor
{
    public TResult? Result { get; protected set; } = default;

    internal OutputSink(string? id = null) : base(id)
    { }
}

internal class OutputCollectorExecutor<TInput, TResult> : OutputSink<TResult>, IMessageHandler<TInput>
{
    private readonly StreamingAggregator<TInput, TResult> _aggregator;
    public OutputCollectorExecutor(StreamingAggregator<TInput, TResult> aggregator, string? id = null) : base(id)
    {
        this._aggregator = Throw.IfNull(aggregator);
    }

    public ValueTask HandleAsync(TInput message, IWorkflowContext context)
    {
        this.Result = this._aggregator(message);
        return default;
    }
}
