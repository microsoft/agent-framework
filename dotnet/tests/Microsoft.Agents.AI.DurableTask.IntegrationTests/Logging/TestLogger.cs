// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.DurableTask.IntegrationTests.Logging;

internal sealed class TestLogger(string category, ITestOutputHelper output) : ILogger
{
    private readonly string _category = category;
    private readonly ITestOutputHelper _output = output;
    private readonly ConcurrentQueue<LogEntry> _entries = new();

    public IReadOnlyCollection<LogEntry> GetLogs() => this._entries;

    public void ClearLogs() => this._entries.Clear();

    IDisposable? ILogger.BeginScope<TState>(TState state) => null;

    bool ILogger.IsEnabled(LogLevel logLevel) => true;

    void ILogger.Log<TState>(
        LogLevel logLevel,
        EventId eventId,
        TState state,
        Exception? exception,
        Func<TState, Exception?, string> formatter)
    {
        LogEntry entry = new(
            category: this._category,
            level: logLevel,
            eventId: eventId,
            exception: exception,
            message: formatter(state, exception),
            state: state,
            contextProperties: []);

        this._entries.Enqueue(entry);

        try
        {
            this._output.WriteLine(entry.ToString());
        }
        catch (InvalidOperationException)
        {
            // Expected when tests are shutting down
        }
    }
}
