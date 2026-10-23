// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// Supplies the isolation key of the request that performs the current A2A operation to the task and session stores.
/// </summary>
/// <remarks>
/// A2A servers are shared by all requests, so they must not capture an <see cref="AgentIsolationKeyProvider"/>
/// that can be scoped. Within a request mapped by the A2A endpoint extensions, the key resolved for the request is
/// used. Otherwise, for example when an <c>A2AServer</c> is invoked directly, the provider is resolved from a new
/// service scope for each operation.
/// </remarks>
internal sealed class A2ARequestIsolationKeyProvider(IServiceScopeFactory scopeFactory) : AgentIsolationKeyProvider
{
    /// <inheritdoc/>
    public override async ValueTask<string?> GetIsolationKeyAsync(CancellationToken cancellationToken = default)
    {
        A2ARequestIsolation? isolation = A2ARequestIsolation.Current;
        if (isolation is null)
        {
            AsyncServiceScope scope = scopeFactory.CreateAsyncScope();
            await using (scope.ConfigureAwait(false))
            {
                isolation = await A2ARequestIsolation.ResolveAsync(scope.ServiceProvider, cancellationToken).ConfigureAwait(false);
            }
        }

        return isolation.GetKey();
    }
}
