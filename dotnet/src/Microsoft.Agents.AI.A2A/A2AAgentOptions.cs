// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.A2A;

/// <summary>
/// Represents configuration options for an <see cref="A2AAgent"/>, including its identifier, name, and description.
/// </summary>
/// <remarks>
/// This class is used to encapsulate information about an A2A agent, such as its unique
/// identifier, display name, and a descriptive summary. It provides an alternative to passing
/// these values as individual constructor parameters.
/// </remarks>
public sealed class A2AAgentOptions
{
    /// <summary>
    /// Gets or sets the agent id.
    /// </summary>
    public string? Id { get; set; }

    /// <summary>
    /// Gets or sets the agent name.
    /// </summary>
    public string? Name { get; set; }

    /// <summary>
    /// Gets or sets the agent description.
    /// </summary>
    public string? Description { get; set; }

    /// <summary>
    /// Creates a new instance of <see cref="A2AAgentOptions"/> with the same values as this instance.
    /// </summary>
    public A2AAgentOptions Clone()
        => new()
        {
            Id = this.Id,
            Name = this.Name,
            Description = this.Description
        };
}
