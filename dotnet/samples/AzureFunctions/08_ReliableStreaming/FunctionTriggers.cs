// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Azure.Functions.Worker;
using Microsoft.DurableTask.Client;
using Microsoft.Extensions.Logging;

namespace ReliableStreaming;

/// <summary>
/// HTTP trigger functions for reliable streaming of durable agent responses.
/// </summary>
/// <remarks>
/// This class exposes two endpoints:
/// <list type="bullet">
/// <item>
/// <term>Create</term>
/// <description>Starts an agent run and streams responses. The response format depends on the
/// <c>Accept</c> header: <c>text/plain</c> returns raw text (ideal for terminals), while
/// <c>text/event-stream</c> or any other value returns Server-Sent Events (SSE).</description>
/// </item>
/// <item>
/// <term>Stream</term>
/// <description>Resumes a stream from a cursor position, enabling reliable message delivery</description>
/// </item>
/// </list>
/// </remarks>
public sealed class FunctionTriggers
{
    private readonly RedisStreamResponseHandler _streamHandler;
    private readonly ILogger<FunctionTriggers> _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="FunctionTriggers"/> class.
    /// </summary>
    /// <param name="streamHandler">The Redis stream handler for reading/writing agent responses.</param>
    /// <param name="logger">The logger instance.</param>
    public FunctionTriggers(RedisStreamResponseHandler streamHandler, ILogger<FunctionTriggers> logger)
    {
        this._streamHandler = streamHandler;
        this._logger = logger;
    }

    /// <summary>
    /// Creates a new agent session, starts an agent run with the provided prompt,
    /// and streams the response back to the client.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The response format depends on the <c>Accept</c> header:
    /// <list type="bullet">
    /// <item><c>text/plain</c>: Returns raw text output, ideal for terminal display with curl</item>
    /// <item><c>text/event-stream</c> or other: Returns Server-Sent Events (SSE) with cursor support</item>
    /// </list>
    /// </para>
    /// <para>
    /// The response includes an <c>x-conversation-id</c> header containing the conversation ID.
    /// For SSE responses, clients can use this conversation ID to resume the stream if disconnected
    /// by calling the <see cref="StreamAsync"/> endpoint with the conversation ID and the last received cursor.
    /// </para>
    /// <para>
    /// Each SSE event contains the following fields:
    /// <list type="bullet">
    /// <item><c>id</c>: The Redis stream entry ID (use as cursor for resumption)</item>
    /// <item><c>event</c>: Either "message" for content or "done" for stream completion</item>
    /// <item><c>data</c>: The text content of the response chunk</item>
    /// </list>
    /// </para>
    /// </remarks>
    /// <param name="request">The HTTP request containing the prompt in the body.</param>
    /// <param name="durableClient">The Durable Task client for signaling agents.</param>
    /// <param name="context">The function invocation context.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>A streaming response in the format specified by the Accept header.</returns>
    [Function(nameof(CreateAsync))]
    public async Task<IActionResult> CreateAsync(
        [HttpTrigger(AuthorizationLevel.Anonymous, "post", Route = "agent/create")] HttpRequest request,
        [DurableClient] DurableTaskClient durableClient,
        FunctionContext context,
        CancellationToken cancellationToken)
    {
        // Read the prompt from the request body
        string prompt = await new StreamReader(request.Body).ReadToEndAsync(cancellationToken);
        if (string.IsNullOrWhiteSpace(prompt))
        {
            return new BadRequestObjectResult("Request body must contain a prompt.");
        }

        AIAgent agentProxy = durableClient.AsDurableAgentProxy(context, "TravelPlanner");

        // Create a new agent thread
        AgentThread thread = agentProxy.GetNewThread();
        AgentThreadMetadata metadata = thread.GetService<AgentThreadMetadata>()
            ?? throw new InvalidOperationException("Failed to get AgentThreadMetadata from new thread.");

        this._logger.LogInformation("Creating new agent session: {ConversationId}", metadata.ConversationId);

        // Run the agent in the background (fire-and-forget)
        DurableAgentRunOptions options = new() { IsFireAndForget = true };
        await agentProxy.RunAsync(prompt, thread, options, cancellationToken);

        this._logger.LogInformation("Agent run started for session: {ConversationId}", metadata.ConversationId);

        // Check Accept header to determine response format
        // text/plain = raw text output (ideal for terminals)
        // text/event-stream or other = SSE format (supports resumption)
        string? acceptHeader = request.Headers.Accept.FirstOrDefault();
        bool useSseFormat = acceptHeader?.Contains("text/plain", StringComparison.OrdinalIgnoreCase) != true;

        return await this.StreamToClientAsync(
            conversationId: metadata.ConversationId!, cursor: null, useSseFormat, request.HttpContext, cancellationToken);
    }

    /// <summary>
    /// Resumes streaming from a specific cursor position for an existing session.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Use this endpoint to resume a stream after disconnection. Pass the conversation ID
    /// (from the <c>x-conversation-id</c> response header) and the last received cursor
    /// (Redis stream entry ID) to continue from where you left off.
    /// </para>
    /// <para>
    /// If no cursor is provided, streaming starts from the beginning of the stream.
    /// This allows clients to replay the entire response if needed.
    /// </para>
    /// <para>
    /// The response format depends on the <c>Accept</c> header:
    /// <list type="bullet">
    /// <item><c>text/plain</c>: Returns raw text output, ideal for terminal display with curl</item>
    /// <item><c>text/event-stream</c> or other: Returns Server-Sent Events (SSE) with cursor support</item>
    /// </list>
    /// </para>
    /// </remarks>
    /// <param name="request">The HTTP request. Use the <c>cursor</c> query parameter to specify the cursor position.</param>
    /// <param name="conversationId">The conversation ID to stream from.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>A streaming response in the format specified by the Accept header.</returns>
    [Function(nameof(StreamAsync))]
    public async Task<IActionResult> StreamAsync(
        [HttpTrigger(AuthorizationLevel.Anonymous, "get", Route = "agent/stream/{conversationId}")] HttpRequest request,
        string conversationId,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(conversationId))
        {
            return new BadRequestObjectResult("Conversation ID is required.");
        }

