// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an abstract base class for components that enhance AI context during agent invocations with support for maintaining provider state of type <typeparamref name="TState"/>.
/// </summary>
/// <typeparam name="TState">The type of the state to be maintained by the context provider. Must be a reference type.</typeparam>
/// <remarks>
/// This class extends <see cref="AIContextProvider"/> by introducing a strongly-typed state management mechanism, allowing derived classes to maintain and persist custom state information across invocations.
/// The state is stored in the session's StateBag using a configurable key and JSON serialization options, enabling seamless integration with the agent session lifecycle.
/// </remarks>
public abstract class AIContextProvider<TState> : AIContextProvider
    where TState : class
{
    private readonly Func<AgentSession?, TState> _stateInitializer;
    private readonly string _stateKey;
    private readonly JsonSerializerOptions _jsonSerializerOptions;

    /// <summary>
    /// Initializes a new instance of the <see cref="AIContextProvider{TState}"/> class.
    /// </summary>
    /// <param name="stateInitializer">A function to initialize the state for the context provider.</param>
    /// <param name="stateKey">The key used to store the state in the session's StateBag.</param>
    /// <param name="jsonSerializerOptions">Options for JSON serialization and deserialization of the state.</param>
    /// <param name="provideInputMessageFilter">An optional filter function to apply to input messages before providing context. If not set, defaults to including only <see cref="AgentRequestMessageSourceType.External"/> messages.</param>
    /// <param name="storeInputMessageFilter">An optional filter function to apply to request messages before storing context. If not set, defaults to including only <see cref="AgentRequestMessageSourceType.External"/> messages.</param>
    protected AIContextProvider(
        Func<AgentSession?, TState> stateInitializer,
        string? stateKey,
        JsonSerializerOptions? jsonSerializerOptions,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? provideInputMessageFilter,
        Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? storeInputMessageFilter)
        : base(provideInputMessageFilter, storeInputMessageFilter)
    {
        this._stateInitializer = stateInitializer;
        this._jsonSerializerOptions = jsonSerializerOptions ?? AgentAbstractionsJsonUtilities.DefaultOptions;
        this._stateKey = stateKey ?? this.GetType().Name;
    }

    /// <inheritdoc />
    public override string StateKey => this._stateKey;

    /// <summary>
    /// Gets the state from the session's StateBag, or initializes it using the state initializer if not present.
    /// </summary>
    /// <param name="session">The agent session containing the StateBag.</param>
    /// <returns>The provider state.</returns>
    protected virtual TState GetOrInitializeState(AgentSession? session)
    {
        if (session?.StateBag.TryGetValue<TState>(this._stateKey, out var state, this._jsonSerializerOptions) is true && state is not null)
        {
            return state;
        }

        state = this._stateInitializer(session);
        if (session is not null)
        {
            session.StateBag.SetValue(this._stateKey, state, this._jsonSerializerOptions);
        }

        return state;
    }

    /// <summary>
    /// Saves the specified state to the session's StateBag using the configured state key and JSON serializer options.
    /// If the session is null, this method does nothing.
    /// </summary>
    /// <remarks>
    /// This method provides a convenient way for derived classes to persist state changes back to the session after processing.
    /// It abstracts away the details of how state is stored in the session, allowing derived classes to focus on their specific logic.
    /// </remarks>
    /// <param name="session">The agent session containing the StateBag.</param>
    /// <param name="state">The state to be saved.</param>
    protected virtual void SaveState(AgentSession? session, TState state)
    {
        if (session is not null)
        {
            session.StateBag.SetValue(this._stateKey, state, this._jsonSerializerOptions);
        }
    }
}
