// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Extension methods for reading and writing the <see cref="HostedSessionContext"/> associated
/// with an <see cref="AgentSession"/> in a Foundry hosted agent.
/// </summary>
/// <remarks>
/// The hosted session context is written exactly once by the hosting layer when a session is created,
/// and is validated against the live request on every subsequent invocation. The <see cref="SetHostedContext"/>
/// method is intentionally <see langword="internal"/> so that only the hosting layer can establish the
/// identity values; consumers (such as <see cref="AIContextProvider"/> implementations) read the values
/// through the public <see cref="GetHostedContext"/> accessor.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public static class HostedSessionContextExtensions
{
    /// <summary>
    /// The well-known <see cref="AgentSessionStateBag"/> key used to store the
    /// <see cref="HostedSessionContext"/> on a session.
    /// </summary>
    /// <remarks>
    /// Exposed as a constant so consumers can correlate persisted state across processes.
    /// External code must not write to this key directly; use <see cref="SetHostedContext"/> from the
    /// hosting assembly instead.
    /// </remarks>
    public const string StateKey = "Microsoft.Agents.AI.Foundry.Hosting.HostedSessionContext";

    /// <summary>
    /// Gets the <see cref="HostedSessionContext"/> previously written by the hosting layer
    /// for this session, if any.
    /// </summary>
    /// <param name="session">The session to read from.</param>
    /// <returns>
    /// The <see cref="HostedSessionContext"/> for the session, or <see langword="null"/> when the
    /// session was not produced by a hosted agent (or the value has not yet been written).
    /// </returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="session"/> is <see langword="null"/>.</exception>
    public static HostedSessionContext? GetHostedContext(this AgentSession session)
    {
        Throw.IfNull(session);

        return session.StateBag.TryGetValue<HostedSessionContext>(StateKey, out var context, HostedSessionJsonUtilities.DefaultOptions)
            ? context
            : null;
    }

    /// <summary>
    /// Writes the <see cref="HostedSessionContext"/> for this session.
    /// </summary>
    /// <param name="session">The session to write to.</param>
    /// <param name="context">The hosted session context to associate with <paramref name="session"/>.</param>
    /// <remarks>
    /// Internal to the hosting assembly. Consumers must not invoke this method directly; the hosting
    /// layer is the single writer and uses validation against the live request to detect any tampering
    /// that does occur via lower-level APIs. Throws when a context has already been written for this
    /// session to enforce the write-once contract.
    /// </remarks>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="session"/> or <paramref name="context"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">Thrown when this session already carries a <see cref="HostedSessionContext"/>.</exception>
    internal static void SetHostedContext(this AgentSession session, HostedSessionContext context)
    {
        Throw.IfNull(session);
        Throw.IfNull(context);

        if (session.StateBag.TryGetValue<HostedSessionContext>(StateKey, out _, HostedSessionJsonUtilities.DefaultOptions))
        {
            throw new InvalidOperationException(
                $"A {nameof(HostedSessionContext)} has already been written to this session. " +
                "The hosted session identity is write-once; resumed sessions must validate against the existing context, not overwrite it.");
        }

        session.StateBag.SetValue(StateKey, context, HostedSessionJsonUtilities.DefaultOptions);
    }
}
