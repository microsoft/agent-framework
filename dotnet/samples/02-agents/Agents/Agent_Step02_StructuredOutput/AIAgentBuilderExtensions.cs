// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace SampleApp;

/// <summary>
/// Provides extension methods for adding structured output capabilities to <see cref="AIAgentBuilder"/> instances.
/// </summary>
internal static class AIAgentBuilderExtensions
{
    /// <summary>
    /// Adds structured output capabilities to the agent pipeline, enabling conversion of text responses to structured JSON format.
    /// </summary>
    /// <param name="builder">The <see cref="AIAgentBuilder"/> to which structured output support will be added.</param>
    /// <param name="chatClient">
    /// The chat client used to transform text responses into structured JSON format.
    /// If <see langword="null"/>, the chat client will be resolved from the service provider.
    /// </param>
    /// <param name="optionsFactory">
    /// An optional factory function that returns the <see cref="StructuredOutputAgentOptions"/> instance to use.
    /// This allows for fine-tuning the structured output behavior such as setting the response format or system message.
    /// </param>
    /// <returns>The <see cref="AIAgentBuilder"/> with structured output capabilities added, enabling method chaining.</returns>
    /// <remarks>
    /// <para>
    /// A <see cref="ChatResponseFormatJson"/> must be specified either through the
    /// <see cref="AgentRunOptions.ResponseFormat"/> at runtime or the <see cref="StructuredOutputAgentOptions.ChatOptions"/>
    /// provided during configuration.
    /// </para>
    /// </remarks>
    public static AIAgentBuilder UseStructuredOutput(
        this AIAgentBuilder builder,
        IChatClient? chatClient = null,
        Func<StructuredOutputAgentOptions>? optionsFactory = null)
    {
        ArgumentNullException.ThrowIfNull(builder);

        return builder.Use((innerAgent, services) =>
        {
            chatClient ??= services?.GetService<IChatClient>()
                ?? throw new InvalidOperationException($"No {nameof(IChatClient)} was provided and none could be resolved from the service provider. Either provide an {nameof(IChatClient)} explicitly or register one in the dependency injection container.");

            return new StructuredOutputAgent(innerAgent, chatClient, optionsFactory?.Invoke());
        });
    }
}
