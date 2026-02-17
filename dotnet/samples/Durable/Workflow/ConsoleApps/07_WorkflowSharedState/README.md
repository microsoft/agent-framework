# Shared State Workflow Sample

This sample demonstrates how executors in a durable workflow can share state via `IWorkflowContext`. State written by one executor is accessible to all downstream executors, persisted across supersteps, and survives process restarts.

## Key Concepts Demonstrated

- Writing state with `QueueStateUpdateAsync` — executors store data for downstream executors
- Reading state with `ReadStateAsync` — executors access data written by earlier executors
- Lazy initialization with `ReadOrInitStateAsync` — initialize state only if not already present
- Custom scopes with `scopeName` — partition state into isolated namespaces (e.g., `"shipping"`)
- Clearing scopes with `QueueClearScopeAsync` — remove all entries under a scope when no longer needed
- Early termination with `RequestHaltAsync` — halt the workflow when validation fails
- State persistence across supersteps — the orchestration passes shared state to each activity
- Event streaming with `IStreamingWorkflowRun` — observe executor progress in real time

## Workflow

**OrderPipeline**: `ValidateOrder` → `EnrichOrder` → `ProcessPayment` → `GenerateInvoice`

Return values carry primary business data through the pipeline (`OrderDetails` → `OrderDetails` → payment ref → invoice string). Shared state carries side-channel data that doesn't belong in the message chain:

| Executor | Returns (message flow) | Reads from State | Writes to State |
|----------|----------------------|-----------------|-----------------|
| **ValidateOrder** | `OrderDetails` | — | `taxRate`, `audit:validate` |
| **EnrichOrder** | `OrderDetails` (pass-through) | `audit:validate` | `shippingTier`, `audit:enrich`, `shipping:carrier`, `shipping:estimatedDays` |
| **ProcessPayment** | payment ref string | `taxRate` | `audit:payment` |
| **GenerateInvoice** | invoice string | `audit:validate`, `audit:enrich`, `audit:payment` | clears `shipping` scope |

> **Note:** `EnrichOrder` writes `carrier` and `estimatedDays` under the `"shipping"` scope using `scopeName: "shipping"`. Scoped keys are isolated from the default namespace, so a key like `"carrier"` in the `"shipping"` scope won't collide with a `"carrier"` key in the default scope.

## Environment Setup

See the [README.md](../../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

## Running the Sample

```bash
dotnet run
```

Enter an order ID when prompted. The workflow will process the order through all four executors, streaming events as they occur:

```text
> ORD-001
Started run: abc123
    Wrote to shared state: taxRate = 8.5%
    Wrote to shared state: audit:validate
  [Output] ValidateOrder: Order 'ORD-001' validated. Customer: Jerry, Amount: $249.99
    Read from shared state: shippingTier = Express
    Wrote to shared state: shipping:carrier = Contoso Express
    Wrote to shared state: shipping:estimatedDays = 2
    Read from shared state: audit:validate (previous step: ValidateOrder)
    Wrote to shared state: audit:enrich
  [Output] EnrichOrder: Order enriched. Shipping: Express (previous step: ValidateOrder)
    Read from shared state: taxRate = 8.5%
    Wrote to shared state: audit:payment
  [Output] ProcessPayment: Payment processed. Total: $271.24 (tax: $21.25). Ref: PAY-abc123def456
    Read from shared state: 3 audit entries
    Cleared shared state scope: shipping
  [Output] GenerateInvoice: Invoice complete. Payment: "PAY-abc123def456". Audit trail: [ValidateOrder → EnrichOrder → ProcessPayment]
  Completed: Invoice complete. Payment: "PAY-abc123def456". Audit trail: [ValidateOrder → EnrichOrder → ProcessPayment]
```

### Viewing Workflows in the DTS Dashboard

After running a workflow, you can navigate to the Durable Task Scheduler (DTS) dashboard to inspect the shared state being passed between activities.

If you are using the DTS emulator, the dashboard is available at `http://localhost:8082`.
