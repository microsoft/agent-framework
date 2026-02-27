// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace SampleApp;

/// <summary>
/// Represents configuration options for a <see cref="StructuredOutputAgent"/>.
/// </summary>
#pragma warning disable CA1812 // Instantiated via AIAgentBuilderExtensions.UseStructuredOutput optionsFactory parameter
internal sealed class StructuredOutputAgentOptions
#pragma warning restore CA1812
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
    /// This property is optional. The <see cref="ChatOptions.ResponseFormat"/> should be set to a
    /// <see cref="ChatResponseFormatJson"/> instance to specify the expected JSON schema for the structured output.
    /// Note that if <see cref="AgentRunOptions.ResponseFormat"/> is provided when running the agent,
    /// it will take precedence and override the <see cref="ChatOptions.ResponseFormat"/> specified here.
    /// </remarks>
    public ChatOptions? ChatOptions { get; set; }
}
