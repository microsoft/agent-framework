// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI.Mcp;

/// <summary>
/// An <see cref="AIFunction"/> wrapper around an <see cref="McpClientTool"/> that drives the
/// <see href="https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/tasks">MCP long-running task</see>
/// lifecycle (SEP-2663) on behalf of the agent's tool loop.
/// </summary>
/// <remarks>
/// <para>
/// The wrapper invokes the tool with task augmentation via
/// <see cref="McpClient.CallToolAsTaskAsync"/>, polls to completion via
/// <see cref="McpClient.PollTaskUntilCompleteAsync"/>, and fetches the result via
/// <see cref="McpClient.GetTaskResultAsync"/>. The result is returned to the caller as a
/// <see cref="JsonElement"/> containing the serialized <see cref="CallToolResult"/> — the
/// same wire shape produced by <see cref="McpClientTool"/>.<see cref="AIFunction.InvokeAsync(AIFunctionArguments, CancellationToken)"/>
/// so that downstream <see cref="FunctionResultContent"/> serialization is byte-identical to
/// a non-task-augmented MCP tool call. The agent's function-calling loop is unaware that a
/// task was used.
/// </para>
/// <para>
/// This wrapper is intended to be applied only to tools whose
/// <see cref="ToolExecution.TaskSupport"/> is <see cref="ToolTaskSupport.Required"/>
/// (selected by <see cref="McpClientTaskExtensions.ListAgentToolsWithTaskSupportAsync"/>).
/// As a defensive fallback, if the server still rejects the task-augmented call with
/// <see cref="McpErrorCode.MethodNotFound"/> (e.g. because tool-level capabilities changed
/// between <c>tools/list</c> and invocation), the wrapper transparently falls back to a
/// non-augmented call through the inner <see cref="McpClientTool"/>.
/// </para>
/// </remarks>
internal sealed class TaskAwareMcpClientAIFunction : AIFunction
{
    private readonly McpClient _client;
    private readonly McpClientTool _inner;
    private readonly McpTaskOptions _options;

    internal TaskAwareMcpClientAIFunction(McpClient client, McpClientTool inner, McpTaskOptions options)
    {
        _ = Throw.IfNull(client);
        _ = Throw.IfNull(inner);
        _ = Throw.IfNull(options);

        this._client = client;
        this._inner = inner;
        this._options = options;
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

        McpTaskMetadata? metadata = null;
        if (this._options.DefaultTimeToLive is TimeSpan ttl)
        {
            metadata = new McpTaskMetadata { TimeToLive = ttl };
        }

        McpTask task;
        try
        {
            task = await this._client.CallToolAsTaskAsync(
                this._inner.Name,
                arguments,
                taskMetadata: metadata,
                progress: null,
                options: null,
                cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        catch (McpProtocolException ex) when (ex.ErrorCode == McpErrorCode.MethodNotFound)
        {
            // Defensive fallback: the server's advertised TaskSupport indicated this tool
            // could be invoked as a task, but the server now rejects task augmentation for it
            // (e.g. capability changed between tools/list and invocation). Fall back to a
            // non-augmented call through the inner McpClientTool.
            return await this._inner.InvokeAsync(arguments, cancellationToken).ConfigureAwait(false);
        }

        return await this.PollAndRetrieveResultAsync(task.TaskId, cancellationToken).ConfigureAwait(false);
    }

    private async Task<JsonElement> PollAndRetrieveResultAsync(string taskId, CancellationToken cancellationToken)
    {
        try
        {
            McpTask terminal = await this._client.PollTaskUntilCompleteAsync(taskId, options: null, cancellationToken).ConfigureAwait(false);

            return terminal.Status switch
            {
                McpTaskStatus.Completed => await this._client.GetTaskResultAsync(taskId, options: null, cancellationToken).ConfigureAwait(false),
                McpTaskStatus.Cancelled => throw new OperationCanceledException(FormatTerminalStatusMessage(taskId, terminal)),
                _ => throw new InvalidOperationException(FormatTerminalStatusMessage(taskId, terminal)),// Failed (or any future non-terminal-but-unhandled status that the poll loop returns).
            };
        }
        catch (OperationCanceledException) when (this._options.CancelRemoteTaskOnLocalCancellation && cancellationToken.IsCancellationRequested)
        {
            await this.TryCancelTaskAsync(taskId).ConfigureAwait(false);
            throw;
        }
    }

    private static string FormatTerminalStatusMessage(string taskId, McpTask terminal)
        => string.IsNullOrEmpty(terminal.StatusMessage)
            ? $"MCP task '{taskId}' ended in terminal status '{terminal.Status}'."
            : $"MCP task '{taskId}' ended in terminal status '{terminal.Status}': {terminal.StatusMessage}";

    private async Task TryCancelTaskAsync(string taskId)
    {
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            _ = await this._client.CancelTaskAsync(taskId, options: null, cts.Token).ConfigureAwait(false);
        }
        catch
        {
            // Best-effort cancellation; do not mask the original cancellation reason.
        }
    }
}
