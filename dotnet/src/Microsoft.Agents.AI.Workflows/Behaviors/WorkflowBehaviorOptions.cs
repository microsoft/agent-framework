// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Microsoft.Agents.AI.Workflows.Behaviors;

/// <summary>
/// Provides options for configuring workflow and executor behaviors.
/// </summary>
public sealed class WorkflowBehaviorOptions
{
    internal List<IExecutorBehavior> ExecutorBehaviors { get; } = new();
    internal List<IWorkflowBehavior> WorkflowBehaviors { get; } = new();

    /// <summary>
    /// Registers an executor behavior instance to the pipeline.
    /// </summary>
    /// <param name="behavior">The executor behavior instance to register.</param>
    /// <returns>The current options instance for method chaining.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="behavior"/> is null.</exception>
    public WorkflowBehaviorOptions AddExecutorBehavior(IExecutorBehavior behavior)
    {
        this.ExecutorBehaviors.Add(behavior ?? throw new ArgumentNullException(nameof(behavior)));
        return this;
    }

    /// <summary>
    /// Registers a workflow behavior instance to the pipeline.
    /// </summary>
    /// <param name="behavior">The workflow behavior instance to register.</param>
    /// <returns>The current options instance for method chaining.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="behavior"/> is null.</exception>
    public WorkflowBehaviorOptions AddWorkflowBehavior(IWorkflowBehavior behavior)
    {
        this.WorkflowBehaviors.Add(behavior ?? throw new ArgumentNullException(nameof(behavior)));
        return this;
    }

    /// <summary>
    /// Registers an executor behavior using a parameterless constructor.
    /// </summary>
    /// <typeparam name="TBehavior">The type of executor behavior to register.</typeparam>
    /// <returns>The current options instance for method chaining.</returns>
    public WorkflowBehaviorOptions AddExecutorBehavior<TBehavior>()
        where TBehavior : IExecutorBehavior, new()
    {
        return this.AddExecutorBehavior(new TBehavior());
    }

    /// <summary>
    /// Registers a workflow behavior using a parameterless constructor.
    /// </summary>
    /// <typeparam name="TBehavior">The type of workflow behavior to register.</typeparam>
    /// <returns>The current options instance for method chaining.</returns>
    public WorkflowBehaviorOptions AddWorkflowBehavior<TBehavior>()
        where TBehavior : IWorkflowBehavior, new()
    {
        return this.AddWorkflowBehavior(new TBehavior());
    }

    /// <summary>
    /// Builds a behavior pipeline from the registered behaviors.
    /// </summary>
    /// <returns>A new <see cref="BehaviorPipeline"/> instance.</returns>
    internal BehaviorPipeline BuildPipeline()
    {
        return new BehaviorPipeline(this.ExecutorBehaviors, this.WorkflowBehaviors);
    }
}
