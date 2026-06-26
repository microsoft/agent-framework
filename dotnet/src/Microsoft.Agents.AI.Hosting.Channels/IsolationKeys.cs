// Copyright (c) Microsoft. All rights reserved.

using System.Threading;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Per-request partition hints the Foundry Hosted Agents runtime injects on requests it forwards to the
/// container, lifted off the <c>x-agent-user-isolation-key</c> / <c>x-agent-chat-isolation-key</c> headers.
/// </summary>
/// <remarks>
/// Distinct from the app-level <see cref="ChannelSession.IsolationKey"/>. Consuming providers read
/// <see cref="Current"/> (or inject <see cref="IIsolationKeysAccessor"/>) so individual channels do not each
/// have to parse the platform headers. The host installs the lifting filter only when the Foundry hosting
/// environment flag is present; absent the flag the raw headers are ignored and <see cref="Current"/> stays
/// <see langword="null"/>.
/// </remarks>
public sealed class IsolationKeys
{
    /// <summary>Header name carrying the opaque per-user partition key.</summary>
    public const string UserHeader = "x-agent-user-isolation-key";

    /// <summary>Header name carrying the opaque per-conversation partition key.</summary>
    public const string ChatHeader = "x-agent-chat-isolation-key";

    private static readonly AsyncLocal<IsolationKeys?> s_current = new();

    /// <summary>Initializes a new instance of the <see cref="IsolationKeys"/> class.</summary>
    /// <param name="userKey">The per-user partition key, or <see langword="null"/>.</param>
    /// <param name="chatKey">The per-conversation partition key, or <see langword="null"/>.</param>
    public IsolationKeys(string? userKey, string? chatKey)
    {
        this.UserKey = userKey;
        this.ChatKey = chatKey;
    }

    /// <summary>Gets the per-user partition key, when present.</summary>
    public string? UserKey { get; }

    /// <summary>Gets the per-conversation partition key, when present.</summary>
    public string? ChatKey { get; }

    /// <summary>Gets a value indicating whether both keys are <see langword="null"/>.</summary>
    public bool IsEmpty => this.UserKey is null && this.ChatKey is null;

    /// <summary>Gets or sets the current per-request keys for the executing async flow.</summary>
    public static IsolationKeys? Current
    {
        get => s_current.Value;
        set => s_current.Value = value;
    }
}

/// <summary>Dependency-injection accessor over <see cref="IsolationKeys.Current"/> for testable consumers.</summary>
public interface IIsolationKeysAccessor
{
    /// <summary>Gets the current per-request keys, or <see langword="null"/> when none were lifted.</summary>
    IsolationKeys? Current { get; }
}

internal sealed class IsolationKeysAccessor : IIsolationKeysAccessor
{
    public IsolationKeys? Current => IsolationKeys.Current;
}
