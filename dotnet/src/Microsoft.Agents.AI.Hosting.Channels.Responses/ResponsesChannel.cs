// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.Channels.Responses;

/// <summary>
/// OpenAI Responses-shaped channel. Mounts a single <c>POST {Path}</c> endpoint that accepts a Responses
/// request body and returns either a Responses JSON object (<c>stream=false</c>, default) or a
/// Server-Sent-Events stream (<c>stream=true</c>). The channel owns protocol parsing and rendering; the host
/// owns target invocation and session resolution.
/// </summary>
public sealed class ResponsesChannel : Channel
{
    private readonly ResponsesChannelOptions _options;

    /// <summary>Initializes a new instance.</summary>
    public ResponsesChannel(ResponsesChannelOptions options)
    {
        this._options = Throw.IfNull(options);
    }

    /// <inheritdoc />
    public override string Name => "responses";

    /// <inheritdoc />
    public override string Path => this._options.Path;

    /// <inheritdoc />
    public override ChannelContribution Contribute(ChannelContext context)
    {
        Throw.IfNull(context);
        return new ChannelContribution
        {
            Routes = [endpoints => endpoints.MapPost("/", (HttpContext http) => this.HandleAsync(context, http))],
        };
    }

    private async Task HandleAsync(ChannelContext context, HttpContext http)
    {
        ResponsesRequestModel? body;
        try
        {
            body = await JsonSerializer.DeserializeAsync(http.Request.Body, ResponsesJsonContext.Default.ResponsesRequestModel, http.RequestAborted).ConfigureAwait(false);
        }
        catch (JsonException ex)
        {
            await WriteErrorAsync(http, StatusCodes.Status400BadRequest, ex.Message).ConfigureAwait(false);
            return;
        }

        if (body is null)
        {
            await WriteErrorAsync(http, StatusCodes.Status400BadRequest, "Request body is required.").ConfigureAwait(false);
            return;
        }

        IReadOnlyList<ChatMessage> messages;
        try
        {
            messages = ResponsesParsing.MessagesFromInput(body.Input);
        }
        catch (FormatException ex)
        {
            await WriteErrorAsync(http, StatusCodes.Status422UnprocessableEntity, ex.Message).ConfigureAwait(false);
            return;
        }

        // Session anchoring (mirrors Python `_handle`): an explicit `previous_response_id` wins; else a
        // host-lifted Foundry chat isolation key; else the freshly minted response id anchors the first turn.
        var previousResponseId = string.IsNullOrEmpty(body.PreviousResponseId) ? null : body.PreviousResponseId;
        ChannelSession? session = previousResponseId is not null ? new ChannelSession { IsolationKey = previousResponseId } : null;

        if (session is null)
        {
            var chatKey = IsolationKeys.Current?.ChatKey;
            if (!string.IsNullOrEmpty(chatKey))
            {
                session = new ChannelSession { IsolationKey = chatKey };
            }
        }

        var responseId = (this._options.ResponseIdFactory ?? s_defaultResponseIdFactory)(previousResponseId);
        session ??= new ChannelSession { IsolationKey = responseId };

        // The minted response id (and any previous id) travel on attributes so a host-side history provider
        // can anchor the storage chain on the same handle the envelope reports.
        var attributes = new Dictionary<string, object?>(StringComparer.Ordinal) { ["response_id"] = responseId };
        if (previousResponseId is not null)
        {
            attributes["previous_response_id"] = previousResponseId;
        }

        var request = new ChannelRequest(this.Name, "message.create", messages)
        {
            Stream = body.Stream,
            Session = session,
            Identity = ResponsesParsing.ParseIdentity(body, this.Name),
            Options = ResponsesParsing.BuildOptions(body),
            Attributes = attributes,
        };

        if (this._options.RunHook is not null)
        {
            var hookContext = new ChannelRunHookContext(context.Host) { ProtocolRequest = body };
            request = await this._options.RunHook.OnRequestAsync(request, hookContext, http.RequestAborted).ConfigureAwait(false);
        }
        else
        {
            // Default behavior strips parsed generation options so untrusted callers cannot inject parameters.
            request.Options = null;
        }

        try
        {
            if (request.Stream)
            {
                await this.WriteStreamAsync(context, request, body.Model, responseId, http).ConfigureAwait(false);
            }
            else
            {
                await this.WriteJsonResponseAsync(context, request, body.Model, responseId, http).ConfigureAwait(false);
            }
        }
        catch (Exception ex)
        {
            await WriteErrorAsync(http, StatusCodes.Status500InternalServerError, ex.Message).ConfigureAwait(false);
        }
    }

