// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.A2A;

/// <summary>
/// Represents an A2A response to a user input request, wrapping the response content.
/// </summary>
public sealed class A2AInputResponseContent : InputResponseContent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="A2AInputResponseContent"/> class.
    /// </summary>
    /// <param name="id">The ID that uniquely identifies the user input request/response pair.</param>
    /// <param name="response">The response to the user input request.</param>
    /// <exception cref="ArgumentNullException"><paramref name="id"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="id"/> is empty or composed entirely of whitespace.</exception>
    /// <exception cref="ArgumentNullException"><paramref name="response"/> is <see langword="null"/>.</exception>
    public A2AInputResponseContent(string id, AIContent response) : base(id)
    {
        this.Response = Throw.IfNull(response);
    }

    /// <summary>
    /// Gets the response to the user input request.
    /// </summary>
    public AIContent Response { get; }
}
