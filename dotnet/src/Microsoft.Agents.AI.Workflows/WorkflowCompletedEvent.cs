// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Event triggered when a workflow run reaches a terminal state and the event stream completes,
/// regardless of whether the workflow completed successfully or was halted early.
/// </summary>
/// <param name="result">The optional result produced by the workflow upon run completion.</param>
public sealed class WorkflowCompletedEvent(object? result = null) : WorkflowEvent(data: result);
