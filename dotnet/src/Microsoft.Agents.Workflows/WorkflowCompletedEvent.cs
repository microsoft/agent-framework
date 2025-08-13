// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Event triggered when a workflow completes execution.
/// </summary>
/// <remarks>
/// The user is expected to raise this event from a terminating <see cref="Executor"/>, or to build
/// the workflow with output capture using <see cref="WorkflowBuilderExtensions.BuildWithOutput"/>.
/// </remarks>
/// <param name="result">The result of the execution of the workflow.</param>
public sealed class WorkflowCompletedEvent(object? result = null) : WorkflowEvent(data: result);
