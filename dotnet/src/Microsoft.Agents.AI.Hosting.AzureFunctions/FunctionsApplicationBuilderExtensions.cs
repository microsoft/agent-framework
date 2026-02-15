// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Azure.Functions.Worker.Core.FunctionMetadata;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Extension methods for the <see cref="FunctionsApplicationBuilder"/> class.
/// </summary>
public static class FunctionsApplicationBuilderExtensions
{
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
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunAgentEntityFunctionEntryPoint, StringComparison.Ordinal));
        builder.Services.AddSingleton<BuiltInFunctionExecutor>();

        return builder;
    }

    /// <summary>
    /// Configures durable options for the functions application, allowing customization of Durable Task framework
    /// settings.
    /// </summary>
    /// <remarks>This method ensures that a single shared <see cref="DurableOptions"/> instance is used across all
    /// configuration calls. If any workflows have been added, it configures the necessary orchestrations and registers
    /// required middleware.</remarks>
    /// <param name="builder">The functions application builder to configure. Cannot be null.</param>
    /// <param name="configure">An action that configures the <see cref="DurableOptions"/> instance. Cannot be null.</param>
    /// <returns>The updated <see cref="FunctionsApplicationBuilder"/> instance, enabling method chaining.</returns>
    public static FunctionsApplicationBuilder ConfigureDurableOptions(
        this FunctionsApplicationBuilder builder,
        Action<DurableOptions> configure)
    {
        ArgumentNullException.ThrowIfNull(builder);
        ArgumentNullException.ThrowIfNull(configure);

        builder.Services.ConfigureDurableOptions(configure);

        // Read the shared options to check if workflows were added
        DurableOptions sharedOptions = GetOrCreateSharedOptions(builder.Services);

        if (sharedOptions.Workflows.Workflows.Count > 0)
        {
            builder.Services.TryAddEnumerable(ServiceDescriptor.Singleton<IFunctionMetadataTransformer, DurableWorkflowsFunctionMetadataTransformer>());
        }

        EnsureMiddlewareRegistered(builder);

        return builder;
    }

    /// <summary>
    /// Configures durable workflow support for the specified Azure Functions application builder.
    /// </summary>
    /// <param name="builder">The <see cref="FunctionsApplicationBuilder"/> instance to configure for durable workflows.</param>
    /// <param name="configure">An action that configures the <see cref="DurableWorkflowOptions"/>, allowing customization of durable workflow behavior.</param>
    /// <returns>The updated <see cref="FunctionsApplicationBuilder"/> instance, enabling method chaining.</returns>
    public static FunctionsApplicationBuilder ConfigureDurableWorkflows(
         this FunctionsApplicationBuilder builder,
         Action<DurableWorkflowOptions> configure)
    {
        ArgumentNullException.ThrowIfNull(configure);

        return builder.ConfigureDurableOptions(options => configure(options.Workflows));
    }

    private static void EnsureMiddlewareRegistered(FunctionsApplicationBuilder builder)
    {
        // Guard against registering the middleware filter multiple times in the pipeline.
        if (builder.Services.Any(d => d.ServiceType == typeof(BuiltInFunctionExecutor)))
        {
            return;
        }

        builder.UseWhen<BuiltInFunctionExecutionMiddleware>(static context =>
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunAgentHttpFunctionEntryPoint, StringComparison.Ordinal) ||
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunAgentEntityFunctionEntryPoint, StringComparison.Ordinal) ||
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunWorkflowOrchestrationHttpFunctionEntryPoint, StringComparison.Ordinal) ||
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.RunWorkflowOrchestrationFunctionEntryPoint, StringComparison.Ordinal) ||
            string.Equals(context.FunctionDefinition.EntryPoint, BuiltInFunctions.InvokeWorkflowActivityFunctionEntryPoint, StringComparison.Ordinal)
        );
        builder.Services.TryAddSingleton<BuiltInFunctionExecutor>();
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
}
