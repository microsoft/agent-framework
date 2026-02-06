// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides structured output methods for <see cref="AIAgent"/> that enable requesting responses in a specific type format.
/// </summary>
public abstract partial class AIAgent
{
    /// <summary>
    /// Run the agent with no message assuming that all required instructions are already provided to the agent or on the session, and requesting a response of the specified type <typeparamref name="T"/>.
    /// </summary>
    /// <typeparam name="T">The type of structured output to request.</typeparam>
    /// <param name="session">
    /// The conversation session to use for this invocation. If <see langword="null"/>, a new session will be created.
    /// The session will be updated with any response messages generated during invocation.
    /// </param>
    /// <param name="serializerOptions">Optional JSON serializer options to use for deserializing the response.</param>
    /// <param name="options">Optional configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentResponse{T}"/> with the agent's output.</returns>
    /// <remarks>
    /// This overload is useful when the agent has sufficient context from previous messages in the session
    /// or from its initial configuration to generate a meaningful response without additional input.
    /// </remarks>
    public Task<AgentResponse<T>> RunAsync<T>(
        AgentSession? session = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default) =>
        this.RunAsync<T>([], session, serializerOptions, options, cancellationToken);

    /// <summary>
    /// Runs the agent with a text message from the user, requesting a response of the specified type <typeparamref name="T"/>.
    /// </summary>
    /// <typeparam name="T">The type of structured output to request.</typeparam>
    /// <param name="message">The user message to send to the agent.</param>
    /// <param name="session">
    /// The conversation session to use for this invocation. If <see langword="null"/>, a new session will be created.
    /// The session will be updated with the input message and any response messages generated during invocation.
    /// </param>
    /// <param name="serializerOptions">Optional JSON serializer options to use for deserializing the response.</param>
    /// <param name="options">Optional configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentResponse{T}"/> with the agent's output.</returns>
    /// <exception cref="ArgumentException"><paramref name="message"/> is <see langword="null"/>, empty, or contains only whitespace.</exception>
    /// <remarks>
    /// The provided text will be wrapped in a <see cref="ChatMessage"/> with the <see cref="ChatRole.User"/> role
    /// before being sent to the agent. This is a convenience method for simple text-based interactions.
    /// </remarks>
    public Task<AgentResponse<T>> RunAsync<T>(
        string message,
        AgentSession? session = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNullOrWhitespace(message);

        return this.RunAsync<T>(new ChatMessage(ChatRole.User, message), session, serializerOptions, options, cancellationToken);
    }

    /// <summary>
    /// Runs the agent with a single chat message, requesting a response of the specified type <typeparamref name="T"/>.
    /// </summary>
    /// <typeparam name="T">The type of structured output to request.</typeparam>
    /// <param name="message">The chat message to send to the agent.</param>
    /// <param name="session">
    /// The conversation session to use for this invocation. If <see langword="null"/>, a new session will be created.
    /// The session will be updated with the input message and any response messages generated during invocation.
    /// </param>
    /// <param name="serializerOptions">Optional JSON serializer options to use for deserializing the response.</param>
    /// <param name="options">Optional configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentResponse{T}"/> with the agent's output.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="message"/> is <see langword="null"/>.</exception>
    public Task<AgentResponse<T>> RunAsync<T>(
        ChatMessage message,
        AgentSession? session = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(message);

        return this.RunAsync<T>([message], session, serializerOptions, options, cancellationToken);
    }

    /// <summary>
    /// Runs the agent with a collection of chat messages, requesting a response of the specified type <typeparamref name="T"/>.
    /// </summary>
    /// <typeparam name="T">The type of structured output to request.</typeparam>
    /// <param name="messages">The collection of messages to send to the agent for processing.</param>
    /// <param name="session">
    /// The conversation session to use for this invocation. If <see langword="null"/>, a new session will be created.
    /// The session will be updated with the input messages and any response messages generated during invocation.
    /// </param>
    /// <param name="serializerOptions">Optional JSON serializer options to use for deserializing the response.</param>
    /// <param name="options">Optional configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentResponse{T}"/> with the agent's output.</returns>
    /// <exception cref="NotSupportedException">Thrown when the agent does not support structured output.</exception>
    /// <remarks>
    /// <para>
    /// This method handles collections of messages, allowing for complex conversational scenarios including
    /// multi-turn interactions, function calls, and context-rich conversations.
    /// </para>
    /// <para>
    /// The messages are processed in the order provided and become part of the conversation history.
    /// The agent's response will also be added to <paramref name="session"/> if one is provided.
    /// </para>
    /// </remarks>
    public async Task<AgentResponse<T>> RunAsync<T>(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var metadata = this.GetService<AIAgentMetadata>();
        if (metadata?.SupportsStructuredOutput != true)
        {
            throw new NotSupportedException($"The agent '{this.GetType().Name}' does not support structured output. Consider using the UseStructuredOutput method on AIAgentBuilder to add structured output support to the agent.");
        }

        serializerOptions ??= AgentAbstractionsJsonUtilities.DefaultOptions;

        var responseFormat = ChatResponseFormat.ForJsonSchema<T>(serializerOptions);

        (responseFormat, bool isWrappedInObject) = EnsureObjectSchema(responseFormat);

        options = options?.Clone() ?? new AgentRunOptions();
        options.ResponseFormat = responseFormat;

        AgentResponse response = await this.RunAsync(messages, session, options, cancellationToken).ConfigureAwait(false);

        return new AgentResponse<T>(response, serializerOptions) { IsWrappedInObject = isWrappedInObject };
    }

    private static bool SchemaRepresentsObject(JsonElement? schema)
    {
        if (schema is not { } schemaElement)
        {
            return false;
        }

        if (schemaElement.ValueKind is JsonValueKind.Object)
        {
            foreach (var property in schemaElement.EnumerateObject())
            {
                if (property.NameEquals("type"u8))
                {
                    return property.Value.ValueKind == JsonValueKind.String
                        && property.Value.ValueEquals("object"u8);
                }
            }
        }

        return false;
    }

    private static (ChatResponseFormatJson ResponseFormat, bool IsWrappedInObject) EnsureObjectSchema(ChatResponseFormatJson responseFormat)
    {
        if (responseFormat.Schema is null)
        {
            throw new InvalidOperationException("The response format must have a valid JSON schema.");
        }

        var schema = responseFormat.Schema.Value;
        bool isWrappedInObject = false;

        if (!SchemaRepresentsObject(responseFormat.Schema))
        {
            // For non-object-representing schemas, we wrap them in an object schema, because all
            // the real LLM providers today require an object schema as the root. This is currently
            // true even for providers that support native structured output.
            isWrappedInObject = true;
            schema = JsonSerializer.SerializeToElement(new JsonObject
            {
                { "$schema", "https://json-schema.org/draft/2020-12/schema" },
                { "type", "object" },
                { "properties", new JsonObject { { "data", JsonElementToJsonNode(schema) } } },
                { "additionalProperties", false },
                { "required", new JsonArray("data") },
            }, AIJsonUtilities.DefaultOptions.GetTypeInfo(typeof(JsonObject)));

            responseFormat = ChatResponseFormat.ForJsonSchema(schema, responseFormat.SchemaName, responseFormat.SchemaDescription);
        }

        return (responseFormat, isWrappedInObject);
    }

    private static JsonNode? JsonElementToJsonNode(JsonElement element) =>
        element.ValueKind switch
        {
            JsonValueKind.Null => null,
            JsonValueKind.Array => JsonArray.Create(element),
            JsonValueKind.Object => JsonObject.Create(element),
            _ => JsonValue.Create(element)
        };
}
