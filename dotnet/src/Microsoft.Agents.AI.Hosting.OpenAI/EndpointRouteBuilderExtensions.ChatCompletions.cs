// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using OpenAI.Chat;

namespace Microsoft.Agents.AI.Hosting.OpenAI;

public static partial class EndpointRouteBuilderExtensions
{
    /// <summary>
    /// Maps OpenAI ChatCompletions API endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI ChatCompletions endpoints to.</param>
    /// <param name="agentName">The name of the AI agent service registered in the dependency injection container. This name is used to resolve the <see cref="AIAgent"/> instance from the keyed services.</param>
    /// <param name="path">Custom route path for the chat completions endpoint.</param>
    public static void MapOpenAIChatCompletions(
        this IEndpointRouteBuilder endpoints,
        string agentName,
        [StringSyntax("Route")] string? path = null)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agentName);
        if (path is null)
        {
            ValidateAgentName(agentName);
        }

        var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName);

        path ??= $"/{agentName}/v1/chat/completions";
        var chatCompletionsRouteGroup = endpoints.MapGroup(path);
        MapChatCompletions(chatCompletionsRouteGroup, agent);
    }

    private static void MapChatCompletions(IEndpointRouteBuilder routeGroup, AIAgent agent)
    {
        var endpointAgentName = agent.DisplayName;
        var chatCompletionsProcessor = new AIAgentChatCompletionsProcessor(agent);

        routeGroup.MapPost("/", async (HttpContext requestContext, CancellationToken cancellationToken) =>
        {
            var requestBinary = await BinaryData.FromStreamAsync(requestContext.Request.Body, cancellationToken).ConfigureAwait(false);

            var chatCompletionOptions = new ChatCompletionOptions();
            var chatCompletionOptionsJsonModel = chatCompletionOptions as IJsonModel<ChatCompletionOptions>;
            Debug.Assert(chatCompletionOptionsJsonModel is not null);

            chatCompletionOptions = chatCompletionOptionsJsonModel.Create(requestBinary, ModelReaderWriterOptions.Json);
            if (chatCompletionOptions is null)
            {
                return Results.BadRequest("Invalid request payload.");
            }

            return await chatCompletionsProcessor.CreateChatCompletionAsync(chatCompletionOptions, cancellationToken).ConfigureAwait(false);
        }).WithName(endpointAgentName + "/CreateChatCompletion");
    }
}
