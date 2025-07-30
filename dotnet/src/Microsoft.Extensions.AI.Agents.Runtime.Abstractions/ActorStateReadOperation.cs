// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Base class for read operations that query an actor's internal state.
/// </summary>
public abstract class ActorStateReadOperation : ActorReadOperation
{
    /// <summary>Prevent external derivations.</summary>
    private protected ActorStateReadOperation()
    {
    }
}
