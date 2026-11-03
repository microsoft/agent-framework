// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using ModelContextProtocol;
using ModelContextProtocol.Client;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Describes how one locally executed function-shaped MCP tool is projected onto the caller-facing MCP contract.
/// </summary>
internal sealed record LocalMcpExecutionContract(
    string ServerLabel,
    string ToolName,
    bool RequiresApproval);

/// <summary>
/// Adds caller-facing MCP execution metadata to an arbitrary locally executed function.
/// </summary>
internal sealed class LocalMcpAIFunction : DelegatingAIFunction
{
    private readonly LocalMcpExecutionContract _contract;

    internal LocalMcpAIFunction(AIFunction innerFunction, string serverLabel, string toolName)
        : base(innerFunction)
    {
        this._contract = new(serverLabel, toolName, innerFunction.GetService<ApprovalRequiredAIFunction>() is not null);
    }

    public override object? GetService(Type serviceType, object? serviceKey = null) =>
        serviceKey is null && serviceType == typeof(LocalMcpExecutionContract)
            ? this._contract
            : base.GetService(serviceType, serviceKey);

    protected override async ValueTask<object?> InvokeCoreAsync(
        AIFunctionArguments arguments,
        CancellationToken cancellationToken)
    {
        LocalMcpInvocationTracker.Record(this._contract);
        try
        {
            return await base.InvokeCoreAsync(arguments, cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            // Cancellation produces no FunctionResultContent, so OutputConverter cannot consume
            // the temporary invocation marker. Ordinary failures still need the marker for projection.
            LocalMcpInvocationTracker.RemoveCurrent();
            throw;
        }
    }
}

/// <summary>
/// An <see cref="AIFunction"/> wrapper around <see cref="McpClientTool"/> that intercepts
/// JSON-RPC error -32006 (OAuth consent required) from the Foundry Toolsets proxy and
/// propagates it back to <see cref="AgentFrameworkResponseHandler"/> via
/// <see cref="McpConsentContext"/>.
/// </summary>
/// <remarks>
/// <para>
/// When the proxy returns -32006, the consent URL is stored in <see cref="McpConsentContext.Current"/>
/// and the per-request <see cref="RequestConsentState.CancellationSource"/> is cancelled. This causes
/// <see cref="FunctionInvokingChatClient"/> to stop the tool loop (it guards
/// exceptions with <c>when (!ct.IsCancellationRequested)</c>) and surfaces an
/// <see cref="OperationCanceledException"/> to the handler. The handler then emits the
/// <c>oauth_consent_request</c> output item and marks the response as <c>incomplete</c>.
/// </para>
/// </remarks>
internal sealed class ConsentAwareMcpClientAIFunction : AIFunction
{
    private readonly McpClientTool _inner;
    private readonly LocalMcpExecutionContract _contract;

    internal ConsentAwareMcpClientAIFunction(McpClientTool inner, string toolboxName)
    {
        this._inner = inner;
        this.ToolboxName = toolboxName;
        this._contract = new(toolboxName, inner.Name, RequiresApproval: false);
    }

    public override string Name => this._inner.Name;

    public override string Description => this._inner.Description;

    public override JsonElement JsonSchema => this._inner.JsonSchema;

    public override JsonElement? ReturnJsonSchema => this._inner.ReturnJsonSchema;

    public override JsonSerializerOptions JsonSerializerOptions => this._inner.JsonSerializerOptions;

    internal string ToolboxName { get; }

    internal string ToolName => this._inner.Name;

    public override object? GetService(Type serviceType, object? serviceKey = null) =>
        serviceKey is null && serviceType == typeof(LocalMcpExecutionContract)
            ? this._contract
            : base.GetService(serviceType, serviceKey);

    protected override async ValueTask<object?> InvokeCoreAsync(
        AIFunctionArguments arguments,
        CancellationToken cancellationToken)
    {
        LocalMcpInvocationTracker.Record(this._contract);
        try
        {
            return await this._inner.InvokeAsync(arguments, cancellationToken).ConfigureAwait(false);
        }
        catch (McpProtocolException ex) when ((int)ex.ErrorCode == -32006)
        {
            LocalMcpInvocationTracker.RemoveCurrent();
            var state = McpConsentContext.Current.Value;
            if (state is not null)
            {
                const string RemoteErrorPrefix = "Request failed (remote): ";
                var consentUrl = ex.Data["detail"] switch
                {
                    string detail => detail,
                    JsonElement { ValueKind: JsonValueKind.String } detail => detail.GetString()!,
                    _ when !ex.Data.Contains("detail") => ex.Message.StartsWith(RemoteErrorPrefix, StringComparison.Ordinal)
                        ? ex.Message[RemoteErrorPrefix.Length..]
                        : ex.Message,
                    // The detail field exists but is not a string. Use an empty URL so the
                    // handler rejects this consent response instead of falling back to the message.
                    _ => string.Empty,
                };
                state.Pending = new McpConsentInfo(this.ToolboxName, this._inner.Name, consentUrl);
                state.CancellationSource?.Cancel();
            }

            cancellationToken.ThrowIfCancellationRequested();
            throw; // fallback if the CT wasn't cancelled for some reason
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            // Cancellation produces no FunctionResultContent, so OutputConverter cannot consume
            // the temporary invocation marker. Ordinary failures still need the marker for projection.
            LocalMcpInvocationTracker.RemoveCurrent();
            throw;
        }
    }
}

internal static class LocalMcpInvocationTracker
{
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing function call arguments dictionary.")]
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing function call arguments dictionary.")]
    public static void Record(LocalMcpExecutionContract contract)
    {
        FunctionCallContent? call = FunctionInvokingChatClient.CurrentContext?.CallContent;
        AgentSessionStateBag? stateBag = AIAgent.CurrentRunContext?.Session?.StateBag;
        if (call?.CallId is not { Length: > 0 } callId || stateBag is null)
        {
            return;
        }

        string arguments = call.Arguments is not null
            ? JsonSerializer.Serialize(call.Arguments)
            : "{}";
        LocalMcpInvocationMap.Record(
            stateBag,
            callId,
            call.Name,
            contract.ToolName,
            contract.ServerLabel,
            arguments);
    }

    public static void RemoveCurrent()
    {
        FunctionCallContent? call = FunctionInvokingChatClient.CurrentContext?.CallContent;
        AgentSessionStateBag? stateBag = AIAgent.CurrentRunContext?.Session?.StateBag;
        if (call?.CallId is { Length: > 0 } callId)
        {
            _ = LocalMcpInvocationMap.Consume(stateBag, callId);
        }
    }
}
