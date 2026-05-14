// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Purview.Models.Common;
using Microsoft.Agents.AI.Purview.Models.Jobs;
using Microsoft.Agents.AI.Purview.Models.Responses;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Service that runs jobs in background threads.
/// </summary>
internal sealed class BackgroundJobRunner : IBackgroundJobRunner
{
    private readonly IChannelHandler _channelHandler;
    private readonly IPurviewClient _purviewClient;
    private readonly ICacheProvider _cacheProvider;
    private readonly ILogger _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="BackgroundJobRunner"/> class.
    /// </summary>
    /// <param name="channelHandler">The channel handler used to manage job channels.</param>
    /// <param name="purviewClient">The Purview client used to send requests to Purview.</param>
    /// <param name="cacheProvider">The cache provider used to store protection scopes results.</param>
    /// <param name="logger">The logger used to log information about background jobs.</param>
    /// <param name="purviewSettings">The settings used to configure Purview client behavior.</param>
    public BackgroundJobRunner(IChannelHandler channelHandler, IPurviewClient purviewClient, ICacheProvider cacheProvider, ILogger logger, PurviewSettings purviewSettings)
    {
        this._channelHandler = channelHandler;
        this._purviewClient = purviewClient;
        this._cacheProvider = cacheProvider;
        this._logger = logger;

        for (int i = 0; i < purviewSettings.MaxConcurrentJobConsumers; i++)
        {
            this._channelHandler.AddRunner(async (Channel<BackgroundJobBase> channel) =>
            {
                await foreach (BackgroundJobBase job in channel.Reader.ReadAllAsync().ConfigureAwait(false))
                {
                    try
                    {
                        await this.RunJobAsync(job).ConfigureAwait(false);
                    }
                    catch (Exception e) when (e is not OperationCanceledException and not SystemException)
                    {
                        if (this._logger.IsEnabled(LogLevel.Error))
                        {
                            this._logger.LogError(e, "Error running background job {BackgroundJobError}.", e.Message);
                        }
                    }
                }
            });
        }
    }

    /// <summary>
    /// Runs a job.
    /// </summary>
    /// <param name="job">The job to run.</param>
    /// <returns>A task representing the job.</returns>
    private async Task RunJobAsync(BackgroundJobBase job)
    {
        switch (job)
        {
            case ProcessContentJob processContentJob:
                _ = await this._purviewClient.ProcessContentAsync(processContentJob.Request, CancellationToken.None).ConfigureAwait(false);
                break;
            case ContentActivityJob contentActivityJob:
                _ = await this._purviewClient.SendContentActivitiesAsync(contentActivityJob.Request, CancellationToken.None).ConfigureAwait(false);
                break;
            case ScopeRetrievalJob scopeRetrievalJob:
                try
                {
                    ProtectionScopesResponse response = await this._purviewClient.GetProtectionScopesAsync(scopeRetrievalJob.Request, CancellationToken.None).ConfigureAwait(false);
                    await this.SetCacheBestEffortAsync(scopeRetrievalJob.CacheKey, response, "protection scopes").ConfigureAwait(false);
                }
                catch (PurviewPaymentRequiredException ex)
                {
                    await this.SetCacheBestEffortAsync(
                        new PaymentRequiredCacheKey(scopeRetrievalJob.Request.TenantId),
                        new PaymentRequiredCacheEntry(ex.Message),
                        "payment required state").ConfigureAwait(false);
                }

                break;
        }
    }

    private async Task SetCacheBestEffortAsync<TKey, TValue>(TKey key, TValue value, string cacheEntryName)
    {
        try
        {
            await this._cacheProvider.SetAsync(key, value, CancellationToken.None).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            if (this._logger.IsEnabled(LogLevel.Warning))
            {
                this._logger.LogWarning(ex, "Failed to cache {CacheEntryName} for background scope retrieval.", cacheEntryName);
            }
        }
    }

    /// <summary>
    /// Shutdown the job runners.
    /// </summary>
    public async Task ShutdownAsync()
    {
        await this._channelHandler.StopAndWaitForCompletionAsync().ConfigureAwait(false);
    }
}
