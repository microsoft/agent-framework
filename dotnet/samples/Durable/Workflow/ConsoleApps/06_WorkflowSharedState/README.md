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
| **ValidateOrder** | `OrderDetails` | — | `taxRate`, `auditValidate` |
| **EnrichOrder** | `OrderDetails` (pass-through) | `auditValidate` | `shippingTier`, `auditEnrich`, `carrier` (scope: shipping), `estimatedDays` (scope: shipping) |
| **ProcessPayment** | payment ref string | `taxRate` | `auditPayment` |
| **GenerateInvoice** | invoice string | `auditValidate`, `auditEnrich`, `auditPayment` | clears `shipping` scope |

> [!NOTE]
> `EnrichOrder` writes `carrier` and `estimatedDays` under the `"shipping"` scope using `scopeName: "shipping"`. This keeps these keys separate from keys written without a scope, so a key like `"carrier"` in the `"shipping"` scope won't collide with a `"carrier"` key written elsewhere.

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
    Wrote to shared state: auditValidate
  [Output] ValidateOrder: Order 'ORD-001' validated. Customer: Jerry, Amount: $249.99
    Read from shared state: shippingTier = Express
    Wrote to shared state: carrier = Contoso Express (scope: shipping)
    Wrote to shared state: estimatedDays = 2 (scope: shipping)
    Read from shared state: auditValidate (previous step: ValidateOrder)
    Wrote to shared state: auditEnrich
  [Output] EnrichOrder: Order enriched. Shipping: Express (previous step: ValidateOrder)
    Read from shared state: taxRate = 8.5%
    Wrote to shared state: auditPayment
  [Output] ProcessPayment: Payment processed. Total: $271.24 (tax: $21.25). Ref: PAY-abc123def456
    Read from shared state: 3 audit entries
    Cleared shared state scope: shipping
  [Output] GenerateInvoice: Invoice complete. Payment: "PAY-abc123def456". Audit trail: [ValidateOrder → EnrichOrder → ProcessPayment]
  Completed: Invoice complete. Payment: "PAY-abc123def456". Audit trail: [ValidateOrder → EnrichOrder → ProcessPayment]
```

### Viewing Workflows in the DTS Dashboard

After running a workflow, you can navigate to the Durable Task Scheduler (DTS) dashboard to inspect the orchestration status, activity inputs/outputs, and events.

If you are using the DTS emulator, the dashboard is available at `http://localhost:8082`.

> [!NOTE]
> Shared state updates are included in each activity's output (as `stateUpdates` with scoped keys), so they can be viewed in the dashboard by clicking on an activity and inspecting its output. However, there is no dedicated view for the aggregated shared state across all activities.
