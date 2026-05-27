// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Represents the input envelope for a durable workflow orchestration.
/// </summary>
/// <typeparam name="TInput">The type of the workflow input.</typeparam>
internal sealed class DurableWorkflowInput<TInput>
    where TInput : notnull
{
    /// <summary>
    /// Gets the workflow input data.
    /// </summary>
    public required TInput Input { get; init; }
}
