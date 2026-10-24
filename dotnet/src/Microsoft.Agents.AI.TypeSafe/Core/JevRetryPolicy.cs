// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Globalization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// The default retry policy of the Jev clients, with the defaults of the official TypeSafe SDK
/// (<c>DEFAULT_RETRY_POLICY</c> in <c>retry.ts</c>).
/// </summary>
/// <remarks>
/// <list type="bullet">
/// <item><description>Up to <see cref="DefaultMaxRetries"/> retries after the first attempt.</description></item>
/// <item><description>
/// A server delay from <c>retry-after-ms</c> or <c>Retry-After</c> is honored up to <see cref="MaxRetryAfter"/>.
/// A longer delay falls back to backoff, because waiting it would block the agent run with no feedback.
/// </description></item>
/// <item><description>
/// Otherwise the delay is an exponential backoff from <see cref="InitialBackoff"/>, capped at <see cref="MaxBackoff"/>,
/// minus up to <see cref="BackoffJitter"/> of random jitter so that concurrent callers do not retry in lockstep.
/// </description></item>
/// </list>
/// Which statuses are retried is decided by <see cref="JevResponseClassifier"/>.
/// </remarks>
internal sealed class JevRetryPolicy : ClientRetryPolicy
{
    public const int DefaultMaxRetries = 2;
    public const double BackoffJitter = 0.25;

    public static readonly TimeSpan InitialBackoff = TimeSpan.FromMilliseconds(500);
    public static readonly TimeSpan MaxBackoff = TimeSpan.FromSeconds(5);
    public static readonly TimeSpan MaxRetryAfter = TimeSpan.FromMinutes(1);

    public JevRetryPolicy(int maxRetries = DefaultMaxRetries, bool enableLogging = true, ILoggerFactory? loggerFactory = null)
        : base(maxRetries, enableLogging, loggerFactory)
    {
    }

    /// <summary>
    /// Gets or sets a list that, when set, receives each delay instead of waiting it, so tests can check the delays
    /// without being slowed down by them.
    /// </summary>
    internal List<TimeSpan>? RecordedWaitsForTests { get; set; }

    protected override TimeSpan GetNextDelay(PipelineMessage message, int tryCount)
    {
        if (TryGetServerDelayMilliseconds(message.Response, out double serverDelay) && serverDelay <= MaxRetryAfter.TotalMilliseconds)
        {
            return TimeSpan.FromMilliseconds(serverDelay);
        }

        // tryCount is 1 for the first retry, matching attempt 0 of the SDK's retryDelayMs.
        double exponential = Math.Min(InitialBackoff.TotalMilliseconds * Math.Pow(2, tryCount - 1), MaxBackoff.TotalMilliseconds);
#pragma warning disable CA5394 // Jitter only spreads retries over time; it needs no cryptographic randomness.
        double jitter = Random.Shared.NextDouble() * BackoffJitter;
#pragma warning restore CA5394
        return TimeSpan.FromMilliseconds(Math.Round(exponential * (1 - jitter)));
    }

    protected override Task WaitAsync(TimeSpan time, CancellationToken cancellationToken)
    {
        if (this.RecordedWaitsForTests is { } waits)
        {
            waits.Add(time);
            return Task.CompletedTask;
        }

        return base.WaitAsync(time, cancellationToken);
    }

    protected override void Wait(TimeSpan time, CancellationToken cancellationToken)
    {
        if (this.RecordedWaitsForTests is { } waits)
        {
            waits.Add(time);
            return;
        }

        base.Wait(time, cancellationToken);
    }

    /// <summary>
    /// Reads <c>retry-after-ms</c>, preferred, or <c>Retry-After</c> in seconds or as an HTTP date, like the SDK's
    /// <c>parseRetryAfter</c>, as a number of milliseconds.
    /// </summary>
    /// <remarks>
    /// The delay stays a <see cref="double"/> until it is compared with <see cref="MaxRetryAfter"/>: a huge value such as
    /// <c>1e300</c> or the text <c>NaN</c> would make <see cref="TimeSpan"/> throw and fail the call, where the SDK
    /// simply backs off.
    /// </remarks>
    private static bool TryGetServerDelayMilliseconds(PipelineResponse? response, out double delay)
    {
        delay = 0;
        if (response is null)
        {
            return false;
        }

        if (response.Headers.TryGetValue("retry-after-ms", out string? milliseconds) &&
            double.TryParse(milliseconds, NumberStyles.Float, CultureInfo.InvariantCulture, out double ms) &&
            double.IsFinite(ms) && ms >= 0)
        {
            delay = ms;
            return true;
        }

        if (!response.Headers.TryGetValue("Retry-After", out string? retryAfter) || string.IsNullOrWhiteSpace(retryAfter))
        {
            return false;
        }

        if (double.TryParse(retryAfter, NumberStyles.Float, CultureInfo.InvariantCulture, out double seconds))
        {
            if (!double.IsFinite(seconds) || seconds < 0)
            {
                return false;
            }

            delay = seconds * 1000;
            return double.IsFinite(delay);
        }

        if (DateTimeOffset.TryParse(retryAfter, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out DateTimeOffset date))
        {
            delay = Math.Max(0, (date - DateTimeOffset.UtcNow).TotalMilliseconds);
            return true;
        }

        return false;
    }
}
