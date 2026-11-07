// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.AgentServer.Responses;


namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Options for hosting agents behind the Foundry Responses API.
/// </summary>
/// <remarks>
/// <para>
/// Inherited <see cref="ResponsesServerOptions"/> properties configure AgentServer directly.
/// When this object is supplied to <c>AddFoundryResponses</c>, its values, including upstream
/// defaults, override values from host configuration.
/// </para>
/// <para>
/// Required inputs, such as the agent and an optional replacement <see cref="AgentSessionStore"/>,
/// are supplied directly to <c>AddFoundryResponses</c>.
/// </para>
/// </remarks>
public sealed class FoundryResponsesServerOptions : ResponsesServerOptions
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
    /// <para>
    /// A local conversation marker used by the framework to persist chat history in the agent
    /// session does not count as service-stored output and does not require this option.
    /// </para>
    /// </remarks>
    /// <value>
    /// Default is <see langword="false"/>.
    /// </value>
    public bool InferenceStoredOutputAllowed { get; set; }

    /// <summary>
    /// Gets or sets the function result returned for calls that are not executed because another call
    /// in the same batch requires OAuth consent.
    /// </summary>
    /// <remarks>
    /// This result can be sent to the inference service when
    /// <see cref="InferenceStoredOutputAllowed"/> is <see langword="true"/>, so phrase it as context
    /// for the model rather than as an instruction to the end user. It is also recorded in the
    /// Hosted Agent response for sequential calls skipped by the consent handoff.
    /// </remarks>
    public string OAuthConsentInterruptedToolResult { get; set; } = McpConsentResults.NotExecuted;

    /// <summary>
    /// Gets or sets a value indicating whether to exclude an encrypted version of reasoning tokens from
    /// reasoning item outputs.
    /// </summary>
    /// <remarks>
    /// By default, encrypted reasoning tokens are included so reasoning items can be used in multi-turn
    /// conversations when using the Responses API statelessly (like when the store parameter is set to
    /// false, or when an organization is enrolled in the zero data retention program). Set this option
    /// to <see langword="true"/> to omit them. It applies only while
    /// <see cref="InferenceStoredOutputAllowed"/> is <see langword="false"/>, because that is when hosting
    /// turns storage off and the reasoning items would otherwise be lost between turns.
    /// </remarks>
    /// <value>
    /// Default is <see langword="false"/>.
    /// </value>
    public bool ExcludeReasoningEncryptedContent { get; set; }

}
