---
status: proposed
date: 2026-03-19
contact: sergeymenshykh
---

# Agent Skills: Multi-Source Architecture

## Context and Problem Statement

The Agent Framework needs a skills system that lets agents discover and use domain-specific knowledge, reference documents, and executable scripts. Skills can originate from different sources — filesystem directories (SKILL.md files), inline C# code, or reusable class libraries — and the framework must support all three uniformly while allowing extensibility, composition, and filtering.

## Decision Drivers

- Skills must be definable from multiple sources: filesystem, inline code, and reusable classes
- Common abstractions are needed so the provider and builder work uniformly regardless of skill origin
- File-based scripts must support user-defined executors, enabling custom runtimes and languages; code/class-based scripts execute in-process as C# delegates
- Skills must be filterable so consumers can include or exclude specific skills based on defined criteria
- Multiple skill sources must be composable into a single provider

## Considered Options

- Single monolithic `FileAgentSkillsProvider` (current design)
- Multi-source architecture with abstract base types and builder pattern

## Architecture

### Model-Facing Tools

Skills are presented to the model as up to three tools that progressively disclose skill content. The system prompt lists available skill names and descriptions; the model then calls these tools on demand:

- **`load_skill(skillName)`** — returns the full skill body (instructions, listed resources, listed scripts)
- **`read_skill_resource(skillName, resourceName)`** — reads a supplementary resource (file-based or code-defined) associated with a skill
- **`run_skill_script(skillName, scriptName, arguments?)`** — executes a script associated with a skill; only registered when at least one skill contains scripts

Each tool delegates to the corresponding method on the resolved `AgentSkill` — calling `Resource.ReadAsync()` or `Script.ExecuteAsync()` respectively.

If skills have no scripts defined, the `run_skill_script` tool is **not advertised** to the model and instructions related to script execution are **not included** in the default skills instructions.

### Abstract Base Types

The architecture defines four abstract base types that all skill variants implement:

```csharp
public abstract class AgentSkill
{
    public abstract AgentSkillFrontmatter Frontmatter { get; }
    public abstract string Content { get; }
    public abstract IReadOnlyList<AgentSkillResource>? Resources { get; }
    public abstract IReadOnlyList<AgentSkillScript>? Scripts { get; }
}

public abstract class AgentSkillResource
{
    public string Name { get; }
    public string? Description { get; }
    public abstract Task<object?> ReadAsync(AIFunctionArguments arguments, CancellationToken cancellationToken = default);
}

public abstract class AgentSkillScript
{
    public string Name { get; }
    public string? Description { get; }
    public abstract Task<object?> ExecuteAsync(AgentSkill skill, AIFunctionArguments arguments, CancellationToken cancellationToken = default);
}

public abstract class AgentSkillsSource
{
    public abstract Task<IReadOnlyList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default);
}
```

Skill metadata is captured via `AgentSkillFrontmatter`:

```csharp
public sealed class AgentSkillFrontmatter
{
    public AgentSkillFrontmatter(string name, string description) { ... }

    public string Name { get; }
    public string Description { get; }
    public string? License { get; set; }
    public string? Compatibility { get; set; }
    public string? AllowedTools { get; set; }
    public IDictionary<string, string>? Metadata { get; set; }
}
```

The type hierarchy at a glance:

```
AgentSkill (abstract)               AgentSkillsSource (abstract)
├── AgentFileSkill                  ├── AgentFileSkillsSource
├── AgentCodeSkill                  ├── AgentCodeSkillsSource
└── AgentClassSkill (abstract)      ├── AgentClassSkillsSource
                                    └── CompositeAgentSkillsSource (Composition approach only)
AgentSkillResource (abstract)       AgentSkillScript (abstract)
├── AgentFileSkillResource          ├── AgentFileSkillScript
└── AgentCodeSkillResource          └── AgentCodeSkillScript
```

### File-Based Skills

File-based skills are authored as `SKILL.md` files on disk. Resources and scripts are discovered from corresponding subfolders within the skill directory.

