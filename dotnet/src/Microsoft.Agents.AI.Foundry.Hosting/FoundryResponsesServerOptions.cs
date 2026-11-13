// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.AgentServer.Responses;
using Microsoft.Extensions.DependencyInjection;


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
    /// Gets or sets a value indicating whether the agent's chat client is allowed to store responses
    /// in the inference service it calls.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This option controls storage in the inference service, not storage of the hosted response
    /// returned to the caller. Foundry response storage is configured separately through the hosting
    /// Responses API, including the caller's <c>store</c> setting. Disabling inference-service storage
    /// does not disable Foundry response storage.
    /// </para>
    /// <para>
    /// While this is <see langword="false"/>, hosting sets <c>store</c> to <see langword="false"/> on
    /// OpenAI Responses and Chat Completions requests sent by the agent's chat client to the inference
    /// service. Other request types are left unchanged. The readiness probe reports an agent whose
    /// configuration would keep inference-service storage on. Set this option to <see langword="true"/>
    /// to leave the agent's own storage setting unchanged and skip that check.
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
    /// Gets or sets a value indicating whether hosting should refrain from requesting encrypted
    /// reasoning content from the inference service.
    /// </summary>
    /// <remarks>
    /// <para>
    /// While <see cref="InferenceStoredOutputAllowed"/> is <see langword="false"/>, hosting adds
    /// <c>reasoning.encrypted_content</c> to the included properties of OpenAI Responses requests sent
    /// by the agent's chat client. Encrypted reasoning content is an opaque value that compatible
    /// clients can send back to the inference service to continue reasoning across turns without
    /// storing the response in that service.
    /// </para>
    /// <para>
    /// Set this option to <see langword="true"/> to prevent hosting from adding that included property.
    /// It does not remove an included property already configured by the agent. This option has no
    /// effect while <see cref="InferenceStoredOutputAllowed"/> is <see langword="true"/>.
    /// </para>
    /// <para>
    /// This option changes requests to the inference service, not the hosted response returned to the
    /// caller or Foundry response storage. Requesting encrypted reasoning content does not by itself
    /// ensure that hosting preserves it or sends it back on later turns.
    /// </para>
    /// </remarks>
    /// <value>
    /// Default is <see langword="false"/>.
    /// </value>
    public bool ExcludeReasoningEncryptedContent { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether hosting adds an <see cref="OpenTelemetryAgent"/> to an agent
    /// created for each response.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Hosting adds an <see cref="OpenTelemetryAgent"/> to an agent it reuses for every response, one passed
    /// as an instance or created by a factory with <see cref="ServiceLifetime.Singleton"/>, unless the agent
    /// already has one. It builds that wrapper once and disposes it at shutdown.
    /// </para>
    /// <para>
    /// For an agent created per response by a factory with <see cref="ServiceLifetime.Scoped"/> or
    /// <see cref="ServiceLifetime.Transient"/>, hosting adds the wrapper after applying Foundry workflow
    /// checkpointing and disposes it before disposing the factory-created agent when the response ends.
    /// Return the agent without an <see cref="OpenTelemetryAgent"/> to let hosting own and dispose both lifetimes.
    /// When a factory supplies its own wrapper, hosting uses and disposes that wrapper but the factory must arrange
    /// the lifetime of the agent inside it independently, because <see cref="OpenTelemetryAgent"/> does not own it.
    /// </para>
    /// <para>
    /// Set this option to <see langword="false"/> to serve an agent created per response without agent telemetry.
    /// It has no effect on an agent reused for every response.
    /// </para>
    /// </remarks>
    /// <value>
    /// Default is <see langword="true"/>.
    /// </value>
    public bool RequireOpenTelemetryAgent { get; set; } = true;
}
