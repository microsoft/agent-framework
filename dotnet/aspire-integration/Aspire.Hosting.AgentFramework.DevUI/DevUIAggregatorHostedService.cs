// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Aspire.Hosting.ApplicationModel;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.StaticFiles;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Aspire.Hosting.AgentFramework;

/// <summary>
/// Hosts an in-process reverse proxy that aggregates DevUI entities from multiple agent backends.
/// Serves the DevUI frontend directly from the <c>Microsoft.Agents.AI.DevUI</c> assembly's embedded
/// resources and intercepts API calls to provide multi-backend entity aggregation and request routing.
/// </summary>
internal sealed class DevUIAggregatorHostedService : IAsyncDisposable
{
    private static readonly FileExtensionContentTypeProvider s_contentTypeProvider = new();

    private WebApplication? _app;
    private readonly DevUIResource _resource;
    private readonly ILogger _logger;

    // Frontend resources loaded from the Microsoft.Agents.AI.DevUI assembly (null if unavailable)
    private readonly Dictionary<string, (string ResourceName, string ContentType)>? _frontendResources;

    // Lazily resolved and cached backend map: prefix → base URL
    private Dictionary<string, string>? _cachedBackends;

    public DevUIAggregatorHostedService(
        DevUIResource resource,
        ILogger logger)
    {
        this._resource = resource;
        this._logger = logger;
        this._frontendResources = LoadFrontendResources(logger);
    }

    /// <summary>
    /// Gets the port the aggregator is listening on, available after <see cref="StartAsync"/>.
    /// </summary>
    internal int AllocatedPort { get; private set; }

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        var builder = WebApplication.CreateSlimBuilder();
        builder.Logging.ClearProviders();

