// Copyright (c) Microsoft. All rights reserved.

// This file contains the client for interacting with Azure Video Translation service.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Azure.Identity;

namespace VideoTranslationAgent;

/// <summary>
/// Client for Azure Video Translation service.
/// </summary>
public class VideoTranslationClient : IDisposable
{
    private const string UrlSegmentNameTranslations = "translations";
    private const string UrlSegmentNameIterations = "iterations";
    private const string UrlPathRoot = "videotranslation";
    private const string VideoTranslationScope = "https://cognitiveservices.azure.com/.default";
    private const string OperationLocationHeader = "Operation-Location";

    private readonly HttpClient _httpClient;
    private readonly TokenCredential _credential;
    private readonly string _apiVersion;
    private readonly string _endpoint;
    private AccessToken? _cachedToken;

    public VideoTranslationClient(string? apiVersion = null, TokenCredential? credential = null)
    {
        _apiVersion = apiVersion ?? Environment.GetEnvironmentVariable("VIDEO_TRANSLATION_API_VERSION") ?? "2024-05-20-preview";
        _credential = credential ?? new DefaultAzureCredential();
        _endpoint = Environment.GetEnvironmentVariable("VIDEO_TRANSLATION_ENDPOINT") 
            ?? throw new InvalidOperationException("VIDEO_TRANSLATION_ENDPOINT environment variable is not set.");

        _httpClient = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(300)
        };
    }

    /// <summary>
    /// Gets an authentication token.
    /// </summary>
    private async Task<string> GetAuthTokenAsync(CancellationToken cancellationToken = default)
    {
        if (_cachedToken.HasValue && _cachedToken.Value.ExpiresOn > DateTimeOffset.UtcNow.AddMinutes(5))
        {
            return _cachedToken.Value.Token;
        }

        var tokenContext = new TokenRequestContext([VideoTranslationScope]);
        _cachedToken = await _credential.GetTokenAsync(tokenContext, cancellationToken);
        return _cachedToken.Value.Token;
    }

    /// <summary>
    /// Builds request headers.
    /// </summary>
    private async Task<HttpRequestMessage> CreateRequestAsync(HttpMethod method, string url, CancellationToken cancellationToken = default)
    {
        var token = await GetAuthTokenAsync(cancellationToken);
        var request = new HttpRequestMessage(method, url);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        return request;
    }

    /// <summary>
    /// Builds the translations path.
    /// </summary>
    private string BuildTranslationsPath() => $"{UrlPathRoot}/{UrlSegmentNameTranslations}";

    /// <summary>
    /// Builds the translation path.
    /// </summary>
    private string BuildTranslationPath(string translationId) => $"{BuildTranslationsPath()}/{translationId}";

    /// <summary>
    /// Builds the iterations path.
    /// </summary>
    private string BuildIterationsPath(string translationId) => $"{BuildTranslationPath(translationId)}/{UrlSegmentNameIterations}";

    /// <summary>
    /// Builds the iteration path.
    /// </summary>
    private string BuildIterationPath(string translationId, string iterationId) => $"{BuildIterationsPath(translationId)}/{iterationId}";

    /// <summary>
    /// Builds the full URL.
    /// </summary>
    private string BuildUrl(string path)
    {
        var baseUrl = _endpoint.TrimEnd('/');
        return $"{baseUrl}/{path}?api-version={_apiVersion}";
    }

    /// <summary>
    /// Generates a unique operation ID.
    /// </summary>
    private static string GenerateOperationId() => Guid.NewGuid().ToString();

    /// <summary>
    /// Creates a translation and waits for it to complete.
    /// </summary>
    public async Task<(bool success, string? error, TranslationDefinition? translation)> CreateTranslationUntilTerminatedAsync(
        string videoFileUrl,
        string sourceLocale,
        string targetLocale,
        VoiceKind voiceKind,
        CancellationToken cancellationToken = default)
    {
        var operationId = GenerateOperationId();
        var now = DateTime.UtcNow;
        var translationId = $"{now:MMddyyyyHHmmss}_{sourceLocale}_{targetLocale}_{voiceKind}";

        var (success, error, translation, operationLocation) = await RequestCreateTranslationAsync(
            translationId, videoFileUrl, sourceLocale, targetLocale, voiceKind, operationId: operationId, cancellationToken: cancellationToken);

        if (!success || operationLocation == null)
        {
            return (false, error ?? "Failed to create translation", null);
        }

        await RequestOperationUntilTerminatedAsync(operationLocation, cancellationToken);

        var (getSuccess, getError, resultTranslation) = await RequestGetTranslationAsync(translationId, cancellationToken);
        if (!getSuccess)
        {
            return (false, getError ?? "Failed to query translation", null);
        }

        if (resultTranslation?.Status != nameof(OperationStatus.Succeeded))
        {
            return (false, resultTranslation?.TranslationFailureReason ?? "Translation failed", null);
        }

        return (true, null, resultTranslation);
    }

    /// <summary>
    /// Creates an iteration and waits for it to complete.
    /// </summary>
    public async Task<(bool success, string? error, IterationDefinition? iteration)> CreateIterationUntilTerminatedAsync(
        string translationId,
        string iterationId,
        WebvttFileKind? webvttFileKind = null,
        string? webvttFileUrl = null,
        int? speakerCount = null,
        int? subtitleMaxCharCountPerSegment = null,
        bool? exportSubtitleInVideo = null,
        CancellationToken cancellationToken = default)
    {
        var (success, error, iteration, operationLocation) = await RequestCreateIterationAsync(
            translationId, iterationId, webvttFileKind, webvttFileUrl, speakerCount, 
            subtitleMaxCharCountPerSegment, exportSubtitleInVideo, cancellationToken: cancellationToken);

        if (!success || operationLocation == null)
        {
            return (false, error ?? "Failed to create iteration", null);
        }

        await RequestOperationUntilTerminatedAsync(operationLocation, cancellationToken);

        var (getSuccess, getError, resultIteration) = await RequestGetIterationAsync(translationId, iterationId, cancellationToken);
        if (!getSuccess)
        {
            return (false, getError ?? "Failed to query iteration", null);
        }

        if (resultIteration?.Status != nameof(OperationStatus.Succeeded))
        {
            return (false, resultIteration?.IterationFailureReason ?? "Iteration failed", null);
        }

        return (true, null, resultIteration);
    }

    /// <summary>
    /// Creates a translation and runs the first iteration until both are complete.
    /// </summary>
    public async Task<(bool success, string? error, TranslationDefinition? translation, IterationDefinition? iteration)> 
        CreateTranslateAndRunFirstIterationUntilTerminatedAsync(
        string videoFileUrl,
        string sourceLocale,
        string targetLocale,
        VoiceKind voiceKind,
        int speakerCount = 1,
        int subtitleMaxCharCountPerSegment = 32,
        bool exportSubtitleInVideo = false,
        CancellationToken cancellationToken = default)
    {
        var (success, error, translation) = await CreateTranslationUntilTerminatedAsync(
            videoFileUrl, sourceLocale, targetLocale, voiceKind, cancellationToken);

        if (!success || translation == null)
        {
            return (false, error, null, null);
        }

        var now = DateTime.UtcNow;
        var iterationId = $"{now:MMddyyyyHHmmss}_default";

        var (iterSuccess, iterError, iteration) = await CreateIterationUntilTerminatedAsync(
            translation.Id!, iterationId, speakerCount: speakerCount,
            subtitleMaxCharCountPerSegment: subtitleMaxCharCountPerSegment,
            exportSubtitleInVideo: exportSubtitleInVideo,
            cancellationToken: cancellationToken);

        if (!iterSuccess)
        {
            return (false, iterError, translation, null);
        }

        return (true, null, translation, iteration);
    }

    /// <summary>
    /// Requests creation of a translation.
    /// </summary>
    private async Task<(bool success, string? error, TranslationDefinition? translation, string? operationLocation)> 
        RequestCreateTranslationAsync(
        string translationId,
        string videoFileUrl,
        string sourceLocale,
        string targetLocale,
        VoiceKind voiceKind,
        int speakerCount = 1,
        int subtitleMaxCharCountPerSegment = 32,
        bool exportSubtitleInVideo = false,
        string? translationDisplayName = null,
        string? translationDescription = null,
        string? operationId = null,
        CancellationToken cancellationToken = default)
    {
        operationId ??= GenerateOperationId();

        var inputBody = new Dictionary<string, object>
        {
            ["sourceLocale"] = sourceLocale,
            ["targetLocale"] = targetLocale,
            ["voiceKind"] = voiceKind.ToString(),
            ["videoFileUrl"] = videoFileUrl,
            ["speakerCount"] = speakerCount,
            ["subtitleMaxCharCountPerSegment"] = subtitleMaxCharCountPerSegment,
            ["exportSubtitleInVideo"] = exportSubtitleInVideo
        };

        var translationCreateBody = new Dictionary<string, object>
        {
            ["input"] = inputBody
        };

        if (!string.IsNullOrEmpty(translationDisplayName))
        {
            translationCreateBody["displayName"] = translationDisplayName;
        }

        if (!string.IsNullOrEmpty(translationDescription))
        {
            translationCreateBody["description"] = translationDescription;
        }

        var url = BuildUrl(BuildTranslationPath(translationId));
        var request = await CreateRequestAsync(HttpMethod.Put, url, cancellationToken);
        request.Headers.Add("Operation-Id", operationId);
        request.Content = new StringContent(
            JsonSerializer.Serialize(translationCreateBody),
            Encoding.UTF8,
            "application/json");

        var response = await _httpClient.SendAsync(request, cancellationToken);

        if (!response.IsSuccessStatusCode)
        {
            var errorContent = await response.Content.ReadAsStringAsync(cancellationToken);
            return (false, $"HTTP {response.StatusCode}: {errorContent}", null, null);
        }

        var translation = await response.Content.ReadFromJsonAsync<TranslationDefinition>(cancellationToken: cancellationToken);
        var operationLocation = response.Headers.TryGetValues(OperationLocationHeader, out var values) 
            ? string.Join("", values) 
            : null;

        return (true, null, translation, operationLocation);
    }

    /// <summary>
    /// Requests creation of an iteration.
    /// </summary>
    private async Task<(bool success, string? error, IterationDefinition? iteration, string? operationLocation)> 
        RequestCreateIterationAsync(
        string translationId,
        string iterationId,
        WebvttFileKind? webvttFileKind = null,
        string? webvttFileUrl = null,
        int? speakerCount = null,
        int? subtitleMaxCharCountPerSegment = null,
        bool? exportSubtitleInVideo = null,
        string? iterationDescription = null,
        string? operationId = null,
        CancellationToken cancellationToken = default)
    {
        operationId ??= GenerateOperationId();

        var inputBody = new Dictionary<string, object>();

        if (webvttFileKind.HasValue && !string.IsNullOrEmpty(webvttFileUrl))
        {
            inputBody["webvttFile"] = new Dictionary<string, object>
            {
                ["kind"] = webvttFileKind.Value.ToString(),
                ["url"] = webvttFileUrl
            };
        }

        if (speakerCount.HasValue)
        {
            inputBody["speakerCount"] = speakerCount.Value;
        }

        if (subtitleMaxCharCountPerSegment.HasValue)
        {
            inputBody["subtitleMaxCharCountPerSegment"] = subtitleMaxCharCountPerSegment.Value;
        }

        if (exportSubtitleInVideo.HasValue)
        {
            inputBody["exportSubtitleInVideo"] = exportSubtitleInVideo.Value;
        }

        var iterationCreateBody = new Dictionary<string, object>
        {
            ["input"] = inputBody
        };

        if (!string.IsNullOrEmpty(iterationDescription))
        {
            iterationCreateBody["description"] = iterationDescription;
        }

        var url = BuildUrl(BuildIterationPath(translationId, iterationId));
        var request = await CreateRequestAsync(HttpMethod.Put, url, cancellationToken);
        request.Headers.Add("Operation-Id", operationId);
        request.Content = new StringContent(
            JsonSerializer.Serialize(iterationCreateBody),
            Encoding.UTF8,
            "application/json");

        var response = await _httpClient.SendAsync(request, cancellationToken);

        if (!response.IsSuccessStatusCode)
        {
            var errorContent = await response.Content.ReadAsStringAsync(cancellationToken);
            return (false, $"HTTP {response.StatusCode}: {errorContent}", null, null);
        }

        var iteration = await response.Content.ReadFromJsonAsync<IterationDefinition>(cancellationToken: cancellationToken);
        var operationLocation = response.Headers.TryGetValues(OperationLocationHeader, out var values) 
            ? string.Join("", values) 
            : null;

        return (true, null, iteration, operationLocation);
    }

    /// <summary>
    /// Polls an operation until it's terminated.
    /// </summary>
    private async Task RequestOperationUntilTerminatedAsync(string operationLocation, CancellationToken cancellationToken = default)
    {
        while (true)
        {
            await Task.Delay(TimeSpan.FromSeconds(5), cancellationToken);

            var request = await CreateRequestAsync(HttpMethod.Get, operationLocation, cancellationToken);
            var response = await _httpClient.SendAsync(request, cancellationToken);

            if (!response.IsSuccessStatusCode)
            {
                continue;
            }

            var operation = await response.Content.ReadFromJsonAsync<OperationDefinition>(cancellationToken: cancellationToken);

            if (operation?.Status == nameof(OperationStatus.Succeeded) ||
                operation?.Status == nameof(OperationStatus.Failed) ||
                operation?.Status == nameof(OperationStatus.Canceled))
            {
                break;
            }
        }
    }

    /// <summary>
    /// Gets a translation by ID.
    /// </summary>
    public async Task<(bool success, string? error, TranslationDefinition? translation)> RequestGetTranslationAsync(
        string translationId, CancellationToken cancellationToken = default)
    {
        var url = BuildUrl(BuildTranslationPath(translationId));
        var request = await CreateRequestAsync(HttpMethod.Get, url, cancellationToken);
        var response = await _httpClient.SendAsync(request, cancellationToken);

        if (!response.IsSuccessStatusCode)
        {
            var errorContent = await response.Content.ReadAsStringAsync(cancellationToken);
            return (false, $"HTTP {response.StatusCode}: {errorContent}", null);
        }

        var translation = await response.Content.ReadFromJsonAsync<TranslationDefinition>(cancellationToken: cancellationToken);
        return (true, null, translation);
    }

    /// <summary>
    /// Gets an iteration by ID.
    /// </summary>
    public async Task<(bool success, string? error, IterationDefinition? iteration)> RequestGetIterationAsync(
        string translationId, string iterationId, CancellationToken cancellationToken = default)
    {
        var url = BuildUrl(BuildIterationPath(translationId, iterationId));
        var request = await CreateRequestAsync(HttpMethod.Get, url, cancellationToken);
        var response = await _httpClient.SendAsync(request, cancellationToken);

        if (!response.IsSuccessStatusCode)
        {
            var errorContent = await response.Content.ReadAsStringAsync(cancellationToken);
            return (false, $"HTTP {response.StatusCode}: {errorContent}", null);
        }

        var iteration = await response.Content.ReadFromJsonAsync<IterationDefinition>(cancellationToken: cancellationToken);
        return (true, null, iteration);
    }

    /// <summary>
    /// Lists all translations.
    /// </summary>
    public async Task<(bool success, string? error, PagedTranslationDefinition? paged)> RequestListTranslationsAsync(
        CancellationToken cancellationToken = default)
    {
        var url = BuildUrl(BuildTranslationsPath());
        var request = await CreateRequestAsync(HttpMethod.Get, url, cancellationToken);
        var response = await _httpClient.SendAsync(request, cancellationToken);

        if (!response.IsSuccessStatusCode)
        {
            var errorContent = await response.Content.ReadAsStringAsync(cancellationToken);
            return (false, $"HTTP {response.StatusCode}: {errorContent}", null);
        }

        var paged = await response.Content.ReadFromJsonAsync<PagedTranslationDefinition>(cancellationToken: cancellationToken);
        return (true, null, paged);
    }

    /// <summary>
    /// Lists all iterations for a translation.
    /// </summary>
    public async Task<(bool success, string? error, PagedIterationDefinition? paged)> RequestListIterationsAsync(
        string translationId, CancellationToken cancellationToken = default)
    {
        var url = BuildUrl(BuildIterationsPath(translationId));
        var request = await CreateRequestAsync(HttpMethod.Get, url, cancellationToken);
        var response = await _httpClient.SendAsync(request, cancellationToken);

        if (!response.IsSuccessStatusCode)
        {
            var errorContent = await response.Content.ReadAsStringAsync(cancellationToken);
            return (false, $"HTTP {response.StatusCode}: {errorContent}", null);
        }

        var paged = await response.Content.ReadFromJsonAsync<PagedIterationDefinition>(cancellationToken: cancellationToken);
        return (true, null, paged);
    }

    /// <summary>
    /// Deletes a translation.
    /// </summary>
    public async Task<(bool success, string? error)> RequestDeleteTranslationAsync(
        string translationId, CancellationToken cancellationToken = default)
    {
        var url = BuildUrl(BuildTranslationPath(translationId));
        var request = await CreateRequestAsync(HttpMethod.Delete, url, cancellationToken);
        var response = await _httpClient.SendAsync(request, cancellationToken);

        if (!response.IsSuccessStatusCode)
        {
            var errorContent = await response.Content.ReadAsStringAsync(cancellationToken);
            return (false, $"HTTP {response.StatusCode}: {errorContent}");
        }

        return (true, null);
    }

    protected virtual void Dispose(bool disposing)
    {
        if (disposing)
        {
            _httpClient?.Dispose();
        }
    }

    public void Dispose()
    {
        Dispose(true);
        GC.SuppressFinalize(this);
    }
}
