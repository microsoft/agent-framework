// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Routing;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations;

/// <summary>
/// Minimal API endpoints for OpenAI Conversations API.
/// </summary>
public static class ConversationsHttpApi
{
    /// <summary>
    /// Maps an OpenAI Conversations API to the specified <see cref="IEndpointRouteBuilder"/>.
    /// </summary>
    public static IEndpointConventionBuilder MapConversations(this IEndpointRouteBuilder endpoints)
    {
        var group = endpoints.MapGroup("/v1/conversations")
            .WithTags("Conversations");

        // Conversation endpoints
        // Non-standard extension: List conversations by agent ID
        group.MapGet("", ListConversationsByAgentAsync)
            .WithName("ListConversationsByAgent")
            .WithSummary("List conversations for a specific agent (non-standard extension)");

        group.MapPost("", CreateConversationAsync)
            .WithName("CreateConversation")
            .WithSummary("Create a new conversation");

        group.MapGet("{conversationId}", GetConversationAsync)
            .WithName("GetConversation")
            .WithSummary("Retrieve a conversation by ID");

        group.MapPost("{conversationId}", UpdateConversationAsync)
            .WithName("UpdateConversation")
            .WithSummary("Update a conversation's metadata or title");

        group.MapDelete("{conversationId}", DeleteConversationAsync)
            .WithName("DeleteConversation")
            .WithSummary("Delete a conversation and all its messages");

        // Item endpoints
        group.MapPost("{conversationId}/items", CreateItemsAsync)
            .WithName("CreateItems")
            .WithSummary("Add items to a conversation");

        group.MapGet("{conversationId}/items", ListItemsAsync)
            .WithName("ListItems")
            .WithSummary("List items in a conversation");

        group.MapGet("{conversationId}/items/{itemId}", GetItemAsync)
            .WithName("GetItem")
            .WithSummary("Retrieve a specific item");

        group.MapDelete("{conversationId}/items/{itemId}", DeleteItemAsync)
            .WithName("DeleteItem")
            .WithSummary("Delete a specific item");

        return group;
    }

    // Non-standard extension: List conversations by agent ID
    private static async Task<IResult> ListConversationsByAgentAsync(
        [FromQuery] string? agent_id,
        [FromServices] IAgentConversationIndex? conversationIndex,
        [FromServices] IConversationStorage storage,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrEmpty(agent_id))
        {
            return Results.BadRequest(new ErrorResponse
            {
                Error = new ErrorDetails
                {
                    Message = "agent_id query parameter is required.",
                    Type = "invalid_request_error"
                }
            });
        }

        // Return empty list if conversation index is not registered
        if (conversationIndex == null)
        {
            return Results.Ok(new ConversationListResponse
            {
                Data = [],
                HasMore = false
            });
        }

        var conversationIds = await conversationIndex.GetConversationIdsAsync(agent_id, cancellationToken).ConfigureAwait(false);

        // Fetch full conversation objects
        var conversations = new List<Conversation>();
        foreach (var conversationId in conversationIds)
        {
            var conversation = await storage.GetConversationAsync(conversationId, cancellationToken).ConfigureAwait(false);
            if (conversation is not null)
            {
                conversations.Add(conversation);
            }
        }

