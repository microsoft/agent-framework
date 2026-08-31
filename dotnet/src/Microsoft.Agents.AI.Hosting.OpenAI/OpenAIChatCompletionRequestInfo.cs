// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI;

/// <summary>
/// Exposes the request-supplied generation and tool settings of an OpenAI ChatCompletions
/// <c>create chat completion</c> request that a hosting developer may choose to map onto the
/// <see cref="AgentRunOptions"/> used to run the target <see cref="AIAgent"/>.
/// </summary>
/// <remarks>
/// <para>
/// This type is passed to <see cref="OpenAIChatCompletionsMapOptions.RunOptionsFactory"/>. By default no
/// request setting is mapped onto the agent, because an agent is typically self-contained and
/// allowing callers to override its configuration (for example which tools it may invoke) can cause
/// it to behave in ways its author did not intend.
/// </para>
/// <para>
/// Tool and response-format settings are surfaced using their <c>Microsoft.Extensions.AI</c>
/// equivalents so that a hosting developer can map them directly without re-parsing the wire format.
/// </para>
/// </remarks>
public sealed class OpenAIChatCompletionRequestInfo
{
    /// <summary>
    /// Gets or sets the sampling temperature supplied on the request, if any.
    /// </summary>
    public float? Temperature { get; set; }

    /// <summary>
    /// Gets or sets the nucleus sampling value (<c>top_p</c>) supplied on the request, if any.
    /// </summary>
    public float? TopP { get; set; }

    /// <summary>
    /// Gets or sets the maximum number of completion tokens (<c>max_completion_tokens</c>) supplied on the request, if any.
    /// </summary>
    public int? MaxOutputTokens { get; set; }

    /// <summary>
    /// Gets or sets the frequency penalty supplied on the request, if any.
    /// </summary>
    public float? FrequencyPenalty { get; set; }

    /// <summary>
    /// Gets or sets the presence penalty supplied on the request, if any.
    /// </summary>
    public float? PresencePenalty { get; set; }

    /// <summary>
    /// Gets or sets the deterministic sampling seed supplied on the request, if any.
    /// </summary>
    public long? Seed { get; set; }

    /// <summary>
    /// Gets or sets the stop sequences supplied on the request, if any.
    /// </summary>
    public IReadOnlyList<string>? StopSequences { get; set; }

    /// <summary>
    /// Gets or sets the response format supplied on the request, if any.
    /// </summary>
    public ChatResponseFormat? ResponseFormat { get; set; }

    /// <summary>
    /// Gets or sets the model identifier supplied on the request, if any.
    /// </summary>
    /// <remarks>
    /// This value is informational. It is not applied to local agent execution (the agent runs with
    /// its own <see cref="IChatClient"/>), and the OpenAI ChatCompletions
    /// wire format requires it on every request, so it is intentionally excluded from the default
    /// <see cref="OpenAIChatCompletionsMapOptions.RejectRequestSettings"/> rejection.
    /// </remarks>
    public string? Model { get; set; }

    /// <summary>
    /// Gets or sets the tool selection mode (<c>tool_choice</c>) supplied on the request, if any.
    /// </summary>
    public ChatToolMode? ToolChoice { get; set; }

    /// <summary>
    /// Gets or sets the tools supplied on the request, if any.
    /// </summary>
    public IReadOnlyList<AITool>? Tools { get; set; }
}
