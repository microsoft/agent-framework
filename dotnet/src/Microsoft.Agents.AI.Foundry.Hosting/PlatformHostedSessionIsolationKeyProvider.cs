// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Default <see cref="HostedSessionIsolationKeyProvider"/> implementation that maps the platform-injected
/// <c>x-agent-user-id</c> header from <see cref="ResponseContext.PlatformContext"/> into a
/// <see cref="HostedSessionContext"/>.
/// </summary>
/// <remarks>
/// This is the implementation used in production Foundry hosted environments. When running locally
/// outside the platform, the user id is <see langword="null"/>, which causes
/// <see cref="GetKeysAsync"/> to return <see langword="null"/>. The hosting layer treats a null
/// result differently depending on where the container runs: when hosted by Foundry
/// (<c>FoundryEnvironment.IsHosted</c>) it is a configuration error and surfaces as a 500; when running
/// locally (not hosted) per-user isolation is simply not triggered and the request proceeds with no
/// user partitioning. Local development can still register an alternate
/// <see cref="HostedSessionIsolationKeyProvider"/> implementation to simulate distinct users.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal sealed class PlatformHostedSessionIsolationKeyProvider : HostedSessionIsolationKeyProvider
{
    /// <inheritdoc />
    public override ValueTask<HostedSessionContext?> GetKeysAsync(
        ResponseContext context,
        CreateResponse request,
        CancellationToken cancellationToken)
    {
        var userKey = context?.PlatformContext?.UserIdKey;

        if (string.IsNullOrWhiteSpace(userKey))
        {
            return new ValueTask<HostedSessionContext?>((HostedSessionContext?)null);
        }

        return new ValueTask<HostedSessionContext?>(new HostedSessionContext(userKey!));
    }
}
