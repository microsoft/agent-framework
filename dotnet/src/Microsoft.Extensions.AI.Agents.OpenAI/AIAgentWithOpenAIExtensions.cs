// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;
using OpenAI.Chat;

namespace OpenAI;

/// <summary>
/// Provides extension methods for <see cref="AIAgent"/> to simplify interaction with OpenAI chat messages
/// and return native OpenAI <see cref="ChatCompletion"/> responses.
/// </summary>
/// <remarks>
/// These extensions bridge the gap between the Microsoft Extensions AI framework and the OpenAI SDK,
/// allowing developers to work with native OpenAI types while leveraging the AI Agent framework.
/// The methods handle the conversion between OpenAI chat message types and Microsoft Extensions AI types,
/// and return OpenAI <see cref="ChatCompletion"/> objects directly from the agent's <see cref="AgentRunResponse"/>.
/// </remarks>
public static class AIAgentWithOpenAIExtensions
{
    /// <summary>
    /// Runs the AI agent with a single OpenAI chat message and returns the response as a native OpenAI <see cref="ChatCompletion"/>.
    /// </summary>
    /// <param name="agent">The AI agent to run.</param>
    /// <param name="message">The OpenAI chat message to send to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided message and agent response.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="Task{ChatCompletion}"/> representing the asynchronous operation that returns a native OpenAI <see cref="ChatCompletion"/> response.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agent"/> or <paramref name="message"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when the agent's response cannot be converted to a <see cref="ChatCompletion"/>, typically when the underlying representation is not an OpenAI response.</exception>
    /// <exception cref="NotSupportedException">Thrown when the <paramref name="message"/> type is not supported by the message conversion method.</exception>
    /// <remarks>
    /// This method converts the OpenAI chat message to the Microsoft Extensions AI format using the appropriate conversion method,
    /// runs the agent, and then extracts the native OpenAI <see cref="ChatCompletion"/> from the response using <see cref="AgentRunResponseExtensions.AsChatCompletion"/>.
    /// </remarks>
    public static async Task<ChatCompletion> RunAsync(this AIAgent agent, OpenAI.Chat.ChatMessage message, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);
        Throw.IfNull(message);

        var response = await agent.RunAsync(message.AsChatMessage(), thread, options, cancellationToken).ConfigureAwait(false);

