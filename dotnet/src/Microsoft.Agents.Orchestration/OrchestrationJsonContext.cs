// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.Orchestration;

[JsonSerializable(typeof(SequentialOrchestration.SequentialState))]
[JsonSerializable(typeof(ConcurrentOrchestration.ConcurrentState))]
[JsonSerializable(typeof(GroupChatOrchestration.GroupChatState))]
[JsonSerializable(typeof(HandoffOrchestration.HandoffState))]
internal sealed partial class OrchestrationJsonContext : JsonSerializerContext;
