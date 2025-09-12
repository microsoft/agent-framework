#pragma warning disable IDE0073 // The file header does not match the required text
#pragma warning disable CA1063 // Implement IDisposable Correctly

// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

using System.ClientModel.Primitives;
using System.Diagnostics.CodeAnalysis;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using Microsoft.Shared.Diagnostics;
using OpenAI.Responses;

#pragma warning disable S907 // "goto" statement should not be used
#pragma warning disable S1067 // Expressions should not be too complex
#pragma warning disable S3011 // Reflection should not be used to increase accessibility of classes, methods, or fields
#pragma warning disable S3604 // Member initializer values should not be redundant
#pragma warning disable SA1202 // Elements should be ordered by access
#pragma warning disable SA1204 // Static elements should appear before instance elements
#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

namespace Microsoft.Extensions.AI;

/// <summary>Represents an <see cref="IChatClient"/> for an <see cref="OpenAIResponseClient"/>.</summary>
[ExcludeFromCodeCoverage]
internal sealed class NewOpenAIResponsesChatClient : ICancelableChatClient
{
    // Fix this to not use reflection once https://github.com/openai/openai-dotnet/issues/643 is addressed.
    [DynamicallyAccessedMembers(DynamicallyAccessedMemberTypes.PublicProperties)]
    private static readonly Type? s_internalResponseReasoningSummaryTextDeltaEventType = Type.GetType("OpenAI.Responses.InternalResponseReasoningSummaryTextDeltaEvent, OpenAI");
    private static readonly PropertyInfo? s_summaryTextDeltaProperty = s_internalResponseReasoningSummaryTextDeltaEventType?.GetProperty("Delta");

    /// <summary>Metadata about the client.</summary>
    private readonly ChatClientMetadata _metadata;

    /// <summary>The underlying <see cref="OpenAIResponseClient" />.</summary>
    private readonly OpenAIResponseClient _responseClient;

    /// <summary>Enables long-running responses mode for the chat client, if set to <see langword="true"/>.</summary>
    private readonly bool? _enableLongRunningOperations;

    /// <summary>Initializes a new instance of the <see cref="OpenAIResponsesChatClient"/> class for the specified <see cref="OpenAIResponseClient"/>.</summary>
    /// <param name="responseClient">The underlying client.</param>
    /// <param name="enableLongRunningOperations">Enables long-running responses mode for the chat client, if set to <see langword="true"/>.</param>
    /// <exception cref="ArgumentNullException"><paramref name="responseClient"/> is <see langword="null"/>.</exception>
    public NewOpenAIResponsesChatClient(OpenAIResponseClient responseClient, bool? enableLongRunningOperations = null)
    {
        _ = Throw.IfNull(responseClient);

        _responseClient = responseClient;

        _enableLongRunningOperations = enableLongRunningOperations;

        // https://github.com/openai/openai-dotnet/issues/662
        // Update to avoid reflection once OpenAIResponseClient.Model is exposed publicly.
        string? model = typeof(OpenAIResponseClient).GetField("_model", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)
            ?.GetValue(responseClient) as string;

        _metadata = new("openai", responseClient.Endpoint, model);
    }

    /// <inheritdoc />
    object? IChatClient.GetService(Type serviceType, object? serviceKey)
    {
        _ = Throw.IfNull(serviceType);

        return
            serviceKey is not null ? null :
            serviceType == typeof(ChatClientMetadata) ? _metadata :
            serviceType == typeof(OpenAIResponseClient) ? _responseClient :
            serviceType.IsInstanceOfType(this) ? this :
            null;
    }

    /// <inheritdoc />
    public async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        // Convert the inputs into what OpenAIResponseClient expects.
        var openAIResponseItems = ToOpenAIResponseItems(messages, options);
        var openAIOptions = ToOpenAIResponseCreationOptions(options);

        OpenAIResponse openAIResponse;

        // The response id, provided by a caller, indicates that the caller is interested in the status/result of this response
        // rather than in creating a new one. However, for scenarios where functions are involved, we can't just fetch the response
        // status/result because the method for doing so does not accept messages and therefore can't accept function
        // call results to send to the model. As such, if a function result content is found in the messages, we always create
        // a new response instead of fetching the one specified by the id.
        if (options is NewChatOptions { ResponseId: { } responseId } && !messages.Any(m => m.Contents.OfType<FunctionResultContent>().Any()))
        {
            // If response id is provided, and no functions are involved, get the response by id.
            openAIResponse = (await _responseClient.GetResponseAsync(responseId, cancellationToken).ConfigureAwait(false)).Value;
        }
        else
        {
            // Otherwise, create a new response.
            openAIResponse = (await _responseClient.CreateResponseAsync(openAIResponseItems, openAIOptions, cancellationToken).ConfigureAwait(false)).Value;
        }

