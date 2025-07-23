// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Base class for all actor messages that can be sent between actors.
/// </summary>
/// <remarks>
/// This abstract class serves as the foundation for all actor message types.
/// Each concrete implementation represents a specific type of message,
/// such as request messages or response messages.
/// </remarks>
//[JsonConverter(typeof(Converter))]
[JsonPolymorphic(TypeDiscriminatorPropertyName = "type")]
[JsonDerivedType(typeof(ActorRequestMessage), "request")]
[JsonDerivedType(typeof(ActorResponseMessage), "response")]
public abstract class ActorMessage
{
    /// <summary>Prevent external derivations.</summary>
    private protected ActorMessage()
    {
    }

    /// <summary>
    /// Gets the type of the message.
    /// </summary>
    [JsonIgnore]
    public abstract ActorMessageType Type { get; }

    /// <summary>
    /// Additional properties that can be used to extend the message with custom data.
    /// </summary>
    [JsonExtensionData]
    public Dictionary<string, JsonElement>? ExtensionData { get; set; }
}
