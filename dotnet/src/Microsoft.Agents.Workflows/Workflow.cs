// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Agents.Workflows.Checkpointing;
using Microsoft.Agents.Workflows.Specialized;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// A class that represents a workflow that can be executed.
/// </summary>
public class Workflow
{
    /// <summary>
    /// A dictionary of executor providers, keyed by executor ID.
    /// </summary>
    internal Dictionary<string, ExecutorRegistration> Registrations { get; init; } = [];

    internal Dictionary<string, HashSet<Edge>> Edges { get; init; } = [];

    /// <summary>
    /// Gets the collection of edges grouped by their source node identifier.
    /// </summary>
    public Dictionary<string, HashSet<EdgeInfo>> ReflectEdges()
    {
        return this.Edges.Keys.ToDictionary(
            keySelector: key => key,
            elementSelector: key => new HashSet<EdgeInfo>(this.Edges[key].Select(RepresentationExtensions.ToEdgeInfo))
        );
    }

    internal Dictionary<string, InputPort> Ports { get; init; } = [];

    /// <summary>
    /// Gets the collection of external request ports, keyed by their ID.
    /// </summary>
    /// <remarks>
    /// Each port has a corresponding entry in the <see cref="Registrations"/> dictionary.
    /// </remarks>
    public Dictionary<string, InputPortInfo> ReflectPorts()
    {
        return this.Ports.Keys.ToDictionary(
            keySelector: key => key,
            elementSelector: key => this.Ports[key].ToPortInfo()
        );
    }

    /// <summary>
    /// Gets the identifier of the starting executor of the workflow.
    /// </summary>
    public string StartExecutorId { get; }

    /// <summary>
    /// Gets the type of input expected by the starting executor of the workflow.
    /// </summary>
    public Type InputType { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="Workflow"/> class with the specified starting executor identifier
    /// and input type.
    /// </summary>
    /// <param name="startExecutorId">The unique identifier of the starting executor for the workflow. Cannot be <c>null</c>.</param>
    /// <param name="type">The <see cref="Type"/> representing the input data for the workflow. Cannot be <c>null</c>.</param>
    internal Workflow(string startExecutorId, Type type)
    {
        this.StartExecutorId = Throw.IfNull(startExecutorId);
        this.InputType = Throw.IfNull(type);
    }
}

/// <summary>
/// Represents a workflow that operates on data of type <typeparamref name="T"/>.
/// </summary>
/// <typeparam name="T">The type of input to the workflow.</typeparam>
public class Workflow<T> : Workflow
{
    /// <summary>
    /// Initializes a new instance of the <see cref="Workflow{T}"/> class with the specified starting executor identifier
    /// </summary>
    /// <param name="startExecutorId">The unique identifier of the starting executor for the workflow. Cannot be <c>null</c>.</param>
    public Workflow(string startExecutorId) : base(startExecutorId, typeof(T))
    {
    }

    internal Workflow<T, TResult> Promote<TResult>(IOutputSink<TResult> outputSource)
    {
        Throw.IfNull(outputSource);

        return new Workflow<T, TResult>(this.StartExecutorId, outputSource)
        {
            Registrations = this.Registrations,
            Edges = this.Edges,
            Ports = this.Ports
        };
    }
}

/// <summary>
/// Represents a workflow that operates on data of type <typeparamref name="TInput"/>, resulting in
/// <typeparamref name="TResult"/>.
/// </summary>
/// <typeparam name="TInput">The type of input to the workflow.</typeparam>
/// <typeparam name="TResult">The type of the output from the workflow.</typeparam>
public class Workflow<TInput, TResult> : Workflow<TInput>
{
    private readonly IOutputSink<TResult> _output;

    internal Workflow(string startExecutorId, IOutputSink<TResult> outputSource)
        : base(startExecutorId)
    {
        this._output = Throw.IfNull(outputSource);
    }

    /// <summary>
    /// Gets the unique identifier of the output collector.
    /// </summary>
    public string OutputCollectorId => this._output.Id;

    /// <summary>
    /// The running (partial) output of the workflow, if any.
    /// </summary>
    public TResult? RunningOutput => this._output.Result;
}
