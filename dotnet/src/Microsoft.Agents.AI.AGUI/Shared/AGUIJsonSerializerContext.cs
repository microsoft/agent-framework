// Copyright (c) Microsoft. All rights reserved.

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
[JsonSerializable(typeof(BaseEvent))]
[JsonSerializable(typeof(RunStartedEvent))]
[JsonSerializable(typeof(RunFinishedEvent))]
[JsonSerializable(typeof(RunErrorEvent))]
[JsonSerializable(typeof(TextMessageStartEvent))]
[JsonSerializable(typeof(TextMessageContentEvent))]
[JsonSerializable(typeof(TextMessageEndEvent))]
#if !ASPNETCORE
[JsonSerializable(typeof(AGUIAgentThread.AGUIAgentThreadState))]
#endif
internal partial class AGUIJsonSerializerContext : JsonSerializerContext
{
}
