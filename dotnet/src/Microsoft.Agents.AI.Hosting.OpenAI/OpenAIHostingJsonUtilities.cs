// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI;

/// <summary>
/// Provides JSON serialization options and context for OpenAI Hosting APIs to support AOT and trimming.
/// </summary>
internal static class OpenAIHostingJsonUtilities
{
    /// <summary>
    /// Gets the default <see cref="JsonSerializerOptions"/> instance used for OpenAI API serialization.
    /// Includes support for AIContent types and all OpenAI-related types.
    /// </summary>
    public static JsonSerializerOptions DefaultOptions { get; } = CreateDefaultOptions();

    private static JsonSerializerOptions CreateDefaultOptions()
    {
        JsonSerializerOptions options = new(OpenAIHostingJsonContext.Default.Options);

        // Chain in the resolvers from both AgentAbstractionsJsonUtilities and our source generated context.
        // We want AgentAbstractionsJsonUtilities first to ensure any M.E.AI types are handled via its resolver.
        options.TypeInfoResolverChain.Clear();
        options.TypeInfoResolverChain.Add(AgentAbstractionsJsonUtilities.DefaultOptions.TypeInfoResolver!);
        options.TypeInfoResolverChain.Add(OpenAIHostingJsonContext.Default.Options.TypeInfoResolver!);

        options.MakeReadOnly();
        return options;
    }
}

/// <summary>
/// Provides a unified JSON serialization context for all OpenAI Hosting APIs to support AOT and trimming.
/// Combines Conversations and Responses API types.
/// </summary>
[JsonSourceGenerationOptions(JsonSerializerDefaults.Web,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    NumberHandling = JsonNumberHandling.AllowReadingFromString,
    AllowOutOfOrderMetadataProperties = true,
    WriteIndented = false)]
// Conversations API types
[JsonSerializable(typeof(Conversation))]
[JsonSerializable(typeof(ListResponse<Conversation>))]
[JsonSerializable(typeof(CreateConversationRequest))]
[JsonSerializable(typeof(CreateItemsRequest))]
[JsonSerializable(typeof(UpdateConversationRequest))]
[JsonSerializable(typeof(ListResponse<ItemResource>))]
[JsonSerializable(typeof(List<Conversation>))]
// Shared types
[JsonSerializable(typeof(DeleteResponse))]
[JsonSerializable(typeof(ErrorResponse))]
[JsonSerializable(typeof(ErrorDetails))]
// Responses API types
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
[JsonSerializable(typeof(StreamingFunctionCallArgumentsDelta))]
[JsonSerializable(typeof(StreamingFunctionCallArgumentsDone))]
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
[JsonSerializable(typeof(InputMessageContent))]
[JsonSerializable(typeof(ResponseStatus))]
// ItemResource types
[JsonSerializable(typeof(ItemResource))]
[JsonSerializable(typeof(ResponsesMessageItemResource))]
[JsonSerializable(typeof(ResponsesAssistantMessageItemResource))]
[JsonSerializable(typeof(ResponsesUserMessageItemResource))]
[JsonSerializable(typeof(ResponsesSystemMessageItemResource))]
[JsonSerializable(typeof(ResponsesDeveloperMessageItemResource))]
[JsonSerializable(typeof(FileSearchToolCallItemResource))]
[JsonSerializable(typeof(FunctionToolCallItemResource))]
[JsonSerializable(typeof(FunctionToolCallOutputItemResource))]
[JsonSerializable(typeof(ComputerToolCallItemResource))]
[JsonSerializable(typeof(ComputerToolCallOutputItemResource))]
[JsonSerializable(typeof(WebSearchToolCallItemResource))]
[JsonSerializable(typeof(ReasoningItemResource))]
[JsonSerializable(typeof(ItemReferenceItemResource))]
[JsonSerializable(typeof(ImageGenerationToolCallItemResource))]
[JsonSerializable(typeof(CodeInterpreterToolCallItemResource))]
[JsonSerializable(typeof(LocalShellToolCallItemResource))]
[JsonSerializable(typeof(LocalShellToolCallOutputItemResource))]
[JsonSerializable(typeof(MCPListToolsItemResource))]
[JsonSerializable(typeof(MCPApprovalRequestItemResource))]
[JsonSerializable(typeof(MCPApprovalResponseItemResource))]
[JsonSerializable(typeof(MCPCallItemResource))]
[JsonSerializable(typeof(ExecutorActionItemResource))]
[JsonSerializable(typeof(List<ItemResource>))]
// ItemParam types
[JsonSerializable(typeof(ItemParam))]
[JsonSerializable(typeof(ResponsesMessageItemParam))]
[JsonSerializable(typeof(ResponsesUserMessageItemParam))]
[JsonSerializable(typeof(ResponsesAssistantMessageItemParam))]
[JsonSerializable(typeof(ResponsesSystemMessageItemParam))]
[JsonSerializable(typeof(ResponsesDeveloperMessageItemParam))]
[JsonSerializable(typeof(FunctionToolCallItemParam))]
[JsonSerializable(typeof(FunctionToolCallOutputItemParam))]
[JsonSerializable(typeof(FileSearchToolCallItemParam))]
[JsonSerializable(typeof(ComputerToolCallItemParam))]
[JsonSerializable(typeof(ComputerToolCallOutputItemParam))]
[JsonSerializable(typeof(WebSearchToolCallItemParam))]
[JsonSerializable(typeof(ReasoningItemParam))]
[JsonSerializable(typeof(ItemReferenceItemParam))]
[JsonSerializable(typeof(ImageGenerationToolCallItemParam))]
[JsonSerializable(typeof(CodeInterpreterToolCallItemParam))]
[JsonSerializable(typeof(LocalShellToolCallItemParam))]
[JsonSerializable(typeof(LocalShellToolCallOutputItemParam))]
[JsonSerializable(typeof(MCPListToolsItemParam))]
[JsonSerializable(typeof(MCPApprovalRequestItemParam))]
[JsonSerializable(typeof(MCPApprovalResponseItemParam))]
[JsonSerializable(typeof(MCPCallItemParam))]
[JsonSerializable(typeof(List<ItemParam>))]
// ItemContent types
[JsonSerializable(typeof(List<ItemContent>))]
[JsonSerializable(typeof(IReadOnlyList<ItemContent>))]
[JsonSerializable(typeof(ItemContent[]))]
[JsonSerializable(typeof(ItemContent))]
[JsonSerializable(typeof(ItemContentInputText))]
[JsonSerializable(typeof(ItemContentInputAudio))]
[JsonSerializable(typeof(ItemContentInputImage))]
[JsonSerializable(typeof(ItemContentInputFile))]
[JsonSerializable(typeof(ItemContentOutputText))]
[JsonSerializable(typeof(ItemContentOutputAudio))]
[JsonSerializable(typeof(ItemContentRefusal))]
[JsonSerializable(typeof(TextConfiguration))]
[JsonSerializable(typeof(ResponseTextFormatConfiguration))]
[JsonSerializable(typeof(ResponseTextFormatConfigurationText))]
[JsonSerializable(typeof(ResponseTextFormatConfigurationJsonObject))]
[JsonSerializable(typeof(ResponseTextFormatConfigurationJsonSchema))]
// Common types
[JsonSerializable(typeof(Dictionary<string, string>))]
[ExcludeFromCodeCoverage]
internal sealed partial class OpenAIHostingJsonContext : JsonSerializerContext;
