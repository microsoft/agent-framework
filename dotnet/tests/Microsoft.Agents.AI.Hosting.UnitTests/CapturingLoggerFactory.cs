// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// A minimal <see cref="ILoggerFactory"/> that captures every log entry it produces, for asserting on
/// diagnostics emitted by the system under test.
/// </summary>
internal sealed class CapturingLoggerFactory : ILoggerFactory
{
    public List<(LogLevel Level, string Message)> Entries { get; } = [];

    public ILogger CreateLogger(string categoryName) => new CapturingLogger(this.Entries);

    public void AddProvider(ILoggerProvider provider)
    {
        // No-op: this factory always produces capturing loggers.
    }

    public void Dispose()
    {
        // No-op.
    }

    private sealed class CapturingLogger(List<(LogLevel Level, string Message)> entries) : ILogger
    {
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

        public bool IsEnabled(LogLevel logLevel) => true;

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
            => entries.Add((logLevel, formatter(state, exception)));
    }
}
