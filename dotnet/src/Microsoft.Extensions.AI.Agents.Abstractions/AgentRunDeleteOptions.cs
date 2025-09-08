// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Optional parameters when deleting long-running operation of an agent.
/// </summary>
public class AgentRunDeleteOptions
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRunDeleteOptions"/> class.
    /// </summary>
    public AgentRunDeleteOptions()
    {
    }

    /// <summary>
    /// Agent thread a long-running operation is associated with.
    /// </summary>
    public AgentThread? Thread { get; set; }
}
