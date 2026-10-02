# PostgreSQL checkpoint recovery

This model-free sample prepares an order, persists a pending approval, and exits.
A second process rebuilds the workflow and resumes it from PostgreSQL without
running the preparation executor again.

## Prerequisites

- .NET 10 SDK and PostgreSQL 13 or later. No vector extension or model credentials are needed.
- `POSTGRES_CONNECTION_STRING`: an Npgsql connection string for the database.
- `POSTGRES_TENANT_ID`: the tenant identifier for this run.
- Optional `POSTGRES_APPLICATION_ID` (default `checkpoint-sample`) and `POSTGRES_SCHEMA`
  (default `public`). The schema must exist and the database role must be able to create
  the checkpoint table and index.

Run from this sample directory:

```sh
dotnet run -- start purchase-1042
dotnet run -- resume purchase-1042 approve
```

The first invocation prints `Prepared order: PO-1042`, waits for approval, and saves a
checkpoint before exiting. The second invocation prints `Approved order.` without
preparing the order again. Use `reject` instead of `approve` to reject it. Keep the
application, tenant, run ID, schema, and executor identities unchanged when resuming.

Both SDKs use `agent_framework_checkpoints`. Python and .NET can share the same table,
including application, tenant, and run identifiers, because each filters on its own
`payload_format`. The serialized execution state is SDK-specific: sharing storage does
not make a Python workflow checkpoint resumable by .NET, or vice versa.

The sample's tenant setting is supplied by its operator. A hosted application must
derive that scope from authenticated, authorized identity. Checkpoints are trusted
private data. Recovery after a checkpoint can repeat external side effects, so use
idempotency keys for operations such as creating an order or sending a payment.
