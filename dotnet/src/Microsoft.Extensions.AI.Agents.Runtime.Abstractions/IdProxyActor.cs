// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Provides an actor proxy that allows you to use an <see cref="ActorId"/> in place of its associated <see cref="IRuntimeActor"/>.
/// </summary>
public sealed class IdProxyActor : IRuntimeActor
{
    /// <summary>The runtime instance used to interact with actors.</summary>
    private readonly IAgentRuntime _runtime;
    /// <summary>The metadata for the actor, lazy-loaded.</summary>
    private ActorMetadata? _metadata;

    /// <summary>
    /// Initializes a new instance of the <see cref="IdProxyActor"/> class.
    /// </summary>
    public IdProxyActor(IAgentRuntime runtime, ActorId actorId)
    {
        Throw.IfNull(runtime);

        this.Id = actorId;
        this._runtime = runtime;
    }

    /// <inheritdoc />
    public ActorId Id { get; }

    /// <inheritdoc />
    public ActorMetadata Metadata =>
        this._metadata ??=
#pragma warning disable VSTHRD002 // Avoid problematic synchronous waits
        this._runtime.GetActorMetadataAsync(this.Id).AsTask().GetAwaiter().GetResult();
#pragma warning restore VSTHRD002

    /// <inheritdoc />
    public ValueTask<object?> SendMessageAsync(object message, ActorId sender, string? messageId = null, CancellationToken cancellationToken = default) =>
        this._runtime.SendMessageAsync(message, this.Id, sender, messageId, cancellationToken);

    /// <inheritdoc />
    public ValueTask LoadStateAsync(JsonElement state, CancellationToken cancellationToken = default) =>
        this._runtime.LoadActorStateAsync(this.Id, state, cancellationToken);

    /// <inheritdoc />
    public ValueTask<JsonElement> SaveStateAsync(CancellationToken cancellationToken = default) =>
        this._runtime.SaveActorStateAsync(this.Id, cancellationToken);

    /// <inheritdoc />
    ValueTask<object?> IRuntimeActor.OnMessageAsync(object message, MessageContext messageContext, CancellationToken cancellationToken) =>
        new((object?)null);
}
