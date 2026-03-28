// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace OpenAI.Responses;

/// <summary>
/// Provides extension methods for <see cref="ResponsesClient"/>
/// to simplify the creation of AI agents that work with OpenAI services.
/// </summary>
/// <remarks>
/// These extensions bridge the gap between OpenAI SDK client objects and the Microsoft Agent Framework,
/// allowing developers to easily create AI agents that leverage OpenAI's chat completion and response services.
/// The methods handle the conversion from OpenAI clients to <see cref="IChatClient"/> instances and then wrap them
/// in <see cref="ChatClientAgent"/> objects that implement the <see cref="AIAgent"/> interface.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public static class OpenAIResponseClientExtensions
{
    /// <summary>
    /// Creates an AI agent from an <see cref="ResponsesClient"/> using the OpenAI Response API.
    /// </summary>
    /// <param name="client">The <see cref="ResponsesClient" /> to use for the agent.</param>
    /// <param name="model">Optional default model ID to use for requests. Required when using a plain <see cref="ResponsesClient"/> (not via Azure OpenAI).</param>
    /// <param name="instructions">Optional system instructions that define the agent's behavior and personality.</param>
    /// <param name="name">Optional name for the agent for identification purposes.</param>
    /// <param name="description">Optional description of the agent's capabilities and purpose.</param>
    /// <param name="tools">Optional collection of AI tools that the agent can use during conversations.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>An <see cref="ChatClientAgent"/> instance backed by the OpenAI Response service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> is <see langword="null"/>.</exception>
    public static ChatClientAgent AsAIAgent(
        this ResponsesClient client,
        string? model = null,
        string? instructions = null,
        string? name = null,
        string? description = null,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(client);

        return client.AsAIAgent(
            new ChatClientAgentOptions()
            {
                Name = name,
                Description = description,
                ChatOptions = tools is null && string.IsNullOrWhiteSpace(instructions) ? null : new ChatOptions()
                {
                    Instructions = instructions,
                    Tools = tools,
                }
            },
            model,
            clientFactory,
            loggerFactory,
            services);
    }

    /// <summary>
    /// Creates an AI agent from an <see cref="ResponsesClient"/> using the OpenAI Response API.
    /// </summary>
    /// <param name="client">The <see cref="ResponsesClient" /> to use for the agent.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="model">Optional default model ID to use for requests. Required when using a plain <see cref="ResponsesClient"/> (not via Azure OpenAI).</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>An <see cref="ChatClientAgent"/> instance backed by the OpenAI Response service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    public static ChatClientAgent AsAIAgent(
        this ResponsesClient client,
        ChatClientAgentOptions options,
        string? model = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(client);
        Throw.IfNull(options);

        var chatClient = client.AsIChatClient(model);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        return new ChatClientAgent(chatClient, options, loggerFactory, services);
    }

    /// <summary>
    /// Gets an <see cref="IChatClient"/> for use with this <see cref="ResponsesClient"/> that does not store responses for later retrieval.
    /// </summary>
    /// <remarks>
    /// This corresponds to setting the "store" property in the JSON representation to false.
    /// </remarks>
    /// <param name="responseClient">The client.</param>
    /// <param name="model">Optional default model ID to use for requests.</param>
    /// <param name="includeReasoningEncryptedContent">
    /// Includes an encrypted version of reasoning tokens in reasoning item outputs.
    /// This enables reasoning items to be used in multi-turn conversations when using the Responses API statelessly
    /// (like when the store parameter is set to false, or when an organization is enrolled in the zero data retention program).
    /// Defaults to <see langword="true"/>.
    /// </param>
    /// <returns>An <see cref="IChatClient"/> that can be used to converse via the <see cref="ResponsesClient"/> that does not store responses for later retrieval.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="responseClient"/> is <see langword="null"/>.</exception>
    [Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
    public static IChatClient AsIChatClientWithStoredOutputDisabled(this ResponsesClient responseClient, string? model = null, bool includeReasoningEncryptedContent = true)
    {
        return Throw.IfNull(responseClient)
            .AsIChatClient(model)
            .AsBuilder()
            .ConfigureOptions(x => x.RawRepresentationFactory = _ => includeReasoningEncryptedContent
                ? new CreateResponseOptions() { StoredOutputEnabled = false, IncludedProperties = { IncludedResponseProperty.ReasoningEncryptedContent } }
                : new CreateResponseOptions() { StoredOutputEnabled = false })
            .Build();
    }
}
