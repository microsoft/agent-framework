// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI;

/// <summary>
/// Side-effect-free helpers that convert between the OpenAI Responses wire protocol and Agent Framework
/// run values, for applications that own their own HTTP route, authentication, middleware, and storage.
/// </summary>
/// <remarks>
/// <para>
/// These helpers are the app-owned-routing counterpart to <c>MapOpenAIResponses</c>.
/// <c>MapOpenAIResponses</c> owns routing and storage; these helpers let an application own those concerns
/// and reuse only the protocol conversion. Both share the same internal conversion logic.
/// </para>
/// <para>
/// <strong>Trust boundary.</strong> <see cref="GetSessionStoreId(OpenAIResponsesRunRequest)"/> returns an
/// untrusted candidate continuation key. The application must authenticate the caller and authorize/bind the
/// id to the authenticated principal before using it as a session or checkpoint key. The helpers never
/// perform I/O.
/// </para>
/// </remarks>
public static class OpenAIResponses
{
    /// <summary>
    /// Converts an OpenAI Responses request body into Agent Framework run values (messages and options).
    /// </summary>
    /// <param name="body">The OpenAI Responses-shaped request body.</param>
    /// <param name="mapOptions">
    /// Optional options controlling how request settings are mapped onto the run. By default no request
    /// setting is mapped onto the run.
    /// </param>
    /// <returns>The parsed messages and mapped run options.</returns>
    /// <exception cref="ArgumentException">The body could not be parsed as an OpenAI Responses request.</exception>
    /// <exception cref="NotSupportedException">A request setting is not supported by the configured mapping.</exception>
    public static OpenAIResponsesRunRequest ToAgentRunRequest(JsonElement body, OpenAIResponsesMapOptions? mapOptions = null)
    {
        CreateResponse request;
        try
        {
            request = body.Deserialize(OpenAIHostingJsonContext.Default.CreateResponse)
                ?? throw new ArgumentException("The request body could not be parsed as an OpenAI Responses request.", nameof(body));
        }
        catch (JsonException ex)
        {
            throw new ArgumentException("The request body could not be parsed as an OpenAI Responses request.", nameof(body), ex);
        }

        if (request.Input is null)
        {
            throw new ArgumentException("The request body is missing the required 'input' field.", nameof(body));
        }

        AgentRunOptions? options = (mapOptions ?? new OpenAIResponsesMapOptions()).RunOptionsFactory(request.ToRequestInfo());

        var messages = new List<ChatMessage>();
        foreach (InputMessage inputMessage in request.Input.GetInputMessages())
        {
            messages.Add(inputMessage.ToChatMessage());
        }

        return new OpenAIResponsesRunRequest(messages, options, request.PreviousResponseId, request.Conversation?.Id);
    }

    /// <summary>
    /// Converts a final <see cref="AgentResponse"/> into an OpenAI Responses-shaped payload.
    /// </summary>
    /// <param name="response">The agent response to render.</param>
    /// <param name="responseId">The id to assign to the rendered response (see <see cref="CreateResponseId"/>).</param>
    /// <param name="conversationId">
    /// The optional conversation id to surface on the rendered response.
    /// </param>
    /// <returns>An OpenAI Responses-shaped <see cref="JsonElement"/>.</returns>
    public static JsonElement WriteResponse(AgentResponse response, string responseId, string? conversationId = null)
    {
        ArgumentNullException.ThrowIfNull(response);
        ArgumentException.ThrowIfNullOrEmpty(responseId);

        AgentInvocationContext context = CreateContext(responseId, conversationId);
        Response wire = response.ToResponse(EmptyRequest(), context);
        return JsonSerializer.SerializeToElement(wire, OpenAIHostingJsonContext.Default.Response);
    }

    /// <summary>
    /// Converts a stream of <see cref="AgentResponseUpdate"/> into OpenAI Responses Server-Sent-Event frames.
    /// </summary>
    /// <param name="updates">The agent streaming updates.</param>
    /// <param name="responseId">The id to assign to the rendered response (see <see cref="CreateResponseId"/>).</param>
    /// <param name="conversationId">The optional conversation id to surface on the rendered response.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>An async sequence of SSE frame strings, each terminated by a blank line.</returns>
    public static async IAsyncEnumerable<string> WriteResponseStreamAsync(
        IAsyncEnumerable<AgentResponseUpdate> updates,
        string responseId,
        string? conversationId = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(updates);
        ArgumentException.ThrowIfNullOrEmpty(responseId);

        AgentInvocationContext context = CreateContext(responseId, conversationId);
        await foreach (StreamingResponseEvent streamingEvent in updates
            .ToStreamingResponseAsync(EmptyRequest(), context, cancellationToken)
            .ConfigureAwait(false))
        {
            string json = JsonSerializer.Serialize(streamingEvent, OpenAIHostingJsonContext.Default.StreamingResponseEvent);
            yield return $"event: {streamingEvent.Type}\ndata: {json}\n\n";
        }
    }

    /// <summary>
    /// Extracts the id under which the session should be stored from an already-parsed
    /// <see cref="OpenAIResponsesRunRequest"/>.
    /// </summary>
    /// <param name="request">The parsed request produced by <see cref="ToAgentRunRequest(JsonElement, OpenAIResponsesMapOptions?)"/>.</param>
    /// <returns>
    /// The <c>previous_response_id</c> when present; otherwise the <c>conversation</c> id when present;
    /// otherwise <see langword="null"/> when the request carries neither.
    /// </returns>
    /// <exception cref="ArgumentNullException"><paramref name="request"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// This reads the ids off the already-parsed request rather than re-parsing the body, so an application
    /// calls <see cref="ToAgentRunRequest(JsonElement, OpenAIResponsesMapOptions?)"/> once and then this. It is kept
    /// separate so the trust boundary stays visible: using a request-derived key is an explicit application
    /// decision, and the returned value is an <strong>untrusted candidate key</strong> until the application has
    /// authorized it for the caller. A <see langword="null"/> result means only that the request carried no
    /// continuation id (unparseable bodies are already rejected by <see cref="ToAgentRunRequest(JsonElement, OpenAIResponsesMapOptions?)"/>).
    /// <para>
    /// The Responses protocol treats <c>previous_response_id</c> and <c>conversation</c> as mutually exclusive; if a
    /// request carries both, this helper prefers <c>previous_response_id</c> (the response-chain pointer). Note that
    /// <c>previous_response_id</c> changes each turn and is therefore not a stable partition key; use
    /// <see cref="OpenAIResponsesRunRequest.ConversationId"/> when a stable key is required (for example a workflow
    /// checkpoint cursor key).
    /// </para>
    /// </remarks>
    public static string? GetSessionStoreId(OpenAIResponsesRunRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        return request.PreviousResponseId ?? request.ConversationId;
    }

    /// <summary>
    /// Creates a new OpenAI Responses-shaped response id (a <c>resp_*</c> value).
    /// </summary>
    /// <returns>A new response id.</returns>
    public static string CreateResponseId() => IdGenerator.NewId("resp");

    private static AgentInvocationContext CreateContext(string responseId, string? conversationId)
        => new(new IdGenerator(responseId, conversationId));

    // The rendering converters never read the request input; a minimal request lets the facade render
    // a response without requiring the caller to supply the originating request object.
    private static CreateResponse EmptyRequest() => new() { Input = ResponseInput.FromText(string.Empty) };
}
