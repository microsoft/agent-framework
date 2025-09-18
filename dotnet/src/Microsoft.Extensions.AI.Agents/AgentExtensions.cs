// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Extension methods for <see cref="AIAgent"/>.
/// </summary>
public static class AgentExtensions
{
    /// <summary>
    /// Wraps the agent with OpenTelemetry instrumentation.
    /// </summary>
    /// <param name="agent">The agent to wrap.</param>
    /// <param name="loggerFactory">The <see cref="ILogger"/> to use for emitting events.</param>
    /// <param name="sourceName">An optional source name that will be used on the telemetry data.</param>
    /// <param name="enableSensitiveData">When <see langword="true"/> indicates whether potentially sensitive information should be included in telemetry. Default is <see langword="false"/></param>
    /// <returns>An <see cref="OpenTelemetryAgent"/> that wraps the original agent with telemetry.</returns>
    public static OpenTelemetryAgent WithOpenTelemetry(this AIAgent agent, ILoggerFactory? loggerFactory = null, string? sourceName = null, bool? enableSensitiveData = null) =>
        new(agent, loggerFactory?.CreateLogger(typeof(OpenTelemetryAgent)), sourceName)
        {
            EnableSensitiveData = enableSensitiveData ?? false
        };

    /// <summary>
    /// Creates a <see cref="AIFunction"/> that will invoke the provided Agent.
    /// </summary>
    /// <param name="agent">The <see cref="AIAgent" /> to be represented via the created <see cref="AIFunction"/>.</param>
    /// <param name="options">Metadata to use to override defaults inferred from <paramref name="agent"/>.</param>
    /// <param name="thread">The <see cref="AgentThread"/> to use for the function.</param>
    /// <returns>The created <see cref="AIFunction"/> for invoking the <see cref="AIAgent"/>.</returns>
    public static AIFunction AsAIFunction(this AIAgent agent, AIFunctionFactoryOptions? options = null, AgentThread? thread = null)
    {
        Throw.IfNull(agent);

        [Description("Invoke an agent to retrieve some information.")]
        async Task<string> InvokeAgentAsync(
            [Description("Input query to invoke the agent.")] string query,
            CancellationToken cancellationToken)
        {
            var response = await agent.RunAsync(query, thread: thread, cancellationToken: cancellationToken).ConfigureAwait(false);
            return response.Text;
        }

        options ??= new();
        options.Name ??= agent.Name;
        options.Description ??= agent.Description;

        return AIFunctionFactory.Create(InvokeAgentAsync, options);
    }
}
