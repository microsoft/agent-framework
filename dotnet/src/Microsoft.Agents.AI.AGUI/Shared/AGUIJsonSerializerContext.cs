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

// TODO: See if we can get rid of all the JsonSerializable attributes for types that are not
// related to AG-UI
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
internal partial class AGUIJsonSerializerContext : JsonSerializerContext
{
}
