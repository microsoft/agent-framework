# Checkpoint with Redis

This sample stores workflow checkpoints in Redis with `RedisCheckpointStore` from the `Microsoft.Agents.AI.Redis` package, so a workflow can be resumed by another process, container or machine.

It runs a number guessing workflow, stops it after a few super steps as if the process had crashed, then creates a new store and workflow, finds the latest checkpoint of the session in Redis with `CheckpointManager.GetLatestCheckpointAsync` and resumes from it.

## Prerequisites

- A Redis server, for example:

  ```bash
  docker run -d -p 6379:6379 redis:7-alpine
  ```

- Optionally set `REDIS_CONNECTION_STRING` (defaults to `localhost:6379`).

## Run the sample

```bash
dotnet run
```

The checkpoints are written under the `samples:checkpoints` key prefix and expire one hour after the last checkpoint of a session.
