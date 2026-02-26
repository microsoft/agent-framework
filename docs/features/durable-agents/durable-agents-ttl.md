# Time-To-Live (TTL) for durable agent sessions

## Overview

The durable agents automatically maintain conversation history and state for each session. Without automatic cleanup, this state can accumulate indefinitely, consuming storage resources and increasing costs. The Time-To-Live (TTL) feature provides automatic cleanup of idle agent sessions, ensuring that sessions are automatically deleted after a period of inactivity.

## What is TTL?

Time-To-Live (TTL) is a configurable duration that determines how long an agent session state will be retained after its last interaction. When an agent session is idle (no messages sent to it) for longer than the TTL period, the session state is automatically deleted. Each new interaction with an agent resets the TTL timer, extending the session's lifetime.

## Benefits

- **Automatic cleanup**: No manual intervention required to clean up idle agent sessions
- **Cost optimization**: Reduces storage costs by automatically removing unused session state
- **Resource management**: Prevents unbounded growth of agent session state in storage
- **Configurable**: Set TTL globally or per-agent type to match your application's needs

## Configuration

TTL can be configured at two levels:

1. **Global default TTL**: Applies to all agent sessions unless overridden
2. **Per-agent type TTL**: Overrides the global default for specific agent types

Additionally, you can configure a **minimum deletion delay** that controls how frequently deletion operations are scheduled. The default value is 5 minutes, and the maximum allowed value is also 5 minutes.

> [!NOTE]
> Reducing the minimum deletion delay below 5 minutes can be useful for testing or for ensuring rapid cleanup of short-lived agent sessions. However, this can also increase the load on the system and should be used with caution.

### Default values

- **Default TTL**: 14 days
- **Minimum TTL deletion delay**: 5 minutes (maximum allowed value, subject to change in future releases)

### Configuration examples

#### .NET

```csharp
// Configure global default TTL and minimum signal delay
services.ConfigureDurableAgents(
    options =>
    {
        // Set global default TTL to 7 days
        options.DefaultTimeToLive = TimeSpan.FromDays(7);

        // Add agents (will use global default TTL)
        options.AddAIAgent(myAgent);
    });

// Configure per-agent TTL
services.ConfigureDurableAgents(
    options =>
    {
        options.DefaultTimeToLive = TimeSpan.FromDays(14); // Global default
        
        // Agent with custom TTL of 1 day
        options.AddAIAgent(shortLivedAgent, timeToLive: TimeSpan.FromDays(1));
        
        // Agent with custom TTL of 90 days
        options.AddAIAgent(longLivedAgent, timeToLive: TimeSpan.FromDays(90));
        
        // Agent using global default (14 days)
        options.AddAIAgent(defaultAgent);
    });

// Disable TTL for specific agents by setting TTL to null
services.ConfigureDurableAgents(
    options =>
    {
        options.DefaultTimeToLive = TimeSpan.FromDays(14);
        
        // Agent with no TTL (never expires)
        options.AddAIAgent(permanentAgent, timeToLive: null);
    });
```

## How TTL works

The following sections describe how TTL works in detail.

### Expiration tracking

Each agent session maintains an expiration timestamp in its internally managed state that is updated whenever the session processes a message:

1. When a message is sent to an agent session, the expiration time is set to `current time + TTL`
2. The runtime schedules a delete operation for the expiration time (subject to minimum delay constraints)
3. When the delete operation runs, if the current time is past the expiration time, the session state is deleted. Otherwise, the delete operation is rescheduled for the next expiration time.

### State deletion

When an agent session expires, its entire state is deleted, including:

- Conversation history
- Any custom state data
- Expiration timestamps

After deletion, if a message is sent to the same agent session, a new session is created with a fresh conversation history.

## Behavior examples

The following examples illustrate how TTL works in different scenarios.

### Example 1: Agent session expires after TTL

1. Agent configured with 30-day TTL
2. User sends message at Day 0 → agent session created, expiration set to Day 30
3. No further messages sent
4. At Day 30 → Agent session is deleted
5. User sends message at Day 31 → New agent session created with fresh conversation history

### Example 2: TTL reset on interaction

1. Agent configured with 30-day TTL
2. User sends message at Day 0 → agent session created, expiration set to Day 30
3. User sends message at Day 15 → Expiration reset to Day 45
4. User sends message at Day 40 → Expiration reset to Day 70
5. Agent session remains active as long as there are regular interactions

## Logging

The TTL feature includes comprehensive logging to track state changes:

- **Expiration time updated**: Logged when TTL expiration time is set or updated
- **Deletion scheduled**: Logged when a deletion check signal is scheduled
- **Deletion check**: Logged when a deletion check operation runs
- **Session expired**: Logged when an agent session is deleted due to expiration
- **TTL rescheduled**: Logged when a deletion signal is rescheduled

These logs help monitor TTL behavior and troubleshoot any issues.

## Best practices

1. **Choose appropriate TTL values**: Balance between storage costs and user experience. Too short TTLs may delete active sessions, while too long TTLs may accumulate unnecessary state.

2. **Use per-agent TTLs**: Different agents may have different usage patterns. Configure TTLs per-agent based on expected session lifetimes.

3. **Monitor expiration logs**: Review logs to understand TTL behavior and adjust configuration as needed.

4. **Test with short TTLs**: During development, use short TTLs (e.g., minutes) to verify TTL behavior without waiting for long periods.

## Limitations

- TTL is based on wall-clock time, not activity time. The expiration timer starts from the last message timestamp.
- Deletion checks are durably scheduled operations and may have slight delays depending on system load.
- Once an agent session is deleted, its conversation history cannot be recovered.
- TTL deletion requires at least one worker to be available to process the deletion operation message.