        // Convert the response to a ChatResponse.
        return FromOpenAIResponse(openAIResponse, openAIOptions);
    }

    /// <inheritdoc />
    public async Task<ChatResponse?> CancelResponseAsync(string id, CancelResponseOptions? options = null, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrEmpty(id))
        {
            throw new ArgumentException("Id cannot be null or empty.", nameof(id));
        }

        var openAIResponse = await _responseClient.CancelResponseAsync(id, cancellationToken).ConfigureAwait(false);

        // Setting Background to true here only to get the `Status` property set in the response.
        return FromOpenAIResponse(openAIResponse, openAIOptions: new ResponseCreationOptions { BackgroundModeEnabled = true });
    }

    internal ChatResponse FromOpenAIResponse(OpenAIResponse openAIResponse, ResponseCreationOptions openAIOptions)
    {
        // Convert and return the results.
        NewChatResponse response = new()
        {
            ConversationId = openAIOptions.StoredOutputEnabled is false ? null : openAIResponse.Id,
            CreatedAt = openAIResponse.CreatedAt,
            FinishReason = ToFinishReason(openAIResponse.IncompleteStatusDetails?.Reason),
            ModelId = openAIResponse.Model,
            RawRepresentation = openAIResponse,
            ResponseId = openAIResponse.Id,
            Usage = ToUsageDetails(openAIResponse),
        };

        if (!string.IsNullOrEmpty(openAIResponse.EndUserId))
        {
            (response.AdditionalProperties ??= [])[nameof(openAIResponse.EndUserId)] = openAIResponse.EndUserId;
        }

        if (openAIResponse.Error is not null)
        {
            (response.AdditionalProperties ??= [])[nameof(openAIResponse.Error)] = openAIResponse.Error;
        }

        if (openAIResponse.OutputItems is not null)
        {
            response.Messages = [.. ToChatMessages(openAIResponse.OutputItems)];

            if (response.Messages.LastOrDefault() is { } lastMessage && openAIResponse.Error is { } error)
            {
                lastMessage.Contents.Add(new ErrorContent(error.Message) { ErrorCode = error.Code.ToString() });
            }

            foreach (var message in response.Messages)
            {
                message.CreatedAt ??= openAIResponse.CreatedAt;
            }
        }

        response.Status = ToResponseStatus(openAIResponse.Status, openAIOptions);

        return response;
    }

    internal static IEnumerable<ChatMessage> ToChatMessages(IEnumerable<ResponseItem> items)
    {
        ChatMessage? message = null;

        foreach (ResponseItem outputItem in items)
        {
            message ??= new(ChatRole.Assistant, (string?)null);

            switch (outputItem)
            {
                case MessageResponseItem messageItem:
                    if (message.MessageId is not null && message.MessageId != messageItem.Id)
                    {
                        yield return message;
                        message = new ChatMessage();
                    }

                    message.MessageId = messageItem.Id;
                    message.RawRepresentation = messageItem;
                    message.Role = ToChatRole(messageItem.Role);
                    ((List<AIContent>)message.Contents).AddRange(ToAIContents(messageItem.Content));
                    break;

                case ReasoningResponseItem reasoningItem when reasoningItem.GetSummaryText() is string summary:
                    message.Contents.Add(new TextReasoningContent(summary) { RawRepresentation = outputItem });
                    break;

                case FunctionCallResponseItem functionCall:
                    var fcc = OpenAIClientExtensions3.ParseCallContent(functionCall.FunctionArguments, functionCall.CallId, functionCall.FunctionName);
                    fcc.RawRepresentation = outputItem;
                    message.Contents.Add(fcc);
                    break;

                case FunctionCallOutputResponseItem functionCallOutputItem:
                    message.Contents.Add(new FunctionResultContent(functionCallOutputItem.CallId, functionCallOutputItem.FunctionOutput) { RawRepresentation = functionCallOutputItem });
                    break;

                default:
                    message.Contents.Add(new() { RawRepresentation = outputItem });
                    break;
            }
        }

        if (message is not null)
        {
            yield return message;
        }
    }

    /// <inheritdoc />
    public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        var openAIResponseItems = ToOpenAIResponseItems(messages, options);
        var openAIOptions = ToOpenAIResponseCreationOptions(options);

        IAsyncEnumerable<StreamingResponseUpdate> streamingUpdates;

        // The response id, provided by a caller, indicates that the caller is interested in the status/result of this response
        // rather than in creating a new one. However, for scenarios where functions are involved, we can't just fetch the response
        // status/result because the method for doing so does not accept messages and therefore can't accept function
        // call results to send to the model. As such, if a function result content is found in the messages, we always create
        // a new response instead of fetching the one specified by the id.
        if (options is NewChatOptions { ResponseId: { } responseId } && !messages.Any(m => m.Contents.OfType<FunctionResultContent>().Any()))
        {
            var startingAfter = options is NewChatOptions { StartAfter: { } startAfter } ? int.Parse(startAfter) : (int?)null;

            // If response id is provided, and no functions are involved, get the response by id.
            streamingUpdates = _responseClient.GetResponseStreamingAsync(responseId, startingAfter, cancellationToken);
        }
        else
        {
            // Otherwise, create a new response.
            streamingUpdates = _responseClient.CreateResponseStreamingAsync(openAIResponseItems, openAIOptions, cancellationToken);
        }

        return FromOpenAIStreamingResponseUpdatesAsync(streamingUpdates, openAIOptions, cancellationToken);
    }

    internal static async IAsyncEnumerable<ChatResponseUpdate> FromOpenAIStreamingResponseUpdatesAsync(
        IAsyncEnumerable<StreamingResponseUpdate> streamingResponseUpdates, ResponseCreationOptions options, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        DateTimeOffset? createdAt = null;
        string? responseId = null;
        string? conversationId = null;
        string? modelId = null;
        string? lastMessageId = null;
        NewResponseStatus? responseStatus = null;
        ChatRole? lastRole = null;
        bool anyFunctions = false;

        await foreach (var streamingUpdate in streamingResponseUpdates.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            // Create an update populated with the current state of the response.
            NewChatResponseUpdate CreateUpdate(AIContent? content = null) =>
                new(lastRole, content is not null ? [content] : null)
                {
                    ConversationId = conversationId,
                    CreatedAt = createdAt,
                    MessageId = lastMessageId,
                    ModelId = modelId,
                    RawRepresentation = streamingUpdate,
                    ResponseId = responseId,
                    Status = responseStatus,
                    SequenceNumber = streamingUpdate.SequenceNumber.ToString(),
                };

            switch (streamingUpdate)
            {
                case StreamingResponseCreatedUpdate createdUpdate:
                    createdAt = createdUpdate.Response.CreatedAt;
                    responseId = createdUpdate.Response.Id;
                    conversationId = options.StoredOutputEnabled is false ? null : responseId;
                    modelId = createdUpdate.Response.Model;
                    responseStatus = ToResponseStatus(createdUpdate.Response.Status, options);
                    goto default;

                case StreamingResponseInProgressUpdate inProgressUpdate:
                    responseStatus = ToResponseStatus(inProgressUpdate.Response.Status, options);
                    goto default;

                case StreamingResponseIncompleteUpdate incompleteUpdate:
                    responseStatus = ToResponseStatus(incompleteUpdate.Response.Status, options);
                    goto default;

                case StreamingResponseFailedUpdate failedUpdate:
                    responseStatus = ToResponseStatus(failedUpdate.Response.Status, options);
                    goto default;

                case StreamingResponseCompletedUpdate completedUpdate:
                {
                    responseStatus = ToResponseStatus(completedUpdate.Response.Status, options);
                    var update = CreateUpdate(ToUsageDetails(completedUpdate.Response) is { } usage ? new UsageContent(usage) : null);
                    update.FinishReason =
                        ToFinishReason(completedUpdate.Response?.IncompleteStatusDetails?.Reason) ??
                        (anyFunctions ? ChatFinishReason.ToolCalls :
                        ChatFinishReason.Stop);
                    yield return update;
                    break;
                }

                case StreamingResponseOutputItemAddedUpdate outputItemAddedUpdate:
                    switch (outputItemAddedUpdate.Item)
                    {
                        case MessageResponseItem mri:
                            lastMessageId = outputItemAddedUpdate.Item.Id;
                            lastRole = ToChatRole(mri.Role);
                            break;

                        case FunctionCallResponseItem fcri:
                            anyFunctions = true;
                            lastRole = ChatRole.Assistant;
                            break;
                    }

                    goto default;

                case StreamingResponseOutputTextDeltaUpdate outputTextDeltaUpdate:
                    yield return CreateUpdate(new TextContent(outputTextDeltaUpdate.Delta));
                    break;

                case StreamingResponseOutputItemDoneUpdate outputItemDoneUpdate when outputItemDoneUpdate.Item is FunctionCallResponseItem fcri:
                    yield return CreateUpdate(OpenAIClientExtensions3.ParseCallContent(fcri.FunctionArguments.ToString(), fcri.CallId, fcri.FunctionName));
                    break;

                case StreamingResponseOutputItemDoneUpdate outputItemDoneUpdate when outputItemDoneUpdate.Item is McpToolCallItem mtci:
                    var mcpUpdate = CreateUpdate();
                    AddMcpToolCallContent(mtci, mcpUpdate.Contents);
                    yield return mcpUpdate;
                    break;

                case StreamingResponseOutputItemDoneUpdate outputItemDoneUpdate when outputItemDoneUpdate.Item is McpToolDefinitionListItem mtdli:
                    yield return CreateUpdate(new AIContent { RawRepresentation = mtdli });
                    break;

                case StreamingResponseOutputItemDoneUpdate outputItemDoneUpdate when outputItemDoneUpdate.Item is McpToolCallApprovalRequestItem mtcari:
                    yield return CreateUpdate(new McpServerToolApprovalRequestContent(mtcari.Id, new(mtcari.Id, mtcari.ToolName, mtcari.ServerLabel)
                    {
                        Arguments = JsonSerializer.Deserialize(mtcari.ToolArguments.ToMemory().Span, OpenAIJsonContext2.Default.IReadOnlyDictionaryStringObject)!,
                        RawRepresentation = mtcari,
                    })
                    {
                        RawRepresentation = mtcari,
                    });
                    break;

                case StreamingResponseOutputItemDoneUpdate outputItemDoneUpdate when
                        outputItemDoneUpdate.Item is MessageResponseItem mri &&
                        mri.Content is { Count: > 0 } content &&
                        content.Any(c => c.OutputTextAnnotations is { Count: > 0 }):
                    AIContent annotatedContent = new();
                    foreach (var c in content)
                    {
                        PopulateAnnotations(c, annotatedContent);
                    }

                    yield return CreateUpdate(annotatedContent);
                    break;

                case StreamingResponseErrorUpdate errorUpdate:
                    yield return CreateUpdate(new ErrorContent(errorUpdate.Message)
                    {
                        ErrorCode = errorUpdate.Code,
                        Details = errorUpdate.Param,
                    });
                    break;

                case StreamingResponseRefusalDoneUpdate refusalDone:
                    yield return CreateUpdate(new ErrorContent(refusalDone.Refusal)
                    {
                        ErrorCode = nameof(ResponseContentPart.Refusal),
                    });
                    break;

                // Replace with public StreamingResponseReasoningSummaryTextDelta when available
                case StreamingResponseUpdate when
                        streamingUpdate.GetType() == s_internalResponseReasoningSummaryTextDeltaEventType &&
                        s_summaryTextDeltaProperty?.GetValue(streamingUpdate) is string delta:
                    yield return CreateUpdate(new TextReasoningContent(delta));
                    break;

                default:
                    yield return CreateUpdate();
                    break;
            }
        }
    }

    /// <inheritdoc />
    void IDisposable.Dispose()
    {
        // Nothing to dispose. Implementation required for the IChatClient interface.
    }

    internal static FunctionTool ToResponseTool(AIFunctionDeclaration aiFunction, ChatOptions? options = null)
    {
        bool? strict =
            OpenAIClientExtensions3.HasStrict(aiFunction.AdditionalProperties) ??
            OpenAIClientExtensions3.HasStrict(options?.AdditionalProperties);

        return ResponseTool.CreateFunctionTool(
            aiFunction.Name,
            OpenAIClientExtensions3.ToOpenAIFunctionParameters(aiFunction, strict),
            strict,
            aiFunction.Description);
    }

    /// <summary>Creates a <see cref="ChatRole"/> from a <see cref="MessageRole"/>.</summary>
    private static ChatRole ToChatRole(MessageRole? role) =>
        role switch
        {
            MessageRole.System => ChatRole.System,
            MessageRole.Developer => OpenAIClientExtensions3.ChatRoleDeveloper,
            MessageRole.User => ChatRole.User,
            _ => ChatRole.Assistant,
        };

    /// <summary>Creates a <see cref="ChatFinishReason"/> from a <see cref="ResponseIncompleteStatusReason"/>.</summary>
    private static ChatFinishReason? ToFinishReason(ResponseIncompleteStatusReason? statusReason) =>
        statusReason == ResponseIncompleteStatusReason.ContentFilter ? ChatFinishReason.ContentFilter :
        statusReason == ResponseIncompleteStatusReason.MaxOutputTokens ? ChatFinishReason.Length :
        null;

    /// <summary>Converts a <see cref="ChatOptions"/> to a <see cref="ResponseCreationOptions"/>.</summary>
    private ResponseCreationOptions ToOpenAIResponseCreationOptions(ChatOptions? options)
    {
        if (options is null)
        {
            return new ResponseCreationOptions()
            {
                BackgroundModeEnabled = IsLongRunningResponsesModeEnabled(options),
            };
        }

        if (options.RawRepresentationFactory?.Invoke(this) is not ResponseCreationOptions result)
        {
            result = new ResponseCreationOptions();
        }

        // Handle strongly-typed properties.
        result.MaxOutputTokenCount ??= options.MaxOutputTokens;
        result.ParallelToolCallsEnabled ??= options.AllowMultipleToolCalls;
        result.PreviousResponseId ??= options.ConversationId;
        result.Temperature ??= options.Temperature;
        result.TopP ??= options.TopP;

        if (options.Instructions is { } instructions)
        {
            result.Instructions = string.IsNullOrEmpty(result.Instructions) ?
                instructions :
                $"{result.Instructions}{Environment.NewLine}{instructions}";
        }

        result.BackgroundModeEnabled = IsLongRunningResponsesModeEnabled(options);

        // Populate tools if there are any.
        if (options.Tools is { Count: > 0 } tools)
        {
            foreach (AITool tool in tools)
            {
                switch (tool)
                {
                    case AIFunctionDeclaration aiFunction:
                        result.Tools.Add(ToResponseTool(aiFunction, options));
                        break;

                    case HostedWebSearchTool webSearchTool:
                        WebSearchToolLocation? location = null;
                        if (webSearchTool.AdditionalProperties.TryGetValue(nameof(WebSearchToolLocation), out object? objLocation))
                        {
                            location = objLocation as WebSearchToolLocation;
                        }

                        WebSearchToolContextSize? size = null;
                        if (webSearchTool.AdditionalProperties.TryGetValue(nameof(WebSearchToolContextSize), out object? objSize) &&
                            objSize is WebSearchToolContextSize)
                        {
                            size = (WebSearchToolContextSize)objSize;
                        }

                        result.Tools.Add(ResponseTool.CreateWebSearchTool(location, size));
                        break;

                    case HostedFileSearchTool fileSearchTool:
                        result.Tools.Add(ResponseTool.CreateFileSearchTool(
                            fileSearchTool.Inputs?.OfType<HostedVectorStoreContent>().Select(c => c.VectorStoreId) ?? [],
                            fileSearchTool.MaximumResultCount));
                        break;

                    case HostedCodeInterpreterTool codeTool:
                        string json;
                        if (codeTool.Inputs is { Count: > 0 } inputs)
                        {
                            string jsonArray = JsonSerializer.Serialize(
                                inputs.OfType<HostedFileContent>().Select(c => c.FileId),
                                OpenAIJsonContext2.Default.IEnumerableString);
                            json = $$"""{"type":"code_interpreter","container":{"type":"auto",files:{{jsonArray}}} }""";
                        }
                        else
                        {
                            json = """{"type":"code_interpreter","container":"auto"}""";
                        }

                        result.Tools.Add(ModelReaderWriter.Read<ResponseTool>(BinaryData.FromString(json)));
                        break;

                    case HostedMcpServerTool mcpTool:
                        McpTool responsesMcpTool = ResponseTool.CreateMcpTool(
                            mcpTool.ServerName,
                            mcpTool.Url,
                            mcpTool.Headers);

                        if (mcpTool.AllowedTools is not null)
                        {
                            responsesMcpTool.AllowedTools = new();
                            AddAllMcpFilters(mcpTool.AllowedTools, responsesMcpTool.AllowedTools);
                        }

                        switch (mcpTool.ApprovalMode)
                        {
                            case HostedMcpServerToolAlwaysRequireApprovalMode:
                                responsesMcpTool.ToolCallApprovalPolicy = new McpToolCallApprovalPolicy(GlobalMcpToolCallApprovalPolicy.AlwaysRequireApproval);
                                break;

                            case HostedMcpServerToolNeverRequireApprovalMode:
                                responsesMcpTool.ToolCallApprovalPolicy = new McpToolCallApprovalPolicy(GlobalMcpToolCallApprovalPolicy.NeverRequireApproval);
                                break;

                            case HostedMcpServerToolRequireSpecificApprovalMode specificMode:
                                responsesMcpTool.ToolCallApprovalPolicy = new McpToolCallApprovalPolicy(new CustomMcpToolCallApprovalPolicy());

                                if (specificMode.AlwaysRequireApprovalToolNames is { Count: > 0 } alwaysRequireToolNames)
                                {
                                    responsesMcpTool.ToolCallApprovalPolicy.CustomPolicy.ToolsAlwaysRequiringApproval = new();
                                    AddAllMcpFilters(alwaysRequireToolNames, responsesMcpTool.ToolCallApprovalPolicy.CustomPolicy.ToolsAlwaysRequiringApproval);
                                }

                                if (specificMode.NeverRequireApprovalToolNames is { Count: > 0 } neverRequireToolNames)
                                {
                                    responsesMcpTool.ToolCallApprovalPolicy.CustomPolicy.ToolsNeverRequiringApproval = new();
                                    AddAllMcpFilters(neverRequireToolNames, responsesMcpTool.ToolCallApprovalPolicy.CustomPolicy.ToolsNeverRequiringApproval);
                                }

                                break;
                        }

                        result.Tools.Add(responsesMcpTool);
                        break;
                }
            }

            if (result.ToolChoice is null && result.Tools.Count > 0)
            {
                switch (options.ToolMode)
                {
                    case NoneChatToolMode:
                        result.ToolChoice = ResponseToolChoice.CreateNoneChoice();
                        break;

                    case AutoChatToolMode:
                    case null:
                        result.ToolChoice = ResponseToolChoice.CreateAutoChoice();
                        break;

                    case RequiredChatToolMode required:
                        result.ToolChoice = required.RequiredFunctionName is not null ?
                            ResponseToolChoice.CreateFunctionChoice(required.RequiredFunctionName) :
                            ResponseToolChoice.CreateRequiredChoice();
                        break;
                }
            }
        }

        if (result.TextOptions is null)
        {
            if (options.ResponseFormat is ChatResponseFormatText)
            {
                result.TextOptions = new()
                {
                    TextFormat = ResponseTextFormat.CreateTextFormat()
                };
            }
            else if (options.ResponseFormat is ChatResponseFormatJson jsonFormat)
            {
                result.TextOptions = new()
                {
                    TextFormat = OpenAIClientExtensions3.StrictSchemaTransformCache.GetOrCreateTransformedSchema(jsonFormat) is { } jsonSchema ?
                        ResponseTextFormat.CreateJsonSchemaFormat(
                            jsonFormat.SchemaName ?? "json_schema",
                            BinaryData.FromBytes(JsonSerializer.SerializeToUtf8Bytes(jsonSchema, OpenAIJsonContext2.Default.JsonElement)),
                            jsonFormat.SchemaDescription,
                            OpenAIClientExtensions3.HasStrict(options.AdditionalProperties)) :
                        ResponseTextFormat.CreateJsonObjectFormat(),
                };
            }
        }

        return result;
    }

    /// <summary>Convert a sequence of <see cref="ChatMessage"/>s to <see cref="ResponseItem"/>s.</summary>
    internal static IEnumerable<ResponseItem> ToOpenAIResponseItems(IEnumerable<ChatMessage> inputs, ChatOptions? options)
    {
        _ = options; // currently unused

        Dictionary<string, AIContent>? idToContentMapping = null;

        foreach (ChatMessage input in inputs)
        {
            if (input.Role == ChatRole.System ||
                input.Role == OpenAIClientExtensions3.ChatRoleDeveloper)
            {
                string text = input.Text;
                if (!string.IsNullOrWhiteSpace(text))
                {
                    yield return input.Role == ChatRole.System ?
                        ResponseItem.CreateSystemMessageItem(text) :
                        ResponseItem.CreateDeveloperMessageItem(text);
                }

                continue;
            }

            if (input.Role == ChatRole.User)
            {
                yield return ResponseItem.CreateUserMessageItem(ToResponseContentParts(input.Contents));
                continue;
            }

            if (input.Role == ChatRole.Tool)
            {
                foreach (AIContent item in input.Contents)
                {
                    switch (item)
                    {
                        case AIContent when item.RawRepresentation is ResponseItem rawRep:
                            yield return rawRep;
                            break;

                        case FunctionResultContent resultContent:
                            string? result = resultContent.Result as string;
                            if (result is null && resultContent.Result is not null)
                            {
                                try
                                {
                                    result = JsonSerializer.Serialize(resultContent.Result, AIJsonUtilities.DefaultOptions.GetTypeInfo(typeof(object)));
                                }
                                catch (NotSupportedException)
                                {
                                    // If the type can't be serialized, skip it.
                                }
                            }

                            yield return ResponseItem.CreateFunctionCallOutputItem(resultContent.CallId, result ?? string.Empty);
                            break;

                        case McpServerToolApprovalResponseContent mcpApprovalResponseContent:
                            yield return ResponseItem.CreateMcpApprovalResponseItem(mcpApprovalResponseContent.Id, mcpApprovalResponseContent.Approved);
                            break;
                    }
                }

                continue;
            }

            if (input.Role == ChatRole.Assistant)
            {
                foreach (AIContent item in input.Contents)
                {
                    switch (item)
                    {
                        case AIContent when item.RawRepresentation is ResponseItem rawRep:
                            yield return rawRep;
                            break;

                        case TextContent textContent:
                            yield return ResponseItem.CreateAssistantMessageItem(textContent.Text);
                            break;

                        case TextReasoningContent reasoningContent:
                            yield return ResponseItem.CreateReasoningItem(reasoningContent.Text);
                            break;

                        case FunctionCallContent callContent:
                            yield return ResponseItem.CreateFunctionCallItem(
                                callContent.CallId,
                                callContent.Name,
                                BinaryData.FromBytes(JsonSerializer.SerializeToUtf8Bytes(
                                    callContent.Arguments,
                                    AIJsonUtilities.DefaultOptions.GetTypeInfo(typeof(IDictionary<string, object?>)))));
                            break;

                        case McpServerToolApprovalRequestContent mcpApprovalRequestContent:
                            // BUG https://github.com/openai/openai-dotnet/issues/664: Needs to be able to set an approvalRequestId
                            yield return ResponseItem.CreateMcpApprovalRequestItem(
                                mcpApprovalRequestContent.ToolCall.ServerName,
                                mcpApprovalRequestContent.ToolCall.ToolName,
                                BinaryData.FromBytes(JsonSerializer.SerializeToUtf8Bytes(mcpApprovalRequestContent.ToolCall.Arguments!, OpenAIJsonContext2.Default.IReadOnlyDictionaryStringObject)));
                            break;

                        case McpServerToolCallContent mstcc:
                            (idToContentMapping ??= [])[mstcc.CallId] = mstcc;
                            break;

                        case McpServerToolResultContent mstrc:
                            if (idToContentMapping?.TryGetValue(mstrc.CallId, out AIContent? callContentFromMapping) is true &&
                                callContentFromMapping is McpServerToolCallContent associatedCall)
                            {
                                _ = idToContentMapping.Remove(mstrc.CallId);
                                McpToolCallItem mtci = ResponseItem.CreateMcpToolCallItem(
                                    associatedCall.ServerName,
                                    associatedCall.ToolName,
                                    BinaryData.FromBytes(JsonSerializer.SerializeToUtf8Bytes(associatedCall.Arguments!, OpenAIJsonContext2.Default.IReadOnlyDictionaryStringObject)));
                                if (mstrc.Output?.OfType<ErrorContent>().FirstOrDefault() is ErrorContent errorContent)
                                {
                                    mtci.Error = BinaryData.FromString(errorContent.Message);
                                }
                                else
                                {
                                    mtci.ToolOutput = string.Concat(mstrc.Output?.OfType<TextContent>() ?? []);
                                }

                                yield return mtci;
                            }

                            break;
                    }
                }

                continue;
            }
        }
    }

    /// <summary>Extract usage details from an <see cref="OpenAIResponse"/>.</summary>
    private static UsageDetails? ToUsageDetails(OpenAIResponse? openAIResponse)
    {
        UsageDetails? ud = null;
        if (openAIResponse?.Usage is { } usage)
        {
            ud = new()
            {
                InputTokenCount = usage.InputTokenCount,
                OutputTokenCount = usage.OutputTokenCount,
                TotalTokenCount = usage.TotalTokenCount,
            };

            if (usage.InputTokenDetails is { } inputDetails)
            {
                ud.AdditionalCounts ??= [];
                ud.AdditionalCounts.Add($"{nameof(usage.InputTokenDetails)}.{nameof(inputDetails.CachedTokenCount)}", inputDetails.CachedTokenCount);
            }

            if (usage.OutputTokenDetails is { } outputDetails)
            {
                ud.AdditionalCounts ??= [];
                ud.AdditionalCounts.Add($"{nameof(usage.OutputTokenDetails)}.{nameof(outputDetails.ReasoningTokenCount)}", outputDetails.ReasoningTokenCount);
            }
        }

        return ud;
    }

    /// <summary>Convert a sequence of <see cref="ResponseContentPart"/>s to a list of <see cref="AIContent"/>.</summary>
    private static List<AIContent> ToAIContents(IEnumerable<ResponseContentPart> contents)
    {
        List<AIContent> results = [];

        foreach (ResponseContentPart part in contents)
        {
            switch (part.Kind)
            {
                case ResponseContentPartKind.InputText or ResponseContentPartKind.OutputText:
                    TextContent text = new(part.Text) { RawRepresentation = part };
                    PopulateAnnotations(part, text);
                    results.Add(text);
                    break;

                case ResponseContentPartKind.InputFile:
                    if (!string.IsNullOrWhiteSpace(part.InputImageFileId))
                    {
                        results.Add(new HostedFileContent(part.InputImageFileId) { RawRepresentation = part });
                    }
                    else if (!string.IsNullOrWhiteSpace(part.InputFileId))
                    {
                        results.Add(new HostedFileContent(part.InputFileId) { RawRepresentation = part });
                    }
                    else if (part.InputFileBytes is not null)
                    {
                        results.Add(new DataContent(part.InputFileBytes, part.InputFileBytesMediaType ?? "application/octet-stream")
                        {
                            Name = part.InputFilename,
                            RawRepresentation = part,
                        });
                    }

                    break;

                case ResponseContentPartKind.Refusal:
                    results.Add(new ErrorContent(part.Refusal)
                    {
                        ErrorCode = nameof(ResponseContentPartKind.Refusal),
                        RawRepresentation = part,
                    });
                    break;

                default:
                    results.Add(new() { RawRepresentation = part });
                    break;
            }
        }

        return results;
    }

    /// <summary>Converts any annotations from <paramref name="source"/> and stores them in <paramref name="destination"/>.</summary>
    private static void PopulateAnnotations(ResponseContentPart source, AIContent destination)
    {
        if (source.OutputTextAnnotations is { Count: > 0 })
        {
            foreach (var ota in source.OutputTextAnnotations)
            {
                CitationAnnotation ca = new()
                {
                    RawRepresentation = ota,
                };

                switch (ota)
                {
                    case UriCitationMessageAnnotation ucma:
                        ca.AnnotatedRegions = [new TextSpanAnnotatedRegion { StartIndex = ucma.StartIndex, EndIndex = ucma.EndIndex }];
                        ca.Title = ucma.Title;
                        ca.Url = ucma.Uri;
                        break;

                    case FilePathMessageAnnotation fpma:
                        ca.FileId = fpma.FileId;
                        break;

                    case FileCitationMessageAnnotation fcma:
                        ca.FileId = fcma.FileId;
                        break;
                }

                (destination.Annotations ??= []).Add(ca);
            }
        }
    }

    /// <summary>Convert a list of <see cref="AIContent"/>s to a list of <see cref="ResponseContentPart"/>.</summary>
    private static List<ResponseContentPart> ToResponseContentParts(IList<AIContent> contents)
    {
        List<ResponseContentPart> parts = [];
        foreach (var content in contents)
        {
            switch (content)
            {
                case AIContent when content.RawRepresentation is ResponseContentPart rawRep:
                    parts.Add(rawRep);
                    break;

                case TextContent textContent:
                    parts.Add(ResponseContentPart.CreateInputTextPart(textContent.Text));
                    break;

                case UriContent uriContent when uriContent.HasTopLevelMediaType("image"):
                    parts.Add(ResponseContentPart.CreateInputImagePart(uriContent.Uri));
                    break;

                case DataContent dataContent when dataContent.HasTopLevelMediaType("image"):
                    parts.Add(ResponseContentPart.CreateInputImagePart(BinaryData.FromBytes(dataContent.Data), dataContent.MediaType));
                    break;

                case DataContent dataContent when dataContent.MediaType.StartsWith("application/pdf", StringComparison.OrdinalIgnoreCase):
                    parts.Add(ResponseContentPart.CreateInputFilePart(BinaryData.FromBytes(dataContent.Data), dataContent.MediaType, dataContent.Name ?? $"{Guid.NewGuid():N}.pdf"));
                    break;

                case HostedFileContent fileContent:
                    parts.Add(ResponseContentPart.CreateInputFilePart(fileContent.FileId));
                    break;

                case ErrorContent errorContent when errorContent.ErrorCode == nameof(ResponseContentPartKind.Refusal):
                    parts.Add(ResponseContentPart.CreateRefusalPart(errorContent.Message));
                    break;
            }
        }

        if (parts.Count == 0)
        {
            parts.Add(ResponseContentPart.CreateInputTextPart(string.Empty));
        }

        return parts;
    }

    /// <summary>Adds new <see cref="AIContent"/> for the specified <paramref name="mtci"/> into <paramref name="contents"/>.</summary>
    private static void AddMcpToolCallContent(McpToolCallItem mtci, IList<AIContent> contents)
    {
        contents.Add(new McpServerToolCallContent(mtci.Id, mtci.ToolName, mtci.ServerLabel)
        {
            Arguments = JsonSerializer.Deserialize(mtci.ToolArguments.ToMemory().Span, OpenAIJsonContext2.Default.IReadOnlyDictionaryStringObject)!,

            // We purposefully do not set the RawRepresentation on the McpServerToolCallContent, only on the McpServerToolResultContent, to avoid
            // the same McpToolCallItem being included on two different AIContent instances. When these are roundtripped, we want only one
            // McpToolCallItem sent back for the pair.
        });

        contents.Add(new McpServerToolResultContent(mtci.Id)
        {
            RawRepresentation = mtci,
            Output = [mtci.Error is not null ?
                new ErrorContent(mtci.Error.ToString()) :
                new TextContent(mtci.ToolOutput)],
        });
    }

    /// <summary>Adds all of the tool names from <paramref name="toolNames"/> to <paramref name="filter"/>.</summary>
    private static void AddAllMcpFilters(IList<string> toolNames, McpToolFilter filter)
    {
        foreach (var toolName in toolNames)
        {
            filter.ToolNames.Add(toolName);
        }
    }

    /// <summary>Determines whether long-running responses mode is enabled or not.</summary>
    private bool IsLongRunningResponsesModeEnabled(ChatOptions? options)
    {
        // If specified in options, use that.
        if (options is NewChatOptions { AllowBackgroundResponses: { } allowBackgroundResponses })
        {
            return allowBackgroundResponses;
        }

        // Otherwise, use the value specified at initialization
        return _enableLongRunningOperations ?? false;
    }

    /// <summary>Converts a <see cref="ResponseStatus"/> to a <see cref="NewResponseStatus"/>.</summary>
    private static NewResponseStatus? ToResponseStatus(ResponseStatus? status, ResponseCreationOptions options)
    {
        // Unless the new behavior of not awaiting run completion is requested, we don't return a status
        if (status is null || options.BackgroundModeEnabled is false)
        {
            return null;
        }

        return status switch
        {
            ResponseStatus.InProgress => (NewResponseStatus?)NewResponseStatus.InProgress,
            ResponseStatus.Completed => (NewResponseStatus?)NewResponseStatus.Completed,
            ResponseStatus.Incomplete => (NewResponseStatus?)NewResponseStatus.Incomplete,
            ResponseStatus.Cancelled => (NewResponseStatus?)NewResponseStatus.Canceled,
            ResponseStatus.Queued => (NewResponseStatus?)NewResponseStatus.Queued,
            ResponseStatus.Failed => (NewResponseStatus?)NewResponseStatus.Failed,
            _ => throw new ArgumentOutOfRangeException(nameof(status), status, "Unknown response status."),
        };
    }
}

