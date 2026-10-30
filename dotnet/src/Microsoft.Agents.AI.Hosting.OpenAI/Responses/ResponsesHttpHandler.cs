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
    private readonly Func<HttpContext, (IResponsesService Service, IResponseExecutor Executor)?>? _agentSelector;

    /// <summary>
    /// Initializes a new instance of the <see cref="ResponsesHttpHandler"/> class.
    /// </summary>
    /// <param name="responsesService">The responses service.</param>
    /// <param name="agentSelector">
    /// An optional delegate that selects, for every operation, the responses service bound to the selected agent and
    /// the executor that runs it, returning <see langword="null"/> when no agent matches the request. When omitted,
    /// <paramref name="responsesService"/> and its executor are used.
    /// </param>
    public ResponsesHttpHandler(
        IResponsesService responsesService,
        Func<HttpContext, (IResponsesService Service, IResponseExecutor Executor)?>? agentSelector = null)
    {
        this._responsesService = responsesService ?? throw new ArgumentNullException(nameof(responsesService));
        this._agentSelector = agentSelector;
    }

    /// <summary>
    /// Creates a model response for the given input.
    /// </summary>
    public async Task<IResult> CreateResponseAsync(
        HttpContext httpContext,
        [FromBody] CreateResponse request,
        [FromQuery] bool? stream,
        CancellationToken cancellationToken)
    {
        // Select the agent before validation so an unmatched request never loads session or conversation state.
        if (!this.TrySelectAgent(httpContext, out IResponsesService responsesService, out IResponseExecutor? executor))
        {
            return AgentNotFound();
        }

        // Validate the request first
        ResponseError? validationError = executor is null
            ? await responsesService.ValidateRequestAsync(request, cancellationToken).ConfigureAwait(false)
            : await responsesService.ValidateRequestAsync(request, executor, cancellationToken).ConfigureAwait(false);
        if (validationError is not null)
        {
            var (statusCode, wireCode) = ResponseErrorCodes.MapValidationError(validationError.Code);
            var errorResponse = new ErrorResponse
            {
                Error = new ErrorDetails
                {
                    Message = validationError.Message,
                    Type = "invalid_request_error",
                    Code = wireCode
                }
            };

            // Not-found codes become a 404; other validation failures are 400 bad requests.
            return statusCode == StatusCodes.Status404NotFound
                ? Results.NotFound(errorResponse)
                : Results.BadRequest(errorResponse);
        }

        try
        {
            // Handle streaming vs non-streaming
            bool shouldStream = stream ?? request.Stream ?? false;

            if (shouldStream)
            {
                var streamingResponse = executor is null
                    ? responsesService.CreateResponseStreamingAsync(request, cancellationToken: cancellationToken)
                    : responsesService.CreateResponseStreamingAsync(request, executor, cancellationToken);

                return new SseJsonResult<StreamingResponseEvent>(
                    streamingResponse,
                    static evt => evt.Type,
                    OpenAIHostingJsonContext.Default.StreamingResponseEvent);
            }

            var response = executor is null
                ? await responsesService.CreateResponseAsync(request, cancellationToken: cancellationToken).ConfigureAwait(false)
                : await responsesService.CreateResponseAsync(request, executor, cancellationToken).ConfigureAwait(false);

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
        HttpContext httpContext,
        string responseId,
        [FromQuery] string[]? include,
        [FromQuery] bool? stream,
        [FromQuery] int? starting_after,
        CancellationToken cancellationToken)
    {
        if (!this.TrySelectAgent(httpContext, out IResponsesService responsesService, out _))
        {
            return AgentNotFound();
        }

        // If streaming is requested, return SSE stream
        if (stream == true)
        {
            var streamingResponse = responsesService.GetResponseStreamingAsync(
                responseId,
                startingAfter: starting_after,
                cancellationToken: cancellationToken);

            return new SseJsonResult<StreamingResponseEvent>(
                streamingResponse,
                static evt => evt.Type,
                OpenAIHostingJsonContext.Default.StreamingResponseEvent);
        }

        // Non-streaming: return the response object
        var response = await responsesService.GetResponseAsync(responseId, cancellationToken).ConfigureAwait(false);
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
        HttpContext httpContext,
        string responseId,
        CancellationToken cancellationToken)
    {
        if (!this.TrySelectAgent(httpContext, out IResponsesService responsesService, out _))
        {
            return AgentNotFound();
        }

        try
        {
            var response = await responsesService.CancelResponseAsync(responseId, cancellationToken).ConfigureAwait(false);
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
        HttpContext httpContext,
        string responseId,
        CancellationToken cancellationToken)
    {
        if (!this.TrySelectAgent(httpContext, out IResponsesService responsesService, out _))
        {
            return AgentNotFound();
        }

        var deleted = await responsesService.DeleteResponseAsync(responseId, cancellationToken).ConfigureAwait(false);
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
        HttpContext httpContext,
        string responseId,
        [FromQuery] int? limit,
        [FromQuery] string? order,
        [FromQuery] string? after,
        [FromQuery] string? before,
        CancellationToken cancellationToken)
    {
        if (!this.TrySelectAgent(httpContext, out IResponsesService responsesService, out _))
        {
            return AgentNotFound();
        }

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

            var result = await responsesService.ListResponseInputItemsAsync(
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

    private bool TrySelectAgent(HttpContext httpContext, out IResponsesService responsesService, out IResponseExecutor? executor)
    {
        responsesService = this._responsesService;
        executor = null;
        if (this._agentSelector is null)
        {
            return true;
        }

        if (this._agentSelector(httpContext) is not { } selection)
        {
            return false;
        }

        (responsesService, executor) = selection;
        return true;
    }

    private static IResult AgentNotFound() =>
        Results.NotFound(new ErrorResponse
        {
            Error = new ErrorDetails
            {
                Message = "No agent matches the request.",
                Type = "invalid_request_error",
                Code = "agent_not_found"
            }
        });
}
