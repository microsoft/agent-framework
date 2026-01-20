// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use durable state management in Azure Functions workflows.
// The OrderIdParserExecutor writes a value to shared state, and the EmailSenderExecutor reads it back.
// The state is persisted durably using Durable Entities behind the scenes.

using Microsoft.Agents.AI.Workflows;

namespace SingleAgent;

/// <summary>
/// Constants for shared state scopes used across executors.
/// </summary>
internal static class SharedStateConstants
{
    public const string MessageScope = "MessageState";
    public const string ProcessedMessageKey = "ProcessedMessage";
}

public sealed class Order
{
    public Order(string id, decimal amount)
    {
        this.Id = id;
        this.Amount = amount;
    }
    public string Id { get; }
    public decimal Amount { get; }
    public string? PaymentReferenceNumber { get; set; }
}

/// <summary>
/// First executor that processes a message and stores the result in shared state.
/// </summary>
internal sealed class OrderIdParserExecutor() : Executor<string, Order>("OrderIdParserExecutor")
{
    public override async ValueTask<Order> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Process the message
        string processedMessage = $"Processed: {message}";

        // Store the processed message in shared state for the next executor
        await context.QueueStateUpdateAsync(
            SharedStateConstants.ProcessedMessageKey,
            processedMessage,
            SharedStateConstants.MessageScope,
            cancellationToken);

        return GetOrder(message);
    }

    private static Order GetOrder(string id)
    {
        // Simulate fetching order details
        return new Order(id, 100.0m);
    }
}

/// <summary>
/// Second executor that reads the shared state and appends to the message.
/// </summary>
internal sealed class EmailSenderExecutor() : Executor<Order, string>("EmailSenderExecutor")
{
    public override async ValueTask<string> HandleAsync(Order message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Read the processed message from shared state (written by OrderIdParserExecutor)
        string? storedMessage = await context.ReadStateAsync<string>(
            SharedStateConstants.ProcessedMessageKey,
            SharedStateConstants.MessageScope,
            cancellationToken);

        // Combine with the input message
        return storedMessage is not null
            ? $"From state: [{storedMessage}] | Input: [{message.Id}]"
            : $"No state found | Input: [{message.Id}]";
    }
}

internal sealed class PaymentProcesserExecutor() : Executor<Order, Order>("PaymentProcesserExecutor")
{
    public override async ValueTask<Order> HandleAsync(Order message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Call payment gateway.
        message.PaymentReferenceNumber = Guid.NewGuid().ToString().Substring(0, 4);
        return message;
    }
}
