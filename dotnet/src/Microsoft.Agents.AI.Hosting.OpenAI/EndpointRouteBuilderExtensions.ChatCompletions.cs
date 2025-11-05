// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.AspNetCore.Builder;

public static partial class MicrosoftAgentAIHostingOpenAIEndpointRouteBuilderExtensions
{
    /// <summary>
    /// Maps OpenAI ChatCompletions API endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI ChatCompletions endpoints to.</param>
    /// <param name="agentBuilder">The builder for <see cref="AIAgent"/> to map the OpenAI ChatCompletions endpoints for.</param>
    public static IEndpointConventionBuilder MapOpenAIChatCompletions(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder)
        => MapOpenAIChatCompletions(endpoints, agentBuilder, path: null);

    /// <summary>
    /// Maps OpenAI ChatCompletions API endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI ChatCompletions endpoints to.</param>
    /// <param name="agentBuilder">The builder for <see cref="AIAgent"/> to map the OpenAI ChatCompletions endpoints for.</param>
    /// <param name="path">Custom route path for the chat completions endpoint.</param>
    public static IEndpointConventionBuilder MapOpenAIChatCompletions(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, string? path)
    {
        var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentBuilder.Name);
        return MapOpenAIChatCompletions(endpoints, agent, path);
    }

    /// <summary>
    /// Maps OpenAI ChatCompletions API endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI ChatCompletions endpoints to.</param>
    /// <param name="agent">The <see cref="AIAgent"/> instance to map the OpenAI ChatCompletions endpoints for.</param>
    public static IEndpointConventionBuilder MapOpenAIChatCompletions(this IEndpointRouteBuilder endpoints, AIAgent agent)
        => MapOpenAIChatCompletions(endpoints, agent, path: null);

    /// <summary>
    /// Maps OpenAI ChatCompletions API endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI ChatCompletions endpoints to.</param>
    /// <param name="agent">The <see cref="AIAgent"/> instance to map the OpenAI ChatCompletions endpoints for.</param>
    /// <param name="path">Custom route path for the chat completions endpoint.</param>
    public static IEndpointConventionBuilder MapOpenAIChatCompletions(
        this IEndpointRouteBuilder endpoints,
        AIAgent agent,
        [StringSyntax("Route")] string? path)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrWhiteSpace(agent.Name, nameof(agent.Name));
        ValidateAgentName(agent.Name);

        path ??= $"/{agent.Name}/v1/chat/completions";
        var group = endpoints.MapGroup(path);
        var endpointAgentName = agent.DisplayName;

        group.MapPost("/", async ([FromBody] CreateChatCompletion request, CancellationToken cancellationToken)
            => await AIAgentChatCompletionsProcessor.CreateChatCompletionAsync(agent, request, cancellationToken).ConfigureAwait(false))
            .WithName(endpointAgentName + "/CreateChatCompletion");

        return group;
    }
}
