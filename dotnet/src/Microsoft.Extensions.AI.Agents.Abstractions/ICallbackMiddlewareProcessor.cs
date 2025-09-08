// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Defines a processor for managing and adding callback middleware components.
/// </summary>
/// <remarks>This interface allows the registration of middleware components that can process callbacks.
/// Middleware components are added in the order they should be executed.</remarks>
public interface ICallbackMiddlewareProcessor
{
    /// <summary>
    /// Add a middleware callback to the processor.
    /// </summary>
    /// <param name="middleware">A valid middleware implementation <see cref="ICallbackMiddleware" /> to handle.</param>
    void AddCallback(ICallbackMiddleware middleware);
}
