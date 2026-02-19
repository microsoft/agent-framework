// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides strongly-typed state management for providers, enabling reading and writing of provider-specific state
/// to and from an <see cref="AgentSession"/>'s <see cref="AgentSessionStateBag"/>.
/// </summary>
/// <typeparam name="TState">The type of the state to be maintained. Must be a reference type.</typeparam>
/// <remarks>
/// <para>
/// This class encapsulates the logic for initializing, retrieving, and persisting provider state in the session's StateBag
/// using a configurable key and JSON serialization options. It is intended to be used as a composed field within provider
/// implementations (e.g., <see cref="AIContextProvider"/> or <see cref="ChatHistoryProvider"/> subclasses) to avoid
/// duplicating state management logic across provider type hierarchies.
/// </para>
/// <para>
/// State is stored in the <see cref="AgentSession.StateBag"/> using the <see cref="StateKey"/> property as the key,
/// enabling multiple providers to maintain independent state within the same session.
/// </para>
/// </remarks>
public class ProviderSessionState<TState>
    where TState : class
{
    private readonly Func<AgentSession?, TState> _stateInitializer;
    private readonly JsonSerializerOptions _jsonSerializerOptions;

    /// <summary>
    /// Initializes a new instance of the <see cref="ProviderSessionState{TState}"/> class.
    /// </summary>
    /// <param name="stateInitializer">A function to initialize the state when it is not yet present in the session's StateBag.</param>
    /// <param name="stateKey">The key used to store the state in the session's StateBag.</param>
    /// <param name="jsonSerializerOptions">Options for JSON serialization and deserialization of the state.</param>
    public ProviderSessionState(
        Func<AgentSession?, TState> stateInitializer,
        string stateKey,
        JsonSerializerOptions? jsonSerializerOptions = null)
    {
        this._stateInitializer = stateInitializer;
        this.StateKey = stateKey;
        this._jsonSerializerOptions = jsonSerializerOptions ?? AgentAbstractionsJsonUtilities.DefaultOptions;
    }

    /// <summary>
    /// Gets the key used to store the provider state in the <see cref="AgentSession.StateBag"/>.
    /// </summary>
    public string StateKey { get; }

    /// <summary>
    /// Gets the state from the session's StateBag, or initializes it using the state initializer if not present.
    /// </summary>
    /// <param name="session">The agent session containing the StateBag.</param>
    /// <returns>The provider state.</returns>
    public TState GetOrInitializeState(AgentSession? session)
    {
        if (session?.StateBag.TryGetValue<TState>(this.StateKey, out var state, this._jsonSerializerOptions) is true && state is not null)
        {
            return state;
        }

        state = this._stateInitializer(session);
        if (session is not null)
        {
            session.StateBag.SetValue(this.StateKey, state, this._jsonSerializerOptions);
        }

        return state;
    }

    /// <summary>
    /// Saves the specified state to the session's StateBag using the configured state key and JSON serializer options.
    /// If the session is null, this method does nothing.
    /// </summary>
    /// <param name="session">The agent session containing the StateBag.</param>
    /// <param name="state">The state to be saved.</param>
    public void SaveState(AgentSession? session, TState state)
    {
        if (session is not null)
        {
            session.StateBag.SetValue(this.StateKey, state, this._jsonSerializerOptions);
        }
    }
}
