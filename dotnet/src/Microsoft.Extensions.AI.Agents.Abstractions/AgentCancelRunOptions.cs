// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Optional parameters when cancelling long-running operation.
/// </summary>
public class AgentCancelRunOptions
{
    /// <summary>
    /// Agent thread a long-running operation is associated with.
    /// </summary>
    public AgentThread? Thread { get; set; }
}
