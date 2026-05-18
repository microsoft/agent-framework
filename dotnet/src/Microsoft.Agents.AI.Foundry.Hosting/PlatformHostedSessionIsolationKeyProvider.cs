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
/// <c>x-agent-user-isolation-key</c> and <c>x-agent-chat-isolation-key</c> headers from
/// <see cref="ResponseContext.Isolation"/> into a <see cref="HostedSessionContext"/>.
/// </summary>
/// <remarks>
/// This is the implementation used in production Foundry hosted environments. When running locally
/// outside the platform, both isolation keys are <see langword="null"/>, which causes
/// <see cref="GetKeysAsync"/> to return <see langword="null"/>. The hosting layer treats a null
/// result as a configuration error and surfaces it as a 500 from the request. Local development
/// should register an alternate <see cref="HostedSessionIsolationKeyProvider"/> implementation
/// that provides fallback values for the missing headers.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
internal sealed class PlatformHostedSessionIsolationKeyProvider : HostedSessionIsolationKeyProvider
{
    /// <inheritdoc />
    public override ValueTask<HostedSessionContext?> GetKeysAsync(
        ResponseContext context,
        CreateResponse request,
        CancellationToken cancellationToken)
    {
        var userKey = context?.Isolation?.UserIsolationKey;
        var chatKey = context?.Isolation?.ChatIsolationKey;

        if (string.IsNullOrWhiteSpace(userKey) || string.IsNullOrWhiteSpace(chatKey))
        {
            return new ValueTask<HostedSessionContext?>((HostedSessionContext?)null);
        }

        return new ValueTask<HostedSessionContext?>(new HostedSessionContext(userKey!, chatKey!));
    }
}
