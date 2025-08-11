// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Optional parameters when running an agent.
/// </summary>
public class AgentRunOptions
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRunOptions"/> class.
    /// </summary>
    public AgentRunOptions()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRunOptions"/> class by cloning the provided options.
    /// </summary>
    /// <param name="options">The options to clone.</param>
    public AgentRunOptions(AgentRunOptions options)
    {
        Throw.IfNull(options);
    }

    /// <summary>
    /// Gets a function that creates a new <see cref="AgentThread"/> instance.
    /// Can be used if a specific AgentThread implementation is needed for the same agent run.
    /// </summary>
    public virtual Func<AgentThread>? GetAgentThread { get; set; }
}
