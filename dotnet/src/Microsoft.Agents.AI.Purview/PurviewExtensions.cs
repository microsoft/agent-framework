// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net.Http;
using System.Threading.Channels;
using Azure.Core;
using Microsoft.Agents.AI.Purview.Models.Jobs;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Caching.Distributed;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Extension methods to add Purview capabilities to an <see cref="AIAgent"/>.
/// </summary>
public static class PurviewExtensions
{
    private static PurviewWrapper CreateWrapper(TokenCredential tokenCredential, PurviewSettings purviewSettings, ILogger? logger = null, IDistributedCache? cache = null)
    {
        MemoryDistributedCacheOptions options = new()
        {
            SizeLimit = purviewSettings.InMemoryCacheSizeLimit,
        };

        IDistributedCache distributedCache = cache ?? new MemoryDistributedCache(Options.Create(options));

        ServiceCollection services = new();
        services.AddSingleton(tokenCredential);
        services.AddSingleton(purviewSettings);
        services.AddSingleton<IPurviewClient, PurviewClient>();
        services.AddSingleton<IScopedContentProcessor, ScopedContentProcessor>();
        services.AddSingleton(distributedCache);
        services.AddSingleton<ICacheProvider, CacheProvider>();
        services.AddSingleton<HttpClient>();
        services.AddSingleton(logger ?? NullLogger.Instance);
        services.AddSingleton<PurviewWrapper>();
        services.AddSingleton(Channel.CreateBounded<BackgroundJobBase>(purviewSettings.PendingBackgroundJobLimit));
        services.AddSingleton<IChannelHandler, ChannelHandler>();
        services.AddSingleton<BackgroundJobRunner>();
        ServiceProvider serviceProvider = services.BuildServiceProvider();

        return serviceProvider.GetRequiredService<PurviewWrapper>();
    }

    /// <summary>
    /// Adds Purview capabilities to an <see cref="AIAgentBuilder"/>.
    /// </summary>
    /// <param name="builder">The AI Agent builder for the <see cref="AIAgent"/>.</param>
    /// <param name="tokenCredential">The token credential used to authenticate with Purview.</param>
    /// <param name="purviewSettings">The settings for communication with Purview.</param>
    /// <param name="logger">The logger to use for logging.</param>
    /// <param name="cache">The distributed cache to use for caching Purview responses. An in memory cache will be used if this is null.</param>
    /// <returns>The updated <see cref="AIAgentBuilder"/></returns>
    public static AIAgentBuilder WithPurview(this AIAgentBuilder builder, TokenCredential tokenCredential, PurviewSettings purviewSettings, ILogger? logger = null, IDistributedCache? cache = null)
    {
        PurviewWrapper purviewWrapper = CreateWrapper(tokenCredential, purviewSettings, logger, cache);
        return builder.Use((innerAgent) => new PurviewAgent(innerAgent, purviewWrapper));
    }

    /// <summary>
    /// Adds Purview capabilities to a <see cref="ChatClientBuilder"/>.
    /// </summary>
    /// <param name="builder">The chat client builder for the <see cref="IChatClient"/>.</param>
    /// <param name="tokenCredential">The token credential used to authenticate with Purview.</param>
    /// <param name="purviewSettings">The settings for communication with Purview.</param>
    /// <param name="logger">The logger to use for logging.</param>
    /// <param name="cache">The distributed cache to use for caching Purview responses. An in memory cache will be used if this is null.</param>
    /// <returns>The updated <see cref="ChatClientBuilder"/></returns>
    public static ChatClientBuilder WithPurview(this ChatClientBuilder builder, TokenCredential tokenCredential, PurviewSettings purviewSettings, ILogger? logger = null, IDistributedCache? cache = null)
    {
        PurviewWrapper purviewWrapper = CreateWrapper(tokenCredential, purviewSettings, logger, cache);
        return builder.Use((innerChatClient) => new PurviewChatClient(innerChatClient, purviewWrapper));
    }

    /// <summary>
    /// Creates a Purview middleware function for use with a <see cref="IChatClient"/>.
    /// </summary>
    /// <param name="tokenCredential">The token credential used to authenticate with Purview.</param>
    /// <param name="purviewSettings">The settings for communication with Purview.</param>
    /// <param name="logger">The logger to use for logging.</param>
    /// <param name="cache">The distributed cache to use for caching Purview responses. An in memory cache will be used if this is null.</param>
    /// <returns>A chat middleware delegate.</returns>
    public static Func<IChatClient, IChatClient> PurviewChatMiddleware(TokenCredential tokenCredential, PurviewSettings purviewSettings, ILogger? logger = null, IDistributedCache? cache = null)
    {
        PurviewWrapper purviewWrapper = CreateWrapper(tokenCredential, purviewSettings, logger, cache);
        return (innerChatClient) => new PurviewChatClient(innerChatClient, purviewWrapper);
    }

    /// <summary>
    /// Creates a Purview middleware function for use with an <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="tokenCredential">The token credential used to authenticate with Purview.</param>
    /// <param name="purviewSettings">The settings for communication with Purview.</param>
    /// <param name="logger">The logger to use for logging.</param>
    /// <param name="cache">The distributed cache to use for caching Purview responses. An in memory cache will be used if this is null.</param>
    /// <returns>An agent middleware delegate.</returns>
    public static Func<AIAgent, AIAgent> PurviewAgentMiddleware(TokenCredential tokenCredential, PurviewSettings purviewSettings, ILogger? logger = null, IDistributedCache? cache = null)
    {
        PurviewWrapper purviewWrapper = CreateWrapper(tokenCredential, purviewSettings, logger, cache);
        return (innerAgent) => new PurviewAgent(innerAgent, purviewWrapper);
    }

    /// <summary>
    /// Sets the user id for a message.
    /// </summary>
    /// <param name="message">The message.</param>
    /// <param name="userId">The id of the owner of the message.</param>
    public static void SetUserId(this ChatMessage message, Guid userId)
    {
        message.AdditionalProperties ??= [];
        message.AdditionalProperties[Constants.UserId] = userId.ToString();
    }
}
