// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Purview.Models.Jobs;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Service that runs jobs in background threads.
/// </summary>
internal sealed class BackgroundJobRunner
{
    private readonly IChannelHandler _channelHandler;
    private readonly IPurviewClient _purviewClient;
    private readonly ILogger _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="BackgroundJobRunner"/> class.
    /// </summary>
    /// <param name="channelHandler">The channel handler used to manage job channels.</param>
    /// <param name="purviewClient">The Purview client used to send requests to Purview.</param>
    /// <param name="logger">The logger used to log information about background jobs.</param>
    /// <param name="purviewSettings">The settings used to configure Purview client behavior.</param>
    public BackgroundJobRunner(IChannelHandler channelHandler, IPurviewClient purviewClient, ILogger logger, PurviewSettings purviewSettings)
    {
        this._channelHandler = channelHandler;
        this._purviewClient = purviewClient;
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
                    catch (Exception e) when (
                        !(e is OperationCanceledException) &&
                        !(e is SystemException))
                    {
                        this._logger.LogError(e, "Error running background job {BackgroundJobError}.", e.Message);
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
        }
    }
}