    private async Task WriteJsonResponseAsync(ChannelContext context, ChannelRequest request, string? model, string responseId, HttpContext http)
    {
        var result = await context.RunAsync(request, http.RequestAborted).ConfigureAwait(false);
        result = await this.ApplyResponseHookAsync(result, request, http.RequestAborted).ConfigureAwait(false);

        var response = BuildEnvelope(responseId, model, status: "completed");
        response.Output.AddRange(BuildOutputItems(result.ResultObject));
        response.Usage = BuildUsage(result.ResultObject as AgentResponse);

        http.Response.StatusCode = StatusCodes.Status200OK;
        http.Response.ContentType = "application/json; charset=utf-8";
        await JsonSerializer.SerializeAsync(http.Response.Body, response, ResponsesJsonContext.Default.ResponsesResponseModel, http.RequestAborted).ConfigureAwait(false);
    }

    private async Task WriteStreamAsync(ChannelContext context, ChannelRequest request, string? model, string responseId, HttpContext http)
    {
        http.Response.StatusCode = StatusCodes.Status200OK;
        http.Response.ContentType = "text/event-stream";
        http.Response.Headers.CacheControl = "no-cache";

        var itemId = "msg_" + Guid.NewGuid().ToString("N");
        var sb = new StringBuilder();
        var accumulated = new List<AgentResponseUpdate>();
        var nextOutputIndex = 1;
        HostedRunResult? finalResult = null;

        try
        {
            var created = BuildEnvelope(responseId, model, status: "in_progress");
            await WriteEventAsync(http, "response.created", new ResponsesStreamResponseEvent { Type = "response.created", Response = created }, ResponsesJsonContext.Default.ResponsesStreamResponseEvent).ConfigureAwait(false);

            var addedItem = new ResponsesOutputItem { Type = "message", Id = itemId, Role = "assistant", Status = "in_progress", Content = new JsonArray() };
            await WriteEventAsync(http, "response.output_item.added", new ResponsesStreamOutputItemEvent { Type = "response.output_item.added", OutputIndex = 0, Item = addedItem }, ResponsesJsonContext.Default.ResponsesStreamOutputItemEvent).ConfigureAwait(false);
            await WriteEventAsync(http, "response.content_part.added", new ResponsesStreamContentPartEvent { Type = "response.content_part.added", ItemId = itemId, OutputIndex = 0, ContentIndex = 0, Part = new ResponsesOutputText() }, ResponsesJsonContext.Default.ResponsesStreamContentPartEvent).ConfigureAwait(false);

            var updates = StreamUpdatesAsync(context.StreamAsync(request, http.RequestAborted), r => finalResult = r);
            var transformed = this._options.StreamTransformHook is { } hook
                ? hook.TransformAsync(updates, http.RequestAborted)
                : updates;

            await foreach (var update in transformed.ConfigureAwait(false))
            {
                accumulated.Add(update);
                foreach (var content in update.Contents)
                {
                    if (content is TextContent text)
                    {
                        if (!string.IsNullOrEmpty(text.Text))
                        {
                            sb.Append(text.Text);
                            var deltaEvent = new ResponsesStreamTextDeltaEvent { ItemId = itemId, OutputIndex = 0, ContentIndex = 0, Delta = text.Text };
                            await WriteEventAsync(http, "response.output_text.delta", deltaEvent, ResponsesJsonContext.Default.ResponsesStreamTextDeltaEvent).ConfigureAwait(false);
                        }

                        continue;
                    }

                    if (await this.EmitNonTextContentAsync(http, content, nextOutputIndex).ConfigureAwait(false))
                    {
                        nextOutputIndex++;
                    }
                }
            }
        }
        catch (Exception ex)
        {
            // Once the SSE stream has started, surface the error as a Responses `response.failed` event
            // rather than an (invalid) post-headers JSON error.
            var failed = BuildEnvelope(responseId, model, status: "failed");
            failed.Error = new ResponsesErrorBody { Message = ex.Message };
            await WriteEventAsync(http, "response.failed", new ResponsesStreamResponseEvent { Type = "response.failed", Response = failed }, ResponsesJsonContext.Default.ResponsesStreamResponseEvent).ConfigureAwait(false);
            return;
        }

        // Apply the response hook to the final streamed result (mirrors Python's stream get_final_response).
        if (finalResult is not null)
        {
            finalResult = await this.ApplyResponseHookAsync(finalResult, request, http.RequestAborted).ConfigureAwait(false);
        }

        var finalText = sb.ToString();
        await WriteEventAsync(http, "response.output_text.done", new ResponsesStreamTextDoneEvent { ItemId = itemId, OutputIndex = 0, ContentIndex = 0, Text = finalText }, ResponsesJsonContext.Default.ResponsesStreamTextDoneEvent).ConfigureAwait(false);

        var donePart = new ResponsesOutputText { Text = finalText };
        await WriteEventAsync(http, "response.content_part.done", new ResponsesStreamContentPartEvent { Type = "response.content_part.done", ItemId = itemId, OutputIndex = 0, ContentIndex = 0, Part = donePart }, ResponsesJsonContext.Default.ResponsesStreamContentPartEvent).ConfigureAwait(false);

        var doneItem = new ResponsesOutputItem { Type = "message", Id = itemId, Role = "assistant", Status = "completed", Content = new JsonArray(new JsonObject { ["type"] = "output_text", ["text"] = finalText, ["annotations"] = new JsonArray() }) };
        await WriteEventAsync(http, "response.output_item.done", new ResponsesStreamOutputItemEvent { Type = "response.output_item.done", OutputIndex = 0, Item = doneItem }, ResponsesJsonContext.Default.ResponsesStreamOutputItemEvent).ConfigureAwait(false);

        var completed = BuildEnvelope(responseId, model, status: "completed");
        if (finalResult?.ResultObject is AgentResponse hookResponse)
        {
            completed.Output.AddRange(BuildOutputItems(hookResponse));
        }
        else if (accumulated.Count > 0)
        {
            // Finalize unavailable (e.g. the agent stream could not produce a final response): render the
            // completed envelope from the accumulated streamed updates, matching Python's stream finalizer.
            completed.Output.AddRange(BuildOutputItems(accumulated.ToAgentResponse()));
        }
        else
        {
            completed.Output.Add(doneItem);
        }

        await WriteEventAsync(http, "response.completed", new ResponsesStreamResponseEvent { Type = "response.completed", Response = completed }, ResponsesJsonContext.Default.ResponsesStreamResponseEvent).ConfigureAwait(false);
    }

