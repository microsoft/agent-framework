// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Microsoft.Extensions.AI.Agents;

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
    /// Initializes a new instance of the <see cref="ChatClientAgentOptions"/> class.
    /// </summary>
    public ChatClientAgentOptions()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgentOptions"/> class with the specified parameters.
    /// </summary>
    /// <remarks>If <paramref name="tools"/> is provided, a new <see cref="ChatOptions"/> instance is created
    /// with the specified instructions and tools.</remarks>
    /// <param name="instructions">The instructions or guidelines for the chat client agent. Can be <see langword="null"/> if not specified.</param>
    /// <param name="name">The name of the chat client agent. Can be <see langword="null"/> if not specified.</param>
    /// <param name="description">The description of the chat client agent. Can be <see langword="null"/> if not specified.</param>
    /// <param name="tools">A list of <see cref="AITool"/> instances available to the chat client agent. Can be <see langword="null"/> if no
    /// tools are specified.</param>
    public ChatClientAgentOptions(string? instructions, string? name = null, string? description = null, IList<AITool>? tools = null)
    {
        this.Name = name;
        this.Instructions = instructions;
        this.Description = description;

        if (tools is not null)
        {
            (this.ChatOptions ??= new()).Tools = tools;
        }

        if (instructions is not null)
        {
            (this.ChatOptions ??= new()).Instructions = instructions;
        }
    }

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
    /// Gets or sets a factory function to create an instance of <see cref="IChatMessageStore"/>
    /// which will be used to store chat messages for this agent.
    /// </summary>
    public Func<IChatMessageStore>? ChatMessageStoreFactory { get; set; } = null;

    /// <summary>
    /// Gets or sets a value indicating whether to use the provided <see cref="IChatClient"/> instance as is,
    /// without applying any default decorators.
    /// </summary>
    /// <remarks>
    /// By default the <see cref="ChatClientAgent"/> applies decorators to the provided <see cref="IChatClient"/>
    /// for doing for example automatic function invocation. Setting this property to <see langword="true"/>
    /// disables adding these default decorators.
    /// Disabling is recommended if you want to decorate the <see cref="IChatClient"/> with different decorators
    /// than the default ones. The provided <see cref="IChatClient"/> instance should then already be decorated
    /// with the desired decorators.
    /// </remarks>
    public bool UseProvidedChatClientAsIs { get; set; } = false;

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
            ChatOptions = this.ChatOptions?.Clone(),
            ChatMessageStoreFactory = this.ChatMessageStoreFactory
        };
}
