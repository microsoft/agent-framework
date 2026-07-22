// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace SampleApp;

/// <summary>
/// A delegating AI agent that converts text responses from an inner AI agent into structured output using a chat client.
/// </summary>
/// <remarks>
/// <para>
/// The <see cref="StructuredOutputAgent"/> wraps an inner agent and uses a chat client to transform
/// the inner agent's text response into a structured JSON format based on the specified response format.
/// </para>
/// <para>
/// This agent requires a <see cref="ChatResponseFormatJson"/> to be specified either through the
/// <see cref="AgentRunOptions.ResponseFormat"/> or the <see cref="StructuredOutputAgentOptions.ChatOptions"/>
/// provided during construction.
/// </para>
/// </remarks>
internal sealed class StructuredOutputAgent : DelegatingAIAgent
{
    private readonly IChatClient _chatClient;
    private readonly StructuredOutputAgentOptions? _agentOptions;

    /// <summary>
    /// Initializes a new instance of the <see cref="StructuredOutputAgent"/> class.
    /// </summary>
    /// <param name="innerAgent">The underlying agent that generates text responses to be converted to structured output.</param>
    /// <param name="chatClient">The chat client used to transform text responses into structured JSON format.</param>
    /// <param name="options">Optional configuration options for the structured output agent.</param>
    public StructuredOutputAgent(AIAgent innerAgent, IChatClient chatClient, StructuredOutputAgentOptions? options = null)
        : base(innerAgent)
    {
        this._chatClient = chatClient ?? throw new ArgumentNullException(nameof(chatClient));
        this._agentOptions = options;
    }

    /// <inheritdoc />
    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        // Run the inner agent first, to get back the text response we want to convert.
        var textResponse = await this.InnerAgent.RunAsync(messages, session, options, cancellationToken).ConfigureAwait(false);

        // Invoke the chat client to transform the text output into structured data.
        ChatResponse soResponse = await this._chatClient.GetResponseAsync(
            messages: this.GetChatMessages(textResponse.Text),
            options: this.GetChatOptions(options),
            cancellationToken: cancellationToken).ConfigureAwait(false);

        return new StructuredOutputAgentResponse(soResponse, textResponse);
    }

    private List<ChatMessage> GetChatMessages(string? textResponseText)
    {
        List<ChatMessage> chatMessages = [];

        if (this._agentOptions?.ChatClientSystemMessage is not null)
        {
            chatMessages.Add(new ChatMessage(ChatRole.System, this._agentOptions.ChatClientSystemMessage));
        }

        chatMessages.Add(new ChatMessage(ChatRole.User, textResponseText));

        return chatMessages;
    }

    private ChatOptions GetChatOptions(AgentRunOptions? options)
    {
        ChatResponseFormat responseFormat = options?.ResponseFormat
            ?? this._agentOptions?.ChatOptions?.ResponseFormat
            ?? throw new InvalidOperationException($"A response format of type '{nameof(ChatResponseFormatJson)}' must be specified, but none was specified.");

        if (responseFormat is not ChatResponseFormatJson jsonResponseFormat)
        {
            throw new NotSupportedException($"A response format of type '{nameof(ChatResponseFormatJson)}' must be specified, but was '{responseFormat.GetType().Name}'.");
        }

        var chatOptions = this._agentOptions?.ChatOptions?.Clone() ?? new ChatOptions();
        chatOptions.ResponseFormat = jsonResponseFormat;
        return chatOptions;
    }
}
