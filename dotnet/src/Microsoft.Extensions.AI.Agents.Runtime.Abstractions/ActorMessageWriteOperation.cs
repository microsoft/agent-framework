// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents.Runtime;

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
