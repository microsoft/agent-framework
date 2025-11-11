// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

#if ASPNETCORE
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
#else
using Microsoft.Agents.AI.AGUI.Shared;

namespace Microsoft.Agents.AI.AGUI;
#endif

// All JsonSerializable attributes below are required for AG-UI functionality:
// - AG-UI message types (AGUIMessage, AGUIUserMessage, etc.) for protocol communication
// - Event types (BaseEvent, RunStartedEvent, etc.) for server-sent events streaming
// - Tool-related types (AGUITool, AGUIToolCall, AGUIFunctionCall) for tool calling support
// - Primitive and dictionary types (string, int, Dictionary, JsonElement) are required for
//   serializing tool call parameters and results which can contain arbitrary data types
[JsonSourceGenerationOptions(WriteIndented = false, DefaultIgnoreCondition = JsonIgnoreCondition.Never)]
[JsonSerializable(typeof(RunAgentInput))]
[JsonSerializable(typeof(AGUIMessage))]
[JsonSerializable(typeof(AGUIMessage[]))]
[JsonSerializable(typeof(AGUIDeveloperMessage))]
[JsonSerializable(typeof(AGUISystemMessage))]
[JsonSerializable(typeof(AGUIUserMessage))]
[JsonSerializable(typeof(AGUIAssistantMessage))]
[JsonSerializable(typeof(AGUIToolMessage))]
[JsonSerializable(typeof(AGUITool))]
[JsonSerializable(typeof(AGUIToolCall))]
[JsonSerializable(typeof(AGUIToolCall[]))]
[JsonSerializable(typeof(AGUIFunctionCall))]
[JsonSerializable(typeof(BaseEvent))]
[JsonSerializable(typeof(BaseEvent[]))]
[JsonSerializable(typeof(RunStartedEvent))]
[JsonSerializable(typeof(RunFinishedEvent))]
[JsonSerializable(typeof(RunErrorEvent))]
[JsonSerializable(typeof(TextMessageStartEvent))]
[JsonSerializable(typeof(TextMessageContentEvent))]
[JsonSerializable(typeof(TextMessageEndEvent))]
[JsonSerializable(typeof(ToolCallStartEvent))]
[JsonSerializable(typeof(ToolCallArgsEvent))]
[JsonSerializable(typeof(ToolCallEndEvent))]
[JsonSerializable(typeof(ToolCallResultEvent))]
[JsonSerializable(typeof(StateSnapshotEvent))]
[JsonSerializable(typeof(StateDeltaEvent))]
[JsonSerializable(typeof(IDictionary<string, object?>))]
[JsonSerializable(typeof(Dictionary<string, object?>))]
[JsonSerializable(typeof(IDictionary<string, System.Text.Json.JsonElement?>))]
[JsonSerializable(typeof(Dictionary<string, System.Text.Json.JsonElement?>))]
[JsonSerializable(typeof(System.Text.Json.JsonElement))]
[JsonSerializable(typeof(Dictionary<string, System.Text.Json.JsonElement>))]
[JsonSerializable(typeof(string))]
[JsonSerializable(typeof(int))]
[JsonSerializable(typeof(long))]
[JsonSerializable(typeof(double))]
[JsonSerializable(typeof(float))]
[JsonSerializable(typeof(bool))]
[JsonSerializable(typeof(decimal))]
internal sealed partial class AGUIJsonSerializerContext : JsonSerializerContext
{
}
