// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// An external request port for a <see cref="Workflow"/> with the specified request and response types.
/// </summary>
/// <param name="Id"></param>
/// <param name="Request"></param>
/// <param name="Response"></param>
public sealed record InputPort(string Id, Type Request, Type Response)
{
    /// <summary>
    /// Creates a new <see cref="InputPort"/> instance configured for the specified request and response types.
    /// </summary>
    /// <typeparam name="TRequest">The type of the request messages that the input port will accept.</typeparam>
    /// <typeparam name="TResponse">The type of the response messages that the input port will produce.</typeparam>
    /// <param name="id">The unique identifier for the input port.</param>
    /// <returns>An <see cref="InputPort"/> instance associated with the specified <paramref name="id"/>, configured to handle
    /// requests of type <typeparamref name="TRequest"/> and responses of type <typeparamref name="TResponse"/>.</returns>
    public static InputPort Create<TRequest, TResponse>(string id) => new(id, typeof(TRequest), typeof(TResponse));
};
