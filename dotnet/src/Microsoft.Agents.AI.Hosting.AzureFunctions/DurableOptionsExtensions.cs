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
        ConfigureMiddleware(builder);
        ConfigureWorkflowOrchestration(builder);

        return builder;
    }

    private static void RegisterServices(FunctionsApplicationBuilder builder, DurableOptions options)
    {
        builder.Services.AddSingleton(options);
        builder.Services.AddSingleton(options.Agents);
        builder.Services.AddSingleton<BuiltInFunctionExecutor>();
        builder.Services.AddSingleton<DurableWorkflowRunner>();
        builder.Services.AddSingleton<IFunctionMetadataTransformer, DurableAgentFunctionMetadataTransformer>();
        builder.Services.AddSingleton<IFunctionMetadataTransformer, DurableWorkflowFunctionMetadataTransformer>();

        builder.Services.TryAddSingleton<IFunctionsAgentOptionsProvider>(_ =>
            new DefaultFunctionsAgentOptionsProvider(DurableAgentsOptionsExtensions.GetAgentOptionsSnapshot()));
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

    private static void ConfigureMiddleware(FunctionsApplicationBuilder builder)
    {
        builder.UseWhen<BuiltInFunctionExecutionMiddleware>(static context =>
            IsBuiltInFunction(context.FunctionDefinition.EntryPoint));
    }

    private static bool IsBuiltInFunction(string? entryPoint)
    {
        return string.Equals(entryPoint, BuiltInFunctions.RunAgentHttpFunctionEntryPoint, StringComparison.Ordinal)
            || string.Equals(entryPoint, BuiltInFunctions.RunAgentMcpToolFunctionEntryPoint, StringComparison.Ordinal)
            || string.Equals(entryPoint, BuiltInFunctions.RunWorkflowOrechstrtationHttpFunctionEntryPoint, StringComparison.Ordinal)
            || string.Equals(entryPoint, BuiltInFunctions.InvokeWorkflowActivityFunctionEntryPoint, StringComparison.Ordinal)
            || string.Equals(entryPoint, BuiltInFunctions.RunAgentEntityFunctionEntryPoint, StringComparison.Ordinal);
    }

    private static void ConfigureWorkflowOrchestration(FunctionsApplicationBuilder builder)
    {
        // Registering a single orchestration function to handle all workflow runs.
        // This is due to a gap in durable extension today and can be replace with dynamic orchestration registration in future, per workflow.

        builder.ConfigureDurableWorker().AddTasks(tasks =>
            tasks.AddOrchestratorFunc<DuableWorkflowRunRequest, List<string>>(
                "WorkflowRunnerOrchestration",
                async (orchestrationContext, request) =>
                {
                    FunctionContext functionContext = orchestrationContext.GetFunctionContext()
                        ?? throw new InvalidOperationException("FunctionContext is not available in the orchestration context.");

                    DurableWorkflowRunner runner = functionContext.InstanceServices.GetRequiredService<DurableWorkflowRunner>();
                    ILogger logger = orchestrationContext.CreateReplaySafeLogger("WorkflowRunnerOrchestration");

                    return await runner.RunWorkflowOrchestrationAsync(orchestrationContext, request, logger).ConfigureAwait(true);
                }));
    }
}
