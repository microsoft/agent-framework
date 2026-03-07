// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Event triggered when a workflow completes execution successfully.
/// </summary>
/// <param name="result">The optional result produced by the workflow upon completion.</param>
public sealed class WorkflowCompletedEvent(object? result = null) : WorkflowEvent(data: result);
