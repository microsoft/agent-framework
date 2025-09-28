// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Runtime;

/// <summary>
/// Builder interface for configuring actor types in the runtime.
/// </summary>
public interface IActorRuntimeBuilder
{
    /// <summary>
    /// Registers an actor type with its factory method.
    /// </summary>
    /// <param name="type">The actor type to register.</param>
    /// <param name="activator">The factory method to create instances of the actor.</param>
    void AddActorType(ActorType type, Func<IServiceProvider, IActorRuntimeContext, IActor> activator);
}
