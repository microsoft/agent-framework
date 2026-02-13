// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Hosting.AzureFunctions.Workflows;
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
    /// Tracks workflow orchestration names that have already been registered to prevent duplicates.
    /// </summary>
    private static readonly HashSet<string> s_registeredOrchestrations = new(StringComparer.OrdinalIgnoreCase);

    /// <summary>
    /// Tracks whether middleware and shared services have been registered.
    /// </summary>
    private static bool s_middlewareRegistered;

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
    /// Multiple calls to this method are supported and configurations are composed additively.
    /// </remarks>
    public static FunctionsApplicationBuilder ConfigureDurableOptions(
        this FunctionsApplicationBuilder builder,
        Action<DurableOptions> configure)
    {
        ArgumentNullException.ThrowIfNull(builder);
        ArgumentNullException.ThrowIfNull(configure);

        // Delegate to the shared DurableOptions registration in Microsoft.Agents.AI.DurableTask.
        // This ensures a single shared DurableOptions instance across all Configure* calls.
        builder.Services.ConfigureDurableOptions(options => configure(options));

        // Read the shared options to check if workflows were added
        DurableOptions sharedOptions = GetOrCreateSharedOptions(builder.Services);

        if (sharedOptions.Workflows.Workflows.Count > 0)
        {
            ConfigureWorkflowOrchestrations(builder, sharedOptions.Workflows);

            builder.Services.TryAddEnumerable(
                ServiceDescriptor.Singleton<IFunctionMetadataTransformer, DurableWorkflowFunctionMetadataTransformer>());
        }

        EnsureMiddlewareRegistered(builder);

        return builder;
    }

    /// <summary>
    /// Gets or creates a shared <see cref="DurableOptions"/> instance from the service collection.
    /// </summary>
    private static DurableOptions GetOrCreateSharedOptions(IServiceCollection services)
    {
        ServiceDescriptor? existingDescriptor = services.FirstOrDefault(
            d => d.ServiceType == typeof(DurableOptions) && d.ImplementationInstance is not null);

        if (existingDescriptor?.ImplementationInstance is DurableOptions existing)
        {
            return existing;
        }

        DurableOptions options = new();
        services.AddSingleton(options);
        return options;
    }

    private static void ConfigureWorkflowOrchestrations(FunctionsApplicationBuilder builder, DurableWorkflowOptions workflowOptions)
    {
        // Collect only workflows that haven't been registered yet
        List<string> newWorkflowNames = workflowOptions.Workflows
            .Select(kp => kp.Key)
            .Where(name => s_registeredOrchestrations.Add(name))
            .ToList();

        if (newWorkflowNames.Count == 0)
        {
            return;
        }

        builder.ConfigureDurableWorker().AddTasks(tasks =>
        {
            foreach (string workflowName in newWorkflowNames)
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

    /// <summary>
    /// Configures durable workflow services for the Azure Functions application.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This method registers the services required for durable workflows in an Azure Functions app,
    /// including orchestration triggers, HTTP triggers, and activity/entity triggers for executors.
    /// </para>
    /// <para>
    /// Multiple calls to this method are supported and configurations are composed additively.
    /// Agents referenced in workflows are automatically discovered and registered.
    /// </para>
    /// </remarks>
    /// <param name="builder">The application builder used to configure services and middleware for the Azure Functions app.</param>
    /// <param name="configure">A delegate that is used to configure the durable workflow options. Cannot be null.</param>
    /// <returns>The same <see cref="FunctionsApplicationBuilder"/> instance that this method was called on, to support method
    /// chaining.</returns>
    public static FunctionsApplicationBuilder ConfigureDurableWorkflows(this FunctionsApplicationBuilder builder, Action<DurableWorkflowOptions> configure)
    {
        ArgumentNullException.ThrowIfNull(configure);

        return builder.ConfigureDurableOptions(options => configure(options.Workflows));
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

        EnsureMiddlewareRegistered(builder);

        return builder;
    }

    /// <summary>
    /// Registers the built-in function execution middleware and executor exactly once.
    /// </summary>
    private static void EnsureMiddlewareRegistered(FunctionsApplicationBuilder builder)
    {
        if (s_middlewareRegistered)
        {
            return;
        }

        s_middlewareRegistered = true;

        builder.UseWhen<BuiltInFunctionExecutionMiddleware>(static context =>
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunAgentHttpFunctionEntryPoint, StringComparison.Ordinal) ||
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunAgentMcpToolFunctionEntryPoint, StringComparison.Ordinal) ||
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunAgentEntityFunctionEntryPoint, StringComparison.Ordinal) ||
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunWorkflowOrechstrtationHttpFunctionEntryPoint, StringComparison.Ordinal) ||
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.InvokeWorkflowOrchestrationFunctionEntryPoint, StringComparison.Ordinal) ||
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.InvokeWorkflowActivityFunctionEntryPoint, StringComparison.Ordinal)
        );
        builder.Services.TryAddSingleton<BuiltInFunctionExecutor>();
    }
}
