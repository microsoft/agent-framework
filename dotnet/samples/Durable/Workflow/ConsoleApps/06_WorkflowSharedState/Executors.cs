// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace WorkflowSharedState;

// ═══════════════════════════════════════════════════════════════════════════════
// Domain models
// ═══════════════════════════════════════════════════════════════════════════════

/// <summary>
/// The primary order data passed through the pipeline via return values.
/// </summary>
internal sealed record OrderDetails(string OrderId, string CustomerName, decimal Amount, DateTime OrderDate);

/// <summary>
/// Cross-cutting audit trail accumulated in shared state across executors.
/// Each executor appends its step name and timestamp. This data does not flow
/// through return values — it lives only in shared state.
/// </summary>
internal sealed record AuditEntry(string Step, string Timestamp, string Detail);

// ═══════════════════════════════════════════════════════════════════════════════
// Executors
// ═══════════════════════════════════════════════════════════════════════════════

/// <summary>
/// Validates the order and writes the initial audit entry and tax rate to shared state.
/// The order details are returned as the executor output (normal message flow),
/// while the audit trail and tax rate are stored in shared state (side-channel).
/// If the order ID starts with "INVALID", the executor halts the workflow early
/// using <see cref="IWorkflowContext.RequestHaltAsync"/>.
/// </summary>
internal sealed class ValidateOrder() : Executor<string, OrderDetails>("ValidateOrder")
{
    public override async ValueTask<OrderDetails> HandleAsync(
        string message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        await Task.Delay(TimeSpan.FromMilliseconds(200), cancellationToken);

        // Halt the workflow early if the order ID is invalid.
        // No downstream executors will run after this.
        if (message.StartsWith("INVALID", StringComparison.OrdinalIgnoreCase))
        {
            await context.YieldOutputAsync($"Order '{message}' failed validation. Halting workflow.", cancellationToken);
            await context.RequestHaltAsync();
            return new OrderDetails(message, "Unknown", 0, DateTime.UtcNow);
        }

        OrderDetails details = new(message, "Jerry", 249.99m, DateTime.UtcNow);

        // Store the tax rate in shared state — downstream ProcessPayment reads it
        // without needing it in the message chain.
        await context.QueueStateUpdateAsync("taxRate", 0.085m, cancellationToken: cancellationToken);
        Console.WriteLine("    Wrote to shared state: taxRate = 8.5%");

        // Start the audit trail in shared state
        AuditEntry audit = new("ValidateOrder", DateTime.UtcNow.ToString("o"), $"Validated order {message}");
        await context.QueueStateUpdateAsync("auditValidate", audit, cancellationToken: cancellationToken);
        Console.WriteLine("    Wrote to shared state: auditValidate");

        await context.YieldOutputAsync($"Order '{message}' validated. Customer: {details.CustomerName}, Amount: {details.Amount:C}", cancellationToken);

        return details;
    }
}

/// <summary>
/// Enriches the order with shipping information.
/// Reads the audit trail from shared state and appends its own entry.
/// Uses ReadOrInitStateAsync to lazily initialize a shipping tier.
/// Demonstrates custom scopes by writing shipping details under the "shipping" scope.
/// </summary>
internal sealed class EnrichOrder() : Executor<OrderDetails, OrderDetails>("EnrichOrder")
{
    public override async ValueTask<OrderDetails> HandleAsync(
        OrderDetails message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        await Task.Delay(TimeSpan.FromMilliseconds(200), cancellationToken);

        // Use ReadOrInitStateAsync — only initializes if no value exists yet
        string shippingTier = await context.ReadOrInitStateAsync(
            "shippingTier",
            () => "Express",
            cancellationToken: cancellationToken);
        Console.WriteLine($"    Read from shared state: shippingTier = {shippingTier}");

        // Write carrier under a custom "shipping" scope.
        // This keeps the key separate from keys written without a scope,
        // so "carrier" here won't collide with a "carrier" key written elsewhere.
        await context.QueueStateUpdateAsync("carrier", "Contoso Express", scopeName: "shipping", cancellationToken: cancellationToken);
        Console.WriteLine("    Wrote to shared state: carrier = Contoso Express (scope: shipping)");

        // Verify we can read the audit entry from the previous step
        AuditEntry? previousAudit = await context.ReadStateAsync<AuditEntry>("auditValidate", cancellationToken: cancellationToken);
        string auditStatus = previousAudit is not null ? $"(previous step: {previousAudit.Step})" : "(no prior audit)";
        Console.WriteLine($"    Read from shared state: auditValidate {auditStatus}");

        // Append our own audit entry
        AuditEntry audit = new("EnrichOrder", DateTime.UtcNow.ToString("o"), $"Enriched with {shippingTier} shipping {auditStatus}");
        await context.QueueStateUpdateAsync("auditEnrich", audit, cancellationToken: cancellationToken);
        Console.WriteLine("    Wrote to shared state: auditEnrich");

        await context.YieldOutputAsync($"Order enriched. Shipping: {shippingTier} {auditStatus}", cancellationToken);

        return message;
    }
}

