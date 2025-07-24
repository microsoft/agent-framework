// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Source-generated JSON type information for use by all agent runtime abstractions.
/// </summary>
[JsonSourceGenerationOptions(
    JsonSerializerDefaults.Web,
    UseStringEnumConverter = true,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    WriteIndented = false)]
[JsonSerializable(typeof(ActorId))]
[JsonSerializable(typeof(ActorMessage))]
[JsonSerializable(typeof(ActorReadOperation))]
[JsonSerializable(typeof(ActorReadOperationBatch))]
[JsonSerializable(typeof(ActorReadResult))]
[JsonSerializable(typeof(ActorRequest))]
[JsonSerializable(typeof(ActorRequestMessage))]
[JsonSerializable(typeof(ActorRequestUpdate))]
[JsonSerializable(typeof(ActorResponse))]
[JsonSerializable(typeof(ActorResponseMessage))]
[JsonSerializable(typeof(ActorType))]
[JsonSerializable(typeof(ActorWriteOperation))]
[JsonSerializable(typeof(ActorWriteOperationBatch))]
[JsonSerializable(typeof(GetValueOperation))]
[JsonSerializable(typeof(GetValueResult))]
[JsonSerializable(typeof(JsonElement))]
[JsonSerializable(typeof(ListKeysOperation))]
[JsonSerializable(typeof(ListKeysResult))]
[JsonSerializable(typeof(ReadResponse))]
[JsonSerializable(typeof(RemoveKeyOperation))]
[JsonSerializable(typeof(RequestStatus))]
[JsonSerializable(typeof(SendRequestOperation))]
[JsonSerializable(typeof(SetValueOperation))]
[JsonSerializable(typeof(UpdateRequestOperation))]
[JsonSerializable(typeof(WriteResponse))]
internal sealed partial class ActorJsonContext : JsonSerializerContext;
