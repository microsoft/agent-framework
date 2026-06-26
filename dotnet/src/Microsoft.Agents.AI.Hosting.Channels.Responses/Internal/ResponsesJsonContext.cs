// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.Channels.Responses;

[JsonSourceGenerationOptions(DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull)]
[JsonSerializable(typeof(ResponsesRequestModel))]
[JsonSerializable(typeof(ResponsesResponseModel))]
[JsonSerializable(typeof(ResponsesStreamResponseEvent))]
[JsonSerializable(typeof(ResponsesStreamOutputItemEvent))]
[JsonSerializable(typeof(ResponsesStreamContentPartEvent))]
[JsonSerializable(typeof(ResponsesStreamTextDeltaEvent))]
[JsonSerializable(typeof(ResponsesStreamTextDoneEvent))]
[JsonSerializable(typeof(ResponsesStreamReasoningTextDeltaEvent))]
[JsonSerializable(typeof(ResponsesStreamReasoningTextDoneEvent))]
[JsonSerializable(typeof(ResponsesStreamFunctionCallArgumentsDeltaEvent))]
[JsonSerializable(typeof(ResponsesStreamFunctionCallArgumentsDoneEvent))]
[JsonSerializable(typeof(ResponsesErrorModel))]
[JsonSerializable(typeof(System.Text.Json.JsonElement))]
[JsonSerializable(typeof(System.Text.Json.Nodes.JsonNode))]
internal sealed partial class ResponsesJsonContext : JsonSerializerContext;
