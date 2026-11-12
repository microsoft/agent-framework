// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DevUI;

/// <summary>
/// Applies DevUI access validation to the standard OpenAI Responses and Conversations routes.
/// </summary>
internal sealed class DevUIAccessControlMiddleware
{
    private static readonly PathString s_responsesPath = new("/v1/responses");
    private static readonly PathString s_conversationsPath = new("/v1/conversations");

    private readonly RequestDelegate _next;

    /// <summary>
    /// Initializes a new instance of the <see cref="DevUIAccessControlMiddleware"/> class.
    /// </summary>
    /// <param name="next">The next middleware in the request pipeline.</param>
    public DevUIAccessControlMiddleware(RequestDelegate next)
    {
        ArgumentNullException.ThrowIfNull(next);
        this._next = next;
    }

    /// <summary>
    /// Validates protected DevUI backend routes and continues allowed requests.
    /// </summary>
    /// <param name="context">The current HTTP context.</param>
    /// <param name="validator">The shared DevUI request validator.</param>
    /// <returns>A task that represents processing the request.</returns>
    public async Task InvokeAsync(HttpContext context, DevUIRequestValidator validator)
    {
        var requestPath = context.Request.PathBase.Add(context.Request.Path);
        if (IsProtectedPath(requestPath))
        {
            var failure = validator.ValidateLocalRequest(context);
            if (failure is not null)
            {
                await failure.ExecuteAsync(context).ConfigureAwait(false);
                return;
            }
        }

        await this._next(context).ConfigureAwait(false);
    }

    private static bool IsProtectedPath(PathString path)
        => ContainsPathSegment(path, s_responsesPath) || ContainsPathSegment(path, s_conversationsPath);

    private static bool ContainsPathSegment(PathString path, PathString routePath)
    {
        var pathValue = path.Value;
        var routeValue = routePath.Value;
        if (pathValue is null || routeValue is null)
        {
            return false;
        }

        var matchIndex = pathValue.IndexOf(routeValue, StringComparison.OrdinalIgnoreCase);
        while (matchIndex >= 0)
        {
            var matchEnd = matchIndex + routeValue.Length;
            if (matchEnd == pathValue.Length || pathValue[matchEnd] == '/')
            {
                return true;
            }

            matchIndex = pathValue.IndexOf(routeValue, matchEnd, StringComparison.OrdinalIgnoreCase);
        }

        return false;
    }
}
