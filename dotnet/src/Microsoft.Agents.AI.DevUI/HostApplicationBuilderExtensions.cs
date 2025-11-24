// Copyright (c) Microsoft. All rights reserved.

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
    {
        ArgumentNullException.ThrowIfNull(builder);

        builder.Services.AddDevUI();

        return builder;
    }
}
