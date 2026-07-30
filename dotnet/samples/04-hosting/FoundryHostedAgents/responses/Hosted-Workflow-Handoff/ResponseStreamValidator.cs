// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace HostedWorkflowHandoff;

/// <summary>Captured SSE event for validation.</summary>
[System.Diagnostics.CodeAnalysis.SuppressMessage("Microsoft.Performance", "CA1812:AvoidUninstantiatedInternalClasses", Justification = "Instantiated by JSON deserialization")]
internal sealed record CapturedSseEvent(
    [property: JsonPropertyName("eventType")] string EventType,
    [property: JsonPropertyName("data")] string Data);

/// <summary>Captured SSE stream sent from the client for server-side validation.</summary>
[System.Diagnostics.CodeAnalysis.SuppressMessage("Microsoft.Performance", "CA1812:AvoidUninstantiatedInternalClasses", Justification = "Instantiated by JSON deserialization")]
internal sealed record CapturedSseStream(
    [property: JsonPropertyName("events")] List<CapturedSseEvent> Events);

/// <summary>
/// Validates an SSE event stream from the Azure AI Responses Server SDK against
/// the API behaviour contract. Feed events sequentially via <see cref="ProcessEvent"/>
/// and call <see cref="Complete"/> when the stream ends.
/// </summary>
internal sealed class ResponseStreamValidator
{
    private readonly List<ValidationViolation> _violations = [];
    private int _eventCount;
    private int _expectedSequenceNumber;
    private StreamState _state = StreamState.Initial;
    private string? _responseId;
    private readonly HashSet<int> _addedItemIndices = [];
    private readonly HashSet<int> _doneItemIndices = [];
    private readonly HashSet<string> _addedContentParts = []; // "outputIdx:partIdx"
    private readonly HashSet<string> _doneContentParts = [];
    private readonly Dictionary<string, string> _textAccumulators = []; // "outputIdx:contentIdx" → accumulated text
    private bool _hasTerminal;

    /// <summary>All violations found so far.</summary>
    internal IReadOnlyList<ValidationViolation> Violations => this._violations;

    /// <summary>
    /// Processes a single SSE event line pair (event type + JSON data).
    /// </summary>
    /// <param name="eventType">The SSE event type (e.g. "response.created").</param>
    /// <param name="jsonData">The raw JSON data payload.</param>
    internal void ProcessEvent(string eventType, string jsonData)
    {
        JsonElement data;
        try
        {
            data = JsonDocument.Parse(jsonData).RootElement;
        }
        catch (JsonException ex)
        {
            this.Fail("PARSE-01", $"Invalid JSON in event data: {ex.Message}");
            return;
        }

        this._eventCount++;

        // ── Sequence number validation ──────────────────────────────────
        if (data.TryGetProperty("sequence_number", out var seqProp) && seqProp.ValueKind == JsonValueKind.Number)
        {
            int seq = seqProp.GetInt32();
            if (seq != this._expectedSequenceNumber)
            {
                this.Fail("SEQ-01", $"Expected sequence_number {this._expectedSequenceNumber}, got {seq}");
            }

            this._expectedSequenceNumber = seq + 1;
        }
        else if (this._state != StreamState.Initial || eventType != "error")
        {
            // Pre-creation error events may not have sequence_number
            this.Fail("SEQ-02", $"Missing sequence_number on event '{eventType}'");
        }

        // ── Post-terminal guard ─────────────────────────────────────────
        if (this._hasTerminal)
        {
            this.Fail("TERM-01", $"Event '{eventType}' received after terminal event");
            return;
        }

        // ── Dispatch by event type ──────────────────────────────────────
        switch (eventType)
        {
            case "response.created":
                this.ValidateResponseCreated(data);
                break;

            case "response.queued":
                this.ValidateStateTransition(eventType, StreamState.Created, StreamState.Queued);
                this.ValidateResponseEnvelope(data, eventType);
                break;

            case "response.in_progress":
                if (this._state is StreamState.Created or StreamState.Queued)
                {
                    this._state = StreamState.InProgress;
                }
                else
                {
                    this.Fail("ORDER-02", $"'response.in_progress' received in state {this._state} (expected Created or Queued)");
                }

                this.ValidateResponseEnvelope(data, eventType);
                break;

            case "response.output_item.added":
            case "output_item.added":
                this.ValidateInProgress(eventType);
                this.ValidateOutputItemAdded(data);
                break;

            case "response.output_item.done":
            case "output_item.done":
                this.ValidateInProgress(eventType);
                this.ValidateOutputItemDone(data);
                break;

            case "response.content_part.added":
            case "content_part.added":
                this.ValidateInProgress(eventType);
                this.ValidateContentPartAdded(data);
                break;

            case "response.content_part.done":
            case "content_part.done":
                this.ValidateInProgress(eventType);
                this.ValidateContentPartDone(data);
                break;

            case "response.output_text.delta":
            case "output_text.delta":
                this.ValidateInProgress(eventType);
                this.ValidateTextDelta(data);
                break;

            case "response.output_text.done":
            case "output_text.done":
                this.ValidateInProgress(eventType);
                this.ValidateTextDone(data);
                break;

            case "response.function_call_arguments.delta":
            case "function_call_arguments.delta":
                this.ValidateInProgress(eventType);
                break;

            case "response.function_call_arguments.done":
            case "function_call_arguments.done":
                this.ValidateInProgress(eventType);
                break;

            case "response.completed":
                this.ValidateTerminal(data, "completed");
                break;

            case "response.failed":
                this.ValidateTerminal(data, "failed");
                break;

            case "response.incomplete":
                this.ValidateTerminal(data, "incomplete");
                break;

            case "error":
                // Pre-creation error — standalone, no response.created precedes it
                if (this._state != StreamState.Initial)
                {
                    this.Fail("ERR-01", "'error' event received after response.created — should use response.failed instead");
                }

                this._hasTerminal = true;
                break;

            default:
                // Unknown events are not violations — the spec may evolve
                break;
        }
    }

