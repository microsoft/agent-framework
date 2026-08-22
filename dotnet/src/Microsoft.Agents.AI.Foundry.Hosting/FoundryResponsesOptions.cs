// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Options for hosting agents behind the Foundry Responses API.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FoundryResponsesOptions
{
    /// <summary>
    /// Gets or sets a value indicating whether the agent's own chat client is allowed to store the
    /// responses it produces.
    /// </summary>
    /// <remarks>
    /// <para>
    /// A hosted turn is already recorded by the storage provider that runs around this handler, and
    /// that record is the conversation the caller reads back. When the service behind the agent's chat
    /// client also stores the turn, the same exchange is written a second time onto a trail of its own,
    /// which nothing here reads and no one reconciles with the first.
    /// </para>
    /// <para>
    /// While this is <see langword="false"/>, hosting turns that storage off for every run (the "store"
    /// property in the JSON representation), and the readiness probe reports an agent whose
    /// configuration would keep it on. Set it to <see langword="true"/> to leave the agent's own
    /// setting exactly as the container configured it, in which case hosting neither changes it nor
    /// checks it.
    /// </para>
    /// </remarks>
    /// <value>
    /// Default is <see langword="false"/>.
    /// </value>
    public bool AllowStoredOutputEnabled { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether to include an encrypted version of reasoning tokens in
    /// reasoning item outputs.
    /// </summary>
    /// <remarks>
    /// This enables reasoning items to be used in multi-turn conversations when using the Responses API
    /// statelessly (like when the store parameter is set to false, or when an organization is enrolled
    /// in the zero data retention program). It applies only while
    /// <see cref="AllowStoredOutputEnabled"/> is <see langword="false"/>, because that is when hosting
    /// turns storage off and the reasoning items would otherwise be lost between turns.
    /// </remarks>
    /// <value>
    /// Default is <see langword="true"/>.
    /// </value>
    public bool IncludeReasoningEncryptedContent { get; set; } = true;

    /// <summary>
    /// Gets or sets a value indicating whether background responses are resilient to process crashes
    /// and graceful shutdown.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When <see langword="true"/>, accepted background responses (<c>background=true</c> and
    /// <c>store</c> omitted or <see langword="true"/>) are registered with the durable task subsystem
    /// so a handler interrupted by a crash or shutdown is
    /// re-invoked in a subsequent process lifetime with the original request context restored
    /// (<c>ResponseContext.IsRecovery</c> is <see langword="true"/>). AgentServer supplies its last durable
    /// response snapshot. For workflow agents, the hosting handler pairs completed supersteps with response
    /// checkpoints and records the matching workflow checkpoint ID in AgentServer internal response metadata.
    /// Recovery restores the AgentSession, selects that exact workflow checkpoint, skips re-injecting the
    /// original input, and defers on shutdown instead of ending the response as incomplete. Regular agents
    /// continue to depend on their serialized AgentSession state.
    /// </para>
    /// <para>
    /// When <see langword="false"/> (the default), an interrupted background response transitions to a
    /// failed terminal state and is not re-invoked. The hosting handler does not perform resilient
    /// mid-turn session saves or shutdown deferral.
    /// </para>
    /// <para>
    /// This value is forwarded to
    /// <see cref="Azure.AI.AgentServer.Responses.ResponsesServerOptions.ResilientBackground"/>.
    /// </para>
    /// </remarks>
    /// <value>
    /// Default is <see langword="false"/>.
    /// </value>
    public bool ResilientBackground { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether in-flight conversations accept steering (mid-turn
    /// additional input) sharing a single resilient task.
    /// </summary>
    /// <remarks>
    /// Forwarded to
    /// <see cref="Azure.AI.AgentServer.Responses.ResponsesServerOptions.SteerableConversations"/>.
    /// When <see langword="false"/> (the default), steering is disabled.
    /// </remarks>
    /// <value>
    /// Default is <see langword="false"/>.
    /// </value>
    public bool SteerableConversations { get; set; }
}
