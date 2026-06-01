// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DevUI;

namespace Microsoft.Extensions.Hosting;

/// <summary>
/// Extension methods for <see cref="IHostApplicationBuilder"/> to configure DevUI.
/// </summary>
public static class MicrosoftAgentAIDevUIHostApplicationBuilderExtensions
{
    /// <summary>
    /// Adds DevUI services to the host application builder.
    /// </summary>
    /// <param name="builder">The <see cref="IHostApplicationBuilder"/> to configure.</param>
    /// <returns>The <see cref="IHostApplicationBuilder"/> for method chaining.</returns>
    public static IHostApplicationBuilder AddDevUI(this IHostApplicationBuilder builder)
        => AddDevUI(builder, configure: null);

    /// <summary>
    /// Adds DevUI services to the host application builder.
    /// </summary>
    /// <param name="builder">The <see cref="IHostApplicationBuilder"/> to configure.</param>
    /// <param name="configure">Optional callback used to configure <see cref="DevUIOptions"/>.</param>
    /// <returns>The <see cref="IHostApplicationBuilder"/> for method chaining.</returns>
    public static IHostApplicationBuilder AddDevUI(this IHostApplicationBuilder builder, Action<DevUIOptions>? configure)
    {
        ArgumentNullException.ThrowIfNull(builder);

        builder.Services.AddDevUI(configure);

        return builder;
    }
}