    /// <summary>
    /// Call after the stream ends. Checks that a terminal event was received.
    /// </summary>
    internal void Complete()
    {
        if (!this._hasTerminal && this._state != StreamState.Initial)
        {
            this.Fail("TERM-02", "Stream ended without a terminal event (response.completed, response.failed, or response.incomplete)");
        }

        if (this._state == StreamState.Initial && this._eventCount == 0)
        {
            this.Fail("EMPTY-01", "No events received in the stream");
        }

        // Check for output items that were added but never completed
        foreach (int idx in this._addedItemIndices)
        {
            if (!this._doneItemIndices.Contains(idx))
            {
                this.Fail("ITEM-03", $"Output item at index {idx} was added but never received output_item.done");
            }
        }

        // Check for content parts that were added but never completed
        foreach (string key in this._addedContentParts)
        {
            if (!this._doneContentParts.Contains(key))
            {
                this.Fail("CONTENT-03", $"Content part '{key}' was added but never received content_part.done");
            }
        }
    }

    /// <summary>
    /// Returns a summary of all validation results.
    /// </summary>
    internal ValidationResult GetResult()
    {
        return new ValidationResult(
            EventCount: this._eventCount,
            IsValid: this._violations.Count == 0,
            Violations: [.. this._violations]);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Event-specific validators
    // ═══════════════════════════════════════════════════════════════════════

    private void ValidateResponseCreated(JsonElement data)
    {
        if (this._state != StreamState.Initial)
        {
            this.Fail("ORDER-01", $"'response.created' received in state {this._state} (expected Initial — must be first event)");
            return;
        }

        this._state = StreamState.Created;

        // Must have a response envelope
        if (!data.TryGetProperty("response", out var resp))
        {
            this.Fail("FIELD-01", "'response.created' missing 'response' object");
            return;
        }

        // Required response fields
        this.ValidateRequiredResponseFields(resp, "response.created");

        // Capture response ID for cross-event checks
        if (resp.TryGetProperty("id", out var idProp))
        {
            this._responseId = idProp.GetString();
        }

        // Status must be non-terminal
        if (resp.TryGetProperty("status", out var statusProp))
        {
            string? status = statusProp.GetString();
            if (status is "completed" or "failed" or "incomplete" or "cancelled")
            {
                this.Fail("STATUS-01", $"'response.created' has terminal status '{status}' — must be 'queued' or 'in_progress'");
            }
        }
    }

    private void ValidateTerminal(JsonElement data, string expectedKind)
    {
        if (this._state is StreamState.Initial or StreamState.Created)
        {
            this.Fail("ORDER-03", $"Terminal event 'response.{expectedKind}' received before 'response.in_progress'");
        }

        this._hasTerminal = true;
        this._state = StreamState.Terminal;

        if (!data.TryGetProperty("response", out var resp))
        {
            this.Fail("FIELD-01", $"'response.{expectedKind}' missing 'response' object");
            return;
        }

        this.ValidateRequiredResponseFields(resp, $"response.{expectedKind}");

        if (resp.TryGetProperty("status", out var statusProp))
        {
            string? status = statusProp.GetString();

            // completed_at validation (B6)
            bool hasCompletedAt = resp.TryGetProperty("completed_at", out var catProp)
                && catProp.ValueKind != JsonValueKind.Null;

            if (status == "completed" && !hasCompletedAt)
            {
                this.Fail("FIELD-02", "'completed_at' must be non-null when status is 'completed'");
            }

            if (status != "completed" && hasCompletedAt)
            {
                this.Fail("FIELD-03", $"'completed_at' must be null when status is '{status}'");
            }

            // error field validation
            bool hasError = resp.TryGetProperty("error", out var errProp)
                && errProp.ValueKind != JsonValueKind.Null;

            if (status == "failed" && !hasError)
            {
                this.Fail("FIELD-04", "'error' must be non-null when status is 'failed'");
            }

            if (status is "completed" or "incomplete" && hasError)
            {
                this.Fail("FIELD-05", $"'error' must be null when status is '{status}'");
            }

            // error structure validation
            if (hasError)
            {
                this.ValidateErrorObject(errProp, $"response.{expectedKind}");
            }

            // cancelled output must be empty (B11)
            if (status == "cancelled" && resp.TryGetProperty("output", out var outputProp)
                && outputProp.ValueKind == JsonValueKind.Array && outputProp.GetArrayLength() > 0)
            {
                this.Fail("CANCEL-01", "Cancelled response must have empty output array (B11)");
            }

            // response ID consistency
            if (this._responseId is not null && resp.TryGetProperty("id", out var idProp)
                && idProp.GetString() != this._responseId)
            {
                this.Fail("ID-01", $"Response ID changed: was '{this._responseId}', now '{idProp.GetString()}'");
            }
        }

        // Usage validation (optional, but if present must be structured correctly)
        if (resp.TryGetProperty("usage", out var usageProp) && usageProp.ValueKind == JsonValueKind.Object)
        {
            this.ValidateUsage(usageProp, $"response.{expectedKind}");
        }
    }

    private void ValidateOutputItemAdded(JsonElement data)
    {
        if (data.TryGetProperty("output_index", out var idxProp) && idxProp.ValueKind == JsonValueKind.Number)
        {
            int index = idxProp.GetInt32();
            if (!this._addedItemIndices.Add(index))
            {
                this.Fail("ITEM-01", $"Duplicate output_item.added for output_index {index}");
            }
        }
        else
        {
            this.Fail("FIELD-06", "output_item.added missing 'output_index' field");
        }

        if (!data.TryGetProperty("item", out _))
        {
            this.Fail("FIELD-07", "output_item.added missing 'item' object");
        }
    }

    private void ValidateOutputItemDone(JsonElement data)
    {
        if (data.TryGetProperty("output_index", out var idxProp) && idxProp.ValueKind == JsonValueKind.Number)
        {
            int index = idxProp.GetInt32();
            if (!this._addedItemIndices.Contains(index))
            {
                this.Fail("ITEM-02", $"output_item.done for output_index {index} without preceding output_item.added");
            }

            this._doneItemIndices.Add(index);
        }
        else
        {
            this.Fail("FIELD-06", "output_item.done missing 'output_index' field");
        }
    }

    private void ValidateContentPartAdded(JsonElement data)
    {
        string key = GetContentPartKey(data);
        if (!this._addedContentParts.Add(key))
        {
            this.Fail("CONTENT-01", $"Duplicate content_part.added for {key}");
        }
    }

    private void ValidateContentPartDone(JsonElement data)
    {
        string key = GetContentPartKey(data);
        if (!this._addedContentParts.Contains(key))
        {
            this.Fail("CONTENT-02", $"content_part.done for {key} without preceding content_part.added");
        }

        this._doneContentParts.Add(key);
    }

    private void ValidateTextDelta(JsonElement data)
    {
        string key = GetTextKey(data);
        string delta = data.TryGetProperty("delta", out var deltaProp)
            ? deltaProp.GetString() ?? string.Empty
            : string.Empty;

        if (!this._textAccumulators.TryGetValue(key, out string? existing))
        {
            this._textAccumulators[key] = delta;
        }
        else
        {
            this._textAccumulators[key] = existing + delta;
        }
    }

    private void ValidateTextDone(JsonElement data)
    {
        string key = GetTextKey(data);
        string? finalText = data.TryGetProperty("text", out var textProp)
            ? textProp.GetString()
            : null;

        if (finalText is null)
        {
            this.Fail("TEXT-01", $"output_text.done for {key} missing 'text' field");
            return;
        }

        if (this._textAccumulators.TryGetValue(key, out string? accumulated) && accumulated != finalText)
        {
            this.Fail("TEXT-02", $"output_text.done text for {key} does not match accumulated deltas (accumulated {accumulated.Length} chars, done has {finalText.Length} chars)");
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Shared field validators
    // ═══════════════════════════════════════════════════════════════════════

    private void ValidateRequiredResponseFields(JsonElement resp, string context)
    {
        if (!HasNonNullString(resp, "id"))
        {
            this.Fail("FIELD-01", $"{context}: response missing 'id'");
        }

        if (resp.TryGetProperty("object", out var objProp))
        {
            if (objProp.GetString() != "response")
            {
                this.Fail("FIELD-08", $"{context}: response.object must be 'response', got '{objProp.GetString()}'");
            }
        }
        else
        {
            this.Fail("FIELD-08", $"{context}: response missing 'object' field");
        }

        if (!resp.TryGetProperty("created_at", out var catProp) || catProp.ValueKind == JsonValueKind.Null)
        {
            this.Fail("FIELD-09", $"{context}: response missing 'created_at'");
        }

        if (!resp.TryGetProperty("status", out _))
        {
            this.Fail("FIELD-10", $"{context}: response missing 'status'");
        }

        if (!resp.TryGetProperty("output", out var outputProp) || outputProp.ValueKind != JsonValueKind.Array)
        {
            this.Fail("FIELD-11", $"{context}: response missing 'output' array");
        }
    }

    private void ValidateErrorObject(JsonElement error, string context)
    {
        if (!HasNonNullString(error, "code"))
        {
            this.Fail("ERR-02", $"{context}: error object missing 'code' field");
        }

        if (!HasNonNullString(error, "message"))
        {
            this.Fail("ERR-03", $"{context}: error object missing 'message' field");
        }
    }

    private void ValidateUsage(JsonElement usage, string context)
    {
        if (!usage.TryGetProperty("input_tokens", out _))
        {
            this.Fail("USAGE-01", $"{context}: usage missing 'input_tokens'");
        }

        if (!usage.TryGetProperty("output_tokens", out _))
        {
            this.Fail("USAGE-02", $"{context}: usage missing 'output_tokens'");
        }

        if (!usage.TryGetProperty("total_tokens", out _))
        {
            this.Fail("USAGE-03", $"{context}: usage missing 'total_tokens'");
        }
    }

    private void ValidateResponseEnvelope(JsonElement data, string eventType)
    {
        if (!data.TryGetProperty("response", out var resp))
        {
            this.Fail("FIELD-01", $"'{eventType}' missing 'response' object");
            return;
        }

        this.ValidateRequiredResponseFields(resp, eventType);

        // Response ID consistency
        if (this._responseId is not null && resp.TryGetProperty("id", out var idProp)
            && idProp.GetString() != this._responseId)
        {
            this.Fail("ID-01", $"Response ID changed: was '{this._responseId}', now '{idProp.GetString()}'");
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Helpers
    // ═══════════════════════════════════════════════════════════════════════

    private void ValidateInProgress(string eventType)
    {
        if (this._state != StreamState.InProgress)
        {
            this.Fail("ORDER-04", $"'{eventType}' received in state {this._state} (expected InProgress)");
        }
    }

    private void ValidateStateTransition(string eventType, StreamState expected, StreamState next)
    {
        if (this._state != expected)
        {
            this.Fail("ORDER-05", $"'{eventType}' received in state {this._state} (expected {expected})");
        }
        else
        {
            this._state = next;
        }
    }

    private void Fail(string ruleId, string message)
    {
        this._violations.Add(new ValidationViolation(ruleId, message, this._eventCount));
    }

    private static bool HasNonNullString(JsonElement obj, string property)
    {
        return obj.TryGetProperty(property, out var prop)
            && prop.ValueKind == JsonValueKind.String
            && !string.IsNullOrEmpty(prop.GetString());
    }

    private static string GetContentPartKey(JsonElement data)
    {
        int outputIdx = data.TryGetProperty("output_index", out var oi) ? oi.GetInt32() : -1;
        int partIdx = data.TryGetProperty("content_index", out var pi) ? pi.GetInt32() : -1;
        return $"{outputIdx}:{partIdx}";
    }

    private static string GetTextKey(JsonElement data)
    {
        int outputIdx = data.TryGetProperty("output_index", out var oi) ? oi.GetInt32() : -1;
        int contentIdx = data.TryGetProperty("content_index", out var ci) ? ci.GetInt32() : -1;
        return $"{outputIdx}:{contentIdx}";
    }

    private enum StreamState
    {
        Initial,
        Created,
        Queued,
        InProgress,
        Terminal,
    }
}

/// <summary>A single validation violation.</summary>
/// <param name="RuleId">The rule identifier (e.g. SEQ-01, FIELD-02).</param>
/// <param name="Message">Human-readable description of the violation.</param>
/// <param name="EventIndex">1-based index of the event that triggered this violation.</param>
internal sealed record ValidationViolation(string RuleId, string Message, int EventIndex);

/// <summary>Overall validation result.</summary>
/// <param name="EventCount">Total number of events processed.</param>
/// <param name="IsValid">True if no violations were found.</param>
/// <param name="Violations">List of all violations.</param>
internal sealed record ValidationResult(int EventCount, bool IsValid, IReadOnlyList<ValidationViolation> Violations);
