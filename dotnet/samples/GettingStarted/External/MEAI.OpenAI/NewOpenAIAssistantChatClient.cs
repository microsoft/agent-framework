#pragma warning disable IDE0005 // Using directive is unnecessary.
#pragma warning disable IDE0073 // The file header does not match the required text
#pragma warning disable CS0436 // Type conflicts with imported type
#pragma warning disable CA1063 // Implement IDisposable Correctly

// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;
using OpenAI;
using OpenAI.Assistants;
using OpenAI.Audio;
using OpenAI.Chat;
using OpenAI.Embeddings;

#pragma warning disable CA1031 // Do not catch general exception types
#pragma warning disable SA1005 // Single line comments should begin with single space
#pragma warning disable SA1204 // Static elements should appear before instance elements
#pragma warning disable S125 // Sections of code should not be commented out
#pragma warning disable S907 // "goto" statement should not be used
#pragma warning disable S1067 // Expressions should not be too complex
#pragma warning disable S1751 // Loops with at most one iteration should be refactored
#pragma warning disable S3011 // Reflection should not be used to increase accessibility of classes, methods, or fields
#pragma warning disable S4456 // Parameter validation in yielding methods should be wrapped
#pragma warning disable S4457 // Parameter validation in "async"/"await" methods should be wrapped

namespace Microsoft.Extensions.AI;

/// <summary>Represents an <see cref="IChatClient"/> for an Azure.AI.Agents.Persistent <see cref="AssistantClient"/>.</summary>
public sealed class NewOpenAIAssistantChatClient : IChatClient
{
    /// <summary>The underlying <see cref="AssistantClient" />.</summary>
#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
    private readonly AssistantClient _client;

    /// <summary>Metadata for the client.</summary>
    private readonly ChatClientMetadata _metadata;

    /// <summary>The ID of the agent to use.</summary>
    private readonly string _assistantId;

    /// <summary>The thread ID to use if none is supplied in <see cref="ChatOptions.ConversationId"/>.</summary>
    private readonly string? _defaultThreadId;

    /// <summary>List of tools associated with the assistant.</summary>
    private IReadOnlyList<ToolDefinition>? _assistantTools;

    /// <summary>Initializes a new instance of the <see cref="OpenAIAssistantChatClient"/> class for the specified <see cref="AssistantClient"/>.</summary>
    public NewOpenAIAssistantChatClient(AssistantClient assistantClient, string assistantId, string? defaultThreadId)
    {
        _client = Throw.IfNull(assistantClient);
        _assistantId = Throw.IfNullOrWhitespace(assistantId);

        _defaultThreadId = defaultThreadId;

        // https://github.com/openai/openai-dotnet/issues/215
        // The endpoint isn't currently exposed, so use reflection to get at it, temporarily. Once packages
        // implement the abstractions directly rather than providing adapters on top of the public APIs,
        // the package can provide such implementations separate from what's exposed in the public API.
        Uri providerUrl = typeof(AssistantClient).GetField("_endpoint", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)
            ?.GetValue(assistantClient) as Uri ?? OpenAIClientExtensions2.DefaultOpenAIEndpoint;

        _metadata = new("openai", providerUrl);
    }

    /// <inheritdoc />
    public object? GetService(Type serviceType, object? serviceKey = null) =>
        serviceType is null ? throw new ArgumentNullException(nameof(serviceType)) :
        serviceKey is not null ? null :
        serviceType == typeof(ChatClientMetadata) ? _metadata :
        serviceType == typeof(AssistantClient) ? _client :
        serviceType.IsInstanceOfType(this) ? this :
        null;

