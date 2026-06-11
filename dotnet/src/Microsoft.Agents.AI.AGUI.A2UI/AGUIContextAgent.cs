// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI.A2UI;

/// <summary>
/// Surfaces forwarded AG-UI context entries to the model by prepending them as a system
/// message. The AG-UI hosting layer stores incoming <c>context</c> entries in
/// <see cref="ChatOptions.AdditionalProperties"/> (<c>ag_ui_context</c>), where the model
/// never sees them; this wrapper renders each entry as a markdown section so
/// client-driven guidance — e.g. the A2UI middleware's injected component schema and
/// render-tool usage guide — reaches the prompt without any agent-specific code.
/// </summary>
/// <remarks>
/// This is the missing piece of the zero-configuration A2UI path: the AG-UI client
/// middleware injects the <c>render_a2ui</c> tool (bound automatically from the incoming
/// tool list) plus its usage guidelines and catalog schema as context entries; with this
/// wrapper the model receives both, and a plain chat agent can render A2UI surfaces with
/// no further setup.
/// </remarks>
public sealed class AGUIContextAgent : DelegatingAIAgent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AGUIContextAgent"/> class.
    /// </summary>
    /// <param name="innerAgent">The agent to wrap.</param>
    public AGUIContextAgent(AIAgent innerAgent)
        : base(innerAgent)
    {
    }

    /// <inheritdoc/>
    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
        => this.InnerAgent.RunAsync(WithContextPrompt(messages, options), session, options, cancellationToken);

    /// <inheritdoc/>
    protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
        => this.InnerAgent.RunStreamingAsync(WithContextPrompt(messages, options), session, options, cancellationToken);

    private static IEnumerable<ChatMessage> WithContextPrompt(IEnumerable<ChatMessage> messages, AgentRunOptions? options)
    {
        if (options is not ChatClientAgentRunOptions { ChatOptions.AdditionalProperties: { } properties })
        {
            return messages;
        }

        // Shared routing with A2UIAgent: the catalog schema entry lands in the
        // canonical "## Available Components" section, other entries become
        // plain context sections — both agents render the same prompt for the
        // same forwarded context.
        string prompt = A2UIToolkit.BuildContextPrompt(A2UIAgent.ReadAgentState(properties));

        return prompt.Length == 0
            ? messages
            : messages.Prepend(new ChatMessage(ChatRole.System, prompt));
    }
}
