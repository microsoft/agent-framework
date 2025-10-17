// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

[JsonSourceGenerationOptions(JsonSerializerDefaults.Web,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        NumberHandling = JsonNumberHandling.AllowReadingFromString,
        WriteIndented = false)]
[JsonSerializable(typeof(Dictionary<string, string>))]
[JsonSerializable(typeof(CreateResponse))]
[JsonSerializable(typeof(Response))]
[JsonSerializable(typeof(StreamingResponseEvent))]
[JsonSerializable(typeof(StreamingResponseCreated))]
[JsonSerializable(typeof(StreamingResponseInProgress))]
[JsonSerializable(typeof(StreamingResponseCompleted))]
[JsonSerializable(typeof(StreamingResponseIncomplete))]
[JsonSerializable(typeof(StreamingResponseFailed))]
[JsonSerializable(typeof(StreamingOutputItemAdded))]
[JsonSerializable(typeof(StreamingOutputItemDone))]
[JsonSerializable(typeof(StreamingContentPartAdded))]
[JsonSerializable(typeof(StreamingContentPartDone))]
[JsonSerializable(typeof(StreamingOutputTextDelta))]
[JsonSerializable(typeof(StreamingOutputTextDone))]
[JsonSerializable(typeof(ListResponseItemsResponse))]
[JsonSerializable(typeof(ReasoningOptions))]
[JsonSerializable(typeof(ResponseUsage))]
[JsonSerializable(typeof(ResponseError))]
[JsonSerializable(typeof(IncompleteDetails))]
[JsonSerializable(typeof(InputTokensDetails))]
[JsonSerializable(typeof(OutputTokensDetails))]
[JsonSerializable(typeof(ConversationReference))]
[JsonSerializable(typeof(ResponseInput))]
[JsonSerializable(typeof(InputMessage))]
[JsonSerializable(typeof(List<InputMessage>))]
[JsonSerializable(typeof(IReadOnlyList<InputMessage>))]
[JsonSerializable(typeof(InputMessageContent))]
[JsonSerializable(typeof(ResponseStatus))]
[JsonSerializable(typeof(List<ItemContent>))]
[ExcludeFromCodeCoverage]
internal sealed partial class ResponsesJsonContext : JsonSerializerContext;
