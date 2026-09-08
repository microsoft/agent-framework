// Copyright (c) Microsoft. All rights reserved.

using System.Net.Http.Json;
using System.Text.Json;

namespace Hosted_Shared_Contributor_Setup;

/// <summary>
/// Calls the idempotent operation service used by the resilience samples.
/// </summary>
/// <remarks>
/// <para>
/// For demonstration purposes only. This sample client and its backing service should not be used as-is in production.
/// </para>
/// <para>
/// Recovery may execute a workflow step again if its checkpoint was not saved before a crash.
/// Services called by that step must handle repeated requests without repeating unintended downstream effects.
/// This sample reuses the same scope and operation ID so the service can return the previously stored result.
/// Idempotency is enforced by the service, not by this client.
/// </para>
/// </remarks>
public sealed class IdempotentServiceClient(HttpClient httpClient)
{
    /// <summary>
    /// Executes an operation or returns its previously stored result.
    /// </summary>
    /// <param name="scope">The operation scope.</param>
    /// <param name="operationId">The operation identifier within the scope.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The operation result.</returns>
    public async Task<string> ExecuteOperationAsync(
        string scope,
        int operationId,
        CancellationToken cancellationToken = default)
    {
        using HttpResponseMessage response = await httpClient.PostAsync(
            new Uri($"operations/{Uri.EscapeDataString(scope)}/{operationId}", UriKind.Relative),
            content: null,
            cancellationToken);
        response.EnsureSuccessStatusCode();
        await using Stream content = await response.Content.ReadAsStreamAsync(cancellationToken);
        using JsonDocument document = await JsonDocument.ParseAsync(content, cancellationToken: cancellationToken);
        return document.RootElement.GetProperty("result").GetString()
            ?? throw new InvalidOperationException("The idempotent service returned an empty result.");
    }

    /// <summary>
    /// Gets the number of completed operations in a scope.
    /// </summary>
    /// <param name="scope">The operation scope.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The number of completed operations.</returns>
    public async Task<int> GetOperationCountAsync(string scope, CancellationToken cancellationToken = default)
    {
        int? count = await httpClient.GetFromJsonAsync<int?>(
            new Uri($"operations/{Uri.EscapeDataString(scope)}/count", UriKind.Relative),
            cancellationToken);
        return count
            ?? throw new InvalidOperationException("The idempotent service returned an empty operation count.");
    }
}
