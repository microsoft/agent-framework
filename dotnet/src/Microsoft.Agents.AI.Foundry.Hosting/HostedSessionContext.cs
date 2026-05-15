// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Captures the per-session identity values produced by a <see cref="HostedSessionIsolationKeyProvider"/>
/// when a Foundry hosted agent processes a request.
/// </summary>
/// <remarks>
/// <para>
/// The <see cref="UserId"/> partitions data that belongs to the individual who initiated the request
/// (e.g., personal memory, per-user preferences). The <see cref="ChatId"/> partitions data that belongs
/// to the conversation (e.g., conversation history, turn state). Both values are opaque strings whose
/// meaning is determined by the active <see cref="HostedSessionIsolationKeyProvider"/>.
/// </para>
/// <para>
/// Instances are constructed by the hosting layer from the platform-provided
/// <c>IsolationContext</c> headers and stored on the session via
/// <see cref="HostedSessionContextExtensions.SetHostedContext"/>. Consumers (typically
/// <see cref="AIContextProvider"/> implementations) read the values through
/// <see cref="HostedSessionContextExtensions.GetHostedContext"/>.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public sealed class HostedSessionContext
{
    /// <summary>
    /// Initializes a new instance of the <see cref="HostedSessionContext"/> class.
    /// </summary>
    /// <param name="userId">The opaque user identity for this hosted session. Must not be null or whitespace.</param>
    /// <param name="chatId">The opaque chat (conversation) identity for this hosted session. Must not be null or whitespace.</param>
    /// <exception cref="System.ArgumentException">Thrown when <paramref name="userId"/> or <paramref name="chatId"/> is null or whitespace.</exception>
    public HostedSessionContext(string userId, string chatId)
    {
        this.UserId = Throw.IfNullOrWhitespace(userId);
        this.ChatId = Throw.IfNullOrWhitespace(chatId);
    }

    /// <summary>
    /// Gets the opaque user identity for this hosted session.
    /// </summary>
    /// <remarks>
    /// Stable for a given user across sessions. In production this is sourced from the
    /// <c>x-agent-user-isolation-key</c> platform header.
    /// </remarks>
    public string UserId { get; }

    /// <summary>
    /// Gets the opaque chat (conversation) identity for this hosted session.
    /// </summary>
    /// <remarks>
    /// In a 1:1 user-to-agent chat this typically equals <see cref="UserId"/>. In shared-surface
    /// scenarios (e.g., a Teams group chat) it represents the common partition all participants
    /// write to. In production this is sourced from the <c>x-agent-chat-isolation-key</c> platform header.
    /// </remarks>
    public string ChatId { get; }
}
