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
        _ = Microsoft.Agents.AI.OpenAI.OpenAIUserAgentPolicies.Registration.TryRegister(chatClient);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        chatClient = new Microsoft.Agents.AI.OpenAI.FeatureUsageChatClient(chatClient);
        return new ChatClientAgent(chatClient, options, loggerFactory, services);
    }

    /// <summary>
    /// Creates an AI agent from an <see cref="ResponsesClient"/> using the OpenAI Response API.
    /// </summary>
    /// <param name="client">The <see cref="ResponsesClient" /> to use for the agent.</param>
    /// <param name="options">OpenAI Specific Options for the agent</param>
    /// <returns></returns>
#pragma warning disable RS0016
    public static ChatClientAgent AsAIAgent(
        this ResponsesClient client,
        OpenAIAgentOptions options)
    {
        bool anyOptionsSet = false;
        ChatOptions chatOptions = new();

        if (options.Tools != null)
        {
            anyOptionsSet = true;
            chatOptions.Tools = options.Tools;
        }

        if (options.MaxOutputTokens.HasValue)
        {
            anyOptionsSet = true;
            chatOptions.MaxOutputTokens = options.MaxOutputTokens.Value;
        }

        string? instructions = options.Instructions;
        if (!string.IsNullOrWhiteSpace(instructions))
        {
            anyOptionsSet = true;
            chatOptions.Instructions = instructions;
        }

        bool? storedOutputEnabled = options.StoredOutputEnabled;

        if (storedOutputEnabled.HasValue || options.ReasoningEffort != null || options.ServiceTier != null)
        {
            anyOptionsSet = true;
            chatOptions.RawRepresentationFactory = _ => new CreateResponseOptions
            {
                StoredOutputEnabled = storedOutputEnabled,
                ReasoningOptions = options.ReasoningEffort != null
                    ? new ResponseReasoningOptions
                    {
                        ReasoningEffortLevel = options.ReasoningEffort,
                        ReasoningSummaryVerbosity = options.ReasoningSummaryVerbosity
                    }
                    : null,
                ServiceTier = options.ServiceTier
            };
        }

        ChatClientAgentOptions chatClientAgentOptions = new()
        {
            Name = options.Name,
            Description = options.Description,
            Id = options.Id,
            AIContextProviders = options.AIContextProviders,
            ChatHistoryProvider = options.ChatHistoryProvider,
        };

        if (anyOptionsSet)
        {
            chatClientAgentOptions.ChatOptions = chatOptions;
        }

        options.AdditionalChatClientAgentOptions?.Invoke(chatClientAgentOptions);

        return client.AsAIAgent(chatClientAgentOptions, options.Model, options.ClientFactory, options.LoggerFactory, options.Services);
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
        IChatClient chatClient = Throw.IfNull(responseClient).AsIChatClient(model);
        _ = Microsoft.Agents.AI.OpenAI.OpenAIUserAgentPolicies.Registration.TryRegister(chatClient);

        return chatClient
            .AsBuilder()
            .ConfigureOptions(x =>
            {
                Microsoft.Agents.AI.OpenAI.FeatureUsageMarker.MarkUsed();
                var previousFactory = x.RawRepresentationFactory;
                x.RawRepresentationFactory = state =>
                {
                    var responseOptions = previousFactory?.Invoke(state) as CreateResponseOptions ?? new CreateResponseOptions();

                    responseOptions.StoredOutputEnabled = false;

                    if (includeReasoningEncryptedContent &&
                        !responseOptions.IncludedProperties.Contains(IncludedResponseProperty.ReasoningEncryptedContent))
                    {
                        responseOptions.IncludedProperties.Add(IncludedResponseProperty.ReasoningEncryptedContent);
                    }

                    return responseOptions;
                };
            })
            .Build();
    }
}

#pragma warning disable RS0016
/// <summary>
/// Options for an OpenAI Specific Client
/// </summary>
public class OpenAIAgentOptions
{
    /// <summary>
    /// Model to use
    /// </summary>
    public required string Model { get; set; }

    /// <summary>
    /// ID of the Agent
    /// </summary>
    public string? Id { get; set; }

    /// <summary>
    /// The Name of the Agent (Optional in most cases, but some scenarios to require one)
    /// </summary>
    public string? Name { get; set; }

    /// <summary>
    /// The Description of the Agent (Information only and not used by the LLM)
    /// </summary>
    public string? Description { get; set; }

    /// <summary>
    /// Instruction for the Agent to be fed to the LLM as System/Developer Message
    /// </summary>
    public string? Instructions { get; set; }

    /// <summary>
    /// A set of Tools that the Agent are allowed to call
    /// </summary>
    public IList<AITool>? Tools { get; set; }

    /// <summary>
    /// The maximum number of tokens in the generated chat response.
    /// </summary>
    public int? MaxOutputTokens { get; set; }

    /// <summary>
    /// An Action that allow you to inject additional ChatClientAgentOptions settings beyond what these options can do
    /// </summary>
    public Action<ChatClientAgentOptions>? AdditionalChatClientAgentOptions { get; set; }

    /// <summary>
    /// An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.
    /// </summary>
    public IServiceProvider? Services { get; set; }

    /// <summary>
    /// Optional logger factory for enabling logging within the agent.
    /// </summary>
    public ILoggerFactory? LoggerFactory { get; set; }

    /// <summary>
    /// Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.
    /// </summary>
    public Func<IChatClient, IChatClient>? ClientFactory { get; set; }

    /// <summary>
    /// Define the reasoning Effort
    /// </summary>
#pragma warning disable OPENAI001
    public ResponseReasoningEffortLevel? ReasoningEffort { get; set; }
#pragma warning restore OPENAI001

    /// <summary>
    /// Define the reasoning summary verbosity
    /// </summary>
#pragma warning disable OPENAI001
    public ResponseReasoningSummaryVerbosity? ReasoningSummaryVerbosity { get; set; }
#pragma warning restore OPENAI001

    /// <summary>
    /// Gets or sets the <see cref="ChatHistoryProvider"/> instance to use for providing chat history for this agent.
    /// </summary>
    public ChatHistoryProvider? ChatHistoryProvider { get; set; }

    /// <summary>
    /// Gets or sets the list of <see cref="AIContextProvider"/> instances to use for providing additional context for each agent run.
    /// </summary>
    public IEnumerable<AIContextProvider>? AIContextProviders { get; set; }

    /// <summary>
    /// What service Tier to use
    /// </summary>
#pragma warning disable OPENAI001
    public ResponseServiceTier? ServiceTier { get; set; }
#pragma warning restore OPENAI001

    /// <summary>
    /// sets whether the response should be stored for later retrieval. This corresponds to the "store" property in the JSON representation.
    /// </summary>
    public bool? StoredOutputEnabled { get; set; }
}