    /// <summary>
    /// Emits the SSE events for a single non-text streamed content. Reasoning and function-call content emit
    /// an in-progress item, their incremental delta/done events, then the completed item; every other
    /// renderable content emits an output_item.added/done pair carrying the rendered item. Returns whether an
    /// output item was produced (and thus the output index should advance).
    /// </summary>
    private async ValueTask<bool> EmitNonTextContentAsync(HttpContext http, AIContent content, int outputIndex)
    {
        switch (content)
        {
            case TextReasoningContent reasoning:
                var reasoningAdded = new ResponsesOutputItem { Type = "reasoning", Id = "rs_" + Guid.NewGuid().ToString("N"), Summary = new JsonArray(), Content = new JsonArray(), Status = "in_progress" };
                await this.WriteOutputItemEventAsync(http, "response.output_item.added", outputIndex, reasoningAdded).ConfigureAwait(false);
                if (!string.IsNullOrEmpty(reasoning.Text))
                {
                    await WriteEventAsync(http, "response.reasoning_text.delta", new ResponsesStreamReasoningTextDeltaEvent { ItemId = reasoningAdded.Id, OutputIndex = outputIndex, ContentIndex = 0, Delta = reasoning.Text! }, ResponsesJsonContext.Default.ResponsesStreamReasoningTextDeltaEvent).ConfigureAwait(false);
                    await WriteEventAsync(http, "response.reasoning_text.done", new ResponsesStreamReasoningTextDoneEvent { ItemId = reasoningAdded.Id, OutputIndex = outputIndex, ContentIndex = 0, Text = reasoning.Text! }, ResponsesJsonContext.Default.ResponsesStreamReasoningTextDoneEvent).ConfigureAwait(false);
                }

                var reasoningDone = ResponsesOutputRenderer.Render([content], status: "completed")[0];
                reasoningDone.Id = reasoningAdded.Id;
                await this.WriteOutputItemEventAsync(http, "response.output_item.done", outputIndex, reasoningDone).ConfigureAwait(false);
                return true;

            case FunctionCallContent call:
                var arguments = ResponsesOutputRenderer.SerializeArguments(call.Arguments);
                var callId = call.CallId ?? "call_" + Guid.NewGuid().ToString("N");
                var name = string.IsNullOrEmpty(call.Name) ? "tool" : call.Name;
                var callAdded = new ResponsesOutputItem { Type = "function_call", Id = "fc_" + Guid.NewGuid().ToString("N"), CallId = callId, Name = name, Arguments = string.Empty, Status = "in_progress" };
                await this.WriteOutputItemEventAsync(http, "response.output_item.added", outputIndex, callAdded).ConfigureAwait(false);
                if (call.Arguments is { Count: > 0 })
                {
                    await WriteEventAsync(http, "response.function_call_arguments.delta", new ResponsesStreamFunctionCallArgumentsDeltaEvent { ItemId = callAdded.Id, OutputIndex = outputIndex, Delta = arguments }, ResponsesJsonContext.Default.ResponsesStreamFunctionCallArgumentsDeltaEvent).ConfigureAwait(false);
                    await WriteEventAsync(http, "response.function_call_arguments.done", new ResponsesStreamFunctionCallArgumentsDoneEvent { ItemId = callAdded.Id, OutputIndex = outputIndex, Arguments = arguments, Name = name }, ResponsesJsonContext.Default.ResponsesStreamFunctionCallArgumentsDoneEvent).ConfigureAwait(false);
                }

                var callDone = ResponsesOutputRenderer.Render([content], status: "completed")[0];
                callDone.Id = callAdded.Id;
                await this.WriteOutputItemEventAsync(http, "response.output_item.done", outputIndex, callDone).ConfigureAwait(false);
                return true;

            default:
                var items = ResponsesOutputRenderer.Render([content], status: "completed");
                var produced = false;
                foreach (var item in items)
                {
                    produced = true;
                    await this.WriteOutputItemEventAsync(http, "response.output_item.added", outputIndex, item).ConfigureAwait(false);
                    await this.WriteOutputItemEventAsync(http, "response.output_item.done", outputIndex, item).ConfigureAwait(false);
                }

                return produced;
        }
    }

