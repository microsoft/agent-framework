// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol;
using ModelContextProtocol.Client;
using ModelContextProtocol.Extensions.Tasks;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI.Mcp;

/// <summary>
/// An <see cref="AIFunction"/> wrapper around an <see cref="McpClientTool"/> that drives the
/// <see href="https://modelcontextprotocol.io/extensions/tasks/overview">MCP Tasks extension</see>
/// lifecycle on behalf of the agent's tool loop.
/// </summary>
/// <remarks>
/// <para>
/// The wrapper uses the public MCP Tasks extension primitives to retain the created task handle,
/// poll to completion, resolve <c>input_required</c> requests, and cancel remote work when the
/// local invocation is cancelled. Its result projection matches <see cref="McpClientTool"/> so
/// the agent's function-calling loop is unaware whether the server used a task.
/// </para>
/// </remarks>
internal sealed class TaskAwareMcpClientAIFunction : AIFunction
{
    private const long DefaultPollIntervalMs = 1000;

    private readonly McpClient _client;
    private readonly McpClientTool _inner;
    private readonly bool _cancelRemoteTaskOnLocalCancellation;
    private readonly int _maxConsecutiveStuckPolls;
    private readonly int _maxTotalInputRequests;
    private readonly TimeSpan _remoteCancellationTimeout;
    private readonly long _minimumPollIntervalMs;
    private readonly long _maximumPollIntervalMs;

    internal TaskAwareMcpClientAIFunction(McpClient client, McpClientTool inner, McpTaskOptions options)
    {
        _ = Throw.IfNull(client);
        _ = Throw.IfNull(inner);
        _ = Throw.IfNull(options);

        this._client = client;
        this._inner = inner;
        this._cancelRemoteTaskOnLocalCancellation = options.CancelRemoteTaskOnLocalCancellation;
        this._maxConsecutiveStuckPolls = options.MaxConsecutiveStuckPolls;
        this._maxTotalInputRequests = options.MaxTotalInputRequests;
        this._remoteCancellationTimeout = options.RemoteCancellationTimeout;
        this._minimumPollIntervalMs = (long)Math.Ceiling(options.MinimumPollingInterval.TotalMilliseconds);
        this._maximumPollIntervalMs = (long)Math.Floor(options.MaximumPollingInterval.TotalMilliseconds);
    }

    /// <inheritdoc />
    public override string Name => this._inner.Name;

    /// <inheritdoc />
    public override string Description => this._inner.Description;

    /// <inheritdoc />
    public override JsonElement JsonSchema => this._inner.JsonSchema;

    /// <inheritdoc />
    public override JsonElement? ReturnJsonSchema => this._inner.ReturnJsonSchema;

    /// <inheritdoc />
    public override JsonSerializerOptions JsonSerializerOptions => this._inner.JsonSerializerOptions;

    /// <inheritdoc />
    protected override async ValueTask<object?> InvokeCoreAsync(
        AIFunctionArguments arguments,
        CancellationToken cancellationToken)
    {
        _ = Throw.IfNull(arguments);

        ResultOrCreatedTask<CallToolResult> invocation = await this._client.CallToolAsTaskAsync(
            new CallToolRequestParams
            {
                Name = this._inner.ProtocolTool.Name,
                Arguments = ToArgumentsDictionary(arguments, this.JsonSerializerOptions),
            },
            cancellationToken: cancellationToken).ConfigureAwait(false);

        CallToolResult result;
        if (!invocation.IsTask)
        {
            result = invocation.Result!;
        }
        else
        {
            result = await this.PollTaskToCompletionAsync(invocation.TaskCreated!, cancellationToken).ConfigureAwait(false);
        }

        return ProjectResult(result, this.JsonSerializerOptions);
    }

