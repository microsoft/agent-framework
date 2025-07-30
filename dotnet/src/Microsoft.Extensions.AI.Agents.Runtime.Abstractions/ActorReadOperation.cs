// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Base class for all actor read operations that can query actor state or messaging.
/// </summary>
/// <remarks>
/// This abstract class serves as the foundation for all actor read operation types.
/// Each concrete implementation represents a specific type of read operation,
/// such as querying actor state or messaging information.
/// </remarks>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "type")]
[JsonDerivedType(typeof(ListKeysOperation), "list_keys")]
[JsonDerivedType(typeof(GetValueOperation), "get_value")]
public abstract class ActorReadOperation
{
    /// <summary>Prevent external derivations.</summary>
    private protected ActorReadOperation()
    {
    }

    /// <summary>
    /// Gets the type of the read operation.
    /// </summary>
    [JsonIgnore]
    public abstract ActorReadOperationType Type { get; }
}
