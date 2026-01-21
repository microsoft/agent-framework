// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Worker;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;

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
    /// It automatically generates HTTP API endpoints for agents and workflows, and configures
    /// the necessary middleware and services for durable execution.
    /// </remarks>
    public static FunctionsApplicationBuilder ConfigureDurableOptions(
        this FunctionsApplicationBuilder builder,
        Action<DurableOptions> configure)
    {
        ArgumentNullException.ThrowIfNull(builder);
        ArgumentNullException.ThrowIfNull(configure);

        DurableOptions options = new();
        configure(options);

        RegisterServices(builder, options);
        ConfigureAgents(builder, options);
        builder.ConfigureBuiltInFunctionMiddleware();

        if (options.Workflows.Workflows.Count > 0)
        {
            builder.RegisterWorkflowServices();
            ConfigureWorkflowOrchestrations(builder, options.Workflows);
        }

        return builder;
    }

    private static void RegisterServices(FunctionsApplicationBuilder builder, DurableOptions options)
    {
        builder.Services.TryAddSingleton(options);
        builder.Services.TryAddSingleton(options.Agents); // backward compatibility. can be removed in future.

        builder.RegisterCoreAgentServices();
    }

    private static void ConfigureAgents(FunctionsApplicationBuilder builder, DurableOptions options)
    {
        builder.Services.ConfigureDurableAgents(agentOpts =>
        {
            foreach (KeyValuePair<string, Func<IServiceProvider, AIAgent>> agentFactory in options.Agents.GetAgentFactories())
            {
                bool isWorkflowOnly = options.Agents.IsWorkflowOnly(agentFactory.Key);

                agentOpts.AddAIAgentFactory(
                    agentFactory.Key,
                    agentFactory.Value,
                    enableHttpTrigger: !isWorkflowOnly,
                    enableMcpToolTrigger: false,
                    timeToLive: options.Agents.GetTimeToLive(agentFactory.Key));
            }

            agentOpts.DefaultTimeToLive = options.Agents.DefaultTimeToLive;
            agentOpts.MinimumTimeToLiveSignalDelay = options.Agents.MinimumTimeToLiveSignalDelay;
        });
    }

    private static void ConfigureWorkflowOrchestrations(FunctionsApplicationBuilder builder, DurableWorkflowOptions workflows)
    {
        builder.ConfigureDurableWorker().AddTasks(tasks =>
        {
            // Register the workflow state entity for shared state management within workflows.
            tasks.AddEntity<WorkflowSharedStateEntity>(WorkflowSharedStateEntity.EntityName);

            foreach (string workflowName in workflows.Workflows.Select(kp => kp.Key))
            {
                string orchestrationFunctionName = WorkflowNamingHelper.ToOrchestrationFunctionName(workflowName);

                tasks.AddOrchestratorFunc<string, string>(
                    orchestrationFunctionName,
                    async (orchestrationContext, request) =>
                    {
                        FunctionContext functionContext = orchestrationContext.GetFunctionContext()
                            ?? throw new InvalidOperationException("FunctionContext is not available in the orchestration context.");

                        DurableWorkflowRunner runner = functionContext.InstanceServices.GetRequiredService<DurableWorkflowRunner>();
                        ILogger logger = orchestrationContext.CreateReplaySafeLogger(orchestrationFunctionName);

                        return await runner.RunWorkflowOrchestrationAsync(orchestrationContext, request, logger).ConfigureAwait(true);
                    });
            }
        });
    }
}