**`AgentFileSkill`** — A filesystem-based skill discovered from a directory containing a `SKILL.md` file. Parsed from YAML frontmatter; content is the raw markdown body. Resources and scripts are discovered from files in corresponding subfolders:

```csharp
public sealed class AgentFileSkill : AgentSkill
{
    public AgentFileSkill(
        AgentSkillFrontmatter frontmatter, string content, string sourcePath,
        IReadOnlyList<AgentSkillResource>? resources = null,
        IReadOnlyList<AgentSkillScript>? scripts = null) { ... }
}
```

**`AgentFileSkillResource`** — A file-based skill resource. Reads content from a file on disk relative to the skill directory:

```csharp
public sealed class AgentFileSkillResource : AgentSkillResource
{
    public AgentFileSkillResource(string name, string path) { ... }

    public override Task<object?> ReadAsync(AIFunctionArguments arguments, CancellationToken cancellationToken = default)
    {
        return File.ReadAllTextAsync(path, cancellationToken);
    }
}
```

**`AgentFileSkillScript`** — A file-based skill script that represents a script file on disk. Delegates execution to an external `AgentFileSkillScriptExecutor` callback (e.g., runs Python/shell via `Process.Start`). Throws `NotSupportedException` if no executor is configured:

```csharp
public delegate Task<object?> AgentFileSkillScriptExecutor(
    AgentSkill skill, AgentFileSkillScript script,
    AIFunctionArguments arguments, CancellationToken cancellationToken);

public sealed class AgentFileSkillScript : AgentSkillScript
{
    private readonly AgentFileSkillScriptExecutor? _executor;

    internal AgentFileSkillScript(string name, string path, AgentFileSkillScriptExecutor? executor = null)
        : base(name) { ... }

    public override async Task<object?> ExecuteAsync(AgentSkill skill, AIFunctionArguments arguments, ...)
    {
        if (_executor == null)
        {
            throw new NotSupportedException($"File-based script '{Name}' requires an external executor and cannot be executed directly.");
        }

        return await _executor(skill, this, arguments, cancellationToken);
    }
}
```

The executor can be provided at the **provider level** via `AgentSkillsProviderBuilder.WithFileScriptExecutor(executor)` and optionally overridden for a **particular file skill** or for a **set of skills** at the file skill source level, giving fine-grained control over how different scripts are executed.

**`AgentFileSkillsSource`** — A skill source that discovers skills from filesystem directories containing `SKILL.md` files. Recursively scans directories (max 2 levels), validates frontmatter, and enforces path traversal and symlink security checks:

```csharp
public sealed partial class AgentFileSkillsSource : AgentSkillsSource
{
    public AgentFileSkillsSource(
        IEnumerable<string> skillPaths,
        ILoggerFactory? loggerFactory = null,
        AgentFileSkillScriptExecutor? scriptExecutor = null,
        IEnumerable<string>? allowedResourceExtensions = null,
        IEnumerable<string>? allowedScriptExtensions = null) { ... }
}
```

**Example** — A file-based skill on disk and how it is added to a source:

```
skills/
└── unit-converter/
    ├── SKILL.md               # frontmatter + instructions
    ├── resources/
    │   └── conversion-table.csv   # discovered as a resource
    └── scripts/
        └── convert.py             # discovered as a script
```

```csharp
var source = new AgentFileSkillsSource(skillPaths: ["./skills"], scriptExecutor: SubprocessExecutor.RunAsync);

var provider = new AgentSkillsProvider(source);

AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions
{
    AIContextProviders = [provider],
});
```

### Code-Defined Skills

Code-defined skills are built programmatically in C#.

**`AgentCodeSkill`** — A skill defined entirely in code. Resources can be static values or functions; scripts are always functions. Constructed with name, description, and instructions, then extended with resources and scripts:

