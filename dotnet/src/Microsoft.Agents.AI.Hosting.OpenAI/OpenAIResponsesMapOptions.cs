// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.OpenAI;

/// <summary>
/// Options that control how an OpenAI Responses endpoint maps incoming requests onto the target
/// <see cref="AIAgent"/>.
/// </summary>
public sealed class OpenAIResponsesMapOptions
{
    /// <summary>
    /// Gets or sets the callback used to produce the <see cref="AgentRunOptions"/> for a request from
    /// the request-supplied generation and tool settings.
    /// </summary>
    /// <remarks>
    /// <para>
    /// By default this uses <see cref="RejectRequestSettings"/>, which throws when the request
    /// carries any setting that would otherwise be mapped onto the agent (for example
    /// <c>temperature</c>, <c>instructions</c>, <c>tools</c> or <c>tool_choice</c>). This prevents a
    /// caller from silently overriding the configuration of a self-contained agent.
    /// Enabling <see cref="DangerouslyAllowClientFunctionTools"/> selects a default mapping that
    /// forwards function declarations while continuing to reject other unsupported settings.
    /// </para>
    /// <para>
    /// Hosting developers that want to honor specific request settings can supply their own callback
    /// that maps the desired fields onto an <see cref="AgentRunOptions"/> (or a subclass such as
    /// <see cref="ChatClientAgentRunOptions"/>), and may choose to throw, map, or ignore any field.
    /// A custom callback receives all request settings, including the complete
    /// <see cref="OpenAIResponseRequestInfo.Tools"/> collection, and replaces the default mapping.
    /// Its result is used unchanged, regardless of <see cref="DangerouslyAllowClientFunctionTools"/>.
    /// Returning <see langword="null"/> runs the agent with its own configuration only.
    /// </para>
    /// </remarks>
    public Func<OpenAIResponseRequestInfo, AgentRunOptions?> RunOptionsFactory
    {
        get
        {
#pragma warning disable MAAI001
            return field ?? (this.DangerouslyAllowClientFunctionTools
                ? MapClientFunctionTools
                : RejectRequestSettings);
#pragma warning restore MAAI001
        }
        set
        {
            field = Throw.IfNull(value);
        }
    }

    /// <summary>
    /// Gets or sets whether the default mapping forwards client-provided function declarations
    /// in the agent's run options.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This setting is dangerous because client-provided function names, descriptions, and schemas
    /// can change which tools the model chooses. The declarations do not contain executable code.
    /// The downstream chat client and provider determine how function calls are handled.
    /// </para>
    /// <para>
    /// A client function may cause the model to choose it instead of a function configured by the
    /// hosted agent developer, even when their names do not conflict. Function arguments and any data
    /// included in those arguments are then returned to the client.
    /// </para>
    /// <para>
    /// The default is <see langword="false"/>, which leaves client-provided tools subject to
    /// <see cref="RunOptionsFactory"/> and its default <see cref="RejectRequestSettings"/> behavior. The request's
    /// <c>tool_choice</c> is not enabled by this setting and remains controlled by
    /// <see cref="RunOptionsFactory"/>.
    /// </para>
    /// <para>
    /// With the default mapping, accepted function declarations are converted to
    /// <c>ChatClientAgentRunOptions.ChatOptions.Tools</c>. Other tool types and unsupported request
    /// settings are rejected. This setting has no effect when a custom <see cref="RunOptionsFactory"/>
    /// is supplied; that callback owns the entire mapping.
    /// </para>
    /// <para>
    /// The default mapping produces <see cref="ChatClientAgentRunOptions"/>. The hosting layer
    /// does not require a particular agent implementation. Agents that do not consume these options
    /// may ignore the mapped functions; enabling this setting does not add function support to them.
    /// </para>
    /// <para>
    /// Function names are not checked for conflicts or deduplicated. The downstream chat client and
    /// provider determine whether duplicate names are accepted and which function is selected.
    /// The hosting layer does not guarantee that a hosted function takes precedence over a client
    /// declaration. The agent's parallel tool calling configuration is not changed.
    /// </para>
    /// </remarks>
    [Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
    public bool DangerouslyAllowClientFunctionTools { get; set; }

    /// <summary>
    /// The default <see cref="RunOptionsFactory"/> implementation. Throws a <see cref="NotSupportedException"/>
    /// when the request specifies any setting that would otherwise be mapped onto the agent, and otherwise
    /// returns <see langword="null"/> so that the agent runs with its own configuration only.
    /// </summary>
    /// <param name="request">The request-supplied settings.</param>
    /// <returns>Always <see langword="null"/> when no unsupported setting is present.</returns>
    /// <remarks>
    /// <see cref="OpenAIResponseRequestInfo.Model"/> is intentionally not treated as an unsupported
    /// setting: it is informational and is not applied to local execution.
    /// </remarks>
    /// <exception cref="NotSupportedException">One or more request settings are not supported.</exception>
    public static AgentRunOptions? RejectRequestSettings(OpenAIResponseRequestInfo request)
    {
        ArgumentNullException.ThrowIfNull(request);

        ThrowIfUnsupportedRequestSettings(request, request.Tools);
        return null;
    }

    private static AgentRunOptions? MapClientFunctionTools(OpenAIResponseRequestInfo request)
    {
        ArgumentNullException.ThrowIfNull(request);

        if (request.Tools is not { Count: > 0 } tools)
        {
            return RejectRequestSettings(request);
        }

        (List<AITool>? clientTools, List<JsonElement>? remainingTools) = tools.ConvertClientFunctionTools();
        ThrowIfUnsupportedRequestSettings(request, remainingTools);
        return clientTools is { Count: > 0 }
            ? new ChatClientAgentRunOptions(new ChatOptions { Tools = clientTools })
            : null;
    }

    private static void ThrowIfUnsupportedRequestSettings(
        OpenAIResponseRequestInfo request,
        IReadOnlyList<JsonElement>? tools)
    {
        List<string>? unsupported = null;
        void LocalAdd(string name) => (unsupported ??= []).Add(name);

        if (request.Temperature is not null)
        {
            LocalAdd("temperature");
        }

        if (request.TopP is not null)
        {
            LocalAdd("top_p");
        }

        if (request.MaxOutputTokens is not null)
        {
            LocalAdd("max_output_tokens");
        }

        if (request.Instructions is not null)
        {
            LocalAdd("instructions");
        }

        if (tools is { Count: > 0 })
        {
            LocalAdd("tools");
        }

        if (request.HasToolChoice || request.ToolChoice is not null)
        {
            LocalAdd("tool_choice");
        }

        if (unsupported is not null)
        {
            throw new NotSupportedException(
                $"The following request setting(s) are not supported by this agent endpoint: {string.Join(", ", unsupported)}. " +
                "Configure an OpenAIResponsesMapOptions.RunOptionsFactory to map these settings onto the agent if they should be honored.");
        }
    }
}
