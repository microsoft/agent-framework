// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents an output for an agent.
/// </summary>
public sealed class AgentOutput
{
    /// <summary>
    /// Gets or sets the type of the output.
    /// </summary>
    /// <remarks>
    /// This can be either a string, number, array, object, or boolean.
    /// </remarks>
    public string? Type { get; set; }

    /// <summary>
    /// Gets or sets the name of the output.
    /// </summary>
    public string? Name { get; set; }

    /// <summary>
    /// Gets or sets a description of the output.
    /// </summary>
    public string? Description { get; set; }

    /// <summary>
    /// Gets or sets JSON Schema describing this output.
    /// </summary>
    public string? JsonSchema { get; set; }
}
