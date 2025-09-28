// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Runtime;

/// <summary>
/// Base class for all actor write operations that can modify actor state or messaging.
/// </summary>
/// <remarks>
/// This abstract class serves as the foundation for all actor write operation types.
/// Each concrete implementation represents a specific type of write operation,
/// such as modifying actor state or sending messages.
/// </remarks>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "type")]
[JsonDerivedType(typeof(SetValueOperation), "set_value")]
[JsonDerivedType(typeof(RemoveKeyOperation), "remove_key")]
[JsonDerivedType(typeof(UpdateRequestOperation), "update_request")]
[JsonDerivedType(typeof(SendRequestOperation), "send_request")]
public abstract class ActorWriteOperation
{
    /// <summary>Prevent external derivations.</summary>
    private protected ActorWriteOperation()
    {
    }

    /// <summary>
    /// Gets the type of the write operation.
    /// </summary>
    [JsonIgnore]
    public abstract ActorWriteOperationType Type { get; }
}
