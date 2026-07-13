// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
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
    /// By default this is set to <see cref="RejectRequestSettings"/>, which throws when the request
    /// carries any setting that would otherwise be mapped onto the agent (for example
    /// <c>temperature</c>, <c>instructions</c>, <c>tools</c> or <c>tool_choice</c>). This prevents a
    /// caller from silently overriding the configuration of a self-contained agent.
    /// </para>
    /// <para>
    /// Hosting developers that want to honor specific request settings can supply their own callback
    /// that maps the desired fields onto an <see cref="AgentRunOptions"/> (or a subclass such as
    /// <see cref="ChatClientAgentRunOptions"/>), and may choose to throw, map, or ignore any field.
    /// Returning <see langword="null"/> runs the agent with its own configuration only.
    /// </para>
    /// </remarks>
    public Func<OpenAIResponseRequestInfo, AgentRunOptions?> RunOptionsFactory
    {
        get;
        set
        {
            field = Throw.IfNull(value);
        }
    } = RejectRequestSettings;

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

        if (request.Tools is { Count: > 0 })
        {
            LocalAdd("tools");
        }

        if (request.ToolChoice is not null)
        {
            LocalAdd("tool_choice");
        }

        if (unsupported is not null)
        {
            throw new NotSupportedException(
                $"The following request setting(s) are not supported by this agent endpoint: {string.Join(", ", unsupported)}. " +
                "Configure an OpenAIResponsesMapOptions.RunOptionsFactory to map these settings onto the agent if they should be honored.");
        }

        return null;
    }
}
