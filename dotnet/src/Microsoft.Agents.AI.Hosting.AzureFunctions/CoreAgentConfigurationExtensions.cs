// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Azure.Functions.Worker.Core.FunctionMetadata;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Shared configuration logic for durable agents and workflows.
/// This class consolidates common service registrations used by both
/// <see cref="FunctionsApplicationBuilderExtensions.ConfigureDurableAgents"/> and
/// <see cref="DurableOptionsExtensions.ConfigureDurableOptions"/>.
/// </summary>
internal static class CoreAgentConfigurationExtensions
{
    /// <summary>
    /// Registers the core agent services required for durable agents.
    /// </summary>
    /// <param name="builder">The functions application builder.</param>
    /// <returns>The functions application builder for method chaining.</returns>
    internal static FunctionsApplicationBuilder RegisterCoreAgentServices(this FunctionsApplicationBuilder builder)
    {
        builder.Services.TryAddSingleton<IFunctionsAgentOptionsProvider>(_ =>
            new DefaultFunctionsAgentOptionsProvider(DurableAgentsOptionsExtensions.GetAgentOptionsSnapshot()));

        builder.Services.TryAddEnumerable(ServiceDescriptor.Singleton<IFunctionMetadataTransformer, DurableAgentFunctionMetadataTransformer>());

        return builder;
    }

    /// <summary>
    /// Registers the workflow-specific services required for durable workflows.
    /// This should only be called when workflows are configured in the application.
    /// </summary>
    /// <param name="builder">The functions application builder.</param>
    /// <returns>The functions application builder for method chaining.</returns>
    internal static FunctionsApplicationBuilder RegisterWorkflowServices(this FunctionsApplicationBuilder builder)
    {
        builder.Services.TryAddSingleton<DurableWorkflowRunner>();
        builder.Services.TryAddEnumerable(ServiceDescriptor.Singleton<IFunctionMetadataTransformer, DurableWorkflowFunctionMetadataTransformer>());

        return builder;
    }

    /// <summary>
    /// Configures the middleware and executor for handling built-in function execution.
    /// This is shared by both agents and workflows, handling Agent HTTP, MCP tool,
    /// workflow orchestration, and Entity invocations.
    /// </summary>
    /// <param name="builder">The functions application builder.</param>
    /// <returns>The functions application builder for method chaining.</returns>
    internal static FunctionsApplicationBuilder ConfigureBuiltInFunctionMiddleware(this FunctionsApplicationBuilder builder)
    {
        builder.Services.TryAddSingleton<BuiltInFunctionExecutor>();

        builder.UseWhen<BuiltInFunctionExecutionMiddleware>(static context =>
            IsBuiltInFunction(context.FunctionDefinition.EntryPoint));

        return builder;
    }

    private static bool IsBuiltInFunction(string? entryPoint)
    {
        return string.Equals(entryPoint, BuiltInFunctions.RunAgentHttpFunctionEntryPoint, StringComparison.Ordinal)
            || string.Equals(entryPoint, BuiltInFunctions.RunAgentMcpToolFunctionEntryPoint, StringComparison.Ordinal)
            || string.Equals(entryPoint, BuiltInFunctions.RunWorkflowOrechstrtationHttpFunctionEntryPoint, StringComparison.Ordinal)
            || string.Equals(entryPoint, BuiltInFunctions.InvokeWorkflowActivityFunctionEntryPoint, StringComparison.Ordinal)
            || string.Equals(entryPoint, BuiltInFunctions.RunAgentEntityFunctionEntryPoint, StringComparison.Ordinal);
    }
}