    /// <inheritdoc />
    public Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default) =>
        GetStreamingResponseAsync(messages, options, cancellationToken).ToChatResponseAsync(cancellationToken);

    /// <inheritdoc />
    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        // Extract necessary state from messages and options.
        (RunCreationOptions runOptions, List<FunctionResultContent>? toolResults) = await CreateRunOptionsAsync(messages, options, cancellationToken).ConfigureAwait(false);

        // Get the thread ID.
        string? threadId = options?.ConversationId ?? _defaultThreadId;
        if (threadId is null && toolResults is not null)
        {
            Throw.ArgumentException(nameof(messages), "No thread ID was provided, but chat messages includes tool results.");
        }

        // Get any active run ID for this thread. This is necessary in case a thread has been left with an
        // active run, in which all attempts other than submitting tools will fail. We thus need to cancel
        // any active run on the thread.
        ThreadRun? threadRun = null;
        if (threadId is not null)
        {
            await foreach (var run in _client.GetRunsAsync(
                threadId,
                new RunCollectionOptions { Order = RunCollectionOrder.Descending, PageSizeLimit = 1 },
                cancellationToken: cancellationToken).ConfigureAwait(false))
            {
                if (run.Status != RunStatus.Completed && run.Status != RunStatus.Cancelled && run.Status != RunStatus.Failed && run.Status != RunStatus.Expired)
                {
                    threadRun = run;
                }

                break;
            }
        }

        // Submit the request.
        IAsyncEnumerable<StreamingUpdate> updates;
        if (threadRun is not null &&
            ConvertFunctionResultsToToolOutput(toolResults, out List<ToolOutput>? toolOutputs) is { } toolRunId &&
            toolRunId == threadRun.Id)
        {
            // There's an active run and we have tool results to submit, so submit the results and continue streaming.
            // This is going to ignore any additional messages in the run options, as we are only submitting tool outputs,
            // but there doesn't appear to be a way to submit additional messages, and having such additional messages is rare.
            updates = _client.SubmitToolOutputsToRunStreamingAsync(threadRun.ThreadId, threadRun.Id, toolOutputs, cancellationToken);
        }
        else
        {
            if (threadId is null)
            {
                // No thread ID was provided, so create a new thread.
                ThreadCreationOptions threadCreationOptions = new();
                foreach (var message in runOptions.AdditionalMessages)
                {
                    threadCreationOptions.InitialMessages.Add(message);
                }

                runOptions.AdditionalMessages.Clear();

                var thread = await _client.CreateThreadAsync(threadCreationOptions, cancellationToken).ConfigureAwait(false);
                threadId = thread.Value.Id;
            }
            else if (threadRun is not null)
            {
                // There was an active run; we need to cancel it before starting a new run.
                _ = await _client.CancelRunAsync(threadId, threadRun.Id, cancellationToken).ConfigureAwait(false);
                threadRun = null;
            }

            // Now create a new run and stream the results.
            updates = _client.CreateRunStreamingAsync(
                threadId: threadId,
                _assistantId,
                runOptions,
                cancellationToken);
        }

        // Process each update.
        string? responseId = null;
        await foreach (var update in updates.ConfigureAwait(false))
        {
            switch (update)
            {
                case ThreadUpdate tu:
                    threadId ??= tu.Value.Id;
                    goto default;

                case RunUpdate ru:
                    threadId ??= ru.Value.ThreadId;
                    responseId ??= ru.Value.Id;

                    ChatResponseUpdate ruUpdate = new()
                    {
                        AuthorName = _assistantId,
                        ConversationId = threadId,
                        CreatedAt = ru.Value.CreatedAt,
                        MessageId = responseId,
                        ModelId = ru.Value.Model,
                        RawRepresentation = ru,
                        ResponseId = responseId,
                        Role = ChatRole.Assistant,
                    };

                    if (ru.Value.Usage is { } usage)
                    {
                        ruUpdate.Contents.Add(new UsageContent(new()
                        {
                            InputTokenCount = usage.InputTokenCount,
                            OutputTokenCount = usage.OutputTokenCount,
                            TotalTokenCount = usage.TotalTokenCount,
                        }));
                    }

                    if (ru is RequiredActionUpdate rau && rau.ToolCallId is string toolCallId && rau.FunctionName is string functionName)
                    {
                        ruUpdate.Contents.Add(
                            new FunctionCallContent(
                                JsonSerializer.Serialize([ru.Value.Id, toolCallId], OpenAIJsonContext.Default.StringArray),
                                functionName,
                                JsonSerializer.Deserialize(rau.FunctionArguments, OpenAIJsonContext.Default.IDictionaryStringObject)!));
                    }

                    yield return ruUpdate;
                    break;

                case MessageContentUpdate mcu:
                    yield return new(mcu.Role == MessageRole.User ? ChatRole.User : ChatRole.Assistant, mcu.Text)
                    {
                        AuthorName = _assistantId,
                        ConversationId = threadId,
                        MessageId = responseId,
                        RawRepresentation = mcu,
                        ResponseId = responseId,
                    };
                    break;

                default:
                    yield return new ChatResponseUpdate
                    {
                        AuthorName = _assistantId,
                        ConversationId = threadId,
                        MessageId = responseId,
                        RawRepresentation = update,
                        ResponseId = responseId,
                        Role = ChatRole.Assistant,
                    };
                    break;
            }
        }
    }

    /// <inheritdoc />
    void IDisposable.Dispose()
    {
        // nop
    }

    /// <summary>Converts an Extensions function to an OpenAI assistants function tool.</summary>
    internal static FunctionToolDefinition ToOpenAIAssistantsFunctionToolDefinition(AIFunction aiFunction, ChatOptions? options = null)
    {
        bool? strict =
            OpenAIClientExtensions2.HasStrict(aiFunction.AdditionalProperties) ??
            OpenAIClientExtensions2.HasStrict(options?.AdditionalProperties);

        return new FunctionToolDefinition(aiFunction.Name)
        {
            Description = aiFunction.Description,
            Parameters = OpenAIClientExtensions2.ToOpenAIFunctionParameters(aiFunction, strict),
            StrictParameterSchemaEnabled = strict,
        };
    }

    /// <summary>
    /// Creates the <see cref="RunCreationOptions"/> to use for the request and extracts any function result contents
    /// that need to be submitted as tool results.
    /// </summary>
    private async ValueTask<(RunCreationOptions RunOptions, List<FunctionResultContent>? ToolResults)> CreateRunOptionsAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken cancellationToken)
    {
        // Create the options instance to populate, either a fresh or using one the caller provides.
        RunCreationOptions runOptions =
            options?.RawRepresentationFactory?.Invoke(this) as RunCreationOptions ??
            new();

        // Populate the run options from the ChatOptions, if provided.
        if (options is not null)
        {
            runOptions.MaxOutputTokenCount ??= options.MaxOutputTokens;
            runOptions.ModelOverride ??= options.ModelId;
            runOptions.NucleusSamplingFactor ??= options.TopP;
            runOptions.Temperature ??= options.Temperature;
            runOptions.AllowParallelToolCalls ??= options.AllowMultipleToolCalls;

            if (options.Tools is { Count: > 0 } tools)
            {
                // If the caller has provided any tool overrides, we'll assume they don't want to use the assistant's tools.
                // But if they haven't, the only way we can provide our tools is via an override, whereas we'd really like to
                // just add them. To handle that, we'll get all of the assistant's tools and add them to the override list
                // along with our tools.
                if (runOptions.ToolsOverride.Count == 0)
                {
                    if (_assistantTools is null)
                    {
                        var assistant = await _client.GetAssistantAsync(_assistantId, cancellationToken).ConfigureAwait(false);
                        _assistantTools = assistant.Value.Tools;
                    }

                    foreach (var tool in _assistantTools)
                    {
                        runOptions.ToolsOverride.Add(tool);
                    }
                }

                // The caller can provide tools in the supplied ThreadAndRunOptions. Augment it with any supplied via ChatOptions.Tools.
                foreach (AITool tool in tools)
                {
                    switch (tool)
                    {
                        case AIFunction aiFunction:
                            runOptions.ToolsOverride.Add(ToOpenAIAssistantsFunctionToolDefinition(aiFunction, options));
                            break;

                        case HostedCodeInterpreterTool:
                            var codeInterpreterToolDefinition = new CodeInterpreterToolDefinition();
                            runOptions.ToolsOverride.Add(codeInterpreterToolDefinition);

                            // Once available, HostedCodeInterpreterTool.FileIds property will be used instead of the AdditionalProperties.
                            if (tool.AdditionalProperties.TryGetValue("fileIds", out object? fileIdsObject) && fileIdsObject is IEnumerable<string> fileIds)
                            {
                                var threadInitializationMessage = new ThreadInitializationMessage(OpenAI.Assistants.MessageRole.User, [OpenAI.Assistants.MessageContent.FromText("attachments")]);

                                foreach (var fileId in fileIds)
                                {
                                    threadInitializationMessage.Attachments.Add(new(fileId, [codeInterpreterToolDefinition]));
                                }

                                runOptions.AdditionalMessages.Add(threadInitializationMessage);
                            }

                            break;
                    }
                }
            }

            // Store the tool mode, if relevant.
            if (runOptions.ToolConstraint is null)
            {
                switch (options.ToolMode)
                {
                    case NoneChatToolMode:
                        runOptions.ToolConstraint = ToolConstraint.None;
                        break;

                    case AutoChatToolMode:
                        runOptions.ToolConstraint = ToolConstraint.Auto;
                        break;

                    case RequiredChatToolMode required when required.RequiredFunctionName is { } functionName:
                        runOptions.ToolConstraint = new ToolConstraint(ToolDefinition.CreateFunction(functionName));
                        break;

                    case RequiredChatToolMode required:
                        runOptions.ToolConstraint = ToolConstraint.Required;
                        break;
                }
            }

            // Store the response format, if relevant.
            if (runOptions.ResponseFormat is null)
            {
                switch (options.ResponseFormat)
                {
                    case ChatResponseFormatText:
                        runOptions.ResponseFormat = AssistantResponseFormat.CreateTextFormat();
                        break;

                    case ChatResponseFormatJson jsonFormat when OpenAIClientExtensions2.StrictSchemaTransformCache.GetOrCreateTransformedSchema(jsonFormat) is { } jsonSchema:
                        runOptions.ResponseFormat = AssistantResponseFormat.CreateJsonSchemaFormat(
                            jsonFormat.SchemaName,
                            BinaryData.FromBytes(JsonSerializer.SerializeToUtf8Bytes(jsonSchema, OpenAIJsonContext.Default.JsonElement)),
                            jsonFormat.SchemaDescription,
                            OpenAIClientExtensions2.HasStrict(options.AdditionalProperties));
                        break;

                    case ChatResponseFormatJson jsonFormat:
                        runOptions.ResponseFormat = AssistantResponseFormat.CreateJsonObjectFormat();
                        break;
                }
            }
        }

        // Configure system instructions.
        StringBuilder? instructions = null;
        void AppendSystemInstructions(string? toAppend)
        {
            if (!string.IsNullOrEmpty(toAppend))
            {
                if (instructions is null)
                {
                    instructions = new(toAppend);
                }
                else
                {
                    _ = instructions.AppendLine().AppendLine(toAppend);
                }
            }
        }

        AppendSystemInstructions(runOptions.AdditionalInstructions);
        AppendSystemInstructions(options?.Instructions);

        // Process ChatMessages.
        List<FunctionResultContent>? functionResults = null;
        foreach (var chatMessage in messages)
        {
            List<MessageContent> messageContents = [];

            // Assistants doesn't support system/developer messages directly. It does support transient per-request instructions,
            // so we can use the system/developer messages to build up a set of instructions that will be passed to the assistant
            // as part of this request. However, in doing so, on a subsequent request that information will be lost, as there's no
            // way to store per-thread instructions in the OpenAI Assistants API. We don't want to convert these to user messages,
            // however, as that would then expose the system/developer messages in a way that might make the model more likely
            // to include that information in its responses. System messages should ideally be instead done as instructions to
            // the assistant when the assistant is created.
            if (chatMessage.Role == ChatRole.System ||
                chatMessage.Role == OpenAIClientExtensions2.ChatRoleDeveloper)
            {
                foreach (var textContent in chatMessage.Contents.OfType<TextContent>())
                {
                    AppendSystemInstructions(textContent.Text);
                }

                continue;
            }

            foreach (AIContent content in chatMessage.Contents)
            {
                switch (content)
                {
                    case TextContent text:
                        messageContents.Add(MessageContent.FromText(text.Text));
                        break;

                    case UriContent image when image.HasTopLevelMediaType("image"):
                        messageContents.Add(MessageContent.FromImageUri(image.Uri));
                        break;

                    // Assistants doesn't support data URIs.
                    //case DataContent image when image.HasTopLevelMediaType("image"):
                    //    messageContents.Add(MessageContent.FromImageUri(new Uri(image.Uri)));
                    //    break;

                    case FunctionResultContent result:
                        (functionResults ??= []).Add(result);
                        break;

                    case AIContent when content.RawRepresentation is MessageContent rawRep:
                        messageContents.Add(rawRep);
                        break;
                }
            }

            if (messageContents.Count > 0)
            {
                runOptions.AdditionalMessages.Add(new ThreadInitializationMessage(
                    chatMessage.Role == ChatRole.Assistant ? MessageRole.Assistant : MessageRole.User,
                    messageContents));
            }
        }

        runOptions.AdditionalInstructions = instructions?.ToString();

        return (runOptions, functionResults);
    }

    /// <summary>Convert <see cref="FunctionResultContent"/> instances to <see cref="ToolOutput"/> instances.</summary>
    /// <param name="toolResults">The tool results to process.</param>
    /// <param name="toolOutputs">The generated list of tool outputs, if any could be created.</param>
    /// <returns>The run ID associated with the corresponding function call requests.</returns>
    private static string? ConvertFunctionResultsToToolOutput(List<FunctionResultContent>? toolResults, out List<ToolOutput>? toolOutputs)
    {
        string? runId = null;
        toolOutputs = null;
        if (toolResults?.Count > 0)
        {
            foreach (var frc in toolResults)
            {
                // When creating the FunctionCallContext, we created it with a CallId == [runId, callId].
                // We need to extract the run ID and ensure that the ToolOutput we send back to Azure
                // is only the call ID.
                string[]? runAndCallIDs;
                try
                {
                    runAndCallIDs = JsonSerializer.Deserialize(frc.CallId, OpenAIJsonContext.Default.StringArray);
                }
                catch
                {
                    continue;
                }

                if (runAndCallIDs is null ||
                    runAndCallIDs.Length != 2 ||
                    string.IsNullOrWhiteSpace(runAndCallIDs[0]) || // run ID
                    string.IsNullOrWhiteSpace(runAndCallIDs[1]) || // call ID
                    (runId is not null && runId != runAndCallIDs[0]))
                {
                    continue;
                }

                runId = runAndCallIDs[0];
                (toolOutputs ??= []).Add(new(runAndCallIDs[1], frc.Result?.ToString() ?? string.Empty));
            }
        }

        return runId;
    }
}

