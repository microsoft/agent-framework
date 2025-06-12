// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents;

/// <summary>
/// Represents metadata for a chat client agent, including its identifier, name, instructions, and description.
/// </summary>
/// <remarks>
/// This class is used to encapsulate information about a chat client agent, such as its unique
/// identifier, display name, operational instructions, and a descriptive summary. It can be used to store and transfer
/// agent-related metadata within a chat application.
/// </remarks>
public class ChatClientAgentOptions
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
    /// Gets or sets the agent instructions.
    /// </summary>
    public string? Instructions { get; set; }

    /// <summary>
    /// Gets or sets the agent description.
    /// </summary>
    public string? Description { get; set; }

    /// <summary>
    /// Gets or sets the default chatOptions to use.
    /// </summary>
    public ChatOptions? ChatOptions { get; set; }

    /// <summary>
    /// Creates a new instance of <see cref="ChatClientAgentOptions"/> with the same values as this instance.
    /// </summary>
    internal ChatClientAgentOptions Clone()
        => new()
        {
            Id = this.Id,
            Name = this.Name,
            Instructions = this.Instructions,
            Description = this.Description,
            ChatOptions = this.ChatOptions?.Clone()
        };
}
