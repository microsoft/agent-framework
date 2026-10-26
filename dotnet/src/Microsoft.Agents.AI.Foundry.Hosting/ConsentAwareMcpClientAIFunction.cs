// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using ModelContextProtocol;
using ModelContextProtocol.Client;

namespace Microsoft.Agents.AI.Foundry.Hosting;

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
    private readonly string _toolboxName;

    internal ConsentAwareMcpClientAIFunction(McpClientTool inner, string toolboxName)
    {
        this._inner = inner;
        this._toolboxName = toolboxName;
    }

    public override string Name => this._inner.Name;

    public override string Description => this._inner.Description;

    public override JsonElement JsonSchema => this._inner.JsonSchema;

    public override JsonElement? ReturnJsonSchema => this._inner.ReturnJsonSchema;

    public override JsonSerializerOptions JsonSerializerOptions => this._inner.JsonSerializerOptions;

    protected override async ValueTask<object?> InvokeCoreAsync(
        AIFunctionArguments arguments,
        CancellationToken cancellationToken)
    {
        try
        {
            return await this._inner.InvokeAsync(arguments, cancellationToken).ConfigureAwait(false);
        }
        catch (McpProtocolException ex) when ((int)ex.ErrorCode == -32006)
        {
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
                state.Pending = new McpConsentInfo(this._toolboxName, this._inner.Name, consentUrl);
                state.CancellationSource?.Cancel();
            }

            cancellationToken.ThrowIfCancellationRequested();
            throw; // fallback if the CT wasn't cancelled for some reason
        }
    }
}
