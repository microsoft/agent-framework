// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// Handles route requests for OpenAI Responses API endpoints.
/// </summary>
internal sealed class ResponsesHttpHandler
{
    private readonly IResponsesService _responsesService;

    /// <summary>
    /// Initializes a new instance of the <see cref="ResponsesHttpHandler"/> class.
    /// </summary>
    /// <param name="responsesService">The responses service.</param>
    public ResponsesHttpHandler(IResponsesService responsesService)
    {
        this._responsesService = responsesService ?? throw new ArgumentNullException(nameof(responsesService));
    }

    /// <summary>
    /// Creates a model response for the given input.
    /// </summary>
    public async Task<IResult> CreateResponseAsync(
        [FromBody] CreateResponse request,
        [FromQuery] bool? stream,
        CancellationToken cancellationToken)
    {
        // Validate the request first
        ResponseError? validationError = await this._responsesService.ValidateRequestAsync(request, cancellationToken).ConfigureAwait(false);
        if (validationError is not null)
        {
            return Results.BadRequest(new ErrorResponse
            {
                Error = new ErrorDetails
                {
                    Message = validationError.Message,
                    Type = "invalid_request_error",
                    Code = validationError.Code
                }
            });
        }

        try
        {
            // Handle streaming vs non-streaming
            bool shouldStream = stream ?? request.Stream ?? false;

            if (shouldStream)
            {
                var streamingResponse = this._responsesService.CreateResponseStreamingAsync(
                    request,
                    cancellationToken: cancellationToken);

                return new SseJsonResult<StreamingResponseEvent>(
                    streamingResponse,
                    static evt => evt.Type,
                    OpenAIHostingJsonContext.Default.StreamingResponseEvent);
            }

            var response = await this._responsesService.CreateResponseAsync(
                request,
                cancellationToken: cancellationToken).ConfigureAwait(false);

            return response.Status switch
            {
                ResponseStatus.Failed when response.Error is { } error => Results.Problem(
                    detail: error.Message,
                    statusCode: StatusCodes.Status500InternalServerError,
                    title: error.Code ?? "Internal Server Error"),
                ResponseStatus.Failed => Results.Problem(),
                ResponseStatus.Queued => Results.Accepted(value: response),
                _ => Results.Ok(response)
            };
        }
        catch (Exception ex)
        {
            // Return InternalServerError for unexpected exceptions
            return Results.Problem(
                detail: ex.Message,
                statusCode: StatusCodes.Status500InternalServerError,
                title: "Internal Server Error");
        }
    }

    /// <summary>
    /// Retrieves a response by ID.
    /// </summary>
    public async Task<IResult> GetResponseAsync(
        string responseId,
        [FromQuery] string[]? include,
        [FromQuery] bool? stream,
        [FromQuery] int? starting_after,
        CancellationToken cancellationToken)
    {
        // If streaming is requested, return SSE stream
        if (stream == true)
        {
            var streamingResponse = this._responsesService.GetResponseStreamingAsync(
                responseId,
                startingAfter: starting_after,
                cancellationToken: cancellationToken);

            return new SseJsonResult<StreamingResponseEvent>(
                streamingResponse,
                static evt => evt.Type,
                OpenAIHostingJsonContext.Default.StreamingResponseEvent);
        }

        // Non-streaming: return the response object
        var response = await this._responsesService.GetResponseAsync(responseId, cancellationToken).ConfigureAwait(false);
        return response is not null
            ? Results.Ok(response)
            : Results.NotFound(new ErrorResponse
            {
                Error = new ErrorDetails
                {
                    Message = $"Response '{responseId}' not found.",
                    Type = "invalid_request_error"
                }
            });
    }

    /// <summary>
    /// Cancels an in-progress response.
    /// </summary>
    public async Task<IResult> CancelResponseAsync(
        string responseId,
        CancellationToken cancellationToken)
    {
        try
        {
            var response = await this._responsesService.CancelResponseAsync(responseId, cancellationToken).ConfigureAwait(false);
            return Results.Ok(response);
        }
        catch (InvalidOperationException ex)
        {
            return Results.BadRequest(new ErrorResponse
            {
                Error = new ErrorDetails
                {
                    Message = ex.Message,
                    Type = "invalid_request_error"
                }
            });
        }
    }

    /// <summary>
    /// Deletes a response.
    /// </summary>
    public async Task<IResult> DeleteResponseAsync(
        string responseId,
        CancellationToken cancellationToken)
    {
        var deleted = await this._responsesService.DeleteResponseAsync(responseId, cancellationToken).ConfigureAwait(false);
        return deleted
            ? Results.Ok(new DeleteResponse { Id = responseId, Object = "response", Deleted = true })
            : Results.NotFound(new ErrorResponse
            {
                Error = new ErrorDetails
                {
                    Message = $"Response '{responseId}' not found.",
                    Type = "invalid_request_error"
                }
            });
    }

    /// <summary>
    /// Lists the input items for a response.
    /// </summary>
    public async Task<IResult> ListResponseInputItemsAsync(
        string responseId,
        [FromQuery] int? limit,
        [FromQuery] string? order,
        [FromQuery] string? after,
        [FromQuery] string? before,
        CancellationToken cancellationToken)
    {
        try
        {
            // Convert string order to SortOrder enum
            SortOrder? sortOrder = order switch
            {
                string s when s.Equals("asc", StringComparison.OrdinalIgnoreCase) => SortOrder.Ascending,
                string s when s.Equals("desc", StringComparison.OrdinalIgnoreCase) => SortOrder.Descending,
                null => null,
                _ => throw new InvalidOperationException($"Invalid order value: {order}. Must be 'asc' or 'desc'.")
            };

            var result = await this._responsesService.ListResponseInputItemsAsync(
                responseId,
                limit,
                sortOrder,
                after,
                before,
                cancellationToken).ConfigureAwait(false);

            return Results.Ok(result);
        }
        catch (InvalidOperationException ex)
        {
            return Results.NotFound(new ErrorResponse
            {
                Error = new ErrorDetails
                {
                    Message = ex.Message,
                    Type = "invalid_request_error"
                }
            });
        }
    }
}
