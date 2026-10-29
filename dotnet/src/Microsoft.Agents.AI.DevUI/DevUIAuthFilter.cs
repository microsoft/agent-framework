// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DevUI;

/// <summary>
/// Endpoint filter that applies the shared DevUI request validation policy.
/// </summary>
internal sealed class DevUIAuthFilter : IEndpointFilter
{
    private readonly DevUIRequestValidator _validator;

    /// <summary>
    /// Gets a value indicating whether a bearer token is required by this filter
    /// (either via <see cref="DevUIOptions.AuthToken"/> or the
    /// <c>DEVUI_AUTH_TOKEN</c> environment variable).
    /// </summary>
    public bool TokenRequired => this._validator.TokenRequired;

    public DevUIAuthFilter(DevUIRequestValidator validator)
    {
        ArgumentNullException.ThrowIfNull(validator);
        this._validator = validator;
    }

    public async ValueTask<object?> InvokeAsync(EndpointFilterInvocationContext context, EndpointFilterDelegate next)
    {
        var failure = this._validator.ValidateLocalRequest(context.HttpContext)
            ?? this._validator.ValidateToken(context.HttpContext);
        return failure ?? await next(context).ConfigureAwait(false);
    }
}
