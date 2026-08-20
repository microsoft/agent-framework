// Copyright (c) Microsoft. All rights reserved.

using Mem0Sharp;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

internal sealed class Mem0SharpProvider(MemoryService memory, string userId) : AIContextProvider
{
    protected override async ValueTask StoreAIContextAsync(
        InvokedContext context,
        CancellationToken cancellationToken = default)
    {
        foreach (ChatMessage message in context.RequestMessages.Where(message => message.Role == ChatRole.User && !string.IsNullOrWhiteSpace(message.Text)))
        {
            await memory.AddAsync(
                message.Text!,
                new MemoryAddOptions { UserId = userId, Infer = false },
                cancellationToken);
        }
    }

    protected override async ValueTask<AIContext> ProvideAIContextAsync(
        InvokingContext context,
        CancellationToken cancellationToken = default)
    {
        var memories = await memory.GetAllAsync(
            new MemoryFilter(UserId: userId),
            cancellationToken: cancellationToken);

        return memories.Count == 0
            ? new AIContext()
            : new AIContext
            {
                Instructions = $"Relevant memories for this user:\n{string.Join(Environment.NewLine, memories.Select(item => $"- {item.Text}"))}",
            };
    }
}