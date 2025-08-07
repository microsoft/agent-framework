// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Agents.Workflows.Specialized;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// .
/// </summary>
public class Workflow
{
    /// <summary>
    /// .
    /// </summary>
    public Dictionary<string, ExecutorProvider<Executor>> ExecutorProviders { get; internal init; } = new();

    /// <summary>
    /// .
    /// </summary>
    public Dictionary<string, HashSet<Edge>> Edges { get; internal init; } = new();

    /// <summary>
    /// .
    /// </summary>
    public Dictionary<string, InputPort> Ports { get; internal init; } = new();

    /// <summary>
    /// .
    /// </summary>
    public string StartExecutorId { get; }

    /// <summary>
    /// .
    /// </summary>
    public Type InputType { get; }

    internal Workflow(string startExecutorId, Type type)
    {
        this.StartExecutorId = Throw.IfNull(startExecutorId);
        this.InputType = Throw.IfNull(type);

        // TODO: How do we (1) ensure the types are happy, and (2) work under AOT?
    }
}

/// <summary>
/// .
/// </summary>
/// <typeparam name="T"></typeparam>
public class Workflow<T> : Workflow
{
    /// <summary>
    /// .
    /// </summary>
    /// <param name="startExecutorId"></param>
    public Workflow(string startExecutorId) : base(startExecutorId, typeof(T))
    {
    }

    internal Workflow<T, TResult> Promote<TResult>(OutputSink<TResult> outputSource)
    {
        Throw.IfNull(outputSource);

        return new Workflow<T, TResult>(this.StartExecutorId, outputSource)
        {
            ExecutorProviders = this.ExecutorProviders,
            Edges = this.Edges,
            Ports = this.Ports
        };
    }
}

/// <summary>
/// .
/// </summary>
/// <typeparam name="TInput"></typeparam>
/// <typeparam name="TResult"></typeparam>
public class Workflow<TInput, TResult> : Workflow<TInput>
{
    private readonly OutputSink<TResult> _output;

    internal Workflow(string startExecutorId, OutputSink<TResult> outputSource)
        : base(startExecutorId)
    {
        this._output = Throw.IfNull(outputSource);
    }

    /// <summary>
    /// .
    /// </summary>
    public TResult? RunningOutput => this._output.Result;
}
