// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Runtime.CompilerServices;
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
/// and the current invocation records an explicit consent-required result. When the downstream
/// inference service keeps its own history, the function loop performs one final no-tools request
/// so that result batch is stored there. Otherwise it terminates before that unnecessary request.
/// The handler then emits the <c>oauth_consent_request</c> output item and marks the response as
/// <c>incomplete</c>.
/// Outside a function-invoking loop, cancellation signals the handoff to the handler.
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
                state.AddPendingConsent(new McpConsentInfo(this._toolboxName, this._inner.Name, consentUrl));
                if (FunctionInvokingChatClient.CurrentContext is { } invocation)
                {
                    if (state.ReconcileDownstreamHistory)
                    {
                        // Keep the current function batch running so every call receives a result,
                        // then prohibit another tool batch while FICC sends those results to the
                        // downstream service-managed conversation.
                        invocation.Options!.ToolMode = ChatToolMode.None;
                        return McpConsentResults.ConsentRequired;
                    }

                    // AgentServer owns the only history in this mode. Stop before an unnecessary
                    // follow-up model request; the response handler pairs any skipped calls below.
                    invocation.Terminate = true;
                    return McpConsentResults.ConsentRequired;
                }

                state.CancellationSource?.Cancel();
            }

            cancellationToken.ThrowIfCancellationRequested();
            throw; // fallback if the CT wasn't cancelled for some reason
        }
    }
}

/// <summary>
/// Installs a request-aware FICC invoker that prevents later functions from executing after OAuth consent is required.
/// </summary>
internal static class ConsentBlockingFunctionInvoker
{
    private static readonly ConditionalWeakTable<FunctionInvokingChatClient, object> s_installedClients = new();

    /// <summary>
    /// Installs the consent gate once on a shared FICC instance while preserving any caller-provided invoker.
    /// </summary>
    internal static void EnsureInstalled(FunctionInvokingChatClient client)
    {
        lock (s_installedClients)
        {
            if (s_installedClients.TryGetValue(client, out _))
            {
                return;
            }

            var innerInvoker = client.FunctionInvoker;
            client.FunctionInvoker = (context, cancellationToken) =>
                InvokeAsync(innerInvoker, context, cancellationToken);
            s_installedClients.Add(client, new object());
        }
    }

    private static ValueTask<object?> InvokeAsync(
        Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>>? innerInvoker,
        FunctionInvocationContext context,
        CancellationToken cancellationToken)
    {
        if (McpConsentContext.Current.Value is
            {
                ReconcileDownstreamHistory: true,
                HasPendingConsents: true,
            } state)
        {
            return new ValueTask<object?>(state.InterruptedToolResult);
        }

        return innerInvoker is not null
            ? innerInvoker(context, cancellationToken)
            : context.Function.InvokeAsync(context.Arguments, cancellationToken);
    }
}
