// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Defines a middleware component for processing callback contexts in a pipeline.
/// </summary>
/// <remarks>Middleware components implementing this interface are used to process callback contexts and
/// optionally perform additional operations before or after invoking the next middleware in the pipeline. The pipeline
/// allows for modular and extensible handling of callback processing.</remarks>
public interface ICallbackMiddleware
{
    /// <summary>
    /// Determines whether this middleware can process the specified context type.
    /// </summary>
    /// <param name="contextType">The type of context to check.</param>
    /// <returns><see langword="true"/> if this middleware can process the context type; otherwise, <see langword="false"/>.</returns>
    bool CanProcess(Type contextType);

    /// <summary>
    /// Processes the specified callback context and invokes the next middleware in the pipeline.
    /// </summary>
    /// <remarks>This method is typically used in middleware pipelines to process a callback and optionally
    /// perform additional operations before or after invoking the next middleware.</remarks>
    /// <param name="context">The context for the current callback, containing relevant data and state.</param>
    /// <param name="next">A delegate representing the next middleware to be executed in the pipeline.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A task that represents the asynchronous operation.</returns>
    Task OnProcessAsync(CallbackContext context, Func<CallbackContext, Task> next, CancellationToken cancellationToken);
}
