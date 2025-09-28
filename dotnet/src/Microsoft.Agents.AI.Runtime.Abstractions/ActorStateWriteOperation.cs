// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Runtime;

/// <summary>
/// Base class for write operations that modify an actor's internal state.
/// </summary>
/// <remarks>
/// This abstract class serves as the foundation for all actor state write operation types.
/// Each concrete implementation represents a specific type of state modification operation,
/// such as setting or removing key-value pairs in an actor's state.
/// </remarks>
public abstract class ActorStateWriteOperation : ActorWriteOperation
{
    /// <summary>Prevent external derivations.</summary>
    private protected ActorStateWriteOperation()
    {
    }
}
