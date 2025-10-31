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

[JsonSourceGenerationOptions(WriteIndented = false, DefaultIgnoreCondition = JsonIgnoreCondition.Never)]
[JsonSerializable(typeof(RunAgentInput))]
[JsonSerializable(typeof(AGUITool))]
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
[JsonSerializable(typeof(IDictionary<string, object?>))]
[JsonSerializable(typeof(Dictionary<string, object?>))]
[JsonSerializable(typeof(System.Text.Json.JsonElement))]
[JsonSerializable(typeof(Dictionary<string, System.Text.Json.JsonElement>))]
[JsonSerializable(typeof(string))]
[JsonSerializable(typeof(int))]
[JsonSerializable(typeof(long))]
[JsonSerializable(typeof(double))]
[JsonSerializable(typeof(float))]
[JsonSerializable(typeof(bool))]
[JsonSerializable(typeof(decimal))]
#if !ASPNETCORE
[JsonSerializable(typeof(AGUIAgentThread.AGUIAgentThreadState))]
#endif
internal partial class AGUIJsonSerializerContext : JsonSerializerContext
{
}
