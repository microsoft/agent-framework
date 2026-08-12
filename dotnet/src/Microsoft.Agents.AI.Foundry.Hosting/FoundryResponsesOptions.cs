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
}
