// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents configuration options for a <see cref="StructuredOutputAgent"/>.
/// </summary>
public sealed class StructuredOutputAgentOptions
{
    /// <summary>
    /// Gets or sets the system message to use when invoking the chat client for structured output conversion.
    /// </summary>
    public string? ChatClientSystemMessage { get; set; }

    /// <summary>
    /// Gets or sets the chat options to use for the structured output conversion by the chat client
    /// used by the agent.
    /// </summary>
    /// <remarks>
    /// The <see cref="ChatOptions.ResponseFormat"/> should be set to a <see cref="ChatResponseFormatJson"/>
    /// instance to specify the expected JSON schema for the structured output.
    /// </remarks>
    public ChatOptions? ChatOptions { get; set; }
}
