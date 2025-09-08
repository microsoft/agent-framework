// Copyright (c) Microsoft. All rights reserved.

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
    /// Specifies whether the agent should await the long-running operation completion.
    /// </summary>
    public bool? AwaitLongRunCompletion { get; set; }

    /// <summary>
    /// Specifies the identifier of an update within a conversation to start generating chat responses after.
    /// </summary>
    public string? StartAfter { get; set; }

    /// <summary>
    /// Specifies identifier of either a long-running operation or an identifier
    /// of an entity representing a long-running operation.
    /// </summary>
    public string? ResponseId { get; set; }
}
