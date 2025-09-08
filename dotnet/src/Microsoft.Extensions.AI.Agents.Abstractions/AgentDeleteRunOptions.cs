// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Optional parameters when deleting long-running operation.
/// </summary>
public class AgentDeleteRunOptions
{
    /// <summary>
    /// Agent thread a long-running operation is associated with.
    /// </summary>
    public AgentThread? Thread { get; set; }
}
