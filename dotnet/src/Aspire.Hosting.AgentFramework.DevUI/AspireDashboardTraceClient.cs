// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace Aspire.Hosting.AgentFramework;

/// <summary>
/// Connection details for the Aspire Dashboard telemetry API.
/// </summary>
internal sealed record AspireDashboardConnection(Uri BaseUri, string? ApiKey);

/// <summary>
/// Converts OTLP JSON returned by the Aspire Dashboard telemetry API into DevUI trace events.
/// </summary>
internal static class AspireDashboardTraceClient
{
    private const string ApiKeyHeaderName = "x-api-key";

    /// <summary>
    /// Checks whether the configured Aspire Dashboard exposes its authenticated telemetry API.
    /// </summary>
    internal static async Task<bool> IsAvailableAsync(
        HttpClient client,
        Uri dashboardBaseUri,
        string? dashboardApiKey,
        CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, new Uri(dashboardBaseUri, "/api/telemetry/resources"));
        AddApiKey(request, dashboardApiKey);

        using var response = await client.SendAsync(request, cancellationToken).ConfigureAwait(false);
        return response.IsSuccessStatusCode;
    }

    /// <summary>
    /// Reads the spans for one response trace from the Aspire Dashboard telemetry API.
    /// </summary>
    internal static async Task<IReadOnlyList<JsonObject>?> GetTraceEventsAsync(
        HttpClient client,
        Uri dashboardBaseUri,
        string? dashboardApiKey,
        string traceId,
        string responseId,
        string entityId,
        CancellationToken cancellationToken)
    {
        var path = $"/api/telemetry/traces/{Uri.EscapeDataString(traceId)}";
        using var request = new HttpRequestMessage(HttpMethod.Get, new Uri(dashboardBaseUri, path));
        AddApiKey(request, dashboardApiKey);

        using var response = await client.SendAsync(request, cancellationToken).ConfigureAwait(false);
        if (response.StatusCode == HttpStatusCode.NotFound)
        {
            return [];
        }

        if (!response.IsSuccessStatusCode)
        {
            return null;
        }

        using var document = await JsonDocument.ParseAsync(
            await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false),
            cancellationToken: cancellationToken).ConfigureAwait(false);

        if (document.RootElement.TryGetProperty("totalCount", out var totalCount) &&
            totalCount.TryGetInt64(out var total) &&
            document.RootElement.TryGetProperty("returnedCount", out var returnedCount) &&
            returnedCount.TryGetInt64(out var returned) &&
            total != returned)
        {
            return null;
        }

        if (!document.RootElement.TryGetProperty("data", out var data) || data.ValueKind != JsonValueKind.Object)
        {
            return [];
        }

        return ConvertToTraceEvents(data, responseId, entityId);
    }

    private static void AddApiKey(HttpRequestMessage request, string? dashboardApiKey)
    {
        if (!string.IsNullOrEmpty(dashboardApiKey))
        {
            request.Headers.TryAddWithoutValidation(ApiKeyHeaderName, dashboardApiKey);
        }
    }

    /// <summary>
    /// Converts an OTLP trace response to the trace-event contract consumed by DevUI.
    /// </summary>
    internal static IReadOnlyList<JsonObject> ConvertToTraceEvents(
        JsonElement response,
        string responseId,
        string entityId)
    {
        var results = new List<JsonObject>();

        if (!response.TryGetProperty("resourceSpans", out var resourceSpans) ||
            resourceSpans.ValueKind != JsonValueKind.Array)
        {
            return results;
        }

        foreach (var resourceSpan in resourceSpans.EnumerateArray())
        {
            if (!resourceSpan.TryGetProperty("scopeSpans", out var scopeSpans) ||
                scopeSpans.ValueKind != JsonValueKind.Array)
            {
                continue;
            }

            foreach (var scopeSpan in scopeSpans.EnumerateArray())
            {
                if (!scopeSpan.TryGetProperty("spans", out var spans) || spans.ValueKind != JsonValueKind.Array)
                {
                    continue;
                }

                foreach (var span in spans.EnumerateArray())
                {
                    var data = ConvertSpan(span, responseId, entityId);
                    if (data is not null)
                    {
                        results.Add(new JsonObject
                        {
                            ["type"] = "response.trace.completed",
                            ["data"] = data,
                            ["sequence_number"] = 0
                        });
                    }
                }
            }
        }

        return results;
    }

    private static JsonObject? ConvertSpan(JsonElement span, string responseId, string entityId)
    {
        if (!TryGetString(span, "traceId", out var traceId) ||
            !TryGetString(span, "spanId", out var spanId) ||
            !TryGetString(span, "name", out var name))
        {
            return null;
        }

        var startTime = ReadUnixNanoseconds(span, "startTimeUnixNano");
        var endTime = ReadUnixNanoseconds(span, "endTimeUnixNano");
        var status = ReadStatus(span, out var error);

        var data = new JsonObject
        {
            ["type"] = "trace_span",
            ["span_id"] = spanId,
            ["trace_id"] = traceId,
            ["parent_span_id"] = ReadOptionalString(span, "parentSpanId"),
            ["operation_name"] = name,
            ["start_time"] = startTime,
            ["end_time"] = endTime,
            ["duration_ms"] = startTime is not null && endTime is not null
                ? (endTime.Value - startTime.Value) * 1000
                : null,
            ["attributes"] = ReadAttributes(span),
            ["status"] = status,
            ["response_id"] = responseId,
            ["entity_id"] = entityId
        };

        if (error is not null)
        {
            data["error"] = error;
        }

        if (span.TryGetProperty("events", out var events) && events.ValueKind == JsonValueKind.Array)
        {
            var convertedEvents = new JsonArray();
            foreach (var spanEvent in events.EnumerateArray())
            {
                convertedEvents.Add(new JsonObject
                {
                    ["name"] = ReadOptionalString(spanEvent, "name"),
                    ["timestamp"] = ReadUnixNanoseconds(spanEvent, "timeUnixNano"),
                    ["attributes"] = ReadAttributes(spanEvent)
                });
            }

            data["events"] = convertedEvents;
        }

        return data;
    }

    private static string ReadStatus(JsonElement span, out string? error)
    {
        error = null;
        if (!span.TryGetProperty("status", out var status) || status.ValueKind != JsonValueKind.Object)
        {
            return "StatusCode.UNSET";
        }

        var code = status.TryGetProperty("code", out var codeElement) && codeElement.TryGetInt32(out var value)
            ? value
            : 0;

        if (code == 2)
        {
            error = ReadOptionalString(status, "message") ?? "Unknown error";
            return "ERROR";
        }

        return code == 1 ? "OK" : "StatusCode.UNSET";
    }

    private static JsonObject ReadAttributes(JsonElement container)
    {
        var result = new JsonObject();
        if (!container.TryGetProperty("attributes", out var attributes) || attributes.ValueKind != JsonValueKind.Array)
        {
            return result;
        }

        foreach (var attribute in attributes.EnumerateArray())
        {
            if (!TryGetString(attribute, "key", out var key) ||
                !attribute.TryGetProperty("value", out var value) ||
                value.ValueKind != JsonValueKind.Object)
            {
                continue;
            }

            result[key] = ReadAnyValue(value);
        }

        return result;
    }

    private static JsonNode? ReadAnyValue(JsonElement value)
    {
        if (value.TryGetProperty("stringValue", out var stringValue))
        {
            return JsonValue.Create(stringValue.GetString());
        }

        if (value.TryGetProperty("boolValue", out var boolValue) &&
            boolValue.ValueKind is JsonValueKind.True or JsonValueKind.False)
        {
            return JsonValue.Create(boolValue.GetBoolean());
        }

        if (value.TryGetProperty("intValue", out var intValue))
        {
            if (intValue.ValueKind == JsonValueKind.Number && intValue.TryGetInt64(out var number))
            {
                return JsonValue.Create(number);
            }

            if (intValue.ValueKind == JsonValueKind.String &&
                long.TryParse(intValue.GetString(), NumberStyles.Integer, CultureInfo.InvariantCulture, out number))
            {
                return JsonValue.Create(number);
            }
        }

        if (value.TryGetProperty("doubleValue", out var doubleValue) && doubleValue.TryGetDouble(out var floatingPoint))
        {
            return JsonValue.Create(floatingPoint);
        }

        return JsonNode.Parse(value.GetRawText());
    }

    private static double? ReadUnixNanoseconds(JsonElement container, string propertyName)
    {
        if (!container.TryGetProperty(propertyName, out var value))
        {
            return null;
        }

        if (value.ValueKind == JsonValueKind.String &&
            decimal.TryParse(value.GetString(), NumberStyles.Integer, CultureInfo.InvariantCulture, out var nanoseconds))
        {
            return (double)(nanoseconds / 1_000_000_000m);
        }

        if (value.ValueKind == JsonValueKind.Number && value.TryGetDecimal(out nanoseconds))
        {
            return (double)(nanoseconds / 1_000_000_000m);
        }

        return null;
    }

    private static bool TryGetString(JsonElement container, string propertyName, out string value)
    {
        value = string.Empty;
        if (!container.TryGetProperty(propertyName, out var property) || property.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        value = property.GetString()!;
        return true;
    }

    private static string? ReadOptionalString(JsonElement container, string propertyName)
        => TryGetString(container, propertyName, out var value) && !string.IsNullOrEmpty(value) ? value : null;
}