    // This mirrors the MCP SDK 2.1 poller but is maintained here so the wrapper retains
    // the task ID needed for remote cancellation. Recompare lifecycle behavior when
    // upgrading ModelContextProtocol.Extensions.Tasks.
    private async Task<CallToolResult> PollTaskToCompletionAsync(
        CreateTaskResult createdTask,
        CancellationToken cancellationToken)
    {
        string taskId = createdTask.TaskId;
        long pollIntervalMs = createdTask.PollIntervalMs ??
            Math.Clamp(DefaultPollIntervalMs, this._minimumPollIntervalMs, this._maximumPollIntervalMs);
        HashSet<string>? observedInputRequestKeys = null;
        bool isFirstPoll = true;
        int consecutiveStuckPolls = 0;
        bool isTerminal = false;

        try
        {
            while (true)
            {
                if (!isFirstPoll)
                {
                    await Task.Delay(this.GetValidatedPollDelay(taskId, pollIntervalMs), cancellationToken).ConfigureAwait(false);
                }

                isFirstPoll = false;

                GetTaskResult taskResult = await this._client.GetTaskAsync(taskId, cancellationToken).ConfigureAwait(false);

                switch (taskResult)
                {
                    case CompletedTaskResult completed:
                        isTerminal = true;
                        return JsonSerializer.Deserialize(
                            completed.Result,
                            McpJsonUtilities.DefaultOptions.GetTypeInfo<CallToolResult>())
                            ?? throw new JsonException("Failed to deserialize CallToolResult from completed task.");

                    case FailedTaskResult failed:
                        isTerminal = true;
                        throw new McpException($"Task '{taskId}' failed: {failed.Error}");

                    case CancelledTaskResult:
                        isTerminal = true;
                        throw new OperationCanceledException($"Task '{taskId}' was cancelled by the server.");

                    case InputRequiredTaskResult inputRequired:
                        pollIntervalMs = inputRequired.PollIntervalMs ?? pollIntervalMs;
                        Dictionary<string, InputRequest> newRequests = [];
                        int observedCount = observedInputRequestKeys?.Count ?? 0;
                        int remainingInputRequests = this._maxTotalInputRequests - observedCount;
                        if (inputRequired.InputRequests is { } incomingRequests)
                        {
                            foreach (KeyValuePair<string, InputRequest> request in incomingRequests)
                            {
                                if (observedInputRequestKeys?.Contains(request.Key) is not true)
                                {
                                    if (newRequests.Count >= remainingInputRequests)
                                    {
                                        throw new McpException(
                                            $"Task '{taskId}' exceeded the limit of " +
                                            $"{this._maxTotalInputRequests} unique input requests.");
                                    }

                                    newRequests.Add(request.Key, request.Value);
                                }
                            }
                        }

                        if (newRequests.Count > 0)
                        {
                            observedInputRequestKeys ??= new(StringComparer.Ordinal);
                            foreach (string key in newRequests.Keys)
                            {
                                _ = observedInputRequestKeys.Add(key);
                            }

                            consecutiveStuckPolls = 0;
                            IDictionary<string, InputResponse> inputResponses =
                                await this._client.ResolveInputRequestsAsync(
                                    newRequests,
                                    cancellationToken).ConfigureAwait(false);

                            _ = await this._client.UpdateTaskAsync(
                                new UpdateTaskRequestParams
                                {
                                    TaskId = taskId,
                                    InputResponses = inputResponses,
                                },
                                cancellationToken).ConfigureAwait(false);
                        }
                        else if (++consecutiveStuckPolls >= this._maxConsecutiveStuckPolls)
                        {
                            throw new McpException(
                                $"Task '{taskId}' has remained in '{McpTaskStatus.InputRequired}' for " +
                                $"{this._maxConsecutiveStuckPolls} consecutive polls without publishing new input " +
                                "requests after all previously requested inputs were resolved.");
                        }

                        break;

                    case WorkingTaskResult:
                        pollIntervalMs = taskResult.PollIntervalMs ?? pollIntervalMs;
                        consecutiveStuckPolls = 0;
                        break;

                    default:
                        throw new McpException(
                            $"Unexpected task result type '{taskResult.GetType().Name}' for task '{taskId}'.");
                }
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            if (!isTerminal && this._cancelRemoteTaskOnLocalCancellation)
            {
                await this.TryCancelTaskAsync(taskId).ConfigureAwait(false);
            }

            throw;
        }
        catch
        {
            if (!isTerminal)
            {
                await this.TryCancelTaskAsync(taskId).ConfigureAwait(false);
            }

            throw;
        }
    }

    private TimeSpan GetValidatedPollDelay(string taskId, long pollIntervalMs)
    {
        if (pollIntervalMs < this._minimumPollIntervalMs || pollIntervalMs > this._maximumPollIntervalMs)
        {
            throw new McpException(
                $"Task '{taskId}' returned an unusable pollIntervalMs of {pollIntervalMs}. " +
                $"The configured range is {this._minimumPollIntervalMs} through " +
                $"{this._maximumPollIntervalMs} milliseconds.");
        }

        return TimeSpan.FromMilliseconds(pollIntervalMs);
    }

    private static object ProjectResult(CallToolResult result, JsonSerializerOptions serializerOptions)
    {
        if (result.IsError is not true &&
            result.StructuredContent is null &&
            !HasApplicationResultMetadata(result.Meta))
        {
            switch (result.Content.Count)
            {
                case 1 when result.Content[0].ToAIContent(serializerOptions) is { } aiContent:
                    return aiContent;

                case > 1 when result.Content.Select(c => c.ToAIContent(serializerOptions)).ToArray() is { } aiContents &&
                    aiContents.All(static c => c is not null):
                    return aiContents;
            }
        }

        return JsonSerializer.SerializeToElement(
            result,
            McpJsonUtilities.DefaultOptions.GetTypeInfo<CallToolResult>());
    }

    private async Task TryCancelTaskAsync(string taskId)
    {
        try
        {
            using var cts = new CancellationTokenSource(this._remoteCancellationTimeout);
            _ = await this._client.CancelTaskAsync(taskId, cts.Token).ConfigureAwait(false);
        }
        catch
        {
            // Remote cancellation is best-effort and must not mask the original failure.
        }
    }

    private static Dictionary<string, JsonElement> ToArgumentsDictionary(
        AIFunctionArguments arguments,
        JsonSerializerOptions options)
    {
        var typeInfo = options.GetTypeInfo<object?>();
        Dictionary<string, JsonElement> result = new(arguments.Count);
        foreach (KeyValuePair<string, object?> argument in arguments)
        {
            result.Add(
                argument.Key,
                argument.Value is JsonElement element
                    ? element
                    : JsonSerializer.SerializeToElement(argument.Value, typeInfo));
        }

        return result;
    }

    private static bool HasApplicationResultMetadata(JsonObject? metadata)
    {
        if (metadata is null)
        {
            return false;
        }

        foreach (KeyValuePair<string, JsonNode?> property in metadata)
        {
            if (!string.Equals(property.Key, MetaKeys.ServerInfo, StringComparison.Ordinal))
            {
                return true;
            }
        }

        return false;
    }
}
