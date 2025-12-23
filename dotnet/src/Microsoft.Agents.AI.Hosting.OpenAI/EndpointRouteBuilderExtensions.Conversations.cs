// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.AspNetCore.Builder;

/// <summary>
/// Provides extension methods for mapping OpenAI Conversations API to an <see cref="IEndpointRouteBuilder"/>.
/// </summary>
public static partial class MicrosoftAgentAIHostingOpenAIEndpointRouteBuilderExtensions
{
    /// <summary>
    /// Maps OpenAI Conversations API endpoints to the specified <see cref="IEndpointRouteBuilder"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI Conversations endpoints to.</param>
    public static IEndpointConventionBuilder MapOpenAIConversations(this IEndpointRouteBuilder endpoints)
    {
        ArgumentNullException.ThrowIfNull(endpoints);

        var storage = endpoints.ServiceProvider.GetService<IConversationStorage>()
            ?? throw new InvalidOperationException("IConversationStorage is not registered. Call AddOpenAIConversations() in your service configuration.");
        var conversationIndex = endpoints.ServiceProvider.GetService<IAgentConversationIndex>();
        var handlers = new ConversationsHttpHandler(storage, conversationIndex);

        var group = endpoints.MapGroup("/v1/conversations")
            .WithTags("Conversations");

        // Conversation endpoints
        // Non-standard extension: List conversations by agent ID
        group.MapGet("", handlers.ListConversationsByAgentAsync)
            .WithName("ListConversationsByAgent")
            .WithSummary("List conversations for a specific agent (non-standard extension)");

        group.MapPost("", handlers.CreateConversationAsync)
            .WithName("CreateConversation")
            .WithSummary("Create a new conversation");

        group.MapGet("{conversationId}", handlers.GetConversationAsync)
            .WithName("GetConversation")
            .WithSummary("Retrieve a conversation by ID");

        group.MapPost("{conversationId}", handlers.UpdateConversationAsync)
            .WithName("UpdateConversation")
            .WithSummary("Update a conversation's metadata or title");

        group.MapDelete("{conversationId}", handlers.DeleteConversationAsync)
            .WithName("DeleteConversation")
            .WithSummary("Delete a conversation and all its messages");

        // Item endpoints
        group.MapPost("{conversationId}/items", handlers.CreateItemsAsync)
            .WithName("CreateItems")
            .WithSummary("Add items to a conversation");

        group.MapGet("{conversationId}/items", handlers.ListItemsAsync)
            .WithName("ListItems")
            .WithSummary("List items in a conversation");

        group.MapGet("{conversationId}/items/{itemId}", handlers.GetItemAsync)
            .WithName("GetItem")
            .WithSummary("Retrieve a specific item");

        group.MapDelete("{conversationId}/items/{itemId}", handlers.DeleteItemAsync)
            .WithName("DeleteItem")
            .WithSummary("Delete a specific item");

        return group;
    }
}
