// Copyright (c) Microsoft. All rights reserved.
#pragma warning disable CA1852 // Use sealed class
#pragma warning disable IDE0161 // Convert to file-scoped namespace
#pragma warning disable CA1063 // Implement IDisposable Correctly
#pragma warning disable CA1816 // Implement IDisposable Correctly

// Proposal for a new Persistent Agents Chat Client code based on the Azure.AI.Agents.Persistent library.
// Source: https://raw.githubusercontent.com/Azure/azure-sdk-for-net/0497c087147/sdk/ai/Azure.AI.Agents.Persistent/src/Custom/PersistentAgentsChatClient.cs

#nullable enable

using System.Collections;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Azure.AI.Agents.Persistent
{
    /// <summary>Represents an <see cref="IChatClient"/> for an Azure.AI.Agents.Persistent <see cref="PersistentAgentsClient"/>.</summary>
    internal partial class NewPersistentAgentsChatClient : IChatClient, ICancelableChatClient
    {
        /// <summary>The name of the chat client provider.</summary>
        private const string ProviderName = "azure";

        /// <summary>The underlying <see cref="PersistentAgentsClient" />.</summary>
        private readonly PersistentAgentsClient? _client;

        /// <summary>Metadata for the client.</summary>
        private readonly ChatClientMetadata? _metadata;

        /// <summary>The ID of the agent to use.</summary>
        private readonly string? _agentId;

        /// <summary>The thread ID to use if none is supplied in <see cref="ChatOptions.ConversationId"/>.</summary>
        private readonly string? _defaultThreadId;

        /// <summary>Lazily-retrieved agent instance. Used for its properties.</summary>
        private PersistentAgent? _agent;

        /// <summary>Enables long-running responses mode for the chat client, if set to <see langword="true"/>.</summary>
        private readonly bool? _enableLongRunningResponses;

        /// <summary>Initializes a new instance of the <see cref="PersistentAgentsChatClient"/> class for the specified <see cref="PersistentAgentsClient"/>.</summary>
        public NewPersistentAgentsChatClient(PersistentAgentsClient client, string agentId, string? defaultThreadId = null, bool? enableLongRunningOperations = null)
        {
            Argument.AssertNotNull(client, nameof(client));
            Argument.AssertNotNullOrWhiteSpace(agentId, nameof(agentId));

            _client = client;
            _agentId = agentId;
            _defaultThreadId = defaultThreadId;
            _enableLongRunningResponses = enableLongRunningOperations;

            _metadata = new(ProviderName);
        }

        /// <inheritdoc />
        public virtual object? GetService(Type serviceType, object? serviceKey = null) =>
            serviceType is null ? throw new ArgumentNullException(nameof(serviceType)) :
            serviceKey is not null ? null :
            serviceType == typeof(ChatClientMetadata) ? _metadata :
            serviceType == typeof(PersistentAgentsClient) ? _client :
            serviceType.IsInstanceOfType(this) ? this :
            null;

        /// <inheritdoc />
        public virtual async Task<ChatResponse> GetResponseAsync(
            IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
        {
            // Changing the original implementation to provide a RawRepresentation as a list of RawRepresentations of the updates.
            // This wouldn't be needed if the API Change Proposal below is accepted:
            // https://github.com/dotnet/extensions/issues/6746
            var updates = await GetStreamingResponseCoreAsync(messages, streamingCall: false, options, cancellationToken).ToListAsync(cancellationToken).ConfigureAwait(false);
            var response = updates.NewToChatResponse();

            // Expose all the raw representations of the updates.
            response.RawRepresentation = updates.Select(u => u.RawRepresentation).ToArray();
            return response;
        }

        /// <inheritdoc />
        public virtual async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await foreach (var update in GetStreamingResponseCoreAsync(messages, streamingCall: true, options, cancellationToken).ConfigureAwait(false))
            {
                yield return update;
            }
        }

        /// <inheritdoc />
        private async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseCoreAsync(
            IEnumerable<ChatMessage> messages, bool streamingCall, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            Argument.AssertNotNull(messages, nameof(messages));

            // Extract necessary state from messages and options.
            (ThreadAndRunOptions runOptions, List<FunctionResultContent>? toolResults) =
                await CreateRunOptionsAsync(messages, options, cancellationToken).ConfigureAwait(false);

            // Get the thread ID.
            string? threadId = options?.ConversationId ?? _defaultThreadId;
            if (threadId is null && toolResults is not null)
            {
                throw new ArgumentException("No thread ID was provided, but chat messages includes tool results.", nameof(messages));
            }

            // Get any active run ID for this thread.
            ThreadRun? threadRun = null;
            if (threadId is not null)
            {
                if (options is NewChatOptions { ResponseId: string runId })
                {
                    threadRun = await _client!.Runs.GetRunAsync(threadId, runId, cancellationToken: cancellationToken).ConfigureAwait(false);
                }
                else
                {
                    await foreach (ThreadRun? run in _client!.Runs.GetRunsAsync(threadId, limit: 1, ListSortOrder.Descending, cancellationToken: cancellationToken).ConfigureAwait(false))
                    {
                        if (run.Status != RunStatus.Completed && run.Status != RunStatus.Cancelled && run.Status != RunStatus.Failed && run.Status != RunStatus.Expired)
                        {
                            threadRun = run;
                            break;
                        }
                    }
                }
            }

            // Submit the request.
            IAsyncEnumerable<StreamingUpdate> updates;
            if (toolResults is not null &&
                threadRun is not null &&
                ConvertFunctionResultsToToolOutput(toolResults, out List<ToolOutput>? toolOutputs) is { } toolRunId &&
                toolRunId == threadRun.Id)
            {
                // There's an active run and we have tool results to submit, so submit the results and continue streaming.
                // This is going to ignore any additional messages in the run options, as we are only submitting tool outputs,
                // but there doesn't appear to be a way to submit additional messages, and having such additional messages is rare.
                updates = _client!.Runs.SubmitToolOutputsToStreamAsync(threadRun, toolOutputs, cancellationToken);
            }
            else
            {
                if (options is NewChatOptions { ResponseId: not null } && threadRun is not null)
                {
                    await foreach (var update in GetRunUpdatesAsync(threadRun!, streamingCall, options, cancellationToken).ConfigureAwait(false))
                    {
                        yield return update;
                    }
                    yield break;
                }

                if (threadId is null)
                {
                    // No thread ID was provided, so create a new thread.
                    PersistentAgentThread thread = await _client!.Threads.CreateThreadAsync(runOptions.ThreadOptions.Messages, runOptions.ToolResources, runOptions.Metadata, cancellationToken).ConfigureAwait(false);
                    runOptions.ThreadOptions.Messages.Clear();
                    threadId = thread.Id;
                }
                else if (threadRun is not null)
                {
                    // There was an active run; we need to cancel it before starting a new run.
                    await _client!.Runs.CancelRunAsync(threadId, threadRun.Id, cancellationToken).ConfigureAwait(false);
                    threadRun = null;
                }

                // Now create a new run and stream the results.
                CreateRunStreamingOptions opts = new()
                {
                    OverrideModelName = runOptions.OverrideModelName,
                    OverrideInstructions = runOptions.OverrideInstructions,
                    AdditionalInstructions = null,
                    AdditionalMessages = runOptions.ThreadOptions.Messages,
                    OverrideTools = runOptions.OverrideTools,
                    ToolResources = runOptions.ToolResources,
                    Temperature = runOptions.Temperature,
                    TopP = runOptions.TopP,
                    MaxPromptTokens = runOptions.MaxPromptTokens,
                    MaxCompletionTokens = runOptions.MaxCompletionTokens,
                    TruncationStrategy = runOptions.TruncationStrategy,
                    ToolChoice = runOptions.ToolChoice,
                    ResponseFormat = runOptions.ResponseFormat,
                    ParallelToolCalls = runOptions.ParallelToolCalls,
                    Metadata = runOptions.Metadata
                };

                // This method added for compatibility, before the include parameter support was enabled.
                updates = _client!.Runs.CreateRunStreamingAsync(
                    threadId: threadId,
                    agentId: _agentId,
                    options: opts,
                    cancellationToken: cancellationToken
                );
            }

            // Process each update.
            string? responseId = null;
            RunStatus runStatus = RunStatus.InProgress;
            bool isFirstUpdate = true;
            string? stepId = null;
            await foreach (StreamingUpdate? update in updates.ConfigureAwait(false))
            {
                switch (update)
                {
                    case ThreadUpdate tu:
                        threadId ??= tu.Value.Id;
                        goto default;

                    case RunStepUpdate rsu:
                        stepId = rsu.Value.Id;
                        goto default;

                    case RunUpdate ru:
                        threadId ??= ru.Value.ThreadId;
                        responseId ??= ru.Value.Id;
                        runStatus = ru.Value.Status;

                        NewChatResponseUpdate ruUpdate = new()
                        {
                            AuthorName = ru.Value.AssistantId,
                            ConversationId = threadId,
                            CreatedAt = ru.Value.CreatedAt,
                            MessageId = responseId,
                            ModelId = ru.Value.Model,
                            RawRepresentation = ru,
                            ResponseId = responseId,
                            Role = ChatRole.Assistant,
                            Status = ToResponseStatus(runStatus, options),
                        };

                        if (ru.Value.Usage is { } usage)
                        {
                            ruUpdate.Contents.Add(new UsageContent(new()
                            {
                                InputTokenCount = usage.PromptTokens,
                                OutputTokenCount = usage.CompletionTokens,
                                TotalTokenCount = usage.TotalTokens,
                            }));
                        }

                        if (ru is RequiredActionUpdate rau && rau.ToolCallId is string toolCallId && rau.FunctionName is string functionName)
                        {
                            ruUpdate.Contents.Add(
                                new FunctionCallContent(
                                    JsonSerializer.Serialize([ru.Value.Id, toolCallId], AgentsChatClientJsonContext.Default.StringArray),
                                    functionName,
                                    JsonSerializer.Deserialize(rau.FunctionArguments, AgentsChatClientJsonContext.Default.IDictionaryStringObject)!));
                        }

                        yield return ruUpdate;

                        // Stop here if this is the first non-streaming update and we are not awaiting the run result.
                        if (isFirstUpdate && !streamingCall)
                        {
                            isFirstUpdate = false;
                            if (IsLongRunningResponsesModeEnabled(options) && (options as NewChatOptions)?.ResponseId is null)
                            {
                                yield break;
                            }
                        }
                        break;

                    case MessageContentUpdate mcu:
                        NewChatResponseUpdate textUpdate = new(mcu.Role == MessageRole.User ? ChatRole.User : ChatRole.Assistant, mcu.Text)
                        {
                            AuthorName = _agentId,
                            ConversationId = threadId,
                            MessageId = responseId,
                            RawRepresentation = mcu,
                            ResponseId = responseId,
                            Status = ToResponseStatus(runStatus, options),
                        };

                        // Add any annotations from the text update. The OpenAI Assistants API does not support passing these back
                        // into the model (MessageContent.FromXx does not support providing annotations), so they end up being one way and are dropped
                        // on subsequent requests.
                        if (mcu.TextAnnotation is { } tau)
                        {
                            string? fileId = null;
                            string? toolName = null;
                            if (!string.IsNullOrWhiteSpace(tau.InputFileId))
                            {
                                fileId = tau.InputFileId;
                                toolName = "file_search";
                            }
                            else if (!string.IsNullOrWhiteSpace(tau.OutputFileId))
                            {
                                fileId = tau.OutputFileId;
                                toolName = "code_interpreter";
                            }

                            if (fileId is not null)
                            {
                                if (textUpdate.Contents.Count == 0)
                                {
                                    // In case a chunk doesn't have text content, create one with empty text to hold the annotation.
                                    textUpdate.Contents.Add(new TextContent(string.Empty));
                                }

                                (((TextContent)textUpdate.Contents[0]).Annotations ??= []).Add(new CitationAnnotation
                                {
                                    RawRepresentation = tau,
                                    AnnotatedRegions = [new TextSpanAnnotatedRegion { StartIndex = tau.StartIndex, EndIndex = tau.EndIndex }],
                                    FileId = fileId,
                                    ToolName = toolName,
                                });
                            }
                        }

                        yield return textUpdate;
                        break;

                    default:
                    {
                        var updateToReturn = new NewChatResponseUpdate
                        {
                            AuthorName = _agentId,
                            ConversationId = threadId,
                            MessageId = responseId,
                            RawRepresentation = update,
                            ResponseId = responseId,
                            Role = ChatRole.Assistant,
                            Status = ToResponseStatus(runStatus, options),
                            SequenceNumber = stepId,
                        };

                        yield return updateToReturn;
                        break;
                    }
                }
            }
        }

        /// <inheritdoc />
        public void Dispose() { }

        /// <summary>
        /// Creates the <see cref="ThreadAndRunOptions"/> to use for the request and extracts any function result contents
        /// that need to be submitted as tool results.
        /// </summary>
        private async ValueTask<(ThreadAndRunOptions RunOptions, List<FunctionResultContent>? ToolResults)> CreateRunOptionsAsync(
            IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken cancellationToken)
        {
            // Create the options instance to populate, either a fresh or using one the caller provides.
            ThreadAndRunOptions runOptions =
                options?.RawRepresentationFactory?.Invoke(this) as ThreadAndRunOptions ??
                new();

            // Load details about the agent if not already loaded.
            if (_agent is null)
            {
                PersistentAgent agent = await _client!.Administration.GetAgentAsync(_agentId, cancellationToken).ConfigureAwait(false);
                Interlocked.CompareExchange(ref _agent, agent, null);
            }

            // Populate the run options from the ChatOptions, if provided.
            if (options is not null)
            {
                runOptions.OverrideInstructions ??= options.Instructions ?? _agent.Instructions;
                runOptions.MaxCompletionTokens ??= options.MaxOutputTokens;
                runOptions.OverrideModelName ??= options.ModelId;
                runOptions.TopP ??= options.TopP;
                runOptions.Temperature ??= options.Temperature;
                runOptions.ParallelToolCalls ??= options.AllowMultipleToolCalls;
                // Ignored: options.TopK, options.FrequencyPenalty, options.Seed, options.StopSequences

                if (options.Tools is { Count: > 0 } tools)
                {
                    List<ToolDefinition> toolDefinitions = [];
                    ToolResources? toolResources = null;

                    // If the caller has provided any tool overrides, we'll assume they don't want to use the agent's tools.
                    // But if they haven't, the only way we can provide our tools is via an override, whereas we'd really like to
                    // just add them. To handle that, we'll get all of the agent's tools and add them to the override list
                    // along with our tools.
                    if (runOptions.OverrideTools is null || !runOptions.OverrideTools.Any())
                    {
                        toolDefinitions.AddRange(_agent.Tools);
                    }

                    // The caller can provide tools in the supplied ThreadAndRunOptions.
                    if (runOptions.OverrideTools is not null)
                    {
                        toolDefinitions.AddRange(runOptions.OverrideTools);
                    }

                    // Now add the tools from ChatOptions.Tools.
                    foreach (AITool tool in tools)
                    {
                        switch (tool)
                        {
                            case AIFunction aiFunction:
                                toolDefinitions.Add(new FunctionToolDefinition(
                                    aiFunction.Name,
                                    aiFunction.Description,
                                    BinaryData.FromBytes(JsonSerializer.SerializeToUtf8Bytes(aiFunction.JsonSchema, AgentsChatClientJsonContext.Default.JsonElement))));
                                break;

                            case HostedCodeInterpreterTool codeTool:
                                toolDefinitions.Add(new CodeInterpreterToolDefinition());

                                if (codeTool.Inputs is { Count: > 0 })
                                {
                                    foreach (var input in codeTool.Inputs)
                                    {
                                        switch (input)
                                        {
                                            case HostedFileContent hostedFile:
                                                // If the input is a HostedFileContent, we can use its ID directly.
                                                (toolResources ??= new() { CodeInterpreter = new() }).CodeInterpreter.FileIds.Add(hostedFile.FileId);
                                                break;
                                        }
                                    }
                                }
                                break;

                            case HostedFileSearchTool fileSearchTool:
                                toolDefinitions.Add(new FileSearchToolDefinition()
                                {
                                    FileSearch = new() { MaxNumResults = fileSearchTool.MaximumResultCount }
                                });

                                if (fileSearchTool.Inputs is { Count: > 0 })
                                {
                                    foreach (var input in fileSearchTool.Inputs)
                                    {
                                        switch (input)
                                        {
                                            case HostedVectorStoreContent hostedVectorStore:
                                                (toolResources ??= new() { FileSearch = new() }).FileSearch.VectorStoreIds.Add(hostedVectorStore.VectorStoreId);
                                                break;
                                        }
                                    }
                                }
                                break;

                            case HostedWebSearchTool webSearch when webSearch.AdditionalProperties?.TryGetValue("connectionId", out object? connectionId) is true:
                                toolDefinitions.Add(new BingGroundingToolDefinition(new BingGroundingSearchToolParameters([new BingGroundingSearchConfiguration(connectionId!.ToString())])));
                                break;
                        }
                    }

                    if (toolDefinitions.Count > 0)
                    {
                        runOptions.OverrideTools = toolDefinitions;
                    }

                    if (toolResources is not null)
                    {
                        runOptions.ToolResources = toolResources;
                    }
                }

                // Store the tool mode, if relevant.
                if (runOptions.ToolChoice is null)
                {
                    switch (options.ToolMode)
                    {
                        case NoneChatToolMode:
                            runOptions.ToolChoice = BinaryData.FromString("\"none\"");
                            break;

                        case RequiredChatToolMode required:
                            runOptions.ToolChoice = required.RequiredFunctionName is string functionName ?
                                BinaryData.FromString($$"""{"type": "function", "function": {"name": "{{functionName}}"} }""") :
                                BinaryData.FromString("required");
                            break;
                        case AutoChatToolMode:
                            runOptions.ToolChoice = BinaryData.FromString("\"auto\"");
                            break;
                    }
                }

                // Store the response format, if relevant.
                if (runOptions.ResponseFormat is null)
                {
                    if (options.ResponseFormat is ChatResponseFormatJson jsonFormat)
                    {
                        if (jsonFormat.Schema is JsonElement schema)
                        {
                            var schemaNode = JsonSerializer.SerializeToNode(schema, AgentsChatClientJsonContext.Default.JsonElement)!;

                            var jsonSchemaObject = new JsonObject
                            {
                                ["schema"] = schemaNode
                            };

                            if (jsonFormat.SchemaName is not null)
                            {
                                jsonSchemaObject["name"] = jsonFormat.SchemaName;
                            }
                            if (jsonFormat.SchemaDescription is not null)
                            {
                                jsonSchemaObject["description"] = jsonFormat.SchemaDescription;
                            }

                            runOptions.ResponseFormat =
                                BinaryData.FromBytes(JsonSerializer.SerializeToUtf8Bytes(new()
                                {
                                    ["type"] = "json_schema",
                                    ["json_schema"] = jsonSchemaObject,
                                }, AgentsChatClientJsonContext.Default.JsonObject));
                        }
                        else
                        {
                            runOptions.ResponseFormat = BinaryData.FromString("""{ "type": "json_object" }""");
                        }
                    }
                    else if (options.ResponseFormat is ChatResponseFormatText textFormat)
                    {
                        runOptions.ResponseFormat = BinaryData.FromString("""{ "type": "text" }""");
                    }
                }
            }

            // Process ChatMessages. System messages are turned into additional instructions.
            // All other messages are added 1:1, treating assistant messages as agent messages
            // and everything else as user messages.
            StringBuilder? instructions = null;
            List<FunctionResultContent>? functionResults = null;

            runOptions.ThreadOptions ??= new();

            bool treatInstructionsAsOverride = false;
            if (runOptions.OverrideInstructions is not null)
            {
                treatInstructionsAsOverride = true;
                (instructions ??= new()).Append(runOptions.OverrideInstructions);
            }

            if (options?.Instructions is not null)
            {
                (instructions ??= new()).Append(options.Instructions);
            }

            foreach (ChatMessage chatMessage in messages)
            {
                List<MessageInputContentBlock> messageContents = [];

                if (chatMessage.Role == ChatRole.System ||
                    chatMessage.Role == new ChatRole("developer"))
                {
                    instructions ??= new();
                    foreach (TextContent textContent in chatMessage.Contents.OfType<TextContent>())
                    {
                        _ = instructions.Append(textContent);
                    }

                    continue;
                }

                foreach (AIContent content in chatMessage.Contents)
                {
                    switch (content)
                    {
                        case TextContent text:
                            messageContents.Add(new MessageInputTextBlock(text.Text));
                            break;

                        case DataContent image when image.HasTopLevelMediaType("image"):
                            messageContents.Add(new MessageInputImageUriBlock(new MessageImageUriParam(image.Uri)));
                            break;

                        case UriContent image when image.HasTopLevelMediaType("image"):
                            messageContents.Add(new MessageInputImageUriBlock(new MessageImageUriParam(image.Uri.AbsoluteUri)));
                            break;

                        case FunctionResultContent result:
                            (functionResults ??= []).Add(result);
                            break;

                        default:
                            if (content.RawRepresentation is MessageInputContentBlock rawContent)
                            {
                                messageContents.Add(rawContent);
                            }
                            break;
                    }
                }

                if (messageContents.Count > 0)
                {
                    runOptions.ThreadOptions.Messages.Add(new ThreadMessageOptions(
                        chatMessage.Role == ChatRole.Assistant ? MessageRole.Agent : MessageRole.User,
                        messageContents));
                }
            }

            if (instructions is not null)
            {
                // If runOptions.OverrideInstructions was set by the caller, then all instructions are treated
                // as an override. Otherwise, we want all of the instructions to augment the agent's instructions,
                // so insert the agent's at the beginning.
                if (!treatInstructionsAsOverride && !string.IsNullOrEmpty(_agent.Instructions))
                {
                    instructions.Insert(0, _agent.Instructions);
                }

                runOptions.OverrideInstructions = instructions.ToString();
            }

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
                foreach (FunctionResultContent frc in toolResults)
                {
                    // When creating the FunctionCallContext, we created it with a CallId == [runId, callId].
                    // We need to extract the run ID and ensure that the ToolOutput we send back to Azure
                    // is only the call ID.
                    string[]? runAndCallIDs;
                    try
                    {
                        runAndCallIDs = JsonSerializer.Deserialize(frc.CallId, AgentsChatClientJsonContext.Default.StringArray);
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

        /// <summary>Converts a <see cref="RunStatus"/> to a <see cref="NewResponseStatus"/>.</summary>
        private NewResponseStatus? ToResponseStatus(RunStatus? status, ChatOptions? options)
        {
            // Unless the new behavior of not awaiting run completion is requested, we don't return a status
            if (status is null || !IsLongRunningResponsesModeEnabled(options))
            {
                return null;
            }

            if (status == RunStatus.Queued)
            {
                return NewResponseStatus.Queued;
            }

            if (status == RunStatus.InProgress)
            {
                return NewResponseStatus.InProgress;
            }

            if (status == RunStatus.RequiresAction)
            {
                return NewResponseStatus.RequiresAction;
            }

            if (status == RunStatus.Cancelling)
            {
                return NewResponseStatus.Canceling;
            }

            if (status == RunStatus.Cancelled)
            {
                return NewResponseStatus.Canceled;
            }

            if (status == RunStatus.Failed)
            {
                return NewResponseStatus.Failed;
            }

            if (status == RunStatus.Completed)
            {
                return NewResponseStatus.Completed;
            }

            if (status == RunStatus.Expired)
            {
                return NewResponseStatus.Expired;
            }

            throw new ArgumentOutOfRangeException(nameof(status), status, "Unknown response status.");
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
            return _enableLongRunningResponses ?? false;
        }

        private async IAsyncEnumerable<ChatResponseUpdate> GetRunUpdatesAsync(ThreadRun run, bool streamingCall, ChatOptions? options, [EnumeratorCancellation] CancellationToken cancellationToken)
        {
            // If this method is called via streaming api, we keep polling the run until the end.
            if (streamingCall)
            {
                // Return updates for the provided run first.
                await foreach (var update in GetRunUpdates_InternalAsync(run, options, cancellationToken).ConfigureAwait(false))
                {
                    yield return update;
                }

                // Keep polling the run and returning its updates until it completes.
                while (run.Status == RunStatus.Queued || run.Status == RunStatus.InProgress || run.Status == RunStatus.Cancelling)
                {
                    //TBD: Use polling settings
                    await Task.Delay(500, cancellationToken).ConfigureAwait(false);
                    run = await _client!.Runs.GetRunAsync(run.ThreadId, (options as NewChatOptions)?.ResponseId, cancellationToken: cancellationToken).ConfigureAwait(false);

                    // Return any new updates.
                    await foreach (var update in GetRunUpdates_InternalAsync(run, options, cancellationToken).ConfigureAwait(false))
                    {
                        yield return update;
                    }
                }
            }
            // If this method is called via non-streaming api, we either poll to completion if requested or return the current status.
            else
            {
                await foreach (var update in GetRunUpdates_InternalAsync(run, options, cancellationToken).ConfigureAwait(false))
                {
                    yield return update;
                }
            }

            async IAsyncEnumerable<ChatResponseUpdate> GetRunUpdates_InternalAsync(ThreadRun run, ChatOptions? options, [EnumeratorCancellation] CancellationToken cancellationToken)
            {
                if (run.Status == RunStatus.Completed || run.Status == RunStatus.Cancelled || run.Status == RunStatus.Failed || run.Status == RunStatus.Expired)
                {
                    List<RunStep> steps = [];

                    string? stepIdToStartAfter = (options as NewChatOptions)?.StartAfter;
                    bool skipSteps = !string.IsNullOrWhiteSpace(stepIdToStartAfter);

                    await foreach (var step in _client!.Runs.GetRunStepsAsync(run, order: ListSortOrder.Ascending, cancellationToken: cancellationToken).ConfigureAwait(false))
                    {
                        // Skipping all steps until we find the one to start after.
                        if (step.Id == stepIdToStartAfter)
                        {
                            skipSteps = false;
                            continue;
                        }

                        if (skipSteps)
                        {
                            continue;
                        }

                        steps.Add(step);
                    }

                    foreach (RunStep step in steps)
                    {
                        if (step.Type == RunStepType.ToolCalls)
                        {
                            // TBD: Handle tool calls
                        }
                        else if (step.Type == RunStepType.MessageCreation)
                        {
                            RunStepMessageCreationDetails messageDetails = (RunStepMessageCreationDetails)step.StepDetails;

                            var message = await _client.Messages.GetMessageAsync(step.ThreadId, messageDetails.MessageCreation.MessageId, cancellationToken).ConfigureAwait(false);

                            yield return this.CreateChatResponseUpdate(run, options, step, message);
                        }
                    }
                }
                else if (run.Status == RunStatus.Queued || run.Status == RunStatus.InProgress || run.Status == RunStatus.Cancelling)
                {
                    yield return this.CreateChatResponseUpdate(run, options);
                }
                else if (run.Status == RunStatus.RequiresAction)
                {
                    await foreach (var step in _client!.Runs.GetRunStepsAsync(run, cancellationToken: cancellationToken).ConfigureAwait(false))
                    {
                        var functionCallContents = GetFunctionCallContents(step);

                        yield return this.CreateChatResponseUpdate(run, options, step, functionCallContents: functionCallContents);
                    }
                }
            }
        }

        private NewChatResponseUpdate CreateChatResponseUpdate(ThreadRun run, ChatOptions? options, RunStep? step = null, PersistentThreadMessage? message = null, IEnumerable<FunctionCallContent>? functionCallContents = null)
        {
            var update = new NewChatResponseUpdate
            {
                AuthorName = run.AssistantId,
                ConversationId = run.ThreadId,
                CreatedAt = message?.CreatedAt ?? step?.CreatedAt ?? run.CreatedAt,
                MessageId = message?.Id ?? step?.Id ?? run.Id,
                ModelId = run.Model,
                RawRepresentation = message ?? step as object ?? run,
                ResponseId = run.Id,
                Role = message?.Role == MessageRole.User ? ChatRole.User : ChatRole.Assistant,
                Status = this.ToResponseStatus(run.Status, options),
                SequenceNumber = step?.Id,
            };

            if (run.Usage is { } usage)
            {
                update.Contents.Add(new UsageContent(new()
                {
                    InputTokenCount = usage.PromptTokens,
                    OutputTokenCount = usage.CompletionTokens,
                    TotalTokenCount = usage.TotalTokens,
                }));
            }

            foreach (MessageContent itemContent in message?.ContentItems ?? [])
            {
                if (itemContent is MessageTextContent textContent)
                {
                    update.Contents.Add(new TextContent(textContent.Text));

                    // TBD: Handle annotations
                }
                else if (itemContent is MessageImageFileContent imageContent)
                {
                    update.Contents.Add(new HostedFileContent(imageContent.FileId));
                }
            }

            foreach (FunctionCallContent functionCallContent in functionCallContents ?? [])
            {
                update.Contents.Add(functionCallContent);
            }

            return update;
        }

        private static IEnumerable<FunctionCallContent> GetFunctionCallContents(RunStep step)
        {
            if (step.Status == RunStepStatus.InProgress && step.Type == RunStepType.ToolCalls)
            {
                RunStepToolCallDetails toolCallDetails = (RunStepToolCallDetails)step.StepDetails;

                foreach (RunStepToolCall toolCall in toolCallDetails.ToolCalls)
                {
                    if (toolCall is RunStepFunctionToolCall functionCall)
                    {
                        yield return new FunctionCallContent(
                            callId: JsonSerializer.Serialize([step.RunId, toolCall.Id], AgentsChatClientJsonContext.Default.StringArray),
                            name: functionCall.Name,
                            arguments: JsonSerializer.Deserialize(functionCall.Arguments, AgentsChatClientJsonContext.Default.IDictionaryStringObject)!);
                    }
                }
            }
        }

        public async Task<ChatResponse?> CancelResponseAsync(string id, CancelResponseOptions? options = null, CancellationToken cancellationToken = default)
        {
            Throw.IfNullOrEmpty(id);
            Throw.IfNullOrEmpty(options?.ConversationId);

            ThreadRun run;

            try
            {
                run = await _client!.Runs.CancelRunAsync(threadId: options.ConversationId, runId: id, cancellationToken).ConfigureAwait(false);
            }
            // Swallow the exception if the run is already completed. Original message: "Cannot cancel run with status 'completed'"
            catch (RequestFailedException ex) when (ex.Status == 400 && ex.Message.Contains("completed"))
            {
                return null;
            }
            // Do nothing if the run is not found.
            catch (RequestFailedException ex) when (ex.Status == 404)
            {
                return null;
            }

            // Setting AllowBackgroundResponses to true here only to get the `Status` property set in the response.
            return new[] { CreateChatResponseUpdate(run, new NewChatOptions { AllowBackgroundResponses = true }) }.NewToChatResponse();
        }

        [JsonSerializable(typeof(JsonElement))]
        [JsonSerializable(typeof(JsonNode))]
        [JsonSerializable(typeof(JsonObject))]
        [JsonSerializable(typeof(string[]))]
        [JsonSerializable(typeof(IDictionary<string, object>))]
        private sealed partial class AgentsChatClientJsonContext : JsonSerializerContext;
    }

    internal static class Argument
    {
        public static void AssertNotNull<T>(T value, string name)
        {
            if (value is null)
            {
                throw new ArgumentNullException(name);
            }
        }

        public static void AssertNotNull<T>(T? value, string name)
        where T : struct
        {
            if (!value.HasValue)
            {
                throw new ArgumentNullException(name);
            }
        }

        public static void AssertNotNullOrEmpty<T>(IEnumerable<T> value, string name)
        {
            if (value is null)
            {
                throw new ArgumentNullException(name);
            }
            if (value is ICollection<T> collectionOfT && collectionOfT.Count == 0)
            {
                throw new ArgumentException("Value cannot be an empty collection.", name);
            }
            if (value is ICollection collection && collection.Count == 0)
            {
                throw new ArgumentException("Value cannot be an empty collection.", name);
            }
            using IEnumerator<T> e = value.GetEnumerator();
            if (!e.MoveNext())
            {
                throw new ArgumentException("Value cannot be an empty collection.", name);
            }
        }

        public static void AssertNotNullOrEmpty(string value, string name)
        {
            if (value is null)
            {
                throw new ArgumentNullException(name);
            }
            if (value.Length == 0)
            {
                throw new ArgumentException("Value cannot be an empty string.", name);
            }
        }

        public static void AssertNotNullOrWhiteSpace(string value, string name)
        {
            if (value is null)
            {
                throw new ArgumentNullException(name);
            }
            if (string.IsNullOrWhiteSpace(value))
            {
                throw new ArgumentException("Value cannot be empty or contain only white-space characters.", name);
            }
        }

        public static void AssertNotDefault<T>(ref T value, string name)
        where T : struct, IEquatable<T>
        {
            if (value.Equals(default))
            {
                throw new ArgumentException("Value cannot be empty.", name);
            }
        }

        public static void AssertInRange<T>(T value, T minimum, T maximum, string name)
        where T : notnull, IComparable<T>
        {
            if (minimum.CompareTo(value) > 0)
            {
                throw new ArgumentOutOfRangeException(name, "Value is less than the minimum allowed.");
            }
            if (maximum.CompareTo(value) < 0)
            {
                throw new ArgumentOutOfRangeException(name, "Value is greater than the maximum allowed.");
            }
        }

        public static void AssertEnumDefined(Type enumType, object value, string name)
        {
            if (!Enum.IsDefined(enumType, value))
            {
                throw new ArgumentException($"Value not defined for {enumType.FullName}.", name);
            }
        }

        public static T CheckNotNull<T>(T value, string name)
        where T : class
        {
            AssertNotNull(value, name);
            return value;
        }

        public static string CheckNotNullOrEmpty(string value, string name)
        {
            AssertNotNullOrEmpty(value, name);
            return value;
        }

        public static void AssertNull<T>(T value, string name, string? message = null)
        {
            if (value != null)
            {
                throw new ArgumentException(message ?? "Value must be null.", name);
            }
        }
    }
}
