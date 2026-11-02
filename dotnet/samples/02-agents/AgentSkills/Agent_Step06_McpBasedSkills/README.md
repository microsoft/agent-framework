# MCP-Based Agent Skills Sample

This sample demonstrates how to discover **Agent Skills served over MCP** with a `ChatClientAgent`.

## What it demonstrates

- Hosting a small MCP server (in this same executable, launched with `--server`) that
  advertises the `io.modelcontextprotocol/skills` extension and exposes `skills/list`.
- Connecting an `McpClient` to the embedded server via stdio transport.
- Building an `AgentSkillsProvider` via `UseMcpSkills(client)`, which discovers skills
  through `skills/list` and reads their instructions through `resources/read`.
- Returning a complete skill list with frontmatter, resource URIs, SHA-256 digests, and byte sizes for
  `SKILL.md` and `references/conversion-table.md`.
- Verifying fetched skill instructions and supporting resources against their listed digests and byte sizes.
- Serving the conversion-table resource from the file-based skills sample, which the
  skill instructions tell the agent to read before performing a conversion.
- The progressive disclosure pattern across MCP: advertise → load → read resources, exactly
  as for filesystem-backed skills.

## Running the Sample

### Prerequisites

- .NET 10.0 SDK
- Microsoft Foundry project with a deployed model

### Setup

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project"
$env:FOUNDRY_MODEL="gpt-5.4-mini"
```

Authenticate with `az login`.

### Run

```powershell
dotnet run
```

## Configuring Cache Durations

The MCP source caches the skill list and each resource separately using the server's time to live (TTL).
The MCP specification requires a TTL, but some servers may not provide it. By default, a missing,
zero, or negative TTL causes a fetch on every access. A positive TTL allows reuse for that duration,
starting when the response arrives.

Set `AgentMcpSkillsSourceOptions.TtlResolver` to override TTLs for the skill list, refreshed skill metadata,
and resources.
For example, use five minutes for missing, zero, or negative TTLs, and keep positive server TTLs unchanged:

```csharp
var options = new AgentMcpSkillsSourceOptions
{
    TtlResolver = static ttl =>
        ttl is null || ttl.Value <= TimeSpan.Zero
            ? TimeSpan.FromMinutes(5)
            : ttl.Value,
};

var provider = new AgentSkillsProviderBuilder()
    .UseMcpSkills(client, options)
    .DisableCaching()
    .Build();
```

The resolver receives the server TTL (`null` if missing) and returns a `TimeSpan`.
A positive result sets the cache duration; zero or a negative result causes a fetch on the next access.
Leaving `TtlResolver` unset keeps the default behavior.

Use `.DisableCaching()`, as above, so the builder's cache does not prevent the MCP source from
checking expiration. Longer cache durations delay observing server changes, but resource validation
still applies.

## Security Considerations

### Sharing a source across authorization contexts

According to the MCP specification, each `skills/list`, `skills/get`, and `resources/read` response must include
a `cacheScope` field that tells the client who may reuse the cached response:

- `public` - the response is the same for every caller and may be shared between them.
- `private` - the response is specific to the caller's credentials (for example, a user or tenant)
  and must not be shared with other callers.

Not all servers follow the specification yet, so a missing or `null` `cacheScope` is treated as `public`.

To keep private responses from leaking between callers, the source needs to know who the current caller is.
By default, it doesn't: all callers share one cache, so the source accepts only public responses and throws
`InvalidOperationException` for a private one. Each response is checked on its own, so a skill from a public
list can still fail if its `SKILL.md` or another file is returned as private.

To accept private responses, set `CachePartitionKeySelector` to return a key for the current caller, such as
a user or tenant ID. Each key gets its own cache partition, so cached skills are never shared between keys.
Set it whenever the server can return private responses, even if your app has only one user:

```csharp
var options = new AgentMcpSkillsSourceOptions
{
    CachePartitionKeySelector = context => GetApplicationAuthorizationKey(context),
    MaxCachedPartitions = 1000,
    PartitionSlidingExpiration = TimeSpan.FromMinutes(30),
    PartitionAbsoluteExpiration = TimeSpan.FromHours(8),
};

using var provider = new AgentSkillsProviderBuilder()
    .UseMcpSkills(sharedMcpClient, options)
    .DisableCaching()
    .Build();
```

`GetApplicationAuthorizationKey` is your own helper, not a framework API. It should return a non-empty ID
for the caller whose credentials the MCP client sends, for example a user or tenant ID.
Use an opaque ID, not an access token.

The source only separates caches; it does not handle authentication. Your app is responsible for:

- configuring the MCP client to send the current caller's credentials;
- keeping the same caller's credentials when a returned skill later reads `SKILL.md` or other files;
- not sharing returned skills between callers.

`DisableCaching()` turns off the provider's own cache, so the source, and therefore the key selector,
runs on every call.

By default, a partition is kept for every key until the source is disposed. In services with many users,
use the other options to limit memory:

- `MaxCachedPartitions` - the maximum number of partitions to keep.
- `PartitionSlidingExpiration` - removes a partition that has not been used for this long.
- `PartitionAbsoluteExpiration` - removes a partition this long after it was created, even if it is still in use.

When a partition is removed, the next call for its key fetches skills from the server again.
Skills that were already returned keep working. These options don't change how long MCP responses
are cached; use `TtlResolver` for that.

### Trust and size limits

Discovering skills over MCP means an external MCP server controls what skill content (including
instructions and supporting resources) reaches the agent. A compromised or
untrustworthy server could return adversarial content designed to manipulate the agent (indirect
prompt injection) or to exfiltrate data through skill instructions/scripts. Only connect `UseMcpSkills`
to MCP servers you have vetted and trust.

Listed resources, including `SKILL.md`, default to a maximum of **1 MiB (1,048,576 bytes)** each.
Discovery rejects oversized advertised sizes, and reads check actual UTF-8 text and decoded binary
sizes before encoding text or decoding blobs for integrity verification.

Configure the resource limit with `AgentMcpSkillsSourceOptions.ListedResourceMaxSizeBytes` passed to
`UseMcpSkills`; the limit must be positive.

These checks do not limit incoming messages before the supplied client receives and parses them.
