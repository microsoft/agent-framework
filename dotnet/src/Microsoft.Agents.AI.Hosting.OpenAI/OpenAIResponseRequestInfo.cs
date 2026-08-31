// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI;

/// <summary>
/// Exposes the request-supplied generation and tool settings of an OpenAI Responses
/// <c>create response</c> request that a hosting developer may choose to map onto the
/// <see cref="AgentRunOptions"/> used to run the target <see cref="AIAgent"/>.
/// </summary>
/// <remarks>
/// <para>
/// This type is passed to <see cref="OpenAIResponsesMapOptions.RunOptionsFactory"/>. By default no
/// request setting is mapped onto the agent, because an agent is typically self-contained and
/// allowing callers to override its configuration (for example its instructions or which tools it
/// may invoke) can cause it to behave in ways its author did not intend.
/// </para>
/// <para>
/// Only the subset of request fields that are meaningful to map onto a local agent run are exposed.
/// The raw wire model is intentionally not surfaced.
/// </para>
/// </remarks>
public sealed class OpenAIResponseRequestInfo
{
    /// <summary>
    /// Gets or sets the sampling temperature supplied on the request, if any.
    /// </summary>
    public double? Temperature { get; set; }

    /// <summary>
    /// Gets or sets the nucleus sampling value (<c>top_p</c>) supplied on the request, if any.
    /// </summary>
    public double? TopP { get; set; }

    /// <summary>
    /// Gets or sets the maximum number of output tokens supplied on the request, if any.
    /// </summary>
    public int? MaxOutputTokens { get; set; }

    /// <summary>
    /// Gets or sets the instructions supplied on the request, if any.
    /// </summary>
    public string? Instructions { get; set; }

    /// <summary>
    /// Gets or sets the model identifier supplied on the request, if any.
    /// </summary>
    /// <remarks>
    /// This value is informational. It is not applied to local agent execution (the agent runs with
    /// its own <see cref="IChatClient"/>), so it is intentionally excluded
    /// from the default <see cref="OpenAIResponsesMapOptions.RejectRequestSettings"/> rejection.
    /// </remarks>
    public string? Model { get; set; }

    /// <summary>
    /// Gets or sets the raw <c>tools</c> array supplied on the request, if any.
    /// </summary>
    /// <remarks>
    /// The OpenAI Responses wire format represents tools as JSON tool declarations rather than
    /// executable functions, so they are surfaced here as the raw <see cref="JsonElement"/> values.
    /// </remarks>
    public IReadOnlyList<JsonElement>? Tools { get; set; }

    /// <summary>
    /// Gets or sets the tool selection mode (<c>tool_choice</c>) supplied on the request, if any.
    /// </summary>
    /// <remarks>
    /// The OpenAI Responses <c>tool_choice</c> value is mapped onto its
    /// <see cref="ChatToolMode"/> equivalent (<c>none</c>, <c>auto</c>,
    /// <c>required</c>, or a specific function). Values that have no equivalent are surfaced as
    /// <see langword="null"/>.
    /// </remarks>
    public ChatToolMode? ToolChoice { get; set; }
}
