using Microsoft.Extensions.Options;

namespace Azure.AI.AgentsHosting.Ingress.Common;

public class SingletonOptionsMonitor<TOptions>(TOptions options) : IOptionsMonitor<TOptions>, IOptionsSnapshot<TOptions>
    where TOptions : class
{
    public TOptions Get(string? name) => this.CurrentValue;

    public IDisposable? OnChange(Action<TOptions, string?> listener)
    {
        return NoopChangeNotification.Instance;
    }

    public TOptions CurrentValue { get; } = options;

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