    private Task WriteOutputItemEventAsync(HttpContext http, string type, int outputIndex, ResponsesOutputItem item) =>
        WriteEventAsync(http, type, new ResponsesStreamOutputItemEvent { Type = type, OutputIndex = outputIndex, Item = item }, ResponsesJsonContext.Default.ResponsesStreamOutputItemEvent);

    private static async IAsyncEnumerable<AgentResponseUpdate> StreamUpdatesAsync(
        IAsyncEnumerable<HostedStreamItem> items,
        Action<HostedRunResult> captureFinal)
    {
        await foreach (var item in items.ConfigureAwait(false))
        {
            switch (item)
            {
                case HostedStreamUpdate update:
                    yield return update.Update;
                    break;
                case HostedStreamCompleted completed:
                    captureFinal(completed.Result);
                    break;
            }
        }
    }

    private async ValueTask<HostedRunResult> ApplyResponseHookAsync(HostedRunResult result, ChannelRequest request, CancellationToken cancellationToken)
    {
        if (this._options.ResponseHook is null)
        {
            return result;
        }
        var ctx = new ChannelResponseContext(request, this.Name);
        return await this._options.ResponseHook.OnResponseAsync(result, ctx, cancellationToken).ConfigureAwait(false);
    }

    private static ResponsesResponseModel BuildEnvelope(string id, string? model, string status) => new()
    {
        Id = id,
        CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
        Status = status,
        Model = string.IsNullOrEmpty(model) ? "agent" : model,
    };

