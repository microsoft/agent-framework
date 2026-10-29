// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Foundry.UnitTests.Hosting;

/// <summary>Captures what the system under test reported, so a test can assert on it.</summary>
internal sealed class RecordingLoggerFactory : ILoggerFactory
{
    public List<(LogLevel Level, string Message, Exception? Exception)> Entries { get; } = [];

    public ILogger CreateLogger(string categoryName) => new RecordingLogger(this.Entries);

    public void AddProvider(ILoggerProvider provider)
    {
    }

    public void Dispose()
    {
    }

    private sealed class RecordingLogger(List<(LogLevel Level, string Message, Exception? Exception)> entries) : ILogger
    {
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

        public bool IsEnabled(LogLevel logLevel) => true;

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
            => entries.Add((logLevel, formatter(state, exception), exception));
    }
}
