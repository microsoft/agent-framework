// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Agents.AI.Foundry.Hosting;

namespace Hosted_Shared_Contributor_Setup;

/// <summary>
/// A <see cref="HostedSessionIsolationKeyProvider"/> for local Docker debugging only.
///
/// When the Foundry platform's <c>x-agent-user-id</c> header is absent (i.e., when the container is
/// running outside the Foundry platform), the hosting layer rejects every request with a 500 because
/// the default <see cref="HostedSessionIsolationKeyProvider"/> returns null. This provider supplies a
/// fallback value from the <c>HOSTED_USER_ID</c> environment variable, defaulting to the
/// constant below when it is not set.
///
/// This should NOT be used in production. The Foundry platform sets the user id for every inbound
/// request and forging it client-side defeats the per-user partitioning. The dev fallback exists
/// solely so a contributor can <c>docker run</c> the sample on their laptop and drive a few requests
/// end to end.
/// </summary>
public sealed class DevTemporaryLocalUserIdProvider : HostedSessionIsolationKeyProvider
{
    /// <summary>
    /// Environment variable that supplies the user id when the platform header is absent.
    /// </summary>
    public const string UserIdEnvironmentVariable = "HOSTED_USER_ID";

    /// <summary>
    /// Default user id used when neither the platform header nor the environment variable
    /// supplies a value. All local requests collapse onto this single bucket unless overridden.
    /// </summary>
    public const string DefaultLocalUserId = "local-dev-user";

    /// <inheritdoc />
    public override ValueTask<HostedSessionContext?> GetKeysAsync(
        ResponseContext context,
        CreateResponse request,
        CancellationToken cancellationToken)
    {
        var userId = !string.IsNullOrWhiteSpace(context?.PlatformContext?.UserIdKey)
            ? context!.PlatformContext!.UserIdKey
            : Environment.GetEnvironmentVariable(UserIdEnvironmentVariable);
        if (string.IsNullOrWhiteSpace(userId))
        {
            userId = DefaultLocalUserId;
        }

        return new ValueTask<HostedSessionContext?>(new HostedSessionContext(userId!));
    }
}