        // Get the cursor from query string (optional)
        string? cursor = request.Query["cursor"].FirstOrDefault();

        this._logger.LogInformation(
            "Resuming stream for conversation {ConversationId} from cursor: {Cursor}",
            conversationId,
            cursor ?? "(beginning)");

        // Check Accept header to determine response format
        // text/plain = raw text output (ideal for terminals)
        // text/event-stream or other = SSE format (supports cursor-based resumption)
        string? acceptHeader = request.Headers.Accept.FirstOrDefault();
        bool useSseFormat = acceptHeader?.Contains("text/plain", StringComparison.OrdinalIgnoreCase) != true;

        return await this.StreamToClientAsync(conversationId, cursor, useSseFormat, request.HttpContext, cancellationToken);
    }

    /// <summary>
    /// Streams chunks from the Redis stream to the HTTP response.
    /// </summary>
    /// <param name="conversationId">The conversation ID to stream from.</param>
    /// <param name="cursor">Optional cursor to resume from. If null, streams from the beginning.</param>
    /// <param name="useSseFormat">True to use SSE format, false for plain text.</param>
    /// <param name="httpContext">The HTTP context for writing the response.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>An empty result after streaming completes.</returns>
    private async Task<IActionResult> StreamToClientAsync(
        string conversationId,
        string? cursor,
        bool useSseFormat,
        HttpContext httpContext,
        CancellationToken cancellationToken)
    {
        // Set response headers based on format
        httpContext.Response.Headers.ContentType = useSseFormat
            ? "text/event-stream"
            : "text/plain; charset=utf-8";
        httpContext.Response.Headers.CacheControl = "no-cache";
        httpContext.Response.Headers.Connection = "keep-alive";
        httpContext.Response.Headers["x-conversation-id"] = conversationId;

        // Disable response buffering if supported
        httpContext.Features.Get<IHttpResponseBodyFeature>()?.DisableBuffering();

        try
        {
            await foreach (StreamChunk chunk in this._streamHandler.ReadStreamAsync(
                conversationId,
                cursor,
                cancellationToken))
            {
                if (chunk.Error != null)
                {
                    this._logger.LogWarning("Stream error for conversation {ConversationId}: {Error}", conversationId, chunk.Error);
                    await WriteErrorAsync(httpContext.Response, chunk.Error, useSseFormat, cancellationToken);
                    break;
                }

                if (chunk.IsDone)
                {
                    await WriteEndOfStreamAsync(httpContext.Response, chunk.EntryId, useSseFormat, cancellationToken);
                    break;
                }

                if (chunk.Text != null)
                {
                    await WriteChunkAsync(httpContext.Response, chunk, useSseFormat, cancellationToken);
                }
            }
        }
        catch (OperationCanceledException)
        {
            this._logger.LogInformation("Client disconnected from stream {ConversationId}", conversationId);
        }

        return new EmptyResult();
    }

    /// <summary>
    /// Writes a text chunk to the response.
    /// </summary>
    private static async Task WriteChunkAsync(
        HttpResponse response,
        StreamChunk chunk,
        bool useSseFormat,
        CancellationToken cancellationToken)
    {
        if (useSseFormat)
        {
            await WriteSSEEventAsync(response, "message", chunk.Text!, chunk.EntryId);
        }
        else
        {
            await response.WriteAsync(chunk.Text!, cancellationToken);
        }

        await response.Body.FlushAsync(cancellationToken);
    }

    /// <summary>
    /// Writes an end-of-stream marker to the response.
    /// </summary>
    private static async Task WriteEndOfStreamAsync(
        HttpResponse response,
        string entryId,
        bool useSseFormat,
        CancellationToken cancellationToken)
    {
        if (useSseFormat)
        {
            await WriteSSEEventAsync(response, "done", "[DONE]", entryId);
        }
        else
        {
            await response.WriteAsync("\n", cancellationToken);
        }

        await response.Body.FlushAsync(cancellationToken);
    }

    /// <summary>
    /// Writes an error message to the response.
    /// </summary>
    private static async Task WriteErrorAsync(
        HttpResponse response,
        string error,
        bool useSseFormat,
        CancellationToken cancellationToken)
    {
        if (useSseFormat)
        {
            await WriteSSEEventAsync(response, "error", error, null);
        }
        else
        {
            await response.WriteAsync($"\n[Error: {error}]\n", cancellationToken);
        }

        await response.Body.FlushAsync(cancellationToken);
    }

    /// <summary>
    /// Writes a Server-Sent Event to the response stream.
    /// </summary>
    private static async Task WriteSSEEventAsync(
        HttpResponse response,
        string eventType,
        string data,
        string? id)
    {
        StringBuilder sb = new();

        // Include the ID if provided (used as cursor for resumption)
        if (!string.IsNullOrEmpty(id))
        {
            sb.AppendLine($"id: {id}");
        }

        sb.AppendLine($"event: {eventType}");
        sb.AppendLine($"data: {data}");
        sb.AppendLine(); // Empty line marks end of event

        await response.WriteAsync(sb.ToString());
    }
}
