// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Specialized;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Represents a workflow that results in <typeparamref name="TResult"/>.
/// </summary>
/// <typeparam name="TResult">The type of the output from the workflow.</typeparam>
public class WorkflowWithOutput<TResult> : Workflow
{
    private readonly IOutputSink<TResult> _output;

    internal WorkflowWithOutput(string startExecutorId, IOutputSink<TResult> outputSource)
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

    /// <inheritdoc cref="Workflow.TryPromoteWithOutputAsync{TInput, TResult}(IOutputSink{TResult})"/>
    public new ValueTask<WorkflowWithOutput<TInput, TResult>?> TryPromoteAsync<TInput>()
        => this.TryPromoteWithOutputAsync<TInput, TResult>(this._output);
}

/// <summary>
/// Represents a workflow that operates on data of type <typeparamref name="TInput"/>, resulting in
/// <typeparamref name="TResult"/>.
/// </summary>
/// <typeparam name="TInput">The type of input to the workflow.</typeparam>
/// <typeparam name="TResult">The type of the output from the workflow.</typeparam>
public class WorkflowWithOutput<TInput, TResult> : WorkflowWithOutput<TResult>
{
    internal WorkflowWithOutput(string startExecutorId, IOutputSink<TResult> outputSource) : base(startExecutorId, outputSource)
    {
        this.InputType = typeof(TInput);
    }

    /// <summary>
    /// Gets the type of input expected by the starting executor of the workflow.
    /// </summary>
    public Type InputType { get; }
}