internal static class OpenAIClientExtensions3
{
    /// <summary>Key into AdditionalProperties used to store a strict option.</summary>
    private const string StrictKey = "strictJsonSchema";

    /// <summary>Gets the default OpenAI endpoint.</summary>
    internal static Uri DefaultOpenAIEndpoint { get; } = new("https://api.openai.com/v1");

    /// <summary>Gets a <see cref="ChatRole"/> for "developer".</summary>
    internal static ChatRole ChatRoleDeveloper { get; } = new ChatRole("developer");

    /// <summary>
    /// Gets the JSON schema transformer cache conforming to OpenAI <b>strict</b> / structured output restrictions per
    /// https://platform.openai.com/docs/guides/structured-outputs?api-mode=responses#supported-schemas.
    /// </summary>
    internal static AIJsonSchemaTransformCache StrictSchemaTransformCache { get; } = new(new()
    {
        DisallowAdditionalProperties = true,
        ConvertBooleanSchemas = true,
        MoveDefaultKeywordToDescription = true,
        RequireAllProperties = true,
        TransformSchemaNode = (ctx, node) =>
        {
            // Move content from common but unsupported properties to description. In particular, we focus on properties that
            // the AIJsonUtilities schema generator might produce and/or that are explicitly mentioned in the OpenAI documentation.

            if (node is JsonObject schemaObj)
            {
                StringBuilder? additionalDescription = null;

                ReadOnlySpan<string> unsupportedProperties =
                [
                    // Produced by AIJsonUtilities but not in allow list at https://platform.openai.com/docs/guides/structured-outputs#supported-properties:
                    "contentEncoding", "contentMediaType", "not",

                    // Explicitly mentioned at https://platform.openai.com/docs/guides/structured-outputs?api-mode=responses#key-ordering as being unsupported with some models:
                    "minLength", "maxLength", "pattern", "format",
                    "minimum", "maximum", "multipleOf",
                    "patternProperties",
                    "minItems", "maxItems",

                    // Explicitly mentioned at https://learn.microsoft.com/azure/ai-services/openai/how-to/structured-outputs?pivots=programming-language-csharp&tabs=python-secure%2Cdotnet-entra-id#unsupported-type-specific-keywords
                    // as being unsupported with Azure OpenAI:
                    "unevaluatedProperties", "propertyNames", "minProperties", "maxProperties",
                    "unevaluatedItems", "contains", "minContains", "maxContains", "uniqueItems",
                ];

                foreach (string propName in unsupportedProperties)
                {
                    if (schemaObj[propName] is { } propNode)
                    {
                        _ = schemaObj.Remove(propName);
                        AppendLine(ref additionalDescription, propName, propNode);
                    }
                }

                if (additionalDescription is not null)
                {
                    schemaObj["description"] = schemaObj["description"] is { } descriptionNode && descriptionNode.GetValueKind() == JsonValueKind.String ?
                        $"{descriptionNode.GetValue<string>()}{Environment.NewLine}{additionalDescription}" :
                        additionalDescription.ToString();
                }

                return node;

                static void AppendLine(ref StringBuilder? sb, string propName, JsonNode propNode)
                {
                    sb ??= new();

                    if (sb.Length > 0)
                    {
                        _ = sb.AppendLine();
                    }

                    _ = sb.Append(propName).Append(": ").Append(propNode);
                }
            }

            return node;
        },
    });

