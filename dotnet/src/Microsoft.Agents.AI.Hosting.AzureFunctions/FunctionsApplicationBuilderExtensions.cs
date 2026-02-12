// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Hosting.AzureFunctions.Workflows;
using Microsoft.Agents.AI.Workflows;
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
/// Extension methods for the <see cref="FunctionsApplicationBuilder"/> class.
/// </summary>
public static class FunctionsApplicationBuilderExtensions
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

        builder.Services.AddSingleton(options);

        if (options.Workflows.Workflows.Count > 0)
        {
            ConfigureWorkflowOrchestrations(builder, options.Workflows);
            // Do things to enable workflow as orchestrator functions.
            // Register the Workflow metadata transformer.
            builder.ConfigureDurableWorkflows(durableWorkflwoOptions =>
            {
                // what
            });

            builder.Services.AddSingleton<IFunctionMetadataTransformer, DurableWorkflowFunctionMetadataTransformer>();

            builder.UseWhen<BuiltInFunctionExecutionMiddleware>(static context =>
    string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunAgentHttpFunctionEntryPoint, StringComparison.Ordinal) ||
    string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunAgentMcpToolFunctionEntryPoint, StringComparison.Ordinal) ||
    string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunAgentEntityFunctionEntryPoint, StringComparison.Ordinal)
    || string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunWorkflowOrechstrtationHttpFunctionEntryPoint, StringComparison.Ordinal)

     || string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunWorkflowOrechstrtationHttpFunctionEntryPoint, StringComparison.Ordinal)
        || string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.InvokeWorkflowOrchestrationFunctionEntryPoint, StringComparison.Ordinal)
        || string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.InvokeWorkflowActivityFunctionEntryPoint, StringComparison.Ordinal)
    );
            builder.Services.AddSingleton<BuiltInFunctionExecutor>();

            //builder.UseWhen<BuiltInFunctionExecutionMiddleware>(static context =>
            //    string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunWorkflowOrechstrtationHttpFunctionEntryPoint, StringComparison.Ordinal)
            //    || string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.InvokeWorkflowOrchestrationFunctionEntryPoint, StringComparison.Ordinal)
            //    || string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.InvokeWorkflowActivityFunctionEntryPoint, StringComparison.Ordinal)
            //    || string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunAgentHttpFunctionEntryPoint, StringComparison.Ordinal)
            // );
            //builder.Services.AddSingleton<BuiltInFunctionExecutor>();
        }

        return builder;
    }

    private static void ConfigureWorkflowOrchestrations(FunctionsApplicationBuilder builder, DurableWorkflowOptions workflows)
    {
        // Discover sub-workflows recursively and add them to the workflows dictionary
        // so they are registered as separate orchestrations alongside the main workflows.
        DiscoverSubWorkflows(workflows);

        builder.ConfigureDurableWorker().AddTasks(tasks =>
        {
            foreach (string workflowName in workflows.Workflows.Select(kp => kp.Key))
            {
                string orchestrationFunctionName = WorkflowNamingHelper.ToOrchestrationFunctionName(workflowName);

                tasks.AddOrchestratorFunc<DurableWorkflowInput<object>, string>(
                    orchestrationFunctionName,
                    async (orchestrationContext, orchInput) =>
                    {
                        FunctionContext functionContext = orchestrationContext.GetFunctionContext()
                            ?? throw new InvalidOperationException("FunctionContext is not available in the orchestration context.");

                        DurableWorkflowRunner runner = functionContext.InstanceServices.GetRequiredService<DurableWorkflowRunner>();
                        ILogger logger = orchestrationContext.CreateReplaySafeLogger(orchestrationFunctionName);
                        DurableWorkflowInput<object> workflowInput = orchInput;

                        return await runner.RunWorkflowOrchestrationAsync(orchestrationContext, workflowInput, logger).ConfigureAwait(true);
                    });
            }
        });
    }

    private static void DiscoverSubWorkflows(DurableWorkflowOptions workflows)
    {
        HashSet<string> visited = new(workflows.Workflows.Keys);
        Queue<Workflow> queue = new(workflows.Workflows.Values);

        while (queue.Count > 0)
        {
            Workflow workflow = queue.Dequeue();

            foreach (ExecutorBinding binding in workflow.ReflectExecutors().Values)
            {
                if (binding is SubworkflowBinding subworkflowBinding)
                {
                    Workflow subWorkflow = subworkflowBinding.WorkflowInstance;
                    if (subWorkflow.Name is not null && visited.Add(subWorkflow.Name))
                    {
                        workflows.AddWorkflow(subWorkflow);
                        queue.Enqueue(subWorkflow);
                    }
                }
            }
        }
    }
    internal static FunctionsApplicationBuilder RegisterWorkflowServices(this FunctionsApplicationBuilder builder)
    {
        // Register FunctionsWorkflowRunner as a singleton
        // builder.Services.TryAddSingleton<FunctionsWorkflowRunner>();

        // Also register it as DurableWorkflowRunner so orchestrations can resolve it by base type
        //builder.Services.TryAddSingleton<DurableWorkflowRunner>(sp => sp.GetRequiredService<FunctionsWorkflowRunner>());

        builder.Services.TryAddEnumerable(ServiceDescriptor.Singleton<IFunctionMetadataTransformer, DurableWorkflowFunctionMetadataTransformer>());

        return builder;
    }

    /// <summary>
    /// Configures durable workflow services for the application and allows customization of durable workflow options.
    /// </summary>
    /// <remarks>This method registers the services required for durable workflows using
    /// Microsoft.DurableTask.Workflows. Call this method during application startup to enable durable workflows in your
    /// Azure Functions app.</remarks>
    /// <param name="builder">The application builder used to configure services and middleware for the Azure Functions app.</param>
    /// <param name="configure">A delegate that is used to configure the durable workflow options. Cannot be null.</param>
    /// <returns>The same <see cref="FunctionsApplicationBuilder"/> instance that this method was called on, to support method
    /// chaining.</returns>
    public static FunctionsApplicationBuilder ConfigureDurableWorkflows(this FunctionsApplicationBuilder builder, Action<DurableWorkflowOptions> configure)
    {
        ArgumentNullException.ThrowIfNull(configure);

        //RegisterWorkflowServices(builder);
        //builder.Services.AddSingleton<IFunctionMetadataTransformer, DurableWorkflowFunctionMetadataTransformer>();

        // The main durable workflows services registration is done in Microsoft.DurableTask.Workflows.
        builder.Services.ConfigureDurableWorkflows(configure);

        return builder;
    }

    /// <summary>
    /// Configures the application to use durable agents with a builder pattern.
    /// </summary>
    /// <param name="builder">The functions application builder.</param>
    /// <param name="configure">A delegate to configure the durable agents.</param>
    /// <returns>The functions application builder.</returns>
    public static FunctionsApplicationBuilder ConfigureDurableAgents(
        this FunctionsApplicationBuilder builder,
        Action<DurableAgentsOptions> configure)
    {
        ArgumentNullException.ThrowIfNull(configure);

        // The main agent services registration is done in Microsoft.DurableTask.Agents.
        builder.Services.ConfigureDurableAgents(configure);

        builder.Services.TryAddSingleton<IFunctionsAgentOptionsProvider>(_ =>
            new DefaultFunctionsAgentOptionsProvider(DurableAgentsOptionsExtensions.GetAgentOptionsSnapshot()));

        builder.Services.AddSingleton<IFunctionMetadataTransformer, DurableAgentFunctionMetadataTransformer>();

        // Handling of built-in function execution for Agent HTTP, MCP tool, or Entity invocations.
        builder.UseWhen<BuiltInFunctionExecutionMiddleware>(static context =>
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunAgentHttpFunctionEntryPoint, StringComparison.Ordinal) ||
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunAgentMcpToolFunctionEntryPoint, StringComparison.Ordinal) ||
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunAgentEntityFunctionEntryPoint, StringComparison.Ordinal)
            || string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunWorkflowOrechstrtationHttpFunctionEntryPoint, StringComparison.Ordinal)

             || string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunWorkflowOrechstrtationHttpFunctionEntryPoint, StringComparison.Ordinal)
                || string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.InvokeWorkflowOrchestrationFunctionEntryPoint, StringComparison.Ordinal)
                || string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.InvokeWorkflowActivityFunctionEntryPoint, StringComparison.Ordinal)
            );
        builder.Services.AddSingleton<BuiltInFunctionExecutor>();

        return builder;
    }
}
