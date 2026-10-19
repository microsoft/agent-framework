// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// Service interface for handling OpenAI Responses API operations.
/// Implementations can use various storage and execution strategies (in-memory, Orleans grains, etc.).
/// </summary>
internal interface IResponsesService
{
    /// <summary>
    /// Default limit for list operations.
    /// </summary>
    const int DefaultListLimit = 20;

    /// <summary>
    /// Validates a create response request before execution.
    /// </summary>
    /// <param name="request">The create response request to validate.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>A ResponseError if validation fails, null if validation succeeds.</returns>
    ValueTask<ResponseError?> ValidateRequestAsync(
        CreateResponse request,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Creates a model response for the given input.
    /// </summary>
    /// <param name="request">The create response request.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The created response.</returns>
    Task<Response> CreateResponseAsync(
        CreateResponse request,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Creates a streaming model response for the given input.
    /// </summary>
    /// <param name="request">The create response request.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>An async enumerable of streaming response events.</returns>
    IAsyncEnumerable<StreamingResponseEvent> CreateResponseStreamingAsync(
        CreateResponse request,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves a response by ID.
    /// </summary>
    /// <param name="responseId">The ID of the response to retrieve.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The response if found, null otherwise.</returns>
    Task<Response?> GetResponseAsync(
        string responseId,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves a response by ID in streaming mode, yielding events as they become available.
    /// </summary>
    /// <param name="responseId">The ID of the response to retrieve.</param>
    /// <param name="startingAfter">The sequence number after which to start streaming. If null, starts from the beginning.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>An async enumerable of streaming updates.</returns>
    IAsyncEnumerable<StreamingResponseEvent> GetResponseStreamingAsync(
        string responseId,
        int? startingAfter = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Cancels an in-progress response.
    /// </summary>
    /// <param name="responseId">The ID of the response to cancel.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The updated response after cancellation.</returns>
    Task<Response> CancelResponseAsync(
        string responseId,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Deletes a response by ID.
    /// </summary>
    /// <param name="responseId">The ID of the response to delete.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>True if the response was deleted, false if it was not found.</returns>
    Task<bool> DeleteResponseAsync(
        string responseId,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Lists the input items for a response.
    /// </summary>
    /// <param name="responseId">The ID of the response.</param>
    /// <param name="limit">Maximum number of items to return (1-100). Defaults to <see cref="DefaultListLimit"/> if null.</param>
    /// <param name="order">Sort order. Defaults to <see cref="SortOrder.Descending"/> if null.</param>
    /// <param name="after">Return items after this ID.</param>
    /// <param name="before">Return items before this ID.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>A list response with items and pagination info.</returns>
    Task<ListResponse<ItemResource>> ListResponseInputItemsAsync(
        string responseId,
        int? limit = null,
        SortOrder? order = null,
        string? after = null,
        string? before = null,
        CancellationToken cancellationToken = default);
}
