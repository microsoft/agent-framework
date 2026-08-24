// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A delegating chat client that reserves a position for OpenTelemetry instrumentation directly above
/// the leaf <see cref="IChatClient"/> and below the <see cref="FunctionInvokingChatClient"/> in a
/// <see cref="ChatClientAgent"/> pipeline.
/// </summary>
/// <remarks>
/// <para>
/// The slot is inert until <see cref="Activate"/> is called: it simply forwards to its inner client.
/// When the agent is wrapped by an <see cref="OpenTelemetryAgent"/>, that agent activates the slot with
/// the resolved source name, at which point the slot routes calls through an
/// <see cref="OpenTelemetryChatClient"/> so chat spans are emitted below the
/// <see cref="FunctionInvokingChatClient"/>.
/// </para>
/// <para>
/// Positioning OpenTelemetry below FICC is required for tool telemetry: the chat span then closes before
/// FICC invokes tools, so <see cref="System.Diagnostics.Activity.Current"/> is the invoke_agent span and
/// FICC emits execute_tool spans on the agent source.
/// </para>
/// </remarks>
internal sealed class DeferredOpenTelemetryChatClient : DelegatingChatClient
{
    private readonly object _activationLock = new();
    private volatile IChatClient _target;
    private OpenTelemetryChatClient? _activatedClient;

    /// <summary>
    /// Initializes a new instance of the <see cref="DeferredOpenTelemetryChatClient"/> class in its inert state.
    /// </summary>
    /// <param name="innerClient">The underlying chat client to forward to until the slot is activated.</param>
    public DeferredOpenTelemetryChatClient(IChatClient innerClient)
        : base(innerClient)
    {
        this._target = innerClient;
    }

    /// <summary>Gets a value indicating whether the slot has been activated.</summary>
    public bool IsActive => !ReferenceEquals(this._target, this.InnerClient);

    /// <summary>
    /// Gets or sets a value indicating whether the activated <see cref="OpenTelemetryChatClient"/> should
    /// include potentially sensitive information (such as message content) in telemetry. Reading or writing
    /// this property is a no-op while the slot is inert; the owning <see cref="OpenTelemetryAgent"/> applies
    /// and propagates the value once the slot is activated.
    /// </summary>
    public bool EnableSensitiveData
    {
        get => this._activatedClient?.EnableSensitiveData ?? false;
        set
        {
            if (this._activatedClient is { } activatedClient)
            {
                activatedClient.EnableSensitiveData = value;
            }
        }
    }

    /// <summary>
    /// Activates the slot so that calls are routed through an <see cref="OpenTelemetryChatClient"/> wrapping
    /// the inner client under the specified <paramref name="sourceName"/>. Idempotent and thread-safe; a
    /// second call (or a call after another thread activated the slot) is a no-op.
    /// </summary>
    /// <param name="sourceName">The telemetry source name to emit chat spans under.</param>
    public void Activate(string sourceName)
    {
        if (this.IsActive)
        {
            return;
        }

        lock (this._activationLock)
        {
            if (this.IsActive)
            {
                return;
            }

            var activatedTarget = this.InnerClient.AsBuilder().UseOpenTelemetry(sourceName: sourceName).Build();

            // Capture the OpenTelemetryChatClient so the owning agent can propagate EnableSensitiveData to it
            // (the agent's value may be set after construction, e.g. via the UseOpenTelemetry configure callback).
            this._activatedClient = activatedTarget.GetService(typeof(OpenTelemetryChatClient)) as OpenTelemetryChatClient;
            this._target = activatedTarget;
        }
    }

    /// <inheritdoc/>
    public override Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default) =>
        this._target.GetResponseAsync(messages, options, cancellationToken);

    /// <inheritdoc/>
    public override IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default) =>
        this._target.GetStreamingResponseAsync(messages, options, cancellationToken);

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        _ = Throw.IfNull(serviceType);

        // Return this slot for its own type and base contracts; otherwise forward to the current target so
        // that, once activated, queries such as OpenTelemetryChatClient and ActivitySource resolve to the
        // activated instrumentation rather than the bare leaf.
        return serviceKey is null && serviceType.IsInstanceOfType(this)
            ? this
            : this._target.GetService(serviceType, serviceKey);
    }

    /// <inheritdoc/>
    protected override void Dispose(bool disposing)
    {
        if (disposing && !ReferenceEquals(this._target, this.InnerClient))
        {
            // When activated, _target is an OpenTelemetryChatClient wrapping the inner client; dispose it so its
            // own telemetry resources are released. It also disposes the inner client, which is idempotent with the
            // base.Dispose call below.
            this._target.Dispose();
        }

        base.Dispose(disposing);
    }
}