/// <summary>Provides extension methods for working with <see cref="OpenAIClient"/>s.</summary>
internal static class OpenAIClientExtensions2
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

    // TODO: Once we're ready to rely on C# 14 features, add an extension property ChatOptions.Strict.

    /// <summary>Gets whether the properties specify that strict schema handling is desired.</summary>
    internal static bool? HasStrict(IReadOnlyDictionary<string, object?>? additionalProperties) =>
        additionalProperties?.TryGetValue(StrictKey, out object? strictObj) is true &&
        strictObj is bool strictValue ?
        strictValue : null;

    /// <summary>Extracts from an <see cref="AIFunction"/> the parameters and strictness setting for use with OpenAI's APIs.</summary>
    internal static BinaryData ToOpenAIFunctionParameters(AIFunction aiFunction, bool? strict)
    {
        // Perform any desirable transformations on the function's JSON schema, if it'll be used in a strict setting.
        JsonElement jsonSchema = strict is true ?
            StrictSchemaTransformCache.GetOrCreateTransformedSchema(aiFunction) :
            aiFunction.JsonSchema;

        // Roundtrip the schema through the ToolJson model type to remove extra properties
        // and force missing ones into existence, then return the serialized UTF8 bytes as BinaryData.
        var tool = jsonSchema.Deserialize(OpenAIJsonContext.Default.ToolJson)!;
        var functionParameters = BinaryData.FromBytes(JsonSerializer.SerializeToUtf8Bytes(tool, OpenAIJsonContext.Default.ToolJson));

        return functionParameters;
    }

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
[JsonSerializable(typeof(OpenAIClientExtensions2.ToolJson))]
[JsonSerializable(typeof(IDictionary<string, object?>))]
[JsonSerializable(typeof(string[]))]
[JsonSerializable(typeof(JsonElement))]
internal sealed partial class OpenAIJsonContext : JsonSerializerContext;
