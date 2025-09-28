// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Runtime;

/// <summary>
/// Base class for write operations that modify an actor's messaging (inbox/outbox).
/// </summary>
public abstract class ActorMessageWriteOperation : ActorWriteOperation
{
    /// <summary>Prevent external derivations.</summary>
    private protected ActorMessageWriteOperation()
    {
    }
}