    /// <summary>Gets whether the properties specify that strict schema handling is desired.</summary>
    internal static bool? HasStrict(IReadOnlyDictionary<string, object?>? additionalProperties) =>
        additionalProperties?.TryGetValue(StrictKey, out object? strictObj) is true &&
        strictObj is bool strictValue ?
        strictValue : null;

    /// <summary>Extracts from an <see cref="AIFunctionDeclaration"/> the parameters and strictness setting for use with OpenAI's APIs.</summary>
    internal static BinaryData ToOpenAIFunctionParameters(AIFunctionDeclaration aiFunction, bool? strict)
    {
        // Perform any desirable transformations on the function's JSON schema, if it'll be used in a strict setting.
        JsonElement jsonSchema = strict is true ?
            StrictSchemaTransformCache.GetOrCreateTransformedSchema(aiFunction) :
            aiFunction.JsonSchema;

        // Roundtrip the schema through the ToolJson model type to remove extra properties
        // and force missing ones into existence, then return the serialized UTF8 bytes as BinaryData.
        var tool = JsonSerializer.Deserialize(jsonSchema, OpenAIJsonContext2.Default.ToolJson)!;
        var functionParameters = BinaryData.FromBytes(JsonSerializer.SerializeToUtf8Bytes(tool, OpenAIJsonContext2.Default.ToolJson));

        return functionParameters;
    }

