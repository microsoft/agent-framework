// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
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
        _ = Throw.IfNull(options);
    }

    /// <summary>
    /// Specifies whether the agent should allow long-running runs if supported by underlying service.
    /// </summary>
    public bool? AllowLongRuns { get; set; }

    /// <summary>
    /// Token to get result of a long-running operation.
    /// </summary>
    public ContinuationToken? ContinuationToken { get; set; }
}
