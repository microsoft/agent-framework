using System;
using System.Diagnostics.CodeAnalysis;

using Microsoft.Extensions.Options;

namespace Azure.AI.AgentsHosting.Ingress.Common;

/// <summary>
/// A singleton implementation of options monitor that returns a fixed options value.
/// </summary>
/// <typeparam name="TOptions">The type of options being monitored.</typeparam>
/// <param name="options">The options instance to return.</param>
public class SingletonOptionsMonitor<[DynamicallyAccessedMembers(DynamicallyAccessedMemberTypes.PublicParameterlessConstructor)] TOptions>(TOptions options) : IOptionsMonitor<TOptions>, IOptionsSnapshot<TOptions>
    where TOptions : class
{
    /// <inheritdoc/>
    public TOptions Get(string? name) => this.CurrentValue;

    /// <inheritdoc/>
    public IDisposable? OnChange(Action<TOptions, string?> listener)
    {
        return NoopChangeNotification.Instance;
    }

    /// <inheritdoc/>
    public TOptions CurrentValue { get; } = options;

    /// <inheritdoc/>
    public TOptions Value => this.CurrentValue;

    private sealed class NoopChangeNotification : IDisposable
    {
        private NoopChangeNotification()
        {
        }

        public static NoopChangeNotification Instance { get; } = new();

        public void Dispose()
        {
        }
    }
}