        var chatCompletion = response.AsChatCompletion();
        return chatCompletion;
    }

    /// <summary>
    /// Runs the AI agent with a collection of OpenAI chat messages and returns the response as a native OpenAI <see cref="ChatCompletion"/>.
    /// </summary>
    /// <param name="agent">The AI agent to run.</param>
    /// <param name="messages">The collection of OpenAI chat messages to send to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided messages and agent response.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="Task{ChatCompletion}"/> representing the asynchronous operation that returns a native OpenAI <see cref="ChatCompletion"/> response.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agent"/> or <paramref name="messages"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when the agent's response cannot be converted to a <see cref="ChatCompletion"/>, typically when the underlying representation is not an OpenAI response.</exception>
    /// <exception cref="NotSupportedException">Thrown when any message in <paramref name="messages"/> has a type that is not supported by the message conversion method.</exception>
    /// <remarks>
    /// This method converts each OpenAI chat message to the Microsoft Extensions AI format using <see cref="AsChatMessages"/>,
    /// runs the agent with the converted message collection, and then extracts the native OpenAI <see cref="ChatCompletion"/> from the response using <see cref="AgentRunResponseExtensions.AsChatCompletion"/>.
    /// </remarks>
    public static async Task<ChatCompletion> RunAsync(this AIAgent agent, IEnumerable<OpenAI.Chat.ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);
        Throw.IfNull(messages);

        var response = await agent.RunAsync([.. messages.AsChatMessages()], thread, options, cancellationToken).ConfigureAwait(false);

        var chatCompletion = response.AsChatCompletion();
        return chatCompletion;
    }

    /// <summary>
    /// Creates a sequence of <see cref="Microsoft.Extensions.AI.ChatMessage"/> instances from the specified OpenAI input messages.
    /// </summary>
    /// <param name="messages">The OpenAI input messages to convert.</param>
    /// <returns>A sequence of Microsoft Extensions AI chat messages converted from the OpenAI messages.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="messages"/> is <see langword="null"/>.</exception>
    /// <exception cref="NotSupportedException">Thrown when a message type is encountered that cannot be converted.</exception>
    /// <remarks>
    /// This method supports conversion of the following OpenAI message types:
    /// <list type="bullet">
    /// <item><description><see cref="AssistantChatMessage"/></description></item>
    /// <item><description><see cref="DeveloperChatMessage"/></description></item>
    /// <item><description><see cref="FunctionChatMessage"/> (obsolete)</description></item>
    /// <item><description><see cref="SystemChatMessage"/></description></item>
    /// <item><description><see cref="ToolChatMessage"/></description></item>
    /// <item><description><see cref="UserChatMessage"/></description></item>
    /// </list>
    /// </remarks>
    internal static IEnumerable<Microsoft.Extensions.AI.ChatMessage> AsChatMessages(this IEnumerable<OpenAI.Chat.ChatMessage> messages)
    {
        Throw.IfNull(messages);

        foreach (OpenAI.Chat.ChatMessage message in messages)
        {
            switch (message)
            {
                case OpenAI.Chat.AssistantChatMessage assistantMessage:
                    yield return assistantMessage.AsChatMessage();
                    break;
                case OpenAI.Chat.DeveloperChatMessage developerMessage:
                    yield return developerMessage.AsChatMessage();
                    break;
#pragma warning disable CS0618 // Type or member is obsolete
                case OpenAI.Chat.FunctionChatMessage functionMessage:
                    yield return functionMessage.AsChatMessage();
                    break;
#pragma warning restore CS0618 // Type or member is obsolete
                case OpenAI.Chat.SystemChatMessage systemMessage:
                    yield return systemMessage.AsChatMessage();
                    break;
                case OpenAI.Chat.ToolChatMessage toolMessage:
                    yield return toolMessage.AsChatMessage();
                    break;
                case OpenAI.Chat.UserChatMessage userMessage:
                    yield return userMessage.AsChatMessage();
                    break;
            }
        }
    }

    /// <summary>
    /// Converts an OpenAI chat message to a Microsoft Extensions AI <see cref="Microsoft.Extensions.AI.ChatMessage"/>.
    /// </summary>
    /// <param name="chatMessage">The OpenAI chat message to convert.</param>
    /// <returns>A <see cref="Microsoft.Extensions.AI.ChatMessage"/> equivalent of the input OpenAI message.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="chatMessage"/> is <see langword="null"/>.</exception>
    /// <exception cref="NotSupportedException">Thrown when the <paramref name="chatMessage"/> type is not supported for conversion.</exception>
    /// <remarks>
    /// This method provides a bridge between OpenAI SDK message types and Microsoft Extensions AI message types.
    /// It handles the conversion by switching on the concrete type of the OpenAI message and calling the appropriate
    /// specialized conversion method.
    /// </remarks>
    internal static Microsoft.Extensions.AI.ChatMessage AsChatMessage(this OpenAI.Chat.ChatMessage chatMessage)
    {
        Throw.IfNull(chatMessage);

        return chatMessage switch
        {
            AssistantChatMessage assistantMessage => assistantMessage.AsChatMessage(),
            DeveloperChatMessage developerMessage => developerMessage.AsChatMessage(),
            SystemChatMessage systemMessage => systemMessage.AsChatMessage(),
            ToolChatMessage toolMessage => toolMessage.AsChatMessage(),
            UserChatMessage userMessage => userMessage.AsChatMessage(),
            _ => throw new NotSupportedException($"Message type {chatMessage.GetType().Name} is not supported for conversion.")
        };
    }

    /// <summary>
    /// Converts OpenAI chat message content to Microsoft Extensions AI content items.
    /// </summary>
    /// <param name="content">The OpenAI chat message content to convert.</param>
    /// <returns>A sequence of <see cref="AIContent"/> items converted from the OpenAI content.</returns>
    /// <remarks>
    /// This method supports conversion of the following OpenAI content part types:
    /// <list type="bullet">
    /// <item><description>Text content (converted to <see cref="TextContent"/>)</description></item>
    /// <item><description>Refusal content (converted to <see cref="TextContent"/>)</description></item>
    /// <item><description>Image content (converted to <see cref="DataContent"/> or <see cref="UriContent"/>)</description></item>
    /// <item><description>Input audio content (converted to <see cref="DataContent"/>)</description></item>
    /// <item><description>File content (converted to <see cref="DataContent"/>)</description></item>
    /// </list>
    /// </remarks>
    private static IEnumerable<AIContent> AsAIContent(this OpenAI.Chat.ChatMessageContent content)
    {
        Throw.IfNull(content);

        foreach (OpenAI.Chat.ChatMessageContentPart part in content)
        {
            switch (part.Kind)
            {
                case OpenAI.Chat.ChatMessageContentPartKind.Text:
                    yield return new TextContent(part.Text)
                    {
                        RawRepresentation = content
                    };
                    break;
                case OpenAI.Chat.ChatMessageContentPartKind.Refusal:
                    yield return new TextContent(part.Refusal)
                    {
                        RawRepresentation = content
                    };
                    break;
                case OpenAI.Chat.ChatMessageContentPartKind.Image:
                    if (part.ImageBytes is not null)
                    {
                        yield return new DataContent(part.ImageBytes, part.ImageBytesMediaType)
                        {
                            RawRepresentation = content
                        };
                    }
                    else
                    {
                        yield return new UriContent(part.ImageUri, "image/*")
                        {
                            RawRepresentation = content
                        };
                    }
                    break;
                case OpenAI.Chat.ChatMessageContentPartKind.InputAudio:
                    yield return new DataContent(part.InputAudioBytes, "audio/*")
                    {
                        RawRepresentation = content
                    };
                    break;
                case OpenAI.Chat.ChatMessageContentPartKind.File:
                    yield return new DataContent(part.FileBytes, part.FileBytesMediaType)
                    {
                        RawRepresentation = content
                    };
                    break;
                default:
                    throw new NotSupportedException($"Content part kind '{part.Kind}' is not supported for conversion to AIContent.");
            }
        }
    }

    /// <summary>
    /// Converts OpenAI chat message content to text.
    /// </summary>
    /// <param name="content">The OpenAI chat message content to convert.</param>
    /// <returns>A string created from the text and refusal parts of the OpenAI content.</returns>
    /// <remarks>
    /// Using when converting OpenAI For <c>tool</c> messages, the contents can only be of type <c>text</c>.
    /// </remarks>
    private static string AsText(this OpenAI.Chat.ChatMessageContent content)
    {
        Throw.IfNull(content);

        StringBuilder text = new();
        foreach (OpenAI.Chat.ChatMessageContentPart part in content)
        {
            switch (part.Kind)
            {
                case OpenAI.Chat.ChatMessageContentPartKind.Text:
                    text.Append(part.Text);
                    break;
                case OpenAI.Chat.ChatMessageContentPartKind.Refusal:
                    text.Append(part.Refusal);
                    break;
                default:
                    throw new NotSupportedException($"Content part kind '{part.Kind}' is not supported for conversion to text.");
            }
        }
        return text.ToString();
    }

    /// <summary>
    /// Converts an OpenAI <see cref="AssistantChatMessage"/> to a Microsoft Extensions AI <see cref="Microsoft.Extensions.AI.ChatMessage"/>.
    /// </summary>
    /// <param name="assistantMessage">The OpenAI assistant message to convert.</param>
    /// <returns>A Microsoft Extensions AI chat message with assistant role.</returns>
    /// <remarks>
    /// This method converts the assistant message content using <see cref="AsAIContent"/> and preserves
    /// the participant name as the author name in the resulting message.
    /// </remarks>
    private static Microsoft.Extensions.AI.ChatMessage AsChatMessage(this AssistantChatMessage assistantMessage)
    {
        Throw.IfNull(assistantMessage);

        return new Microsoft.Extensions.AI.ChatMessage(Microsoft.Extensions.AI.ChatRole.Assistant, [.. assistantMessage.Content.AsAIContent()])
        {
            AuthorName = assistantMessage.ParticipantName,
            RawRepresentation = assistantMessage
        };
    }

    /// <summary>
    /// Converts an OpenAI <see cref="DeveloperChatMessage"/> to a Microsoft Extensions AI <see cref="Microsoft.Extensions.AI.ChatMessage"/>.
    /// </summary>
    /// <param name="developerMessage">The OpenAI developer message to convert.</param>
    /// <returns>A Microsoft Extensions AI chat message with system role.</returns>
    /// <remarks>
    /// Developer messages are treated as system messages in the Microsoft Extensions AI framework.
    /// The participant name is preserved as the author name.
    /// </remarks>
    private static Microsoft.Extensions.AI.ChatMessage AsChatMessage(this DeveloperChatMessage developerMessage)
    {
        Throw.IfNull(developerMessage);

        return new Microsoft.Extensions.AI.ChatMessage(Microsoft.Extensions.AI.ChatRole.System, [.. developerMessage.Content.AsAIContent()])
        {
            AuthorName = developerMessage.ParticipantName,
            RawRepresentation = developerMessage
        };
    }

    /// <summary>
    /// Converts an OpenAI <see cref="SystemChatMessage"/> to a Microsoft Extensions AI <see cref="Microsoft.Extensions.AI.ChatMessage"/>.
    /// </summary>
    /// <param name="systemMessage">The OpenAI system message to convert.</param>
    /// <returns>A Microsoft Extensions AI chat message with system role.</returns>
    /// <remarks>
    /// This method converts the system message content using <see cref="AsAIContent"/> and preserves
    /// the participant name as the author name in the resulting message.
    /// </remarks>
    private static Microsoft.Extensions.AI.ChatMessage AsChatMessage(this SystemChatMessage systemMessage)
    {
        Throw.IfNull(systemMessage);

        return new Microsoft.Extensions.AI.ChatMessage(Microsoft.Extensions.AI.ChatRole.System, [.. systemMessage.Content.AsAIContent()])
        {
            AuthorName = systemMessage.ParticipantName,
            RawRepresentation = systemMessage
        };
    }

    /// <summary>
    /// Converts an OpenAI <see cref="ToolChatMessage"/> to a Microsoft Extensions AI <see cref="Microsoft.Extensions.AI.ChatMessage"/>.
    /// </summary>
    /// <param name="toolMessage">The OpenAI tool message to convert.</param>
    /// <returns>A Microsoft Extensions AI chat message with tool role.</returns>
    /// <remarks>
    /// This method converts tool message content using <see cref="AsAIContent"/> and includes the tool call ID
    /// in the resulting message's additional properties for traceability.
    /// </remarks>
    private static Microsoft.Extensions.AI.ChatMessage AsChatMessage(this ToolChatMessage toolMessage)
    {
        Throw.IfNull(toolMessage);

        var content = new FunctionResultContent(toolMessage.ToolCallId, toolMessage.Content.AsText())
        {
            RawRepresentation = toolMessage
        };
        return new Microsoft.Extensions.AI.ChatMessage(Microsoft.Extensions.AI.ChatRole.Tool, [content])
        {
            RawRepresentation = toolMessage,
            AdditionalProperties = new() { ["tool_call_id"] = toolMessage.ToolCallId }
        };
    }

    /// <summary>
    /// Converts an OpenAI <see cref="UserChatMessage"/> to a Microsoft Extensions AI <see cref="Microsoft.Extensions.AI.ChatMessage"/>.
    /// </summary>
    /// <param name="userMessage">The OpenAI user message to convert.</param>
    /// <returns>A Microsoft Extensions AI chat message with user role.</returns>
    /// <remarks>
    /// This method converts the user message content using <see cref="AsAIContent"/> and preserves
    /// the participant name as the author name in the resulting message.
    /// </remarks>
    private static Microsoft.Extensions.AI.ChatMessage AsChatMessage(this UserChatMessage userMessage)
    {
        Throw.IfNull(userMessage);

        return new Microsoft.Extensions.AI.ChatMessage(Microsoft.Extensions.AI.ChatRole.User, [.. userMessage.Content.AsAIContent()])
        {
            AuthorName = userMessage.ParticipantName,
            RawRepresentation = userMessage
        };
    }
}
