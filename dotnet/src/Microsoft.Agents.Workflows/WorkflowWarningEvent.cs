// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Event triggered when a workflow encounters a warning-condition.
/// </summary>
/// <param name="message">The warning message.</param>
public sealed class WorkflowWarningEvent(string message) : WorkflowEvent(message);
