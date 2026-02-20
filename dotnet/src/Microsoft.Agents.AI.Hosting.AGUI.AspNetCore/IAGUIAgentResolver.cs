// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Http;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

/// <summary>
/// Provides dynamic resolution of <see cref="AIAgent"/> instances based on the incoming HTTP request.
/// </summary>
/// <remarks>
/// <para>
/// Implement this interface to enable dynamic agent resolution based on request context,
/// such as route parameters, headers, or query strings. This is useful for multi-tenant
/// applications or scenarios where the agent to use depends on runtime factors.
/// </para>
/// <para>
/// If an implementation is registered as a singleton or otherwise shared across requests,
/// it must be thread-safe because the same resolver instance may be invoked concurrently
/// for multiple requests.
/// </para>
/// </remarks>
public interface IAGUIAgentResolver
{
    /// <summary>
    /// Resolves an <see cref="AIAgent"/> instance based on the current HTTP request context.
    /// </summary>
    /// <param name="context">The HTTP context containing request information such as route values, headers, and query parameters.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the resolution operation.</param>
    /// <returns>
    /// A <see cref="ValueTask{TResult}"/> representing the asynchronous operation.
    /// Returns the resolved <see cref="AIAgent"/> instance, or <see langword="null"/> if no agent could be resolved
    /// (which will result in a 404 Not Found response).
    /// </returns>
    ValueTask<AIAgent?> ResolveAgentAsync(HttpContext context, CancellationToken cancellationToken);
}
