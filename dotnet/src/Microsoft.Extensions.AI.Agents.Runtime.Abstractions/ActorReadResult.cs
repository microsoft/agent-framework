// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Base class for all actor read operation results.
/// </summary>
/// <remarks>
/// This abstract class serves as the foundation for all actor read operation result types.
/// Each concrete implementation represents a specific type of read operation result,
/// such as listing keys or retrieving values from an actor's state.
/// </remarks>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "type")]
[JsonDerivedType(typeof(ListKeysResult), "list_keys")]
[JsonDerivedType(typeof(GetValueOperation), "get_value")]
public abstract class ActorReadResult
{
    /// <summary>Prevent external derivations.</summary>
    private protected ActorReadResult()
    {
    }

    /// <summary>
    /// Gets the type of the read result operation.
    /// </summary>
    [JsonIgnore]
    public abstract ActorReadResultType Type { get; }
}
