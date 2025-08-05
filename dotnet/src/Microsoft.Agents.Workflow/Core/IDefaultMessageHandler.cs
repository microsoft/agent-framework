// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// A default message handler interface for handling messages that do not have a specific handler registered.
/// </summary>
public interface IDefaultMessageHandler
{
    /// <summary>
    /// Handles the incoming message asynchronously.
    /// </summary>
    /// <remarks>
    /// This is used as a fallback handler for messages that do not have a specific handler registered.
    /// </remarks>
    /// <param name="message">The message to handle.</param>
    /// <param name="context">The execution context.</param>
    /// <returns>A task that represents the asynchronous operation.</returns>
    ValueTask HandleAsync(object message, IWorkflowContext context);
}
