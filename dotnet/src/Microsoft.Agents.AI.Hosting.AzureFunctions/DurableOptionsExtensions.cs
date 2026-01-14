// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Azure.Functions.Worker.Core.FunctionMetadata;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Worker;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Extension methods for configuring durable options (agents and workflows).
/// </summary>
public static class DurableOptionsExtensions
{
    /// <summary>
    /// Configures durable agents and workflows in a unified way.
    /// </summary>
    /// <param name="builder">The Functions application builder.</param>
    /// <param name="configure">A delegate to configure the durable options.</param>
    /// <returns>The Functions application builder for method chaining.</returns>
    /// <remarks>
    /// This method provides a unified configuration point for both durable agents and workflows.
    /// Agents configured here will be automatically registered when referenced in workflows.
    /// </remarks>
    public static FunctionsApplicationBuilder ConfigureDurableOptions(
        this FunctionsApplicationBuilder builder,
        Action<DurableOptions> configure)
    {
        ArgumentNullException.ThrowIfNull(configure);

        DurableOptions options = new();
        configure(options);

        // Register the unified DurableOptions for components that need both agents and workflows
        builder.Services.AddSingleton(options);

        // Register AgentsOption for backward compatibility. Can be removed if needed, after syncing with team.
        builder.Services.AddSingleton(options.Agents);

        // Configure agents using the existing infrastructure
        builder.Services.ConfigureDurableAgents(agentOpts =>
        {
            // Copy agent registrations from the unified options to the service-level options
            foreach (KeyValuePair<string, Func<IServiceProvider, AIAgent>> agentFactory in options.Agents.GetAgentFactories())
            {
                agentOpts.AddAIAgentFactory(
                    agentFactory.Key,
                    agentFactory.Value,
                    options.Agents.GetTimeToLive(agentFactory.Key));
            }

            // Copy TTL settings
            agentOpts.DefaultTimeToLive = options.Agents.DefaultTimeToLive;
            agentOpts.MinimumTimeToLiveSignalDelay = options.Agents.MinimumTimeToLiveSignalDelay;
        });

        builder.Services.TryAddSingleton<IFunctionsAgentOptionsProvider>(_ =>
            new DefaultFunctionsAgentOptionsProvider(DurableAgentsOptionsExtensions.GetAgentOptionsSnapshot()));

        builder.Services.AddSingleton<IFunctionMetadataTransformer, DurableAgentFunctionMetadataTransformer>();

        // Handling of built-in function execution for Agent HTTP, MCP tool, or Entity invocations.
        builder.UseWhen<BuiltInFunctionExecutionMiddleware>(static context =>
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunAgentHttpFunctionEntryPoint, StringComparison.Ordinal) ||
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunAgentMcpToolFunctionEntryPoint, StringComparison.Ordinal) ||
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunWorkflowOrechstrtationFunctionEntryPoint, StringComparison.Ordinal) ||
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunWorkflowOrechstrtationHttpFunctionEntryPoint, StringComparison.Ordinal) ||
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.InvokeWorkflowActivityFunctionEntryPoint, StringComparison.Ordinal) ||
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunAgentEntityFunctionEntryPoint, StringComparison.Ordinal));
        builder.Services.AddSingleton<BuiltInFunctionExecutor>();

        builder.Services.AddSingleton<DurableWorkflowRunner>();

        builder.ConfigureDurableWorker().AddTasks(t => t.AddOrchestratorFunc<DuableWorkflowRunRequest, List<string>>(
            "WorkflowRunnerOrchestration",
            async (tc, inputBindingData) =>
            {
                FunctionContext? functionContext = tc.GetFunctionContext();
                if (functionContext == null)
                {
                    throw new InvalidOperationException("FunctionContext is not available in the orchestration context.");
                }

                DurableWorkflowRunner runner = functionContext.InstanceServices.GetRequiredService<DurableWorkflowRunner>();
                return await runner.RunWorkflowOrchestrationAsync(tc, inputBindingData).ConfigureAwait(false);
            }));

        builder.Services.AddSingleton<IFunctionMetadataTransformer, DurableWorkflowFunctionMetadataTransformer>();

        return builder;
    }
}