    /// <summary>Creates a new instance of <see cref="FunctionCallContent"/> parsing arguments using a specified encoding and parser.</summary>
    /// <param name="json">The input arguments to be parsed.</param>
    /// <param name="callId">The function call ID.</param>
    /// <param name="name">The function name.</param>
    /// <returns>A new instance of <see cref="FunctionCallContent"/> containing the parse result.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="callId"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentNullException"><paramref name="name"/> is <see langword="null"/>.</exception>
    internal static FunctionCallContent ParseCallContent(string json, string callId, string name) =>
        FunctionCallContent.CreateFromParsedArguments(json, callId, name,
            static json => JsonSerializer.Deserialize(json, OpenAIJsonContext2.Default.IDictionaryStringObject)!);

    /// <summary>Creates a new instance of <see cref="FunctionCallContent"/> parsing arguments using a specified encoding and parser.</summary>
    /// <param name="utf8json">The input arguments to be parsed.</param>
    /// <param name="callId">The function call ID.</param>
    /// <param name="name">The function name.</param>
    /// <returns>A new instance of <see cref="FunctionCallContent"/> containing the parse result.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="callId"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentNullException"><paramref name="name"/> is <see langword="null"/>.</exception>
    internal static FunctionCallContent ParseCallContent(BinaryData utf8json, string callId, string name) =>
        FunctionCallContent.CreateFromParsedArguments(utf8json, callId, name,
            static utf8json => JsonSerializer.Deserialize(utf8json, OpenAIJsonContext2.Default.IDictionaryStringObject)!);

    /// <summary>Used to create the JSON payload for an OpenAI tool description.</summary>
    internal sealed class ToolJson
    {
        [JsonPropertyName("type")]
        public string Type { get; set; } = "object";

        [JsonPropertyName("required")]
        public HashSet<string> Required { get; set; } = [];

        [JsonPropertyName("properties")]
        public Dictionary<string, JsonElement> Properties { get; set; } = [];

        [JsonPropertyName("additionalProperties")]
        public bool AdditionalProperties { get; set; }
    }
}

/// <summary>Source-generated JSON type information for use by all OpenAI implementations.</summary>
[JsonSourceGenerationOptions(JsonSerializerDefaults.Web,
    UseStringEnumConverter = true,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    WriteIndented = true)]
[JsonSerializable(typeof(OpenAIClientExtensions3.ToolJson))]
[JsonSerializable(typeof(IDictionary<string, object?>))]
[JsonSerializable(typeof(IReadOnlyDictionary<string, object?>))]
[JsonSerializable(typeof(string[]))]
[JsonSerializable(typeof(IEnumerable<string>))]
[JsonSerializable(typeof(JsonElement))]
internal sealed partial class OpenAIJsonContext2 : JsonSerializerContext;