```csharp
public sealed class AgentCodeSkill : AgentSkill
{
    public AgentCodeSkill(string name, string description, string instructions, string? license = null, string? compatibility = null, ...) { ... }
    public AgentCodeSkill(AgentSkillFrontmatter frontmatter, string instructions) { ... }

    public AgentCodeSkill AddResource(object value, string name, string? description = null);
    public AgentCodeSkill AddResource(Delegate handler, string name, string? description = null);
    public AgentCodeSkill AddScript(Delegate handler, string name, string? description = null);
}
```

**`AgentCodeSkillResource`** — A code-defined skill resource. Wraps either a static value or a function:

```csharp
public sealed class AgentCodeSkillResource : AgentSkillResource
{
    private readonly AIFunction? _function;
    private readonly object? _staticValue;

    public AgentCodeSkillResource(object value, string name, string? description = null)
        : base(name, description)
    {
        _staticValue = value;
    }

    public AgentCodeSkillResource(Delegate handler, string name, string? description = null)
        : base(name, description)
    {
        _function = AIFunctionFactory.Create(handler, name: name);
    }

    public override Task<object?> ReadAsync(AIFunctionArguments arguments, CancellationToken cancellationToken = default)
    {
        if (_function is not null)
        {
            return _function.InvokeAsync(arguments, cancellationToken);
        }

        return Task.FromResult<object?>(_staticValue);
    }
}
```

**`AgentCodeSkillScript`** — A code-defined skill script. Wraps a function and provided JSON schema:

```csharp
public sealed class AgentCodeSkillScript : AgentSkillScript
{
    private readonly AIFunction _function;

    public AgentCodeSkillScript(Delegate handler, string name, string? description = null)
        : base(name, description)
    {
        _function = AIFunctionFactory.Create(handler, name: name);
    }

    public JsonElement? ParametersSchema => _function.JsonSchema;

    public override async Task<object?> ExecuteAsync(AgentSkill skill, AIFunctionArguments arguments, ...)
    {
        return await _function.InvokeAsync(arguments, cancellationToken);
    }
}
```

**`AgentCodeSkillsSource`** — A skill source that holds code-defined `AgentCodeSkill` instances:

```csharp
public sealed class AgentCodeSkillsSource : AgentSkillsSource
{
    public AgentCodeSkillsSource(
        IEnumerable<AgentCodeSkill> skills,
        ILoggerFactory? loggerFactory = null) { ... }
}
```

**Example** — Creating a code-defined skill with a resource and script, then adding it to a source:

```csharp
var skill = new AgentCodeSkill(
        name: "unit-converter",
        description: "Converts between measurement units.",
        instructions: """
            Use this skill to convert values between metric and imperial units.
            Refer to the conversion-table resource for supported unit pairs.
            Run the convert script to perform conversions.
            """
    )
    .AddResource("kg=2.205lb, m=3.281ft, L=0.264gal", "conversion-table", "Supported unit pairs")
    .AddScript(Convert, "convert", "Converts a value between units");

var source = new AgentCodeSkillsSource([skill]);

var provider = new AgentSkillsProvider(source);

AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions
{
    AIContextProviders = [provider],
});

static string Convert(double value, double factor)
    => JsonSerializer.Serialize(new { result = Math.Round(value * factor, 4) });
```

### Class-Based Skills

Class-based skills are designed for packaging skills as reusable libraries. Users subclass `AgentClassSkill` and override properties.

**`AgentClassSkill`** — An abstract base class for defining skills as reusable C# classes that bundle all skill components (frontmatter, instructions, resources, scripts) together. Designed for packaging skills as distributable libraries:

```csharp
public abstract class AgentClassSkill : AgentSkill
{
    public abstract string Instructions { get; }

    // Content is auto-synthesized from Frontmatter + Instructions + Resources + Scripts
    public override string Content =>
        SkillContentBuilder.BuildContent(Frontmatter.Name, Frontmatter.Description,
            SkillContentBuilder.BuildBody(Instructions, Resources, Scripts));
}
```

