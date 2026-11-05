// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

public static partial class FoundryHostingExtensions
{
    private const string HostedUserIdStateKey = "Microsoft.Agents.AI.Foundry.Hosting.HostedUserId";

    /// <summary>
    /// Gets the trusted Foundry user id associated with a hosted agent session.
    /// </summary>
    /// <param name="session">The session to read from.</param>
    /// <returns>The platform user id, or <see langword="null"/> when no hosted user identity was resolved.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="session"/> is <see langword="null"/>.</exception>
    public static string? GetHostedUserId(this AgentSession session)
    {
        Throw.IfNull(session);

        return session.StateBag.TryGetValue<string>(
            HostedUserIdStateKey,
            out var userId)
            ? userId
            : null;
    }

    internal static void SetHostedUserId(this AgentSession session, string userId)
    {
        Throw.IfNull(session);
        Throw.IfNullOrWhitespace(userId);

        if (session.StateBag.TryGetValue<string>(HostedUserIdStateKey, out _))
        {
            throw new InvalidOperationException(
                "A hosted user id has already been written to this session. " +
                "The hosted user id is write-once; resumed sessions must validate it instead of overwriting it.");
        }

        session.StateBag.SetValue(HostedUserIdStateKey, userId);
    }
}
