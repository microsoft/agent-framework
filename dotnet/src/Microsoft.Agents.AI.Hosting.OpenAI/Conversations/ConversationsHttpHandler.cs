// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations;

/// <summary>
/// Handles route requests for OpenAI Conversations API endpoints.
/// </summary>
internal sealed class ConversationsHttpHandler
{
    private readonly IConversationStorage _storage;
    private readonly IAgentConversationIndex? _conversationIndex;

    /// <summary>
    /// Initializes a new instance of the <see cref="ConversationsHttpHandler"/> class.
    /// </summary>
    /// <param name="storage">The conversation storage service.</param>
    /// <param name="conversationIndex">Optional conversation index service.</param>
    public ConversationsHttpHandler(IConversationStorage storage, IAgentConversationIndex? conversationIndex)
    {
        this._storage = storage ?? throw new ArgumentNullException(nameof(storage));
        this._conversationIndex = conversationIndex;
    }

    /// <summary>
    /// Lists conversations by agent ID.
    /// </summary>
    public async Task<IResult> ListConversationsByAgentAsync(
        [FromQuery] string? agent_id,
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
        if (this._conversationIndex == null)
        {
            return Results.Ok(new ListResponse<Conversation>
            {
                Data = [],
                HasMore = false
            });
        }

        var conversationIdsResponse = await this._conversationIndex.GetConversationIdsAsync(agent_id, cancellationToken).ConfigureAwait(false);

        // Fetch full conversation objects
        var conversations = new List<Conversation>();
        foreach (var conversationId in conversationIdsResponse.Data)
        {
            var conversation = await this._storage.GetConversationAsync(conversationId, cancellationToken).ConfigureAwait(false);
            if (conversation is not null)
            {
                conversations.Add(conversation);
            }
        }

        return Results.Ok(new ListResponse<Conversation>
        {
            Data = conversations,
            HasMore = false
        });
    }

    /// <summary>
    /// Creates a new conversation.
    /// </summary>
    public async Task<IResult> CreateConversationAsync(
        [FromBody] CreateConversationRequest request,
        CancellationToken cancellationToken)
    {
        Dictionary<string, string> metadata = request.Metadata ?? [];
        var idGenerator = new IdGenerator(responseId: null, conversationId: null);
        var conversation = new Conversation
        {
            Id = idGenerator.ConversationId,
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Metadata = metadata
        };

        var created = await this._storage.CreateConversationAsync(conversation, cancellationToken).ConfigureAwait(false);

        // Add initial items if provided
        if (request.Items is { Count: > 0 })
        {
            List<ItemResource> itemsToAdd = [.. request.Items.Select(itemParam => itemParam.ToItemResource(idGenerator))];
            await this._storage.AddItemsAsync(created.Id, itemsToAdd, cancellationToken).ConfigureAwait(false);
        }

        // Add to conversation index if available and agent_id is provided in metadata
        if (this._conversationIndex != null && created.Metadata.TryGetValue("agent_id", out var agentId) && !string.IsNullOrEmpty(agentId))
        {
            await this._conversationIndex.AddConversationAsync(agentId, created.Id, cancellationToken).ConfigureAwait(false);
        }

        return Results.Ok(created);
    }

