// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Text;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Rejects an unsupported hosted Responses protocol before the request enters AgentServer's
/// resilient task boundary.
/// </summary>
internal sealed class HostedProtocolCompatibilityFilter : IEndpointFilter
{
    private const string CallIdHeaderName = "x-agent-foundry-call-id";
    private const string ErrorSourceHeaderName = "x-platform-error-source";
    private const string UpstreamErrorSource = "upstream";

    private readonly bool _isHosted;
    private readonly ILogger<HostedProtocolCompatibilityFilter> _logger;

    internal HostedProtocolCompatibilityFilter(
        IConfiguration configuration,
        ILogger<HostedProtocolCompatibilityFilter> logger)
    {
        _ = Throw.IfNull(configuration);
        this._logger = Throw.IfNull(logger);
        this._isHosted = !string.IsNullOrEmpty(
            configuration[FoundryHostingExtensions.FoundryHostingEnvironmentKey]);
    }

    /// <inheritdoc/>
    public ValueTask<object?> InvokeAsync(
        EndpointFilterInvocationContext context,
        EndpointFilterDelegate next)
    {
        _ = Throw.IfNull(context);
        _ = Throw.IfNull(next);

        HttpRequest request = context.HttpContext.Request;
        if (!IsCreateResponseRequest(request))
        {
            return next(context);
        }

        string? callId = request.Headers.TryGetValue(CallIdHeaderName, out var values)
            ? values.ToString()
            : null;
        var unsupportedProtocolError =
            HostedProtocolCompatibility.GetUnsupportedProtocolError(this._isHosted, callId);
        if (unsupportedProtocolError is null)
        {
            return next(context);
        }

        this._logger.LogError(
            "Hosted container served unsupported Responses protocol 1.0.0 (no x-agent-foundry-call-id header); this image requires protocol 2.0.0.");

        BinaryData responseData =
            ((IPersistableModel<ApiErrorResponse>)new ApiErrorResponse(unsupportedProtocolError.Error))
                .Write(ModelReaderWriterOptions.Json);
        context.HttpContext.Response.Headers[ErrorSourceHeaderName] = UpstreamErrorSource;
        return ValueTask.FromResult<object?>(
            Results.Text(
                responseData.ToString(),
                contentType: "application/json",
                contentEncoding: Encoding.UTF8,
                statusCode: unsupportedProtocolError.StatusCode));
    }

    private static bool IsCreateResponseRequest(HttpRequest request)
        => HttpMethods.IsPost(request.Method) &&
            request.Path.Value?.EndsWith("/responses", StringComparison.OrdinalIgnoreCase) is true;
}
