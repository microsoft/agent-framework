// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Purview.Models.Jobs;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Purview;
internal sealed class BackgroundJobRunner
{
    private readonly IChannelHandler _channelHandler;
    private readonly IPurviewClient _purviewClient;
    private readonly ILogger _logger;

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
                    catch (Exception e)
                    {
                        this._logger.LogError(e, "Error running background job {BackgroundJobError}.", e.Message);
                    }
                }
            });
        }
    }

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