/// <summary>
/// Processes payment using the tax rate from shared state (written by ValidateOrder).
/// The tax rate is side-channel data — it doesn't flow through return values.
/// </summary>
internal sealed class ProcessPayment() : Executor<OrderDetails, string>("ProcessPayment")
{
    public override async ValueTask<string> HandleAsync(
        OrderDetails message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        await Task.Delay(TimeSpan.FromMilliseconds(300), cancellationToken);

        // Read tax rate written by ValidateOrder — not available in the message chain
        decimal taxRate = await context.ReadOrInitStateAsync("taxRate", () => 0.0m, cancellationToken: cancellationToken);
        Console.WriteLine($"    Read from shared state: taxRate = {taxRate:P1}");

        decimal tax = message.Amount * taxRate;
        decimal total = message.Amount + tax;
        string paymentRef = $"PAY-{Guid.NewGuid():N}"[..16];

        // Append audit entry
        AuditEntry audit = new("ProcessPayment", DateTime.UtcNow.ToString("o"), $"Charged {total:C} (tax: {tax:C})");
        await context.QueueStateUpdateAsync("auditPayment", audit, cancellationToken: cancellationToken);
        Console.WriteLine("    Wrote to shared state: auditPayment");

        await context.YieldOutputAsync($"Payment processed. Total: {total:C} (tax: {tax:C}). Ref: {paymentRef}", cancellationToken);

        return paymentRef;
    }
}

/// <summary>
/// Generates the final invoice by reading the full audit trail from shared state.
/// Demonstrates reading multiple state entries written by different executors
/// and clearing a scope with <see cref="IWorkflowContext.QueueClearScopeAsync(string?, CancellationToken)"/>.
/// </summary>
internal sealed class GenerateInvoice() : Executor<string, string>("GenerateInvoice")
{
    public override async ValueTask<string> HandleAsync(
        string message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        await Task.Delay(TimeSpan.FromMilliseconds(100), cancellationToken);

        // Read the full audit trail from shared state — each step wrote its own entry
        AuditEntry? validateAudit = await context.ReadStateAsync<AuditEntry>("auditValidate", cancellationToken: cancellationToken);
        AuditEntry? enrichAudit = await context.ReadStateAsync<AuditEntry>("auditEnrich", cancellationToken: cancellationToken);
        AuditEntry? paymentAudit = await context.ReadStateAsync<AuditEntry>("auditPayment", cancellationToken: cancellationToken);
        int auditCount = new[] { validateAudit, enrichAudit, paymentAudit }.Count(a => a is not null);
        Console.WriteLine($"    Read from shared state: {auditCount} audit entries");

        // Read carrier from the "shipping" scope (written by EnrichOrder)
        string? carrier = await context.ReadStateAsync<string>("carrier", scopeName: "shipping", cancellationToken: cancellationToken);
        Console.WriteLine($"    Read from shared state: carrier = {carrier} (scope: shipping)");

        // Clear the "shipping" scope — no longer needed after invoice generation.
        await context.QueueClearScopeAsync("shipping", cancellationToken);
        Console.WriteLine("    Cleared shared state scope: shipping");

        string auditSummary = string.Join(" → ", new[]
        {
            validateAudit?.Step, enrichAudit?.Step, paymentAudit?.Step
        }.Where(s => s is not null));

        return $"Invoice complete. Payment: {message}. Audit trail: [{auditSummary}]";
    }
}
