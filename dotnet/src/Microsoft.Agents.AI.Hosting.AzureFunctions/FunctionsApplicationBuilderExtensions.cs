// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Azure.Functions.Worker.Builder;

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
        ArgumentNullException.ThrowIfNull(builder);
        ArgumentNullException.ThrowIfNull(configure);

        // The main agent services registration is done in Microsoft.DurableTask.Agents.
        builder.Services.ConfigureDurableAgents(configure);

        builder.RegisterCoreAgentServices();

        // Configure middleware for built-in function execution.
        builder.ConfigureBuiltInFunctionMiddleware();

        return builder;
    }
}
