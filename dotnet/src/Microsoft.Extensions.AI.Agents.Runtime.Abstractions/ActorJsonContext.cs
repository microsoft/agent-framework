// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Source-generated JSON type information for use by all Actor abstractions.
/// </summary>
[JsonSourceGenerationOptions(
    JsonSerializerDefaults.Web,
    UseStringEnumConverter = true,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    WriteIndented = false)]
[JsonSerializable(typeof(ActorMessage))]
[JsonSerializable(typeof(ActorRequestMessage))]
[JsonSerializable(typeof(ActorResponseMessage))]
[JsonSerializable(typeof(ActorWriteOperation))]
[JsonSerializable(typeof(SetValueOperation))]
[JsonSerializable(typeof(RemoveKeyOperation))]
[JsonSerializable(typeof(SendRequestOperation))]
[JsonSerializable(typeof(UpdateRequestOperation))]
[JsonSerializable(typeof(ActorReadOperation))]
[JsonSerializable(typeof(ListKeysOperation))]
[JsonSerializable(typeof(GetValueOperation))]
[JsonSerializable(typeof(ActorReadResult))]
[JsonSerializable(typeof(ListKeysResult))]
[JsonSerializable(typeof(GetValueResult))]
[JsonSerializable(typeof(ActorRequest))]
[JsonSerializable(typeof(ActorRequestUpdate))]
[JsonSerializable(typeof(ActorResponse))]
[JsonSerializable(typeof(ActorId))]
[JsonSerializable(typeof(RequestStatus))]
[JsonSerializable(typeof(ActorWriteOperationBatch))]
[JsonSerializable(typeof(ActorReadOperationBatch))]
[JsonSerializable(typeof(ReadResponse))]
[JsonSerializable(typeof(WriteResponse))]
[JsonSerializable(typeof(ActorType))]
[JsonSerializable(typeof(JsonElement))]
internal sealed partial class ActorJsonContext : JsonSerializerContext;