        return Results.Ok(new ConversationListResponse
        {
            Data = conversations,
            HasMore = false
        });
    }

    private static async Task<IResult> CreateConversationAsync(
        [FromBody] CreateConversationRequest request,
        [FromServices] IConversationStorage storage,
        [FromServices] IAgentConversationIndex? conversationIndex,
        CancellationToken cancellationToken)
    {
        var metadata = request.Metadata ?? [];
        var conversation = new Conversation
        {
            Id = $"conv_{Guid.NewGuid():N}",
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = metadata
        };

        var created = await storage.CreateConversationAsync(conversation, cancellationToken).ConfigureAwait(false);

        // Add initial items if provided
        if (request.Items is { Length: > 0 })
        {
            foreach (var item in request.Items)
            {
                var itemToAdd = item with
                {
                    Id = $"msg_{Guid.NewGuid():N}",
                    ConversationId = created.Id,
                    CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds()
                };
                await storage.AddItemAsync(itemToAdd, cancellationToken).ConfigureAwait(false);
            }
        }

        // Add to conversation index if available and agent_id is provided in metadata
        if (conversationIndex != null && created.Metadata.TryGetValue("agent_id", out var agentId) && !string.IsNullOrEmpty(agentId))
        {
            await conversationIndex.AddConversationAsync(agentId, created.Id, cancellationToken).ConfigureAwait(false);
        }

        return Results.Ok(created);
    }

    private static async Task<IResult> GetConversationAsync(
        string conversationId,
        [FromServices] IConversationStorage storage,
        CancellationToken cancellationToken)
    {
        var conversation = await storage.GetConversationAsync(conversationId, cancellationToken).ConfigureAwait(false);
        return conversation is not null
            ? Results.Ok(conversation)
            : Results.NotFound(new ErrorResponse
            {
                Error = new ErrorDetails
                {
                    Message = $"Conversation '{conversationId}' not found.",
                    Type = "invalid_request_error"
                }
            });
    }

    private static async Task<IResult> UpdateConversationAsync(
        string conversationId,
        [FromBody] UpdateConversationRequest request,
        [FromServices] IConversationStorage storage,
        CancellationToken cancellationToken)
    {
        var existing = await storage.GetConversationAsync(conversationId, cancellationToken).ConfigureAwait(false);
        if (existing is null)
        {
            return Results.NotFound(new ErrorResponse
            {
                Error = new ErrorDetails
                {
                    Message = $"Conversation '{conversationId}' not found.",
                    Type = "invalid_request_error"
                }
            });
        }

        var updated = existing with
        {
            Metadata = request.Metadata
        };

        var result = await storage.UpdateConversationAsync(updated, cancellationToken).ConfigureAwait(false);
        return Results.Ok(result);
    }

    private static async Task<IResult> DeleteConversationAsync(
        string conversationId,
        [FromServices] IConversationStorage storage,
        [FromServices] IAgentConversationIndex? conversationIndex,
        CancellationToken cancellationToken)
    {
        // Get conversation first to retrieve agent_id for index removal
        var conversation = await storage.GetConversationAsync(conversationId, cancellationToken).ConfigureAwait(false);

        var deleted = await storage.DeleteConversationAsync(conversationId, cancellationToken).ConfigureAwait(false);
        if (!deleted)
        {
            return Results.NotFound(new ErrorResponse
            {
                Error = new ErrorDetails
                {
                    Message = $"Conversation '{conversationId}' not found.",
                    Type = "invalid_request_error"
                }
            });
        }

        // Remove from conversation index if available and agent_id was present in metadata
        if (conversationIndex != null && conversation?.Metadata.TryGetValue("agent_id", out var agentId) == true && !string.IsNullOrEmpty(agentId))
        {
            await conversationIndex.RemoveConversationAsync(agentId, conversationId, cancellationToken).ConfigureAwait(false);
        }

        return Results.Ok(new DeleteResponse
        {
            Id = conversationId,
            Object = "conversation.deleted",
            Deleted = true
        });
    }

    private static async Task<IResult> CreateItemsAsync(
        string conversationId,
        [FromBody] CreateItemsRequest request,
        [FromQuery] string[]? include,
        [FromServices] IConversationStorage storage,
        CancellationToken cancellationToken)
    {
        var conversation = await storage.GetConversationAsync(conversationId, cancellationToken).ConfigureAwait(false);
        if (conversation is null)
        {
            return Results.NotFound(new ErrorResponse
            {
                Error = new ErrorDetails
                {
                    Message = $"Conversation '{conversationId}' not found.",
                    Type = "invalid_request_error"
                }
            });
        }

        var createdItems = new List<ConversationItem>();
        foreach (var item in request.Items)
        {
            var itemToAdd = item with
            {
                Id = $"msg_{Guid.NewGuid():N}",
                ConversationId = conversationId,
                CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds()
            };
            var created = await storage.AddItemAsync(itemToAdd, cancellationToken).ConfigureAwait(false);
            createdItems.Add(created);
        }

        return Results.Ok(new CreateItemsResponse
        {
            Data = createdItems
        });
    }

    private static async Task<IResult> ListItemsAsync(
        string conversationId,
        [FromQuery] int limit = 20,
        [FromQuery] string order = "desc",
        [FromQuery] string? after = null,
        [FromQuery] string[]? include = null,
        [FromServices] IConversationStorage storage = null!,
        CancellationToken cancellationToken = default)
    {
        var conversation = await storage.GetConversationAsync(conversationId, cancellationToken).ConfigureAwait(false);
        if (conversation is null)
        {
            return Results.NotFound(new ErrorResponse
            {
                Error = new ErrorDetails
                {
                    Message = $"Conversation '{conversationId}' not found.",
                    Type = "invalid_request_error"
                }
            });
        }

        var result = await storage.ListItemsAsync(conversationId, limit, ParseOrder(order), after, cancellationToken).ConfigureAwait(false);
        return Results.Ok(result);
    }

    private static async Task<IResult> GetItemAsync(
        string conversationId,
        string itemId,
        [FromQuery] string[]? include,
        [FromServices] IConversationStorage storage,
        CancellationToken cancellationToken)
    {
        var item = await storage.GetItemAsync(conversationId, itemId, cancellationToken).ConfigureAwait(false);
        return item is not null
            ? Results.Ok(item)
            : Results.NotFound(new ErrorResponse
            {
                Error = new ErrorDetails
                {
                    Message = $"Item '{itemId}' not found in conversation '{conversationId}'.",
                    Type = "invalid_request_error"
                }
            });
    }

    private static async Task<IResult> DeleteItemAsync(
        string conversationId,
        string itemId,
        [FromServices] IConversationStorage storage,
        CancellationToken cancellationToken)
    {
        var deleted = await storage.DeleteItemAsync(conversationId, itemId, cancellationToken).ConfigureAwait(false);
        if (!deleted)
        {
            return Results.NotFound(new ErrorResponse
            {
                Error = new ErrorDetails
                {
                    Message = $"Item '{itemId}' not found in conversation '{conversationId}'.",
                    Type = "invalid_request_error"
                }
            });
        }

        return Results.Ok(new DeleteResponse
        {
            Id = itemId,
            Object = "conversation.item.deleted",
            Deleted = true
        });
    }

    private static SortOrder ParseOrder(string order)
    {
        return string.Equals(order, "asc", StringComparison.OrdinalIgnoreCase) ? SortOrder.Ascending : SortOrder.Descending;
    }
}
