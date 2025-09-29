// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Event triggered when a workflow starts execution.
/// </summary>
/// <param name="message">The message triggering the start of workflow execution.</param>
public sealed class WorkflowStartedEvent(object? message = null) : WorkflowEvent(data: message);
