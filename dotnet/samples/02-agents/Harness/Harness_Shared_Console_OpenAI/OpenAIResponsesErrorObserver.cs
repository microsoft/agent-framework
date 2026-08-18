// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable OPENAI001 // Suppress experimental API warnings for Responses API usage.

using System.Text.Json;
using Harness.Shared.Console.Observers;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

namespace Harness.Shared.Console.OpenAI;

/// <summary>
/// Detects and displays error/incomplete status from OpenAI Responses API streaming updates.
/// Handles <see cref="StreamingResponseFailedUpdate"/> and <see cref="StreamingResponseIncompleteUpdate"/>
/// which are not surfaced as <see cref="ErrorContent"/> by the chat client.
/// </summary>
/// <remarks>
/// Note: <see cref="StreamingResponseErrorUpdate"/> is already handled by the SDK — it produces
/// an <see cref="ErrorContent"/> which is displayed by <see cref="ErrorDisplayObserver"/>.
/// This observer covers the cases where the SDK does not produce <see cref="ErrorContent"/>.
/// </remarks>
public sealed class OpenAIResponsesErrorObserver : ConsoleObserver
{
    /// <inheritdoc/>
    public override async Task OnResponseUpdateAsync(IUXStateDriver ux, AgentResponseUpdate update, AIAgent agent, AgentSession session)
    {
        // AgentResponseUpdate.RawRepresentation is the ChatResponseUpdate,
        // whose RawRepresentation is the underlying StreamingResponseUpdate.
        object? rawUpdate = (update.RawRepresentation as ChatResponseUpdate)?.RawRepresentation
            ?? update.RawRepresentation;

        switch (rawUpdate)
        {
            case StreamingResponseFailedUpdate failedUpdate:
                // Only display if the response has error details populated.
                // When error is null, a follow-up StreamingResponseErrorUpdate typically
                // carries the real error — the SDK surfaces that as ErrorContent,
                // which is displayed by ErrorDisplayObserver.
                if (failedUpdate.Response?.Error is { } error)
                {
                    string errorMessage = error.Message ?? "Unknown error";
                    string? errorCode = error.Code.ToString();
                    string errorText = $"❌ Response failed: {errorMessage}";
                    if (!string.IsNullOrEmpty(errorCode))
                    {
                        errorText += $" (code: {errorCode})";
                    }

                    await ux.WriteInfoLineAsync(errorText, ConsoleColor.Red);
                }

                break;

            case StreamingResponseIncompleteUpdate incompleteUpdate:
                string? reason = incompleteUpdate.Response?.IncompleteStatusDetails?.Reason?.ToString();
                if (string.Equals(reason, "content_filter", StringComparison.OrdinalIgnoreCase))
                {
                    string detail = GetContentFilterDetails(incompleteUpdate);
                    const string Message = "🛡️  The service's built-in content filter guardrails were triggered and the response was cut short.";
                    await ux.WriteInfoLineAsync(
                        string.IsNullOrEmpty(detail) ? Message : $"{Message}\n{detail}",
                        ConsoleColor.Yellow);
                }
                else
                {
                    string incompleteText = $"⚠️ Response incomplete: {reason ?? "unknown reason"}";
                    await ux.WriteInfoLineAsync(incompleteText, ConsoleColor.Yellow);
                }

                break;
        }
    }

    /// <summary>
    /// Extracts content filter details from the serialized response JSON and returns
    /// a formatted string showing which specific categories were triggered.
    /// Returns <see cref="string.Empty"/> if details cannot be extracted.
    /// </summary>
    private static string GetContentFilterDetails(StreamingResponseIncompleteUpdate incompleteUpdate)
    {
        try
        {
            var data = System.ClientModel.Primitives.ModelReaderWriter.Write(incompleteUpdate);
            using var doc = JsonDocument.Parse(data.ToString());
            var root = doc.RootElement;

            // Navigate into the nested response object if present.
            JsonElement responseElement = root.TryGetProperty("response", out var resp) ? resp : root;

            if (!responseElement.TryGetProperty("content_filters", out var filtersArray)
                || filtersArray.ValueKind != JsonValueKind.Array)
            {
                return string.Empty;
            }

            foreach (var filter in filtersArray.EnumerateArray())
            {
                if (!filter.TryGetProperty("content_filter_results", out var results)
                    || results.ValueKind != JsonValueKind.Object)
                {
                    continue;
                }

                // Collect category data for aligned output.
                var categories = new List<(string Name, bool Filtered, string? Severity)>();
                foreach (var category in results.EnumerateObject())
                {
                    if (category.Value.ValueKind != JsonValueKind.Object)
                    {
                        continue;
                    }

                    bool filtered = category.Value.TryGetProperty("filtered", out var f) && f.GetBoolean();
                    string? severity = category.Value.TryGetProperty("severity", out var s) ? s.GetString() : null;
                    categories.Add((category.Name, filtered, severity));
                }

                // Build all category lines into a single string.
                int maxNameLen = categories.Count > 0 ? categories.Max(c => c.Name.Length) : 0;
                var lines = new List<string>();

                foreach (var (name, filtered, severity) in categories)
                {
                    string paddedName = name.PadRight(maxNameLen);
                    string icon = filtered ? "❌" : "✅";
                    string statusText = filtered ? "Filtered    " : "Not Filtered";
                    string severityText = severity is not null ? $"   Severity: {severity}" : "";

                    lines.Add($"    {icon} {paddedName}  {statusText}{severityText}");
                }

                if (lines.Count > 0)
                {
                    return string.Join("\n", lines);
                }
            }

            return string.Empty;
        }
        catch
        {
            // Parsing not critical — skip silently if it fails.
            return string.Empty;
        }
    }
}