    /// <summary>
    /// Retrieves a conversation by ID.
    /// </summary>
    public async Task<IResult> GetConversationAsync(
        string conversationId,
        CancellationToken cancellationToken)
    {
        var conversation = await this._storage.GetConversationAsync(conversationId, cancellationToken).ConfigureAwait(false);
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

    /// <summary>
    /// Updates a conversation's metadata.
    /// </summary>
    public async Task<IResult> UpdateConversationAsync(
        string conversationId,
        [FromBody] UpdateConversationRequest request,
        CancellationToken cancellationToken)
    {
        var existing = await this._storage.GetConversationAsync(conversationId, cancellationToken).ConfigureAwait(false);
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

        var result = await this._storage.UpdateConversationAsync(updated, cancellationToken).ConfigureAwait(false);
        return Results.Ok(result);
    }

    /// <summary>
    /// Deletes a conversation and all its messages.
    /// </summary>
    public async Task<IResult> DeleteConversationAsync(
        string conversationId,
        CancellationToken cancellationToken)
    {
        // Get conversation first to retrieve agent_id for index removal
        var conversation = await this._storage.GetConversationAsync(conversationId, cancellationToken).ConfigureAwait(false);

        var deleted = await this._storage.DeleteConversationAsync(conversationId, cancellationToken).ConfigureAwait(false);
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
        if (this._conversationIndex != null && conversation?.Metadata.TryGetValue("agent_id", out var agentId) == true && !string.IsNullOrEmpty(agentId))
        {
            await this._conversationIndex.RemoveConversationAsync(agentId, conversationId, cancellationToken).ConfigureAwait(false);
        }

        return Results.Ok(new DeleteResponse
        {
            Id = conversationId,
            Object = "conversation.deleted",
            Deleted = true
        });
    }

    /// <summary>
    /// Adds items to a conversation.
    /// </summary>
    public async Task<IResult> CreateItemsAsync(
        string conversationId,
        [FromBody] CreateItemsRequest request,
        [FromQuery] string[]? include,
        CancellationToken cancellationToken)
    {
        var conversation = await this._storage.GetConversationAsync(conversationId, cancellationToken).ConfigureAwait(false);
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

        var idGenerator = new IdGenerator(responseId: null, conversationId: conversationId);
        List<ItemResource> createdItems = [.. request.Items.Select(itemParam => itemParam.ToItemResource(idGenerator))];
        await this._storage.AddItemsAsync(conversationId, createdItems, cancellationToken).ConfigureAwait(false);

        return Results.Ok(new ListResponse<ItemResource>
        {
            Data = createdItems,
            FirstId = createdItems.Count > 0 ? createdItems[0].Id : null,
            LastId = createdItems.Count > 0 ? createdItems[^1].Id : null,
            HasMore = false
        });
    }

    /// <summary>
    /// Lists items in a conversation.
    /// </summary>
    public async Task<IResult> ListItemsAsync(
        string conversationId,
        [FromQuery] int? limit,
        [FromQuery] string? order,
        [FromQuery] string? after,
        [FromQuery] string[]? include,
        CancellationToken cancellationToken)
    {
        // Validate limit parameter
        if (limit is < 1)
        {
            return Results.BadRequest(new ErrorResponse
            {
                Error = new ErrorDetails
                {
                    Message = "Invalid value for 'limit': must be a positive integer.",
                    Type = "invalid_request_error",
                    Code = "invalid_value"
                }
            });
        }

        var conversation = await this._storage.GetConversationAsync(conversationId, cancellationToken).ConfigureAwait(false);
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

        var result = await this._storage.ListItemsAsync(conversationId, limit, ParseOrder(order), after, cancellationToken).ConfigureAwait(false);
        return Results.Ok(result);
    }

    /// <summary>
    /// Retrieves a specific item.
    /// </summary>
    public async Task<IResult> GetItemAsync(
        string conversationId,
        string itemId,
        [FromQuery] string[]? include,
        CancellationToken cancellationToken)
    {
        var item = await this._storage.GetItemAsync(conversationId, itemId, cancellationToken).ConfigureAwait(false);
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

    /// <summary>
    /// Deletes a specific item.
    /// </summary>
    public async Task<IResult> DeleteItemAsync(
        string conversationId,
        string itemId,
        CancellationToken cancellationToken)
    {
        var deleted = await this._storage.DeleteItemAsync(conversationId, itemId, cancellationToken).ConfigureAwait(false);
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

    private static SortOrder? ParseOrder(string? order)
    {
        if (order is null)
        {
            return null;
        }

        return string.Equals(order, "asc", StringComparison.OrdinalIgnoreCase) ? SortOrder.Ascending : SortOrder.Descending;
    }
}
