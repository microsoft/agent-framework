// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Agents.AI.Foundry.Hosting;

namespace Hosted_Shared_Contributor_Setup;

/// <summary>
/// A <see cref="HostedSessionIsolationKeyProvider"/> for local Docker debugging only.
///
/// When the Foundry platform's <c>x-agent-user-isolation-key</c> and
/// <c>x-agent-chat-isolation-key</c> headers are absent (i.e., when the container is running
/// outside the Foundry platform), the hosting layer rejects every request with a 500 because the
/// default <see cref="HostedSessionIsolationKeyProvider"/> returns null. This provider supplies
/// fallback values from the <c>HOSTED_USER_ISOLATION_KEY</c> and <c>HOSTED_CHAT_ISOLATION_KEY</c>
/// environment variables, defaulting to the constants below when neither is set.
///
/// This should NOT be used in production. The Foundry platform sets the isolation keys for every
/// inbound request and forging them client-side defeats the per-user partitioning. The dev
/// fallback exists solely so a contributor can <c>docker run</c> the sample on their laptop and
/// drive a few requests end to end.
/// </summary>
public sealed class DevTemporaryLocalSessionIsolationKeyProvider : HostedSessionIsolationKeyProvider
{
    /// <summary>
    /// Environment variable that supplies the user isolation key when the platform header is absent.
    /// </summary>
    public const string UserIsolationKeyEnvironmentVariable = "HOSTED_USER_ISOLATION_KEY";

    /// <summary>
    /// Environment variable that supplies the chat isolation key when the platform header is absent.
    /// </summary>
    public const string ChatIsolationKeyEnvironmentVariable = "HOSTED_CHAT_ISOLATION_KEY";

    /// <summary>
    /// Default user isolation key used when neither the platform header nor the environment variable
    /// supplies a value. All local requests collapse onto this single bucket unless overridden.
    /// </summary>
    public const string DefaultLocalUserIsolationKey = "local-dev-user";

    /// <summary>
    /// Default chat isolation key used when neither the platform header nor the environment variable
    /// supplies a value.
    /// </summary>
    public const string DefaultLocalChatIsolationKey = "local-dev-chat";

    /// <inheritdoc />
    public override ValueTask<HostedSessionContext?> GetKeysAsync(
        ResponseContext context,
        CreateResponse request,
        CancellationToken cancellationToken)
    {
        var userKey = !string.IsNullOrWhiteSpace(context?.Isolation?.UserIsolationKey)
            ? context!.Isolation!.UserIsolationKey
            : Environment.GetEnvironmentVariable(UserIsolationKeyEnvironmentVariable);
        if (string.IsNullOrWhiteSpace(userKey))
        {
            userKey = DefaultLocalUserIsolationKey;
        }

        var chatKey = !string.IsNullOrWhiteSpace(context?.Isolation?.ChatIsolationKey)
            ? context!.Isolation!.ChatIsolationKey
            : Environment.GetEnvironmentVariable(ChatIsolationKeyEnvironmentVariable);
        if (string.IsNullOrWhiteSpace(chatKey))
        {
            chatKey = DefaultLocalChatIsolationKey;
        }

        return new ValueTask<HostedSessionContext?>(new HostedSessionContext(userKey!, chatKey!));
    }
}