    private static ResponsesUsageModel? BuildUsage(AgentResponse? agentResponse)
    {
        if (agentResponse?.Usage is not { } usage)
        {
            return null;
        }

        return new ResponsesUsageModel
        {
            InputTokens = (int)(usage.InputTokenCount ?? 0),
            OutputTokens = (int)(usage.OutputTokenCount ?? 0),
            TotalTokens = (int)(usage.TotalTokenCount ?? 0),
        };
    }

    /// <summary>
    /// Render an agent result's messages as Responses output items, mirroring the Python channel: consecutive
    /// text coalesces into one assistant message item; reasoning, function calls, and function results each
    /// become their own typed output item. Unmodeled content falls back to text.
    /// </summary>
    private static List<ResponsesOutputItem> BuildOutputItems(object? resultObject)
    {
        var contents = new List<AIContent>();
        foreach (var message in ExtractMessages(resultObject))
        {
            contents.AddRange(message.Contents);
        }

        var items = ResponsesOutputRenderer.Render(contents, status: "completed");
        if (items.Count == 0)
        {
            items.Add(new ResponsesOutputItem
            {
                Type = "message",
                Id = "msg_" + Guid.NewGuid().ToString("N"),
                Role = "assistant",
                Status = "completed",
                Content = new JsonArray(new JsonObject { ["type"] = "output_text", ["text"] = ExtractText(resultObject), ["annotations"] = new JsonArray() }),
            });
        }

        return items;
    }

    private static IEnumerable<ChatMessage> ExtractMessages(object? resultObject) => resultObject switch
    {
        AgentResponse response => response.Messages,
        WorkflowRunResult workflow => FlattenWorkflowOutputs(workflow.Outputs),
        _ => [],
    };

    private static IEnumerable<ChatMessage> FlattenWorkflowOutputs(IReadOnlyList<object?> outputs)
    {
        foreach (var output in outputs)
        {
            switch (output)
            {
                case null:
                    break;
                case ChatMessage message:
                    yield return message;
                    break;
                case AgentResponse response:
                    foreach (var message in response.Messages)
                    {
                        yield return message;
                    }

                    break;
                case IEnumerable<ChatMessage> messages:
                    foreach (var message in messages)
                    {
                        yield return message;
                    }

                    break;
                case AIContent content:
                    yield return new ChatMessage(ChatRole.Assistant, [content]);
                    break;
                case string text:
                    yield return new ChatMessage(ChatRole.Assistant, text);
                    break;
                default:
                    yield return new ChatMessage(ChatRole.Assistant, output.ToString() ?? string.Empty);
                    break;
            }
        }
    }

    private static string ExtractText(object? resultObject) => resultObject switch
    {
        AgentResponse response => response.Text,
        AgentResponseUpdate update => update.Text,
        string s => s,
        _ => resultObject?.ToString() ?? string.Empty,
    };

    private static readonly Func<string?, string> s_defaultResponseIdFactory = _ => "resp_" + Guid.NewGuid().ToString("N");

    private static async Task WriteEventAsync<T>(HttpContext http, string eventType, T payload, System.Text.Json.Serialization.Metadata.JsonTypeInfo<T> typeInfo)
    {
        var json = JsonSerializer.Serialize(payload, typeInfo);
        var frame = string.Create(CultureInfo.InvariantCulture, $"event: {eventType}\ndata: {json}\n\n");
        await http.Response.WriteAsync(frame, http.RequestAborted).ConfigureAwait(false);
        await http.Response.Body.FlushAsync(http.RequestAborted).ConfigureAwait(false);
    }

    private static async Task WriteErrorAsync(HttpContext http, int statusCode, string? message)
    {
        http.Response.StatusCode = statusCode;
        http.Response.ContentType = "application/json; charset=utf-8";
        var error = new ResponsesErrorModel { Error = new ResponsesErrorBody { Message = message } };
        await JsonSerializer.SerializeAsync(http.Response.Body, error, ResponsesJsonContext.Default.ResponsesErrorModel, http.RequestAborted).ConfigureAwait(false);
    }
}
