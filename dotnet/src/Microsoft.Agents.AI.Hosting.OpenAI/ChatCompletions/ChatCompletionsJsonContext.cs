// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions;

[JsonSourceGenerationOptions(JsonSerializerDefaults.Web,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        NumberHandling = JsonNumberHandling.AllowReadingFromString,
        AllowOutOfOrderMetadataProperties = true,
        WriteIndented = false)]
[JsonSerializable(typeof(Dictionary<string, string>))]
[JsonSerializable(typeof(CreateChatCompletion))]
[JsonSerializable(typeof(StopSequences))]
[JsonSerializable(typeof(ChatCompletion))]
[JsonSerializable(typeof(ChatCompletionRequestMessage))]
[JsonSerializable(typeof(IList<ChatCompletionRequestMessage>))]
[JsonSerializable(typeof(MessageContent))]
[JsonSerializable(typeof(MessageContentPart))]
[JsonSerializable(typeof(IReadOnlyList<MessageContentPart>))]
[JsonSerializable(typeof(TextContentPart))]
[JsonSerializable(typeof(ImageContentPart))]
[JsonSerializable(typeof(AudioContentPart))]
[JsonSerializable(typeof(FileContentPart))]
[JsonSerializable(typeof(ChatCompletionChoice))]
[JsonSerializable(typeof(IList<ChatCompletionChoice>))]
[JsonSerializable(typeof(ChoiceMessage))]
[JsonSerializable(typeof(ChoiceMessageAnnotation))]
[JsonSerializable(typeof(ChoiceMessageAudio))]
[JsonSerializable(typeof(ChoiceMessageFunctionCall))]
[JsonSerializable(typeof(ChoiceMessageToolCall))]
[JsonSerializable(typeof(AnnotationUrlCitation))]
[JsonSerializable(typeof(ChatCompletionChoiceChunk))]
[JsonSerializable(typeof(IList<ChatCompletionChoiceChunk>))]
[JsonSerializable(typeof(ChatCompletionChunk))]
[JsonSerializable(typeof(ChatCompletionDelta))]
[JsonSerializable(typeof(ToolChoice))]
[JsonSerializable(typeof(AllowedToolsChoice))]
[JsonSerializable(typeof(AllowedToolsConfiguration))]
[JsonSerializable(typeof(ToolDefinition))]
[JsonSerializable(typeof(IList<ToolDefinition>))]
[JsonSerializable(typeof(FunctionReference))]
[JsonSerializable(typeof(FunctionToolChoice))]
[JsonSerializable(typeof(CustomToolChoice))]
[JsonSerializable(typeof(CustomToolObject))]
[JsonSerializable(typeof(ResponseFormat))]
[JsonSerializable(typeof(TextResponseFormat))]
[JsonSerializable(typeof(JsonSchemaResponseFormat))]
[JsonSerializable(typeof(JsonSchemaConfiguration))]
[JsonSerializable(typeof(JsonObjectResponseFormat))]
[JsonSerializable(typeof(Tool))]
[JsonSerializable(typeof(IList<Tool>))]
[JsonSerializable(typeof(FunctionTool))]
[JsonSerializable(typeof(FunctionDefinition))]
[JsonSerializable(typeof(CustomTool))]
[JsonSerializable(typeof(CustomToolProperties))]
[JsonSerializable(typeof(CustomToolFormat))]
[ExcludeFromCodeCoverage]
internal sealed partial class ChatCompletionsJsonContext : JsonSerializerContext;
