// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.AspNetCore.Http.Json;

namespace Microsoft.Extensions.DependencyInjection;

/// <summary>
/// Extension methods for <see cref="IServiceCollection"/> to configure OpenAI support.
/// </summary>
public static class MicrosoftAgentAIHostingOpenAIServiceCollectionExtensions
{
    /// <summary>
    /// Adds support for exposing <see cref="AIAgent"/> instances via OpenAI ChatCompletions.
    /// </summary>
    /// <param name="services">The <see cref="IServiceCollection"/> to configure.</param>
    /// <returns>The <see cref="IServiceCollection"/> for method chaining.</returns>
    public static IServiceCollection AddOpenAIChatCompletions(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);

        services.Configure<JsonOptions>(options => options.SerializerOptions.TypeInfoResolverChain.Add(ChatCompletionsJsonSerializerOptions.Default.TypeInfoResolver!));

        return services;
    }

    /// <summary>
    /// Adds support for exposing <see cref="AIAgent"/> instances via OpenAI Responses.
    /// </summary>
    /// <param name="services">The <see cref="IServiceCollection"/> to configure.</param>
    /// <returns>The <see cref="IServiceCollection"/> for method chaining.</returns>
    public static IServiceCollection AddOpenAIResponses(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);

        services.Configure<JsonOptions>(options => options.SerializerOptions.TypeInfoResolverChain.Add(ResponsesJsonSerializerOptions.Default.TypeInfoResolver!));

        return services;
    }
}
