// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Frozen;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using Microsoft.AspNetCore.StaticFiles;
using Microsoft.Extensions.Primitives;
using Microsoft.Net.Http.Headers;

namespace Microsoft.Agents.AI.DevUI;

/// <summary>
/// Handler that serves embedded DevUI resource files from the 'resources' directory.
/// </summary>
internal sealed class DevUIMiddleware
{
    private const string GZipEncodingValue = "gzip";
    private static readonly StringValues s_gzipEncodingHeader = new(GZipEncodingValue);
    private static readonly Assembly s_assembly = typeof(DevUIMiddleware).Assembly;
    private static readonly FileExtensionContentTypeProvider s_contentTypeProvider = new();
    private static readonly StringValues s_cacheControl = new(new CacheControlHeaderValue()
    {
        NoCache = true,
        NoStore = true,
    }.ToString());

    private readonly ILogger<DevUIMiddleware> _logger;
    private readonly FrozenDictionary<string, ResourceEntry> _resourceCache;
    private readonly string _basePath;

    /// <summary>
    /// Initializes a new instance of the <see cref="DevUIMiddleware"/> class.
    /// </summary>
    /// <param name="logger">The logger instance.</param>
    /// <param name="basePath">The base path where DevUI is mounted.</param>
    public DevUIMiddleware(ILogger<DevUIMiddleware> logger, string basePath)
    {
        ArgumentNullException.ThrowIfNull(logger);
        ArgumentException.ThrowIfNullOrEmpty(basePath);
        this._logger = logger;
        this._basePath = basePath.TrimEnd('/');

        // Build resource cache
        var resourceNamePrefix = $"{s_assembly.GetName().Name}.resources.";
        this._resourceCache = s_assembly
            .GetManifestResourceNames()
            .Where(p => p.StartsWith(resourceNamePrefix, StringComparison.Ordinal))
            .ToFrozenDictionary(
                p => p[resourceNamePrefix.Length..].Replace('.', '/'),
                CreateResourceEntry,
                StringComparer.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Handles an HTTP request for DevUI resources.
    /// </summary>
    /// <param name="context">The HTTP context.</param>
    public async Task HandleRequestAsync(HttpContext context)
    {
        var path = context.Request.Path.Value;

        if (path == null)
        {
            context.Response.StatusCode = StatusCodes.Status404NotFound;
            return;
        }

        // If requesting the base path without a trailing slash, redirect to include it
        // This ensures relative URLs in the HTML work correctly
        if (string.Equals(path, this._basePath, StringComparison.OrdinalIgnoreCase) && !path.EndsWith('/'))
        {
            var redirectUrl = $"{path}/";
            if (context.Request.QueryString.HasValue)
            {
                redirectUrl += context.Request.QueryString.Value;
            }

            context.Response.StatusCode = StatusCodes.Status301MovedPermanently;
            context.Response.Headers.Location = redirectUrl;
            this._logger.LogDebug("Redirecting {OriginalPath} to {RedirectUrl}", path, redirectUrl);
            return;
        }

        // Remove the base path to get the resource path
        var resourcePath = path.StartsWith(this._basePath, StringComparison.OrdinalIgnoreCase)
            ? path.Substring(this._basePath.Length).TrimStart('/')
            : path.TrimStart('/');

        // If requesting the base path, serve index.html
        if (string.IsNullOrEmpty(resourcePath))
        {
            resourcePath = "index.html";
        }

        // Try to serve the embedded resource
        if (await this.TryServeResourceAsync(context, resourcePath).ConfigureAwait(false))
        {
            return;
        }

        // If resource not found, try serving index.html for client-side routing
        if (!resourcePath.Contains('.', StringComparison.Ordinal) || resourcePath.EndsWith('/'))
        {
            if (await this.TryServeResourceAsync(context, "index.html").ConfigureAwait(false))
            {
                return;
            }
        }

        // Resource not found
        context.Response.StatusCode = StatusCodes.Status404NotFound;
    }

    private async Task<bool> TryServeResourceAsync(HttpContext context, string resourcePath)
    {
        try
        {
            if (!this._resourceCache.TryGetValue(resourcePath.Replace('.', '/'), out var cacheEntry))
            {
                this._logger.LogDebug("Embedded resource not found: {ResourcePath}", resourcePath);
                return false;
            }

            var response = context.Response;

            // Check if client has cached version
            if (context.Request.Headers.IfNoneMatch == cacheEntry.ETag)
            {
                response.StatusCode = StatusCodes.Status304NotModified;
                this._logger.LogDebug("Resource not modified (304): {ResourcePath}", resourcePath);
                return true;
            }

            var responseHeaders = response.Headers;

            byte[] content;
            bool serveCompressed;
            if (cacheEntry.CompressedContent is not null && IsGZipAccepted(context.Request))
            {
                serveCompressed = true;
                responseHeaders.ContentEncoding = s_gzipEncodingHeader;
                responseHeaders.ContentLength = cacheEntry.CompressedContent.Length;
                content = cacheEntry.CompressedContent;
            }
            else
            {
                serveCompressed = false;
                responseHeaders.ContentLength = cacheEntry.DecompressedContent!.Length;
                content = cacheEntry.DecompressedContent;
            }

            responseHeaders.CacheControl = s_cacheControl;
            responseHeaders.ContentType = cacheEntry.ContentType;
            responseHeaders.ETag = cacheEntry.ETag;

            await response.Body.WriteAsync(content, context.RequestAborted).ConfigureAwait(false);

            this._logger.LogDebug("Served embedded resource: {ResourcePath} (compressed: {Compressed})", resourcePath, serveCompressed);
            return true;
        }
        catch (Exception ex)
        {
            this._logger.LogError(ex, "Error serving embedded resource: {ResourcePath}", resourcePath);
            return false;
        }
    }

    private static bool IsGZipAccepted(HttpRequest httpRequest)
    {
        if (httpRequest.GetTypedHeaders().AcceptEncoding is not { Count: > 0 } acceptEncoding)
        {
            return false;
        }

        for (int i = 0; i < acceptEncoding.Count; i++)
        {
            var encoding = acceptEncoding[i];

            if (encoding.Quality is not 0 &&
                string.Equals(encoding.Value.Value, GZipEncodingValue, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }

        return false;
    }

    private static ResourceEntry CreateResourceEntry(string resourceName)
    {
        using var resourceStream = s_assembly.GetManifestResourceStream(resourceName)!;
        using var decompressedContent = new MemoryStream();

        // Read and cache the original resource content
        resourceStream.CopyTo(decompressedContent);
        var decompressedArray = decompressedContent.ToArray();

        // Compress the content
        using var compressedContent = new MemoryStream();
        using (var gzip = new GZipStream(compressedContent, CompressionMode.Compress, leaveOpen: true))
        {
            // This is a synchronous write to a memory stream.
            // There is no benefit to asynchrony here.
            gzip.Write(decompressedArray);
        }

        // Only use compression if it actually reduces size
        byte[]? compressedArray = compressedContent.Length < decompressedArray.Length
            ? compressedContent.ToArray()
            : null;

        var hash = SHA256.HashData(compressedArray ?? decompressedArray);
        var eTag = $"\"{Convert.ToBase64String(hash)}\"";

        // Determine content type from resource name
        var contentType = s_contentTypeProvider.TryGetContentType(resourceName, out var ct)
            ? ct
            : "application/octet-stream";

        return new ResourceEntry(resourceName, decompressedArray, compressedArray, eTag, contentType);
    }

    private sealed class ResourceEntry(string resourceName, byte[] decompressedContent, byte[]? compressedContent, string eTag, string contentType)
    {
        public byte[]? CompressedContent { get; } = compressedContent;

        public string ContentType { get; } = contentType;

        public byte[] DecompressedContent { get; } = decompressedContent;

        public string ETag { get; } = eTag;

        public string ResourceName { get; } = resourceName;
    }
}
