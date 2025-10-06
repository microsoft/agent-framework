// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Event triggered when a workflow encounters a warning-condition.
/// </summary>
/// <param name="message">The warning message.</param>
public class WorkflowWarningEvent(string message) : WorkflowEvent(message);
