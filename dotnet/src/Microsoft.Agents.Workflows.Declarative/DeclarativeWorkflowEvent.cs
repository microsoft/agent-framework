// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Base class for events that occur during the execution of a declarative workflow.
/// </summary>
public class DeclarativeWorkflowEvent(object? data) : WorkflowEvent(data)
{
}
