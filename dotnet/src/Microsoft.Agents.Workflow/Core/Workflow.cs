// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Core;

internal class Workflow
{
    public Dictionary<string, ExecutorProvider<Executor>> ExecutorProviders { get; internal init; } = new();
    public Dictionary<string, HashSet<FlowEdge>> Edges { get; internal init; } = new();

#if NET9_0_OR_GREATER
    required
#endif
    public string StartExecutorId
    { get; init; }

#if NET9_0_OR_GREATER
    required
#endif
    public Type InputType
    { get; init; } = typeof(object);

    public Workflow(string startExecutorId, Type type)
    {
        this.StartExecutorId = startExecutorId ?? throw new ArgumentNullException(nameof(startExecutorId));
        this.InputType = type ?? throw new ArgumentNullException(nameof(type));

        // TODO: How do we (1) ensure the types are happy, and (2) work under AOT?
    }

#if NET9_0_OR_GREATER
    public Workflow()
    { }
#endif
}

internal class Workflow<T> : Workflow
{
    public Workflow(string startExecutorId) : base(startExecutorId, typeof(T))
    {
    }

#if NET9_0_OR_GREATER
    public Workflow()
    {
        this.InputType = typeof(T);
    }
#endif

    internal Workflow<T, TResult> Promote<TResult>(OutputSink<TResult> outputSource)
    {
        Throw.IfNull(outputSource);

        return new Workflow<T, TResult>(this.StartExecutorId, outputSource)
        {
            StartExecutorId = this.StartExecutorId,
            ExecutorProviders = this.ExecutorProviders,
            Edges = this.Edges,
            InputType = this.InputType,
        };
    }
}

internal class Workflow<TInput, TResult> : Workflow<TInput>
{
    private readonly OutputSink<TResult> _output;

    internal Workflow(string startExecutorId, OutputSink<TResult> outputSource)
        : base(startExecutorId)
    {
        this._output = Throw.IfNull(outputSource);
    }

    public TResult? RunningOutput => this._output.Result;
}
