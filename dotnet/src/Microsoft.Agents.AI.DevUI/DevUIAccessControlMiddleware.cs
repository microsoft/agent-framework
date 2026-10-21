// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DevUI;

/// <summary>
/// Applies DevUI access validation to the standard OpenAI Responses and Conversations routes.
/// </summary>
internal sealed class DevUIAccessControlMiddleware
{
    private static readonly PathString ResponsesPath = new("/v1/responses");
    private static readonly PathString ConversationsPath = new("/v1/conversations");

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
        if (IsProtectedPath(context.Request.Path))
        {
            var failure = validator.Validate(context);
            if (failure is not null)
            {
                await failure.ExecuteAsync(context).ConfigureAwait(false);
                return;
            }
        }

        await this._next(context).ConfigureAwait(false);
    }

    private static bool IsProtectedPath(PathString path)
        => path.StartsWithSegments(ResponsesPath) || path.StartsWithSegments(ConversationsPath);
}