**`AgentClassSkillsSource`** — A skill source that holds class-based `AgentClassSkill` instances:

```csharp
public sealed class AgentClassSkillsSource : AgentSkillsSource
{
    public AgentClassSkillsSource(
        IEnumerable<AgentClassSkill> skills,
        ILoggerFactory? loggerFactory = null) { ... }
}
```

**Example** — Defining a class-based skill and adding it to a source:

```csharp
public class UnitConverterSkill : AgentClassSkill
{
    public override AgentSkillFrontmatter Frontmatter { get; } =
        new("unit-converter", "Converts between measurement units.");

    public override string Instructions => """
        Use this skill to convert values between metric and imperial units.
        Refer to the conversion-table resource for supported unit pairs.
        Run the convert script to perform conversions.
        """;

    public override IReadOnlyList<AgentSkillResource>? Resources { get; } =
    [
        new AgentCodeSkillResource("kg=2.205lb, m=3.281ft", "conversion-table"),
    ];

    public override IReadOnlyList<AgentSkillScript>? Scripts { get; } =
    [
        new AgentCodeSkillScript(Convert, "convert"),
    ];

    private static string Convert(double value, double factor)
        => JsonSerializer.Serialize(new { result = Math.Round(value * factor, 4) });
}

var source = new AgentClassSkillsSource([new UnitConverterSkill()]);

var provider = new AgentSkillsProvider(source);

AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions
{
    AIContextProviders = [provider],
});
```

## Filtering, Caching, and Deduplication

The following subsections present alternative approaches for handling filtering, caching, and deduplication of skills across multiple sources.

### Via Composition

In this approach, the `AgentSkillsProvider` accepts a **single** `AgentSkillsSource`. Multiple sources are composed externally via `CompositeAgentSkillsSource`, and cross-cutting concerns like filtering, caching, and deduplication are implemented as **source decorators** — wrappers around any `AgentSkillsSource` that intercept `GetSkillsAsync()`.

**`CompositeAgentSkillsSource`** — Aggregates multiple child sources into a single flat list. The composite source can optionally load skills from all sources in parallel:

```csharp
public sealed class CompositeAgentSkillsSource : AgentSkillsSource
{
    public override async Task<IReadOnlyList<AgentSkill>> GetSkillsAsync(...)
    {
        var allSkills = new List<AgentSkill>();
        foreach (var source in _sources)
        {
            var skills = await source.GetSkillsAsync(cancellationToken);
            allSkills.AddRange(skills);
        }
        return allSkills;
    }
}
```

**`FilteringSkillsSource`** — A decorator that applies filter/transform logic before returning results. The decorator pattern keeps filtering orthogonal to source implementations and allows composing multiple filters:

```csharp
public sealed class FilteringSkillsSource : AgentSkillsSource
{
    private readonly AgentSkillsSource _inner;
    private readonly Func<AgentSkill, bool> _filter;

    public FilteringSkillsSource(AgentSkillsSource inner, Func<AgentSkill, bool> filter)
    {
        _inner = inner;
        _filter = filter;
    }

    public override async Task<IReadOnlyList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
    {
        var skills = await _inner.GetSkillsAsync(cancellationToken);
        return skills.Where(_filter).ToList();
    }
}
```

**`CachingSkillsSource`** — A decorator that caches skills after the first load, keeping the provider stateless and giving consumers control over caching granularity per source. For example, file-based skills (expensive to discover) can be cached while code-defined skills remain uncached:

```csharp
public sealed class CachingSkillsSource : AgentSkillsSource
{
    private readonly AgentSkillsSource _inner;
    private IReadOnlyList<AgentSkill>? _cached;

    public CachingSkillsSource(AgentSkillsSource inner)
    {
        _inner = inner;
    }

    public override async Task<IReadOnlyList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
    {
        return _cached ??= await _inner.GetSkillsAsync(cancellationToken);
    }
}
```

