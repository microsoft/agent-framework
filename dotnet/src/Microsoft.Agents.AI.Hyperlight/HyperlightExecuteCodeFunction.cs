// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hyperlight.Internal;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hyperlight;

/// <summary>
/// Standalone <c>execute_code</c> <see cref="AIFunction"/> backed by a
/// Hyperlight sandbox. Use this for manual/static wiring when an
/// <see cref="AIContextProvider"/> lifecycle is not needed — for example
/// when the tool registry and capability configuration are fixed for the
/// lifetime of the agent.
/// </summary>
/// <remarks>
/// Unlike <see cref="HyperlightCodeActProvider"/>, this type does not hook
/// into the <see cref="AIContextProvider"/> pipeline. It captures a single
/// snapshot of the provided <see cref="HyperlightCodeActProviderOptions"/>
/// at construction time and reuses it for the lifetime of the instance.
/// The instance can be passed directly anywhere an <see cref="AIFunction"/>
/// is accepted; when the configuration requires approval (per
/// <see cref="HyperlightCodeActProviderOptions.ApprovalMode"/> or because a
/// configured tool is itself an <see cref="ApprovalRequiredAIFunction"/>),
/// the instance surfaces an <see cref="ApprovalRequiredAIFunction"/> via
/// <see cref="AITool.GetService(Type, object?)"/>, which is how the rest of
/// the framework discovers approval requirements.
/// </remarks>
public sealed class HyperlightExecuteCodeFunction : AIFunction, IDisposable
{
    private const string ExecuteCodeName = "execute_code";

    private static readonly JsonElement s_schema = JsonDocument.Parse(
        """
        {
          "type": "object",
          "properties": {
            "code": {
              "type": "string",
              "description": "Code to execute using the provider's configured backend/runtime behavior."
            }
          },
          "required": ["code"]
        }
        """).RootElement;

    private readonly SandboxExecutor _executor;
    private readonly SandboxExecutor.RunSnapshot _snapshot;
    private readonly string _description;
    private readonly bool _approvalRequired;
    private ApprovalRequiredAIFunction? _approvalProxy;
    private bool _disposed;

    /// <summary>
    /// Initializes a new instance of the <see cref="HyperlightExecuteCodeFunction"/> class.
    /// </summary>
    /// <param name="options">
    /// Optional configuration options. When <see langword="null"/> the defaults of
    /// <see cref="HyperlightCodeActProviderOptions"/> are used.
    /// </param>
    public HyperlightExecuteCodeFunction(HyperlightCodeActProviderOptions? options = null)
    {
        var effective = options ?? new HyperlightCodeActProviderOptions();
        this._executor = new SandboxExecutor(effective);

        var tools = (effective.Tools?.Where(t => t is not null) ?? []).ToList();
        var fileMounts = (effective.FileMounts?.Where(m => m is not null) ?? []).ToList();
        var allowedDomains = (effective.AllowedDomains?.Where(d => d is not null) ?? []).ToList();

        this._snapshot = new SandboxExecutor.RunSnapshot(tools, fileMounts, allowedDomains, effective.HostInputDirectory);

        this._description = InstructionBuilder.BuildExecuteCodeDescription(
            this._snapshot.Tools,
            this._snapshot.FileMounts,
            this._snapshot.AllowedDomains,
            hasHostInputDirectory: !string.IsNullOrEmpty(this._snapshot.HostInputDirectory));

        this._approvalRequired = HyperlightCodeActProvider.ComputeApprovalRequired(effective.ApprovalMode, this._snapshot.Tools);
    }

    /// <inheritdoc />
    public override string Name => ExecuteCodeName;

    /// <inheritdoc />
    public override string Description => this._description;

    /// <inheritdoc />
    public override JsonElement JsonSchema => s_schema;

    /// <summary>
    /// Builds a CodeAct instruction string describing the available tools and capabilities.
    /// </summary>
    /// <param name="toolsVisibleToModel">
    /// When <see langword="false"/>, the instructions assume tools are only accessible
    /// through CodeAct (via <c>call_tool</c>). When <see langword="true"/>, the instructions
    /// are abbreviated for cases where the same tools are already visible to the model as
    /// direct agent tools.
    /// </param>
    public string BuildInstructions(bool toolsVisibleToModel = false)
    {
        this.ThrowIfDisposed();
        return InstructionBuilder.BuildContextInstructions(toolsVisibleToModel);
    }

    /// <inheritdoc />
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        if (serviceKey is null
            && this._approvalRequired
            && serviceType == typeof(ApprovalRequiredAIFunction))
        {
            return this._approvalProxy ??= new ApprovalRequiredAIFunction(this);
        }

        return base.GetService(serviceType, serviceKey);
    }

    /// <inheritdoc />
    protected override async ValueTask<object?> InvokeCoreAsync(
        AIFunctionArguments arguments,
        CancellationToken cancellationToken)
    {
        this.ThrowIfDisposed();

        if (arguments is null || !arguments.TryGetValue("code", out var codeObj) || codeObj is null)
        {
            throw new ArgumentException("Missing required parameter 'code'.", nameof(arguments));
        }

        var code = codeObj switch
        {
            string s => s,
            JsonElement { ValueKind: JsonValueKind.String } el => el.GetString() ?? string.Empty,
            _ => codeObj.ToString() ?? string.Empty,
        };

        if (string.IsNullOrWhiteSpace(code))
        {
            throw new ArgumentException("Parameter 'code' must not be empty.", nameof(arguments));
        }

        return await this._executor.ExecuteAsync(this._snapshot, code, cancellationToken).ConfigureAwait(false);
    }

    private void ThrowIfDisposed() => ObjectDisposedException.ThrowIf(this._disposed, this);

    /// <summary>Releases the underlying sandbox and associated native resources.</summary>
    public void Dispose()
    {
        if (this._disposed)
        {
            return;
        }

        this._disposed = true;
        this._executor.Dispose();
    }
}
