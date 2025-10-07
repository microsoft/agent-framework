// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the response of the specified type <typeparamref name="T"/> to an <see cref="ChatClientAgent"/> run request.
/// </summary>
/// <typeparam name="T">The type of value expected from the chat response.</typeparam>
/// <remarks>
/// Language models are not guaranteed to honor the requested schema. If the model's output is not
/// parsable as the expected type, you can access the underlying JSON response on the <see cref="AgentRunResponse.Text"/> property.
/// </remarks>
public sealed class ChatClientAgentRunResponse<T> : AgentRunResponse<T>
{
    private readonly ChatResponse<T> _response;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRunResponse{T}"/> class from an existing <see cref="ChatResponse{T}"/>.
    /// </summary>
    /// <param name="response">The <see cref="ChatResponse{T}"/> from which to populate this <see cref="AgentRunResponse{T}"/>.</param>
    /// <exception cref="ArgumentNullException"><paramref name="response"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// This constructor creates an agent response that wraps an existing <see cref="ChatResponse{T}"/>, preserving all
    /// metadata and storing the original response in <see cref="ChatResponse.RawRepresentation"/> for access to
    /// the underlying implementation details.
    /// </remarks>
    public ChatClientAgentRunResponse(ChatResponse<T> response) : base(response)
    {
        _ = Throw.IfNull(response);

        this._response = response;
    }

    /// <summary>
    /// Gets the result value of the agent response as an instance of <typeparamref name="T"/>.
    /// </summary>
    /// <remarks>
    /// If the response did not contain JSON, or if deserialization fails, this property will throw.
    /// To avoid exceptions, use <see cref="AgentRunResponse.TryDeserialize{T}"/> instead.
    /// </remarks>
    public override T Result => this._response.Result;
}
