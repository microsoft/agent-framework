---
status: proposed
contact: sergeymenshykh
date: 2026-06-23
deciders: sergeymenshykh
---

# Skills Over MCP: Implementation Design Options

This document explores design options for two SEP-2640 features. The decisions are not yet finalized.

- **Part 1: MCP Resource Template Skills** - skills described by a URI template with variables that must be resolved before loading.
- **Part 2: Direct Skill References** - reading `skill://` URIs referenced directly (e.g., in server instructions) without being listed in the index.

## Part 1: MCP Resource Template Skills

### Context and Problem Statement

The `AgentMcpSkillsSource` currently only supports `skill-md` type entries from `skill://index.json` (support for `archive` type is planned). The SEP-2640 specification also defines `mcp-resource-template` entries: **parameterized skill namespaces** described by a URI template with variables (e.g., `{product}`) that resolve to concrete `SKILL.md` URIs. Rather than materializing every skill in the index, the template's variables must be resolved before a skill can be loaded.

### Index Entry Format

```json
{
  "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
  "skills": [
    {
      "name": "git-workflow",
      "type": "skill-md",
      "description": "Follow this team's Git conventions for branching and commits",
      "url": "skill://git-workflow/SKILL.md"
    },
    {
      "type": "mcp-resource-template",
      "description": "Per-product documentation skill",
      "url": "skill://docs/{product}/SKILL.md"
    }
  ]
}
```

Key differences from `skill-md`:

| Field | `skill-md` | `mcp-resource-template` |
|-------|------------|-------------------------|
| `name` | Required (the skill name) | **Omitted** (represents many skills) |
| `type` | `"skill-md"` | `"mcp-resource-template"` |
| `url` | Concrete URI to `SKILL.md` | URI template with variables |
| `description` | Describes the skill | Describes the addressable skill space |

### Use Cases

Template skills address two scenarios where listing concrete skills is impractical:

- **Large skill catalogs** - too many skills to enumerate every entry in the index.
- **Dynamically generated skills** - skill content generated on the fly from parameters, so the set of valid skills is not known at index-creation time.

### How Template Skills Are Consumed

Per SEP-2640, the consumption flow relies on the MCP `completion/complete` method:

