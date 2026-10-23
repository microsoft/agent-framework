// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DevUI;

/// <summary>
/// Adds <see cref="DevUIAccessControlMiddleware"/> to the application request pipeline.
/// </summary>
internal sealed class DevUIAccessControlStartupFilter : IStartupFilter
{
    /// <inheritdoc />
    public Action<IApplicationBuilder> Configure(Action<IApplicationBuilder> next)
    {
        ArgumentNullException.ThrowIfNull(next);

        return app =>
        {
            app.UseMiddleware<DevUIAccessControlMiddleware>();
            next(app);
        };
    }
}
