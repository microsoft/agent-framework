// Copyright (c) Microsoft. All rights reserved.

using Microsoft.AspNetCore.Http;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// Well-known error codes returned by response request validation, together with their mapping to
/// the HTTP status code a handler should return for each. Centralizing the codes avoids scattering
/// string literals and keeps the status mapping in a single place.
/// </summary>
internal static class ResponseErrorCodes
{
    /// <summary>
    /// The request was malformed or violated a request-level constraint (HTTP 400).
    /// </summary>
    public const string InvalidRequest = "invalid_request";

    /// <summary>
    /// A conversation referenced by the request does not exist (HTTP 404).
    /// </summary>
    public const string ConversationNotFound = "conversation_not_found";

    /// <summary>
    /// Maps a validation error code to the HTTP status code and the wire error code a handler should
    /// return for it. Not-found codes map to <see cref="StatusCodes.Status404NotFound"/> with a
    /// <see langword="null"/> wire code (matching the OpenAI error body, whose semantics are carried
    /// by the error <c>type</c>); every other validation failure maps to
    /// <see cref="StatusCodes.Status400BadRequest"/> and keeps its code.
    /// </summary>
    /// <param name="code">The <see cref="Models.ResponseError.Code"/> to map.</param>
    /// <returns>The HTTP status code and the wire error code to return for the given error code.</returns>
    public static (int StatusCode, string? WireCode) MapValidationError(string? code) => code switch
    {
        ConversationNotFound => (StatusCodes.Status404NotFound, null),
        _ => (StatusCodes.Status400BadRequest, code),
    };
}
