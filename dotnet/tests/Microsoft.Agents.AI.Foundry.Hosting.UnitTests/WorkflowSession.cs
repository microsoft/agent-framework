// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Stands in for the session a hosted workflow runs with, which the handler recognises by its full
/// type name because the real one is internal to its own package.
/// </summary>
/// <remarks>
/// Declared in the real type's namespace on purpose: the handler matches the full name, so a double
/// declared anywhere else would not exercise the check. The real type is internal to another assembly,
/// so nothing here is ambiguous with it.
/// </remarks>
internal sealed class WorkflowSession : AgentSession
{
}