        builder.Services.AddHttpClient("devui-proxy")
            .ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler
            {
                AllowAutoRedirect = false
            });

        this._app = builder.Build();
        this._app.Urls.Add("http://127.0.0.1:0");

        this.MapRoutes(this._app);

        await this._app.StartAsync(cancellationToken).ConfigureAwait(false);

        var serverAddresses = this._app.Services.GetRequiredService<IServer>()
            .Features.Get<IServerAddressesFeature>();

        if (serverAddresses is not null)
        {
            var address = serverAddresses.Addresses.First();
            var uri = new Uri(address);
            this.AllocatedPort = uri.Port;
            this._logger.LogInformation("DevUI aggregator started on port {Port}", this.AllocatedPort);
        }
    }

    public async Task StopAsync(CancellationToken cancellationToken)
    {
        if (this._app is not null)
        {
            await this._app.StopAsync(cancellationToken).ConfigureAwait(false);
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (this._app is not null)
        {
            await this._app.DisposeAsync().ConfigureAwait(false);
            this._app = null;
        }
    }

    /// <summary>
    /// Loads the DevUI frontend resources from the <c>Microsoft.Agents.AI.DevUI</c> assembly.
    /// The assembly embeds the Vite SPA build output as manifest resources.
    /// Returns null if the assembly is not available.
    /// </summary>
    private static Dictionary<string, (string ResourceName, string ContentType)>? LoadFrontendResources(ILogger logger)
    {
        Assembly assembly;
        try
        {
            assembly = Assembly.Load("Microsoft.Agents.AI.DevUI");
        }
        catch (Exception ex)
        {
            logger.LogDebug(ex, "Microsoft.Agents.AI.DevUI assembly not found. Frontend will be proxied from backends.");
            return null;
        }

        var prefix = $"{assembly.GetName().Name}.resources.";
        var resources = new Dictionary<string, (string, string)>(StringComparer.OrdinalIgnoreCase);

        foreach (var name in assembly.GetManifestResourceNames())
        {
            if (!name.StartsWith(prefix, StringComparison.Ordinal))
            {
                continue;
            }

            // The DevUI middleware maps resource names by replacing dots with slashes.
            // Both the key and lookup use the same transform, so they match.
            var key = name[prefix.Length..].Replace('.', '/');
            s_contentTypeProvider.TryGetContentType(name, out var contentType);
            resources[key] = (name, contentType ?? "application/octet-stream");
        }

        if (resources.Count == 0)
        {
            logger.LogWarning("Microsoft.Agents.AI.DevUI assembly loaded but contains no frontend resources");
            return null;
        }

        logger.LogDebug("Loaded {Count} DevUI frontend resources from assembly", resources.Count);
        return resources;
    }

    /// <summary>
    /// Serves the DevUI frontend. Uses embedded assembly resources if available,
    /// otherwise falls back to proxying from the first backend agent service.
    /// </summary>
    private async Task ServeDevUIFrontendAsync(HttpContext context, string? path)
    {
        // Redirect /devui to /devui/ so relative URLs in the SPA resolve correctly
        if (string.IsNullOrEmpty(path) && context.Request.Path.Value is { } reqPath && !reqPath.EndsWith('/'))
        {
            var redirect = reqPath + "/";
            if (context.Request.QueryString.HasValue)
            {
                redirect += context.Request.QueryString.Value;
            }

            context.Response.StatusCode = StatusCodes.Status301MovedPermanently;
            context.Response.Headers.Location = redirect;
            return;
        }

        // Try embedded resources first
        if (this._frontendResources is not null)
        {
            var resourcePath = string.IsNullOrEmpty(path) ? "index.html" : path;

            if (await this.TryServeResourceAsync(context, resourcePath).ConfigureAwait(false))
            {
                return;
            }

            // SPA fallback: serve index.html for paths without a file extension (client-side routing)
            if (!resourcePath.Contains('.', StringComparison.Ordinal))
            {
                if (await this.TryServeResourceAsync(context, "index.html").ConfigureAwait(false))
                {
                    return;
                }
            }

            context.Response.StatusCode = StatusCodes.Status404NotFound;
            return;
        }

        // Fallback: proxy from the first backend that serves /devui
        var backends = this.ResolveBackends();
        var firstBackendUrl = backends.Values.FirstOrDefault();

        if (firstBackendUrl is null)
        {
            context.Response.StatusCode = StatusCodes.Status503ServiceUnavailable;
            context.Response.ContentType = "text/plain";
            await context.Response.WriteAsync(
                "DevUI: No agent service backends are available yet.", context.RequestAborted).ConfigureAwait(false);
            return;
        }

        var targetPath = string.IsNullOrEmpty(path) ? "/devui/" : $"/devui/{path}";
        await ProxyRequestAsync(
            context, firstBackendUrl, targetPath + context.Request.QueryString, bodyBytes: null).ConfigureAwait(false);
    }

    private async Task<bool> TryServeResourceAsync(HttpContext context, string resourcePath)
    {
        if (this._frontendResources is null)
        {
            return false;
        }

        var key = resourcePath.Replace('.', '/');

        if (!this._frontendResources.TryGetValue(key, out var entry))
        {
            return false;
        }

        Assembly assembly;
        try
        {
            assembly = Assembly.Load("Microsoft.Agents.AI.DevUI");
        }
        catch
        {
            return false;
        }

        using var stream = assembly.GetManifestResourceStream(entry.ResourceName);

        if (stream is null)
        {
            return false;
        }

        context.Response.ContentType = entry.ContentType;
        context.Response.Headers.CacheControl = "no-cache, no-store";
        await stream.CopyToAsync(context.Response.Body, context.RequestAborted).ConfigureAwait(false);
        return true;
    }

    private static IResult GetMeta()
    {
        return Results.Json(new
        {
            ui_mode = "developer",
            version = "0.1.0",
            framework = "agent_framework",
            runtime = "dotnet",
            capabilities = new Dictionary<string, bool>
            {
                ["tracing"] = false,
                ["openai_proxy"] = false,
                ["deployment"] = false
            },
            auth_required = false
        });
    }

    private void MapRoutes(WebApplication app)
    {
        app.MapGet("/health", () => Results.Ok(new { status = "healthy" }));

        // Intercept API calls for multi-backend aggregation and routing
        app.MapGet("/v1/entities", (Delegate)this.AggregateEntitiesAsync);
        app.MapGet("/v1/entities/{**entityPath}", this.RouteEntityInfoAsync);
        app.MapPost("/v1/responses", this.RouteResponsesAsync);
        app.Map("/v1/conversations/{**path}", this.ProxyConversationsAsync);
        app.MapGet("/meta", GetMeta);

        // Serve the DevUI frontend from embedded assembly resources
        app.Map("/devui/{**path}", this.ServeDevUIFrontendAsync);
    }

    /// <summary>
    /// Resolves backend URLs from the resource's <see cref="AgentServiceAnnotation"/> annotations.
    /// Results are cached after first successful resolution of at least one backend.
    /// </summary>
    private Dictionary<string, string> ResolveBackends()
    {
        if (this._cachedBackends is not null)
        {
            return this._cachedBackends;
        }

        var result = new Dictionary<string, string>(StringComparer.Ordinal);

        foreach (var annotation in this._resource.Annotations.OfType<AgentServiceAnnotation>())
        {
            if (annotation.AgentService is not IResourceWithEndpoints rwe)
            {
                continue;
            }

            var prefix = annotation.EntityIdPrefix ?? annotation.AgentService.Name;

            try
            {
                var endpoint = rwe.GetEndpoint("http");
                if (endpoint.IsAllocated)
                {
                    result[prefix] = endpoint.Url;
                }
            }
            catch (Exception ex)
            {
                this._logger.LogDebug(ex, "Backend '{Prefix}' endpoint not yet available", prefix);
            }
        }

        // Only cache if we resolved at least one backend
        if (result.Count > 0)
        {
            this._cachedBackends = result;
        }

        return result;
    }

    private async Task<IResult> AggregateEntitiesAsync(HttpContext context)
    {
        var backends = this.ResolveBackends();
        var allEntities = new JsonArray();

        foreach (var annotation in this._resource.Annotations.OfType<AgentServiceAnnotation>())
        {
            var prefix = annotation.EntityIdPrefix ?? annotation.AgentService.Name;

            if (annotation.Agents.Count > 0)
            {
                // Build entities from AppHost-declared metadata — no backend call needed
                foreach (var agent in annotation.Agents)
                {
                    allEntities.Add(new JsonObject
                    {
                        ["id"] = $"{prefix}/{agent.Id}",
                        ["type"] = agent.Type,
                        ["name"] = agent.Name,
                        ["description"] = agent.Description,
                        ["framework"] = agent.Framework,
                        ["_original_id"] = agent.Id,
                        ["_backend"] = prefix
                    });
                }

                continue;
            }

            // Fallback: query backend /v1/entities for discovery
            if (!backends.TryGetValue(prefix, out var baseUrl))
            {
                continue;
            }

            try
            {
                var httpClientFactory = context.RequestServices.GetRequiredService<IHttpClientFactory>();
                using var client = httpClientFactory.CreateClient("devui-proxy");
                var response = await client.GetAsync(
                    new Uri(new Uri(baseUrl), "/v1/entities"),
                    context.RequestAborted).ConfigureAwait(false);

                if (!response.IsSuccessStatusCode)
                {
                    this._logger.LogWarning(
                        "Failed to fetch entities from backend '{Prefix}' at {Url}: {Status}",
                        prefix, baseUrl, response.StatusCode);
                    continue;
                }

                var json = await response.Content.ReadAsStringAsync(context.RequestAborted).ConfigureAwait(false);
                var doc = JsonNode.Parse(json);
                var entities = doc?["entities"]?.AsArray();

                if (entities is null)
                {
                    continue;
                }

                foreach (var entity in entities)
                {
                    if (entity is null)
                    {
                        continue;
                    }

                    var cloned = entity.DeepClone();
                    var id = cloned["id"]?.GetValue<string>() ?? cloned["name"]?.GetValue<string>();

                    if (id is not null)
                    {
                        cloned["id"] = $"{prefix}/{id}";
                        cloned["_original_id"] = id;
                        cloned["_backend"] = prefix;
                    }

                    allEntities.Add(cloned);
                }
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                this._logger.LogWarning(ex, "Error fetching entities from backend '{Prefix}' at {Url}", prefix, baseUrl);
            }
        }

        return Results.Json(new { entities = allEntities });
    }

    private async Task RouteEntityInfoAsync(HttpContext context, string entityPath)
    {
        var (backendUrl, actualPath) = this.ResolveBackend(entityPath);

        if (backendUrl is null)
        {
            context.Response.StatusCode = StatusCodes.Status404NotFound;
            return;
        }

        var httpClientFactory = context.RequestServices.GetRequiredService<IHttpClientFactory>();
        using var client = httpClientFactory.CreateClient("devui-proxy");
        var targetUrl = new Uri(new Uri(backendUrl), $"/v1/entities/{actualPath}");

        using var response = await client.GetAsync(targetUrl, context.RequestAborted).ConfigureAwait(false);
        await CopyResponseAsync(response, context).ConfigureAwait(false);
    }

    private async Task RouteResponsesAsync(HttpContext context)
    {
        var bodyBytes = await ReadRequestBodyAsync(context.Request).ConfigureAwait(false);
        var json = JsonNode.Parse(bodyBytes);
        var entityId = json?["metadata"]?["entity_id"]?.GetValue<string>();

        if (entityId is null)
        {
            var firstBackend = this.ResolveBackends().Values.FirstOrDefault();
            if (firstBackend is null)
            {
                context.Response.StatusCode = StatusCodes.Status502BadGateway;
                return;
            }

            await ProxyRequestAsync(context, firstBackend, "/v1/responses", bodyBytes).ConfigureAwait(false);
            return;
        }

        var (backendUrl, actualEntityId) = this.ResolveBackend(entityId);

        if (backendUrl is null)
        {
            context.Response.StatusCode = StatusCodes.Status404NotFound;
            await context.Response.WriteAsJsonAsync(
                new { error = $"No backend found for entity '{entityId}'" },
                context.RequestAborted).ConfigureAwait(false);
            return;
        }

        // Rewrite entity_id to the un-prefixed original value
        json!["metadata"]!["entity_id"] = actualEntityId;
        var rewrittenBody = JsonSerializer.SerializeToUtf8Bytes(json);

        await ProxyRequestAsync(context, backendUrl, "/v1/responses", rewrittenBody, streaming: true).ConfigureAwait(false);
    }

    private async Task ProxyConversationsAsync(HttpContext context, string? path)
    {
        // Try to determine the backend from agent_id query param or request body
        string? backendUrl = null;

        var agentId = context.Request.Query["agent_id"].FirstOrDefault();
        if (agentId is not null)
        {
            (backendUrl, _) = this.ResolveBackend(agentId);
        }

        if (backendUrl is null && context.Request.ContentLength > 0)
        {
            var bodyBytes = await ReadRequestBodyAsync(context.Request).ConfigureAwait(false);
            var json = JsonNode.Parse(bodyBytes);
            var entityId = json?["metadata"]?["entity_id"]?.GetValue<string>()
                ?? json?["metadata"]?["agent_id"]?.GetValue<string>();

            if (entityId is not null)
            {
                string actualId;
                (backendUrl, actualId) = this.ResolveBackend(entityId);

                if (backendUrl is not null)
                {
                    // Rewrite the entity/agent id to the un-prefixed value
                    if (json?["metadata"]?["entity_id"] is not null)
                    {
                        json!["metadata"]!["entity_id"] = actualId;
                    }

                    if (json?["metadata"]?["agent_id"] is not null)
                    {
                        json!["metadata"]!["agent_id"] = actualId;
                    }

                    var rewritten = JsonSerializer.SerializeToUtf8Bytes(json);
                    var targetPath = string.IsNullOrEmpty(path) ? "/v1/conversations" : $"/v1/conversations/{path}";
                    await ProxyRequestAsync(
                        context, backendUrl, targetPath + context.Request.QueryString, rewritten).ConfigureAwait(false);
                    return;
                }
            }

            // Couldn't determine backend from body; proxy raw bytes to first backend
            backendUrl = this.ResolveBackends().Values.FirstOrDefault();
            if (backendUrl is null)
            {
                context.Response.StatusCode = StatusCodes.Status502BadGateway;
                return;
            }

            var targetPathFallback = string.IsNullOrEmpty(path) ? "/v1/conversations" : $"/v1/conversations/{path}";
            await ProxyRequestAsync(
                context, backendUrl, targetPathFallback + context.Request.QueryString, bodyBytes).ConfigureAwait(false);
            return;
        }

        // No body and no query param — route to first backend
        backendUrl ??= this.ResolveBackends().Values.FirstOrDefault();
        if (backendUrl is null)
        {
            context.Response.StatusCode = StatusCodes.Status502BadGateway;
            return;
        }

        var convPath = string.IsNullOrEmpty(path) ? "/v1/conversations" : $"/v1/conversations/{path}";
        await ProxyRequestAsync(
            context, backendUrl, convPath + context.Request.QueryString, bodyBytes: null).ConfigureAwait(false);
    }

    private static async Task ProxyRequestAsync(
        HttpContext context,
        string backendUrl,
        string path,
        byte[]? bodyBytes,
        bool streaming = false)
    {
        var httpClientFactory = context.RequestServices.GetRequiredService<IHttpClientFactory>();
        using var client = httpClientFactory.CreateClient("devui-proxy");

        var targetUri = new Uri(new Uri(backendUrl), path);
        using var request = new HttpRequestMessage(new HttpMethod(context.Request.Method), targetUri);

        foreach (var header in context.Request.Headers)
        {
            if (IsHopByHopHeader(header.Key))
            {
                continue;
            }

            request.Headers.TryAddWithoutValidation(header.Key, header.Value.ToArray());
        }

        if (bodyBytes is not null)
        {
            request.Content = new ByteArrayContent(bodyBytes);
            if (context.Request.ContentType is not null)
            {
                request.Content.Headers.ContentType =
                    System.Net.Http.Headers.MediaTypeHeaderValue.Parse(context.Request.ContentType);
            }
        }

        var completionOption = streaming
            ? HttpCompletionOption.ResponseHeadersRead
            : HttpCompletionOption.ResponseContentRead;

        using var response = await client.SendAsync(
            request, completionOption, context.RequestAborted).ConfigureAwait(false);

        if (streaming && response.Content.Headers.ContentType?.MediaType == "text/event-stream")
        {
            context.Response.StatusCode = (int)response.StatusCode;
            context.Response.ContentType = "text/event-stream";
            context.Response.Headers.CacheControl = "no-cache";

            using var stream = await response.Content.ReadAsStreamAsync(context.RequestAborted).ConfigureAwait(false);
            await stream.CopyToAsync(context.Response.Body, context.RequestAborted).ConfigureAwait(false);
        }
        else
        {
            await CopyResponseAsync(response, context).ConfigureAwait(false);
        }
    }

    private (string? BackendUrl, string ActualPath) ResolveBackend(string prefixedId)
    {
        var backends = this.ResolveBackends();
        var slashIndex = prefixedId.IndexOf('/');

        if (slashIndex > 0)
        {
            var prefix = prefixedId[..slashIndex];
            var rest = prefixedId[(slashIndex + 1)..];

            if (backends.TryGetValue(prefix, out var url))
            {
                return (url, rest);
            }
        }

        // Fallback: check all prefixes
        foreach (var (prefix, url) in backends)
        {
            if (prefixedId.StartsWith(prefix + "/", StringComparison.Ordinal))
            {
                return (url, prefixedId[(prefix.Length + 1)..]);
            }
        }

        return (null, prefixedId);
    }

    private static async Task<byte[]> ReadRequestBodyAsync(HttpRequest request)
    {
        using var ms = new MemoryStream();
        await request.Body.CopyToAsync(ms).ConfigureAwait(false);
        return ms.ToArray();
    }

    private static async Task CopyResponseAsync(HttpResponseMessage response, HttpContext context)
    {
        context.Response.StatusCode = (int)response.StatusCode;

        foreach (var header in response.Headers)
        {
            if (!IsHopByHopHeader(header.Key))
            {
                context.Response.Headers[header.Key] = header.Value.ToArray();
            }
        }

        foreach (var header in response.Content.Headers)
        {
            context.Response.Headers[header.Key] = header.Value.ToArray();
        }

        await response.Content.CopyToAsync(context.Response.Body).ConfigureAwait(false);
    }

    private static bool IsHopByHopHeader(string headerName)
    {
        return headerName.Equals("Transfer-Encoding", StringComparison.OrdinalIgnoreCase)
            || headerName.Equals("Connection", StringComparison.OrdinalIgnoreCase)
            || headerName.Equals("Keep-Alive", StringComparison.OrdinalIgnoreCase)
            || headerName.Equals("Host", StringComparison.OrdinalIgnoreCase);
    }
}
