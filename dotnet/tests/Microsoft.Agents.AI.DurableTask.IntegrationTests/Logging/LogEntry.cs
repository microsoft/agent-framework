// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.DurableTask.IntegrationTests.Logging;

internal sealed class LogEntry(
    string category,
    LogLevel level,
    EventId eventId,
    Exception? exception,
    string message,
    object? state,
    IReadOnlyList<KeyValuePair<string, object?>> contextProperties)
{
    public string Category { get; } = category;

    public DateTime Timestamp { get; } = DateTime.Now;

    public EventId EventId { get; } = eventId;

    public LogLevel LogLevel { get; } = level;

    public Exception? Exception { get; } = exception;

    public string Message { get; } = message;

    public object? State { get; } = state;

    public IReadOnlyList<KeyValuePair<string, object?>> ContextProperties { get; } = contextProperties;

    public override string ToString()
    {
        string properties = this.ContextProperties.Count > 0
            ? $"[{string.Join(", ", this.ContextProperties.Select(kvp => $"{kvp.Key}={kvp.Value}"))}] "
            : string.Empty;

        string eventName = this.EventId.Name ?? string.Empty;
        string output = $"{this.Timestamp:o} [{this.Category}] {eventName} {properties}{this.Message}";

        if (this.Exception is not null)
        {
            output += Environment.NewLine + this.Exception;
        }

        return output;
    }
}
