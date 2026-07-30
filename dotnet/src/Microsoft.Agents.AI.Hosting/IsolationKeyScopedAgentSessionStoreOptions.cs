// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Options for configuring <see cref="IsolationKeyScopedAgentSessionStore"/>.
/// </summary>
public class IsolationKeyScopedAgentSessionStoreOptions
{
    /// <summary>
    /// Gets or sets a value indicating whether an exception should be thrown when the isolation key cannot be determined.
    /// </summary>
    /// <remarks>
    /// <para>
    /// If <see langword="true"/> (default), the store will throw an <see cref="System.InvalidOperationException"/>
    /// when <see cref="SessionIsolationKeyProvider.GetSessionIsolationKeyAsync"/> returns <see langword="null"/>.
    /// </para>
    /// <para>
    /// If <see langword="false"/>, the conversation ID is passed through unmodified when the isolation key is absent,
    /// allowing unscoped access to the underlying session store. This mode is suitable for development scenarios
    /// or mixed environments where not all requests have isolation keys.
    /// </para>
    /// </remarks>
    public bool Strict { get; set; } = true;
}
