// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Optional parameters when cancelling long-running operation of an agent.
/// </summary>
public class AgentRunCancelOptions
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRunOptions"/> class.
    /// </summary>
    public AgentRunCancelOptions()
    {
    }

    /// <summary>
    /// Agent thread a long-running operation is associated with.
    /// </summary>
    public AgentThread? Thread { get; set; }
}
