// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Built-in <see cref="FoundryMemoryProvider"/> <c>stateInitializer</c> factories that derive the
/// <see cref="FoundryMemoryProviderScope"/> from the per-session <see cref="HostedSessionContext"/>
/// applied by the Foundry hosting layer.
/// </summary>
/// <remarks>
/// Pass the result of any of these helpers as the <c>stateInitializer</c> argument when constructing
/// <see cref="FoundryMemoryProvider"/>:
/// <code>
/// new FoundryMemoryProvider(client, "my-store",
///     stateInitializer: HostedFoundryMemoryProviderScopes.PerUser());
/// </code>
/// All helpers throw <see cref="InvalidOperationException"/> when
/// <see cref="HostedSessionContextExtensions.GetHostedContext"/> returns <see langword="null"/>.
/// That happens when the agent runs outside the Foundry hosting layer (e.g., a console app); in
/// that case write a custom <c>stateInitializer</c> instead of using these helpers.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public static class HostedFoundryMemoryProviderScopes
{
    /// <summary>
    /// Returns a <c>stateInitializer</c> that scopes memories per end user, using
    /// <see cref="HostedSessionContext.UserId"/> as the partition key.
    /// </summary>
    /// <returns>A delegate suitable for the <c>stateInitializer</c> argument of <see cref="FoundryMemoryProvider"/>.</returns>
    public static Func<AgentSession?, FoundryMemoryProvider.State> PerUser() =>
        session => new FoundryMemoryProvider.State(new FoundryMemoryProviderScope(GetRequiredHostedContext(session).UserId));

    /// <summary>
    /// Returns a <c>stateInitializer</c> that scopes memories per conversation, using
    /// <see cref="HostedSessionContext.ChatId"/> as the partition key. Use this when memories should
    /// be visible to every participant in a shared conversation (for example, a Teams group chat).
    /// </summary>
    /// <returns>A delegate suitable for the <c>stateInitializer</c> argument of <see cref="FoundryMemoryProvider"/>.</returns>
    public static Func<AgentSession?, FoundryMemoryProvider.State> PerChat() =>
        session => new FoundryMemoryProvider.State(new FoundryMemoryProviderScope(GetRequiredHostedContext(session).ChatId));

    /// <summary>
    /// Returns a <c>stateInitializer</c> that scopes memories per (user, chat) pair, using
    /// <c>"{UserId}:{ChatId}"</c> as the partition key. Use this when memories should be visible
    /// only to the same user within the same conversation.
    /// </summary>
    /// <returns>A delegate suitable for the <c>stateInitializer</c> argument of <see cref="FoundryMemoryProvider"/>.</returns>
    public static Func<AgentSession?, FoundryMemoryProvider.State> PerUserAndChat() =>
        session =>
        {
            var ctx = GetRequiredHostedContext(session);
            return new FoundryMemoryProvider.State(new FoundryMemoryProviderScope($"{ctx.UserId}:{ctx.ChatId}"));
        };

    private static HostedSessionContext GetRequiredHostedContext(AgentSession? session) =>
        session?.GetHostedContext()
            ?? throw new InvalidOperationException(
                $"{nameof(HostedSessionContext)} was not provided by the hosting layer. " +
                $"The {nameof(HostedFoundryMemoryProviderScopes)} helpers require the agent to be hosted via the Foundry hosting layer. " +
                "If running outside a hosted Foundry container, supply a custom stateInitializer to FoundryMemoryProvider instead.");
}