1. **Server registers a resource template** - The MCP server registers the same `url` value (e.g., `skill://docs/{product}/SKILL.md`) as an MCP [resource template](https://modelcontextprotocol.io/specification/2025-11-25/server/resources#resource-templates), wiring template variables to the [completion API](https://modelcontextprotocol.io/specification/2025-11-25/server/utilities/completion).

2. **Host reads `skill://index.json`** - Discovers the template entry with `type: "mcp-resource-template"`.

3. **Host surfaces template in UI** - Presents the template as an interactive discovery point where the user fills in variables.

4. **Host calls `completion/complete`** - For each template variable (e.g., `{product}`), the host calls the MCP completion API to get possible values from the server:
   ```json
   {
     "method": "completion/complete",
     "params": {
       "ref": {
         "type": "ref/resource",
         "uri": "skill://docs/{product}/SKILL.md"
       },
       "argument": {
         "name": "product",
         "value": ""
       }
     }
   }
   ```
   The server responds with possible completions:
   ```json
   {
     "completion": {
       "values": ["widgets", "billing", "auth", "payments"],
       "hasMore": false,
       "total": 4
     }
   }
   ```

5. **User selects a value** - The user picks a value (e.g., `"billing"`) from the list.

6. **Host resolves the URI** - The template `skill://docs/{product}/SKILL.md` becomes the concrete URI `skill://docs/billing/SKILL.md`.

7. **Host reads the resolved skill** - Calls `resources/read` with the concrete URI and proceeds as with any `skill-md` skill.

### Potential Implementation Options

### Option 1: Callback on `AgentMcpSkillsSource` for Variable Value Selection

Add a callback to `AgentMcpSkillsSource` (or its options) that is invoked for each `mcp-resource-template` entry to let the caller select variable values.

**Flow:**

1. `AgentMcpSkillsSource.GetSkillsAsync()` reads `skill://index.json`
2. For each entry with `type: "mcp-resource-template"`:
   - Parse the URI template to extract variable names (e.g., `{product}`)
   - Call the MCP `completion/complete` API to get possible values for each variable
   - Invoke the caller-provided callback with the variable name, description, and possible values
   - The callback returns a selected value and a `bool` indicating whether to include the skill
3. Resolve the URI template with the selected values
4. Create an `AgentMcpSkill` from the resolved URI and add it to the skills list

**API sketch:**

```csharp
public delegate Task<(string? SelectedValue, bool IncludeSkill)> McpTemplateVariableSelector(
    string templateDescription,
    string variableName,
    IReadOnlyList<string> possibleValues,
    CancellationToken cancellationToken);

// Usage via builder:
var provider = new AgentSkillsProviderBuilder()
    .UseMcpSkills(mcpClient, options => {
        options.TemplateVariableSelector = async (description, variable, values, ct) =>
        {
            // Present to user, return selection
            var selected = PromptUser(variable, values);
            return (selected, IncludeSkill: selected is not null);
        };
    })
    .Build();
```

**Pros:**
- Simple implementation
- Easy to understand and use

**Cons:**
- Cannot be used in server-side scenarios where there is no interactive user at skill-discovery time
- Does not integrate with the agent's conversational flow

---

### Option 2: Integrate into Agent Conversation via `ChatClientAgent` Decorator

Model the template variable resolution as a request/response interaction within the agent's conversational loop.

**Flow:**

1. A `DelegatingAIAgent` decorator (e.g., `McpTemplateSkillResolutionAgent`) intercepts `RunAsync`/`RunStreamingAsync` calls and checks whether the inner agent has an `AgentSkillsProvider` with an `AgentMcpSkillsSource` containing unresolved template entries. The check is performed via `GetService<AgentMcpSkillsSource>()` on the `AgentSkillsProvider`, which delegates to a `GetService` method on the `AgentSkillsSource` base class.

2. The decorator calls an internal member on `AgentMcpSkillsSource` to get the list of `mcp-resource-template` entries from the index. The `AgentMcpSkillsSource` needs to be extended with an internal member that exposes unresolved template entries separately from concrete skills.

3. For each template entry, the decorator calls an internal member on `AgentMcpSkillsSource` to retrieve possible values for the template's variables via the MCP `completion/complete` API.

4. For each variable needing resolution, the decorator returns an `McpResourceTemplateValueRequestContent` (inherits from MEAI's `InputRequestContent`) in the agent response - bypassing the call to the inner agent. The content carries the template description, variable name, and possible values.

5. The user app receives the response, identifies the `McpResourceTemplateValueRequestContent` content type, and displays UI to the user showing the variable name and possible values, or forwards it further downstream if the user app is a service.

6. The user selects a value, and the user app calls the agent again with a corresponding `McpResourceTemplateValueResponseContent` (inherits from MEAI's `InputResponseContent`) containing the selected value. The `RequestId` property (inherited from the base classes) correlates the response with the original request.

7. The decorator identifies the response content and provides the resolved values to `AgentMcpSkillsSource` so it can use them when constructing concrete skills.

8. Having resolved all template variables, the decorator calls `RunAsync`/`RunStreamingAsync` on the inner agent.

9. The inner agent invokes the `AgentSkillsProvider`, which calls `AgentMcpSkillsSource.GetSkillsAsync()`. The source now has all resolved variable values and constructs concrete `AgentMcpSkill` instances from the resolved URIs, so it can provide the skill content if requested by the model.

**API sketch:**

```csharp
// New content types inheriting from MEAI's InputRequestContent/InputResponseContent:
public sealed class McpResourceTemplateValueRequestContent : InputRequestContent
{
    public string TemplateDescription { get; }
    public string VariableName { get; }
    public IReadOnlyList<string> PossibleValues { get; }
    public string TemplateUrl { get; }
}

public sealed class McpResourceTemplateValueResponseContent : InputResponseContent
{
    public string SelectedValue { get; }
    public string TemplateUrl { get; }
}

// Decorator usage:
var provider = new AgentSkillsProviderBuilder()
    .UseMcpSkills(mcpClient)
    .Build();

AIAgent agent = new ChatClientAgent(chatClient, new ChatClientAgentOptions
{
    AIContextProviders = [provider],
});
agent = new McpTemplateSkillResolutionAgent(agent);
```

**Pros:**
- Works in server-side scenarios
- Fits the existing `DelegatingAIAgent` decorator pattern
- Can be composed with other decorators (tool approval, etc.)

**Cons:**
- Complex implementation
- Requires user app awareness of the new content types
- Users need to know that an additional decorator is required for handling MCP template skills, in addition to registering the MCP skills source
- Resolved template variable values must be persisted across conversation turns so the decorator does not re-prompt on subsequent agent runs within the same session

**Note:** This writeup is high-level and may miss details that could change the design. A POC would be needed to validate the approach.

### Open Questions

1. **Completion API limit** - The MCP completion API returns at most 100 values per request and provides no offset/cursor mechanism for enumeration. If a variable has more than 100 possible values, it's unclear how to retrieve the rest - the API only supports prefix-based filtering (typeahead), not bulk pagination.

2. **Multi-variable templates** - A template like `skill://{org}/{product}/SKILL.md` has multiple variables. Should they be resolved sequentially (org first, then product - since product values may depend on org) or presented together?

3. **Caching** - Should resolved template values be saved in the `AgentSession` so the user isn't re-prompted on every agent run? How should they be persisted between sessions?

---

## Part 2: Direct Skill References

This part covers how to let the model read `skill://` URIs referenced directly (e.g., in an MCP server's `instructions`, in a resource, or in another skill's content) without being listed in `skill://index.json`.

### How MCP Skills and Relative Links Work Today

The `AgentMcpSkillsSource` discovers skills by reading the well-known `skill://index.json` resource from the MCP server:

```json
{
  "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
  "skills": [
    {
      "name": "unit-converter",
      "type": "skill-md",
      "description": "Convert between common units.",
      "url": "skill://unit-converter/SKILL.md"
    },
    {
      "name": "currency-converter",
      "type": "skill-md",
      "description": "Convert between world currencies using live rates.",
      "url": "skill://currency-converter/SKILL.md"
    }
  ]
}
```

For each `skill-md` entry it creates an `AgentMcpSkill` instance - frontmatter (name/description) comes straight from the entry. The `AgentSkillsProvider` lists the discovered skills in the model's context (name + description):

```xml
<available_skills>
  <skill>
    <name>unit-converter</name>
    <description>Convert between common units.</description>
  </skill>
  <skill>
    <name>currency-converter</name>
    <description>Convert between world currencies using live rates.</description>
  </skill>
</available_skills>
```

It also provides functions to the model so it can load a skill and access its resources:

```csharp
// Loads the full content of a specific skill.
load_skill(string skillName)

// Reads a resource associated with a skill (references, assets, dynamic data).
read_skill_resource(string skillName, string resourceName)
```

The model calls `load_skill("unit-converter")` and receives the skill content:

```markdown
---
name: unit-converter
description: Convert between common units.
---
## Usage

For the full conversion table, see references/units-table.md.
```

The skill body references `references/units-table.md` by relative path. The model calls `read_skill_resource("unit-converter", "references/units-table.md")` and receives the resource content:

```markdown
# Unit Conversion Table

| From  | To   | Factor  |
| miles | km   | 1.60934 |
| kg    | lbs  | 2.20462 |
```

### Direct Reference Examples

A `skill://` URI can appear in any of these locations:

**Server instructions** - the MCP server advertises a skill the model should load:

```text
Follow our coding standards. Load skill://code-standards/SKILL.md for details.
```

**A skill body** - a skill's `SKILL.md` links to a sibling resource:

```markdown
---
name: code-standards
description: Coding standards and conventions.
---
## Naming

Follow the naming rules in skill://code-standards/references/naming.md.
```

**A resource** - the linked resource holds the actual content:

```markdown
# Naming Rules

- Use PascalCase for public members and type names.
- Use camelCase for locals and parameters.
- Prefix interfaces with `I` (e.g. `ISkillReader`).
- Suffix async methods with `Async`.

For examples, see skill://code-standards/references/naming-examples.md.
```

How can the model access content by direct reference?

### Function for Reading Direct Skill References

### Option 1: Extend existing `load_skill` and `read_skill_resource` functions

```csharp
// Added optional 'origin' and a direct skill:// URI is passed in 'skillName'.
load_skill(string skillName, string? origin = null)

// Added optional 'origin', made 'skillName' optional, and a direct skill:// URI is passed in 'resourceName'.
read_skill_resource(string resourceName, string? skillName = null, string? origin = null)
```

The optional `origin` identifies the source/MCP server that should handle the direct URI.

| Case | Call |
|------|------|
| Load skill | `load_skill("commit-guidelines")` |
| Relative resource | `read_skill_resource("commit-guidelines", "examples/COMMIT_EXAMPLES.md")` |
| `skill://` link (skill) | `load_skill(skillName: "skill://commit-guidelines/SKILL.md", origin: "DirectRefServer")` |
| `skill://` link (resource) | `read_skill_resource(resourceName: "skill://commit-guidelines/examples/COMMIT_EXAMPLES.md", origin: "DirectRefServer")` |

**Pros:**

- No new functions added: existing tool surface stays at two functions.

**Cons:**

- Unreliable on some models (gpt-4o, gpt-4.1-mini): it often omits `origin` when it should not or calls the wrong function.
- Optional parameters create silent ambiguity - the model can pass `origin` for non-MCP skills or omit it for `skill://` URIs.

### Option 2 (Proposed): Add a dedicated `read_skill_uri` function alongside existing ones

```csharp
// Existing functions stay unchanged.
load_skill(string skillName)
read_skill_resource(string skillName, string resourceName)

// New function added alongside: reads content by direct skill:// URI.
read_skill_uri(string uri, string origin)
```

| Case | Call |
|------|------|
| Load skill | `load_skill("commit-guidelines")` |
| Relative resource | `read_skill_resource("commit-guidelines", "examples/COMMIT_EXAMPLES.md")` |
| `skill://` link (skill) | `read_skill_uri(uri: "skill://commit-guidelines/SKILL.md", origin:"DirectRefServer")` |
| `skill://` link (resource) | `read_skill_uri(uri: "skill://commit-guidelines/examples/COMMIT_EXAMPLES.md", origin: "DirectRefServer")` |

**Pros:**

- Purely additive - no changes to existing functions needed; `read_skill_uri` can be deferred and added later when direct `skill://` reference support is needed.
- Granular approval: each function can have its own approval gate (like the existing `ScriptApproval` for `run_skill_script`), making per-operation approval for skill loading, resource reading, and direct URI access straightforward to add.
- Both `uri` and `origin` are required - no silent misuse through optional parameters.
- Clean split: `load_skill`/`read_skill_resource` for named skills, `read_skill_uri` for `skill://` links - no parameter ambiguity.

**Cons:**

- Three read functions (`load_skill`, `read_skill_resource`, `read_skill_uri`), not counting `run_skill_script`: larger tool surface than a single-function design.

### Option 3: Collapse `load_skill` and `read_skill_resource` into a single `read_resource` function

```csharp
// Single entrypoint for all skill content. 'uri' is required; 'origin' is optional.
read_resource(string uri, string? origin = null)
```

- `uri` - what to read: a skill name, a relative resource path, or a `skill://` link.
- `origin` - determines how `uri` is interpreted:
  - **omitted** → load skill by name (`uri` is the skill name).
  - **skill name** → read a relative resource (`uri` is the path within that skill).
  - **server name** → read content by the `skill://` link (`uri` is handled by the source identified by the `[Origin: X]` marker).

Dispatch is ordered: null `origin` routes to Case 1; if `origin` names a known skill, routes to Case 2; otherwise tries to find an `ISkillUriReader` whose `CanRead` returns true for `origin` (Case 3).

| Case | Call |
|------|------|
| Load skill | `read_resource(uri: "commit-guidelines")` |
| Relative resource | `read_resource(uri: "examples/COMMIT_EXAMPLES.md", origin: "commit-guidelines")` |
| `skill://` link (skill) | `read_resource(uri: "skill://commit-guidelines/SKILL.md", origin: "DirectRefServer")` |
| `skill://` link (resource) | `read_resource(uri: "skill://commit-guidelines/examples/COMMIT_EXAMPLES.md", origin: "DirectRefServer")` |

**Pros:**

- Minimal tool surface: one read function instead of two or three (not counting `run_skill_script`) reduces token usage and gives the model fewer choices.

**Cons:**

- No per-operation approval: all cases (skill loading, resource reading, direct URI access) share one function, so approval cannot be scoped to individual operations.
- Unreliable on gpt-4.1-mini: omits `origin` when reading `skill://` links, passes skill name as `origin` when loading a plain skill (should be omitted), and hallucinates resource names (e.g. `API_SPECIFICATION.md`) that do not exist.


---

### Origin Marker

A `skill://` URI does not carry an origin, but the model needs to provide one when reading it. The `origin` is what routes the read call to the source that can handle the URI - the provider uses it to pick the matching source. Since the URI itself carries no such hint, the MCP source injects an `[Origin: ...]` marker wherever a `skill://` URI appears, so the model can read it back and pass it as the `origin` argument.

The marker is only added when the content actually contains `skill://` references. If a piece of content (server instructions, a skill body, or a resource) has no `skill://` URIs, there is nothing for the model to read back, so no marker is injected.

Into **server instructions**, which may mention `skill://` URIs directly:

```
[Origin: code-standards-server]
Follow our coding standards. Load skill://code-standards/SKILL.md for details.
```

Into **skill bodies**, since a `SKILL.md` may reference other `skill://` URIs (a resource file or a related skill):

```
[Origin: code-standards-server]
# Code Standards

For naming conventions, load skill://code-standards/references/naming.md.
```

Into **skill resources**, since a resource may itself reference further `skill://` URIs:

```
[Origin: code-standards-server]
# Naming Rules

- Use PascalCase for public members and type names.
- Use camelCase for locals and parameters.

For examples, see skill://code-standards/references/naming-examples.md.
```

---

### Read-by-URI Capability: Interface vs Base Class Virtual Methods

Now let's look at how an `AgentSkillsSource` can opt in to reading `skill://` URIs and signal that capability to the provider.

### Option 1: New `ISkillUriReader` interface

```csharp
public interface ISkillUriReader
{
    // Returns true if this reader can handle the given skill:// URI from the given origin.
    bool CanRead(string uri, string origin);

    // Reads and returns the content for the given skill:// URI.
    Task<object?> ReadByUriAsync(string uri, string origin, CancellationToken cancellationToken = default);
}
```

Sources that support direct `skill://` URI reads - such as `AgentMcpSkillsSource` - implement this interface to opt in.

The provider discovers readers via a service locator and dispatches to the first that can handle the URI:

```csharp
// Discover all registered readers.
var readers = source.GetService<IEnumerable<ISkillUriReader>>();

// Pick the first reader that can handle the URI.
var reader = readers.FirstOrDefault(r => r.CanRead(uri, origin))
    ?? throw new InvalidOperationException($"No reader can handle URI '{uri}' from origin '{origin}'.");

// Delegate the read to it.
return await reader.ReadByUriAsync(uri, origin, cancellationToken);
```

The provider may treat a source implementing `ISkillUriReader` as the signal to advertise `read_skill_uri`: if at least one registered source implements the interface, the function is exposed to the model; otherwise it is not.

### Option 2 (Proposed): Virtual methods on `AgentSkillsSource` base class

```csharp
public abstract class AgentSkillsSource
{
    // New members for reading by URI.

    // Whether this source can read by URI; drives whether read_skill_uri is advertised. Off by default.
    public virtual bool SupportsReadByUri => false;

    // Returns true if this source can handle the given skill:// URI from the given origin.
    public virtual bool CanReadByUri(string uri, string origin) => false;

    // Reads and returns the content for the given skill:// URI.
    public virtual Task<object?> ReadByUriAsync(string uri, string origin, CancellationToken cancellationToken = default)
        => Task.FromResult<object?>(null);

    // Existing member.
    public abstract Task<IList<AgentSkills>> GetSkillsAsync(CancellationToken cancellationToken = default);
}
```

Sources opt in by overriding, and the provider calls them directly:

```csharp
// AgentMcpSkillsSource opts in by overriding the virtuals.
public override bool SupportsReadByUri => true;

// Handles the URI when its origin matches this source's MCP server.
public override bool CanReadByUri(string uri, string origin)
    => string.Equals(origin, this.Origin, StringComparison.OrdinalIgnoreCase);

// Reads content by skill:// URI from the MCP server.
public override Task<string?> ReadByUriAsync(string uri, string origin, CancellationToken cancellationToken)
    => /* resolve uri via the MCP server identified by origin */;
```

All sources inherit the methods, so there is no type signal - `SupportsReadByUri` fills that role. The function is advertised when any registered source returns `true`.

### Comparison

| Aspect | Option 1: Interface | Option 2: Base class virtual methods |
|--------|---------------------|--------------------------------------|
| Discovery | Service locator | Direct call on source |
| Advertising signal | Interface implementation | `SupportsReadByUri` flag |
| Adding new members | Breaking change | Non-breaking |
| Complexity | Higher | Lower |

---

### Include MCP Server Instructions Into Agent Instructions

MCP server instructions may contain the `skill://` references the model needs, so we want to surface them in the agent's instructions. But they can also carry system prompts or behavioral directives irrelevant to the agent, polluting context - so inclusion is **opt-in** via the `IncludeServerInstructions` option:

```csharp
public sealed class AgentMcpSkillsSourceOptions
{
    // When true, the MCP server's instructions are injected into the agent instructions. Off by default.
    public bool IncludeServerInstructions { get; set; }
}

builder.UseMcpSkills(mcpClient, options => options.IncludeServerInstructions = true);
```

When enabled, the instructions travel alongside the discovered skills on `AgentSkillsResult`:

```csharp
public class AgentSkillsResult
{
    // The skills discovered from the source.
    public IList<AgentSkill> Skills { get; }

    // The MCP server instructions, when IncludeServerInstructions is enabled; otherwise null.
    public string? Instructions { get; }
}
```

The `AgentSkillsProvider` then appends them to its own skill-usage guidance when building the agent's instructions:

```csharp
var result = await source.GetSkillsAsync(cancellationToken);

var instructions = DefaultSkillsInstructionPrompt;
if (!string.IsNullOrWhiteSpace(result.Instructions))
{
    // Combine the provider's skill-usage guidance with the server instructions.
    instructions += Environment.NewLine + result.Instructions;
}
```

### Enabling Direct Skill References

Following direct `skill://` references is **disabled by default** and activated via an option. When enabled, the provider advertises the read function to the model, and the source injects the `[Origin: ...]` marker into all content provided by the MCP server that contains `skill://` references. When disabled, no function is advertised and no marker is injected.

```csharp
public sealed class AgentMcpSkillsSourceOptions
{
    public bool EnableDirectReferences { get; set; }
}

builder.UseMcpSkills(mcpClient, options => options.EnableDirectReferences = true);
```

## Decision Outcome

### Template Variable Resolution: Callback vs Decorator (Part 1)

**Postponed.** Deferring this decision until:

- We have a concrete list of scenarios that require template variable resolution.
- The skills-over-MCP spec is released (it is still a draft, so the design may change).
- There is a strong signal of demand from users or the ecosystem.

### Function for Reading Direct Skill References (Part 2)

**Postponed.** Leaning toward **Option 2 - dedicated `read_skill_uri` function alongside existing ones** (purely additive, and each function can have its own approval gate for granular per-operation approval), but deferring the decision until:

- The skills-over-MCP spec is released (it is still a draft, so the design may change).
- There is a strong signal of demand from users or the ecosystem.

### Read-by-URI Capability: Interface vs Base Class (Part 2)

**Postponed.** Leaning toward **Option 2 - virtual methods on `AgentSkillsSource`** (non-breaking, lower complexity, and a natural fit with the existing base class hierarchy), but deferring the decision until:

- The skills-over-MCP spec is released (it is still a draft, so the design may change).
- There is a strong signal of demand from users or the ecosystem.

The method naming (`SupportsReadByUri`, `CanReadByUri`, `ReadByUriAsync`) should also be abstracted a little more before adoption, so the same members can be reused when a similar direct-reference concept is needed for other skill types (e.g. file skills).

## References

- [SEP-2640: Skills Extension](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2640) - Draft proposal
- [SEP-2640 Implementation Guidelines: Model-Driven Resource Loading](https://github.com/modelcontextprotocol/experimental-ext-skills/blob/main/docs/sep-draft-skills-extension.md#hosts-model-driven-resource-loading)
- [MCP Completion API](https://modelcontextprotocol.io/specification/2025-11-25/server/utilities/completion) - Used for template variable resolution
- [MCP Resource Templates](https://modelcontextprotocol.io/specification/2025-11-25/server/resources#resource-templates)
- [Skills Over MCP Working Group](https://github.com/modelcontextprotocol/experimental-ext-skills)
- [Open Question #4: Multi-server skill dependencies](https://github.com/modelcontextprotocol/experimental-ext-skills/issues/39)
- [Anthropic Agent Skills - Overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) - Prior art: single skill entrypoint + generic file reads
- [Anthropic Agent Skills in the SDK](https://code.claude.com/docs/en/agent-sdk/skills) - The `Skill` tool exposed to the model
