// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// Interface for executing response generation.
/// Implementations can use local execution (AIAgent) or forward to remote workers.
/// </summary>
internal interface IResponseExecutor
{
    /// <summary>
    /// Validates a create response request before execution.
    /// </summary>
    /// <param name="request">The create response request to validate.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>A <see cref="ResponseError"/> if validation fails, null if validation succeeds.</returns>
    ValueTask<ResponseError?> ValidateRequestAsync(
        CreateResponse request,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Executes a response generation request and returns streaming events.
    /// </summary>
    /// <param name="context">The agent invocation context containing the ID generator and other context information.</param>
    /// <param name="request">The create response request.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>An async enumerable of streaming response events.</returns>
    IAsyncEnumerable<StreamingResponseEvent> ExecuteAsync(
        AgentInvocationContext context,
        CreateResponse request,
        CancellationToken cancellationToken = default);
}
