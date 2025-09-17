// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Function invocation specific extensions for <see cref="CallbackMiddlewareProcessor"/>.
/// </summary>
public static class CallbackMiddlewareProcessorFunctionInvocationExtensions
{
    /// <summary>
    /// Adds a callback middleware to the specified <see cref="CallbackMiddlewareProcessor"/>.
    /// </summary>
    /// <param name="processor">The <see cref="CallbackMiddlewareProcessor"/> to which the middleware will be added. Cannot be <see
    /// langword="null"/>.</param>
    /// <param name="middleware">The callback middleware to add. Cannot be <see langword="null"/>.</param>
    public static CallbackMiddlewareProcessor AddCallback(this CallbackMiddlewareProcessor processor, ICallbackMiddleware<AgentFunctionInvocationContext> middleware)
        => processor.AddCallback(Throw.IfNull(middleware));
}