**Deduplication** can similarly be implemented as a decorator that deduplicates by name (case-insensitive, first-one-wins) and logs a warning for skipped duplicates.

**Example** — Combining file-based and code-defined sources with filtering and caching:

```csharp
var fileSource = new CachingSkillsSource(new AgentFileSkillsSource(["./skills"]));
var codeSource = new AgentCodeSkillsSource([myCodeSkill]);

var compositeSource = new FilteringSkillsSource(
    new CompositeAgentSkillsSource([fileSource, codeSource]),
    filter: s => s.Frontmatter.Name != "internal");

var provider = new AgentSkillsProvider(compositeSource);

AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions
{
    AIContextProviders = [provider],
});
```

**Pros:**
- Clean single-responsibility: the provider serves skills, sources provide them.
- Caching, filtering, and deduplication are composable as source decorators — each concern is a separate, testable wrapper.

**Cons:**
- DI is less flexible: multiple `AgentSkillsSource` implementations registered in the container cannot be auto-injected into the provider. The consumer must manually compose them via `CompositeAgentSkillsSource`.
- Increased public API surface: requires additional public classes (`CompositeAgentSkillsSource`, caching decorators, filtering decorators) that consumers need to learn and use.

### Via AgentSkillsProvider

In this approach, the `AgentSkillsProvider` accepts **`IEnumerable<AgentSkillsSource>`** and handles aggregation, filtering, caching, and deduplication internally. There is no need for `CompositeAgentSkillsSource` or decorator classes — these concerns are built into the provider.

The provider aggregates skills from all registered sources, deduplicates by name (case-insensitive, first-one-wins), caches the result after the first load, and optionally applies filtering via a predicate on `AgentSkillsProviderOptions`. Duplicate skill names are logged as warnings.

**Example** — Registering multiple sources directly with the provider:

```csharp
var fileSource = new AgentFileSkillsSource(["./skills"]);
var codeSource = new AgentCodeSkillsSource([myCodeSkill]);

var provider = new AgentSkillsProvider(
    sources: [fileSource, codeSource],
    options: new AgentSkillsProviderOptions
    {
        Filter = s => s.Frontmatter.Name != "internal",
    });

AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions
{
    AIContextProviders = [provider],
});
```

**Pros:**
- DI-friendly: register multiple `AgentSkillsSource` implementations in the container, and they are all auto-injected into `AgentSkillsProvider` via `IEnumerable<AgentSkillsSource>`.
- Smaller public API surface: no need for `CompositeAgentSkillsSource`, caching decorators, or filtering decorator classes — these concerns are handled internally by the provider.

**Cons:**
- The provider takes on multiple responsibilities — aggregation, caching, deduplication, and filtering.
- Less granular caching control: caching is all-or-nothing across sources rather than per-source as with decorators.
- Less extensible: new behaviors (e.g., ordering, TTL expiration) require modifying the provider rather than adding a decorator.

### Builder Pattern

**`AgentSkillsProviderBuilder`** provides a fluent API for composing skills from multiple sources. The builder centralizes configuration — script executors, approval callbacks, prompt templates, and filtering — so consumers don't need to know the underlying source types.

The builder internally decides how to wire up the object graph: it creates the appropriate source instances, applies caching and filtering, and returns a fully configured `AgentSkillsProvider`. This keeps the setup code concise while still allowing fine-grained control when needed.

**Example** — Using the builder to combine multiple source types with configuration:

```csharp
var provider = new AgentSkillsProviderBuilder()
    .AddFileSkills("./skills")                           // file-based source
    .AddCodeSkills(codeSkill)                            // code-defined source
    .AddClassSkills(new ClassSkill())                    // class-based source
    .WithFileScriptExecutor(SubprocessExecutor.RunAsync) // script runner
    .WithScriptApproval()                                // optional human-in-the-loop
    .WithPromptTemplate(customTemplate)                  // optional prompt customization
    .Build();

AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions
{
    AIContextProviders = [provider],
});
```

## Decision Outcome
