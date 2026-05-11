// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.A2A;

/// <summary>
/// Represents an A2A user input request, wrapping the requested content.
/// </summary>
public sealed class A2AInputRequestContent : InputRequestContent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="A2AInputRequestContent"/> class.
    /// </summary>
    /// <param name="id">The ID that uniquely identifies the user input request/response pair.</param>
    /// <param name="request">The request for user input.</param>
    /// <exception cref="ArgumentNullException"><paramref name="id"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="id"/> is empty or composed entirely of whitespace.</exception>
    /// <exception cref="ArgumentNullException"><paramref name="request"/> is <see langword="null"/>.</exception>
    public A2AInputRequestContent(string id, AIContent request) : base(id)
    {
        this.Request = Throw.IfNull(request);
    }

    /// <summary>
    /// Gets the request for user input.
    /// </summary>
    public AIContent Request { get; }

    /// <summary>
    /// Creates a <see cref="A2AInputResponseContent"/> to provide the user's response to this request.
    /// </summary>
    /// <param name="response">The <see cref="AIContent"/> containing the user's response.</param>
    /// <returns>The <see cref="A2AInputResponseContent"/> representing the response.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="response"/> is <see langword="null"/>.</exception>
    public A2AInputResponseContent CreateResponse(AIContent response) => new(this.RequestId, response);

    /// <summary>
    /// Creates a <see cref="A2AInputResponseContent"/> to provide the user's response to this request from text.
    /// </summary>
    /// <param name="text">The text of the user's response.</param>
    /// <returns>The <see cref="A2AInputResponseContent"/> representing the response.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="text"/> is <see langword="null"/>.</exception>
    public A2AInputResponseContent CreateResponse(string text) => new(this.RequestId, new TextContent(Throw.IfNull(text)));
}
