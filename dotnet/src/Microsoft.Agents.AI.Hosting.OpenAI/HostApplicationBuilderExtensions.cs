// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.AspNetCore.Http.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.OpenAI;

/// <summary>
/// Extension methods for <see cref="IHostApplicationBuilder"/> to configure OpenAI Responses support.
/// </summary>
public static class HostApplicationBuilderExtensions
{
    /// <summary>
    /// Adds support for exposing <see cref="AIAgent"/> instances via OpenAI Responses.
    /// </summary>
    /// <param name="builder">The <see cref="IHostApplicationBuilder"/> to configure.</param>
    /// <returns>The <see cref="IHostApplicationBuilder"/> for method chaining.</returns>
    public static IHostApplicationBuilder AddOpenAIResponses(this IHostApplicationBuilder builder)
    {
        ArgumentNullException.ThrowIfNull(builder);

        builder.Services.Configure<JsonOptions>(options => options.SerializerOptions.TypeInfoResolverChain.Add(ResponsesJsonSerializerOptions.Default.TypeInfoResolver!));

        return builder;
    }
}
