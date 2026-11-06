status: proposed
date: 2026-03-23
contact: sergeymenshykh
deciders: rbarreto, westey-m, eavanvalkenburg
---

# Agent Skills: Multi-Source Architecture

## Context and Problem Statement

The Agent Framework needs a skills system that lets agents discover and use domain-specific knowledge, reference documents, and executable scripts. Skills can originate from different sources — filesystem directories (SKILL.md files), inline C# code, or reusable class libraries — and the framework must support all three uniformly while allowing extensibility, composition, and filtering.

## Decision Drivers

- Skills must be definable from multiple sources: filesystem, inline code, reusable classes, etc
- Common abstractions are needed so the provider and builder work uniformly regardless of skill origin
- File-based scripts must support user-defined executors, enabling custom runtimes and languages; code/class-based scripts execute in-process as C# delegates
- Skills must be filterable so consumers can include or exclude specific skills based on defined criteria
- Multiple skill sources must be composable into a single provider
- It must be possible to add custom skill sources (e.g., databases, REST APIs, package registries) by implementing a common abstraction

## Architecture

### Model-Facing Tools

Skills are presented to the model as up to three tools that progressively disclose skill content. The system prompt lists available skill names and descriptions; the model then calls these tools on demand:

- **`load_skill(skillName)`** — returns the full skill body (instructions, listed resources, listed scripts)
- **`read_skill_resource(skillName, resourceName)`** — reads a supplementary resource (file-based or code-defined) associated with a skill
- **`run_skill_script(skillName, scriptName, arguments?)`** — executes a script associated with a skill; only registered when at least one skill contains scripts

Each tool delegates to the corresponding method on the resolved `AgentSkill` — calling `Resource.ReadAsync()` or `Script.RunAsync()` respectively.

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
    public abstract Task<object?> ReadAsync(IServiceProvider? serviceProvider = null, CancellationToken cancellationToken = default);
}

public abstract class AgentSkillScript
{
    public string Name { get; }
    public string? Description { get; }
    public abstract Task<object?> RunAsync(AgentSkill skill, AIFunctionArguments arguments, CancellationToken cancellationToken = default);
}

public abstract class AgentSkillsSource
{
    public abstract Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default);
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
    public AdditionalPropertiesDictionary? Metadata { get; set; }
}
```

The type hierarchy at a glance:

```
AgentSkill (abstract)                   AgentSkillsSource (abstract)
├── AgentFileSkill                      ├── AgentFileSkillsSource          (public)
└── [Programmatic]                      ├── AgentInMemorySkillsSource      (public)
    ├── AgentInlineSkill                ├── AggregatingAgentSkillsSource     (public)
    └── AgentClassSkill (abstract)      └── DelegatingAgentSkillsSource    (abstract, public)
                                            ├── FilteringAgentSkillsSource  (public)
AgentSkillResource (abstract)               ├── CachingAgentSkillsSource    (public)
├── AgentFileSkillResource                  └── DeduplicatingAgentSkillsSource (public)
└── AgentInlineSkillResource
                                        AgentSkillScript (abstract)
                                        ├── AgentFileSkillScript
                                        └── AgentInlineSkillScript
```

There are two top-level categories of skills:

1. **File-Based Skills** — discovered from `SKILL.md` files on the filesystem. Resources and scripts are files in subdirectories.
2. **Programmatic Skills** — defined in C# code. These are further divided into:
   - **Inline Skills** — built at runtime via the `AgentInlineSkill` class and its fluent API. Ideal for quick, agent-specific skill definitions.
   - **Class-Based Skills** — defined as reusable C# classes that subclass `AgentClassSkill`. Ideal for packaging skills as shared libraries or NuGet packages.

Both programmatic skill types use `AgentInlineSkillResource` and `AgentInlineSkillScript` for their resources and scripts. They are typically served by `AgentInMemorySkillsSource`, which accepts any `AgentSkill` and is not limited to programmatic skills.

### File-Based Skills

File-based skills are authored as `SKILL.md` files on disk. Resources and scripts are discovered from corresponding subfolders within the skill directory.

**`AgentFileSkill`** — A filesystem-based skill discovered from a directory containing a `SKILL.md` file. Parsed from YAML frontmatter; content is the raw markdown body. Resources and scripts are discovered from files in corresponding subfolders:

```csharp
public sealed class AgentFileSkill : AgentSkill
{
    internal AgentFileSkill(
        AgentSkillFrontmatter frontmatter, string content, string path,
        IReadOnlyList<AgentSkillResource>? resources = null,
        IReadOnlyList<AgentSkillScript>? scripts = null) { ... }
}
```

**`AgentFileSkillResource`** — A file-based skill resource. Reads content from a file on disk relative to the skill directory:

```csharp
internal sealed class AgentFileSkillResource : AgentSkillResource
{
    public AgentFileSkillResource(string name, string fullPath) { ... }

    public string FullPath { get; }

    public override Task<object?> ReadAsync(IServiceProvider? serviceProvider = null, CancellationToken cancellationToken = default)
    {
        return File.ReadAllTextAsync(FullPath, Encoding.UTF8, cancellationToken);
    }
}
```

**`AgentFileSkillScript`** — A file-based skill script that represents a script file on disk. Delegates execution to an external `AgentFileSkillScriptRunner` callback (e.g., runs Python/shell via `Process.Start`). Throws `NotSupportedException` if no executor is configured:

```csharp
public delegate Task<object?> AgentFileSkillScriptRunner(
    AgentFileSkill skill, AgentFileSkillScript script,
    AIFunctionArguments arguments, CancellationToken cancellationToken);

public sealed class AgentFileSkillScript : AgentSkillScript
{
    private readonly AgentFileSkillScriptRunner _executor;

    internal AgentFileSkillScript(string name, string fullPath, AgentFileSkillScriptRunner executor)
        : base(name) { ... }

    public override async Task<object?> RunAsync(AgentSkill skill, AIFunctionArguments arguments, ...)
    {

        return await _executor(fileSkill, this, arguments, cancellationToken);
    }
}
```

The executor can be provided at the **provider level** via `AgentSkillsProviderBuilder.UseFileScriptRunner(executor)` and optionally overridden for a **particular file skill** or for a **set of skills** at the file skill source level, giving fine-grained control over how different scripts are executed.

**`AgentFileSkillsSource`** — A skill source that discovers skills from filesystem directories containing `SKILL.md` files. Recursively scans directories (max 2 levels), validates frontmatter, and enforces path traversal and symlink security checks:

```csharp
public sealed partial class AgentFileSkillsSource : AgentSkillsSource
{
    public AgentFileSkillsSource(
        IEnumerable<string> skillPaths,
        AgentFileSkillScriptRunner scriptRunner,
        AgentFileSkillsSourceOptions? options = null,
        ILoggerFactory? loggerFactory = null) { ... }
}
```

**`AgentFileSkillsSourceOptions`** — Configuration options for `AgentFileSkillsSource`. Allows customizing the allowed file extensions for resources and scripts without adding constructor parameters:

```csharp
public sealed class AgentFileSkillsSourceOptions
{
    public IEnumerable<string>? AllowedResourceExtensions { get; set; }
    public IEnumerable<string>? AllowedScriptExtensions { get; set; }
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
var source = new AgentFileSkillsSource(skillPaths: ["./skills"], scriptRunner: SubprocessScriptRunner.RunAsync);

var provider = new AgentSkillsProvider(source);

AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions
{
    AIContextProviders = [provider],
});
```

### Programmatic Skills

Programmatic skills are defined in C# code rather than discovered from the filesystem. There are two kinds: **inline** and **class-based**. Both use `AgentInlineSkillResource` and `AgentInlineSkillScript` for resources and scripts, and are held by a single `AgentInMemorySkillsSource`.

**`AgentInMemorySkillsSource`** — A general-purpose skill source that holds any `AgentSkill` instances in memory. Although commonly used for programmatic skills (`AgentInlineSkill` and `AgentClassSkill`), it accepts any `AgentSkill` subclass and is not restricted to code-defined skills:

```csharp
public sealed class AgentInMemorySkillsSource : AgentSkillsSource
{
    public AgentInMemorySkillsSource(
        IEnumerable<AgentSkill> skills,
        ILoggerFactory? loggerFactory = null) { ... }
}
```

#### Inline Skills

Inline skills are built at runtime via the `AgentInlineSkill` class and its fluent API. They are ideal for quick, agent-specific skill definitions where a full class hierarchy would be overkill.

**`AgentInlineSkill`** — A skill defined entirely in code. Resources can be static values or functions; scripts are always functions. Constructed with name, description, and instructions, then extended with resources and scripts:

```csharp
public sealed class AgentInlineSkill : AgentSkill
{
    public AgentInlineSkill(string name, string description, string instructions, string? license = null, string? compatibility = null, ...) { ... }
    public AgentInlineSkill(AgentSkillFrontmatter frontmatter, string instructions) { ... }

    public AgentInlineSkill AddResource(object value, string name, string? description = null);
    public AgentInlineSkill AddResource(Delegate handler, string name, string? description = null);
    public AgentInlineSkill AddScript(Delegate handler, string name, string? description = null);
}
```

**`AgentInlineSkillResource`** — A skill resource that wraps a static value:

```csharp
public sealed class AgentInlineSkillResource : AgentSkillResource
{
    public AgentInlineSkillResource(object value, string name, string? description = null)
        : base(name, description)
    {
        _value = value;
    }

    public override Task<object?> ReadAsync(IServiceProvider? serviceProvider = null, CancellationToken cancellationToken = default)
    {
        return Task.FromResult<object?>(_value);
    }
}
```

**`AgentInlineSkillResource`** — A skill resource backed by a delegate. The delegate is invoked via an `AIFunction` each time `ReadAsync` is called, producing a dynamic (computed) value:

```csharp
public sealed class AgentInlineSkillResource : AgentSkillResource
{
    public AgentInlineSkillResource(Delegate handler, string name, string? description = null)
        : base(name, description)
    {
        _function = AIFunctionFactory.Create(handler, name: name);
    }

    public override async Task<object?> ReadAsync(IServiceProvider? serviceProvider = null, CancellationToken cancellationToken = default)
    {
        return await _function.InvokeAsync(new AIFunctionArguments() { Services = serviceProvider }, cancellationToken);
    }
}
```

**`AgentInlineSkillScript`** — A skill script backed by a delegate via an `AIFunction`:

```csharp
public sealed class AgentInlineSkillScript : AgentSkillScript
{
    private readonly AIFunction _function;

    public AgentInlineSkillScript(Delegate handler, string name, string? description = null)
        : base(name, description)
    {
        _function = AIFunctionFactory.Create(handler, name: name);
    }

    public JsonElement? ParametersSchema => _function.JsonSchema;

    public override async Task<object?> RunAsync(AgentSkill skill, AIFunctionArguments arguments, ...)
    {
        return await _function.InvokeAsync(arguments, cancellationToken);
    }
}
```

**Example** — Creating an inline skill with a resource and script, then adding it to a source:

```csharp
var skill = new AgentInlineSkill(
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

var source = new AgentInMemorySkillsSource([skill]);

var provider = new AgentSkillsProvider(source);

AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions
{
    AIContextProviders = [provider],
});

static string Convert(double value, double factor)
    => JsonSerializer.Serialize(new { result = Math.Round(value * factor, 4) });
```

#### Class-Based Skills

Class-based skills are designed for packaging skills as reusable libraries. Users subclass `AgentClassSkill` and override properties. Unlike inline skills, class-based skills are self-contained, can live in shared libraries or NuGet packages, and are well-suited for dependency injection.

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
        new AgentInlineSkillResource("kg=2.205lb, m=3.281ft", "conversion-table"),
    ];

    public override IReadOnlyList<AgentSkillScript>? Scripts { get; } =
    [
        new AgentInlineSkillScript(Convert, "convert"),
    ];

    private static string Convert(double value, double factor)
        => JsonSerializer.Serialize(new { result = Math.Round(value * factor, 4) });
}

var source = new AgentInMemorySkillsSource([new UnitConverterSkill()]);

var provider = new AgentSkillsProvider(source);

AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions
{
    AIContextProviders = [provider],
});
```

## Filtering, Caching, and Deduplication

The following subsections present alternative approaches for handling filtering, caching, and deduplication of skills across multiple sources.

### Via Composition

In this approach, the `AgentSkillsProvider` accepts a **single** `AgentSkillsSource`. Multiple sources are composed externally via an aggregate source, and cross-cutting concerns like filtering, caching, and deduplication are implemented as **source decorators** — subclasses of `DelegatingAgentSkillsSource` that intercept `GetSkillsAsync()`.

**`FilteringAgentSkillsSource`** — A decorator that applies filter logic before returning results. The decorator pattern keeps filtering orthogonal to source implementations and allows composing multiple filters:

```csharp
public sealed class FilteringAgentSkillsSource : DelegatingAgentSkillsSource
{
    private readonly Func<AgentSkill, bool> _predicate;

    public FilteringAgentSkillsSource(AgentSkillsSource innerSource, Func<AgentSkill, bool> predicate)
        : base(innerSource)
    {
        _predicate = predicate;
    }

    public override async Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
    {
        var skills = await this.InnerSource.GetSkillsAsync(cancellationToken);
        return skills.Where(_predicate).ToList();
    }
}
```

**`CachingAgentSkillsSource`** — A decorator that caches skills after the first load, keeping the provider stateless and giving consumers control over caching granularity per source. For example, file-based skills (expensive to discover) can be cached while code-defined skills remain uncached:

```csharp
public sealed class CachingAgentSkillsSource : DelegatingAgentSkillsSource
{
    private IList<AgentSkill>? _cached;

    public CachingAgentSkillsSource(AgentSkillsSource innerSource)
        : base(innerSource)
    {
    }

    public override async Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
    {
        return _cached ??= await this.InnerSource.GetSkillsAsync(cancellationToken);
    }
}
```

**Deduplication** is similarly implemented as a decorator (`DeduplicatingAgentSkillsSource`) that deduplicates by name (case-insensitive, first-one-wins) and logs a warning for skipped duplicates.

**Example** — Combining file-based and code-defined sources with filtering and caching:

```csharp
var fileSource = new CachingAgentSkillsSource(new AgentFileSkillsSource(["./skills"]));
var codeSource = new AgentInMemorySkillsSource([myCodeSkill]);

var compositeSource = new FilteringAgentSkillsSource(
    new AggregatingAgentSkillsSource([fileSource, codeSource]),
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
- DI is less flexible: multiple `AgentSkillsSource` implementations registered in the container cannot be auto-injected into the provider. The consumer must manually compose them via an aggregate source.
- Increased public API surface: requires additional public classes (aggregate source, caching decorators, filtering decorators) that consumers need to learn and use.

### Via AgentSkillsProvider

In this approach, the `AgentSkillsProvider` accepts **`IEnumerable<AgentSkillsSource>`** and handles aggregation, filtering, caching, and deduplication internally.

The provider aggregates skills from all registered sources, deduplicates by name (case-insensitive, first-one-wins), caches the result after the first load, and optionally applies filtering via a predicate on `AgentSkillsProviderOptions`. Duplicate skill names are logged as warnings.

**Example** — Registering multiple sources directly with the provider:

```csharp
// Conceptual example — in practice, use AgentSkillsProviderBuilder
var fileSource = new AgentFileSkillsSource(["./skills"]);
var codeSource = new AgentInMemorySkillsSource([myCodeSkill]);

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
- Smaller public API surface: no need for aggregate source, caching decorators, or filtering decorator classes — these concerns are handled internally by the provider.

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
    .UseFileSkill("./skills")                           // file-based source
    .UseInlineSkills(codeSkill)                            // code-defined source
    .UseClassSkills(new ClassSkill())                    // class-based source
    .UseFileScriptRunner(SubprocessScriptRunner.RunAsync) // script runner
    .UseScriptApproval()                                // optional human-in-the-loop
    .UsePromptTemplate(customTemplate)                  // optional prompt customization
    .UseFilter(s => s.Frontmatter.Name != "internal")   // optional skill filtering
    .Build();

AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions
{
    AIContextProviders = [provider],
});
```

## Adding a Custom Skill Type

The skills framework is designed for extensibility. While file-based and inline skills cover common
scenarios, you can introduce entirely new skill types by subclassing the four base classes:

| Base class            | Purpose                                             |
|-----------------------|-----------------------------------------------------|
| `AgentSkillsSource`   | Discovers and loads skills from a particular origin  |
| `AgentSkill`          | Holds metadata, content, resources, and scripts      |
| `AgentSkillResource`  | Provides supplementary content to a skill            |
| `AgentSkillScript`    | Represents an executable action within a skill       |

The example below implements a **cloud-based skill type** where skills, resources, and scripts are
all stored in and executed through a remote cloud service (e.g., Azure Blob Storage + Azure Functions).

### Step 1 — Define a custom resource

A `CloudSkillResource` reads resource content from a cloud storage endpoint instead of the local
filesystem:

```csharp
/// <summary>
/// A skill resource backed by a cloud storage endpoint.
/// </summary>
public sealed class CloudSkillResource : AgentSkillResource
{
    private readonly HttpClient _httpClient;

    public CloudSkillResource(string name, Uri blobUri, HttpClient httpClient, string? description = null)
        : base(name, description)
    {
        BlobUri = blobUri ?? throw new ArgumentNullException(nameof(blobUri));
        _httpClient = httpClient ?? throw new ArgumentNullException(nameof(httpClient));
    }

    /// <summary>
    /// Gets the URI of the cloud blob that holds this resource's content.
    /// </summary>
    public Uri BlobUri { get; }

    /// <inheritdoc/>
    public override async Task<object?> ReadAsync(
        IServiceProvider? serviceProvider = null,
        CancellationToken cancellationToken = default)
    {
        return await _httpClient.GetStringAsync(BlobUri, cancellationToken).ConfigureAwait(false);
    }
}
```

### Step 2 — Define a custom script

A `CloudSkillScript` executes a script by calling a cloud function endpoint, passing arguments as
the request body:

```csharp
/// <summary>
/// A skill script executed via a cloud function endpoint.
/// </summary>
public sealed class CloudSkillScript : AgentSkillScript
{
    private readonly HttpClient _httpClient;

    public CloudSkillScript(string name, Uri functionUri, HttpClient httpClient, string? description = null)
        : base(name, description)
    {
        FunctionUri = functionUri ?? throw new ArgumentNullException(nameof(functionUri));
        _httpClient = httpClient ?? throw new ArgumentNullException(nameof(httpClient));
    }

    /// <summary>
    /// Gets the URI of the cloud function that runs this script.
    /// </summary>
    public Uri FunctionUri { get; }

    /// <inheritdoc/>
    public override async Task<object?> RunAsync(
        AgentSkill skill,
        AIFunctionArguments arguments,
        CancellationToken cancellationToken = default)
    {
        var json = JsonSerializer.Serialize(arguments);
        using var content = new StringContent(json, Encoding.UTF8, "application/json");
        var response = await _httpClient.PostAsync(FunctionUri, content, cancellationToken)
            .ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
    }
}
```

### Step 3 — Define a custom skill

A `CloudSkill` bundles cloud-specific metadata (e.g., the base endpoint) with the standard skill
shape:

```csharp
/// <summary>
/// An <see cref="AgentSkill"/> whose content, resources, and scripts are stored in a cloud service.
/// </summary>
public sealed class CloudSkill : AgentSkill
{
    public CloudSkill(
        AgentSkillFrontmatter frontmatter,
        string content,
        Uri endpoint,
        IReadOnlyList<AgentSkillResource>? resources = null,
        IReadOnlyList<AgentSkillScript>? scripts = null)
    {
        Frontmatter = frontmatter ?? throw new ArgumentNullException(nameof(frontmatter));
        Content = content ?? throw new ArgumentNullException(nameof(content));
        Endpoint = endpoint ?? throw new ArgumentNullException(nameof(endpoint));
        Resources = resources;
        Scripts = scripts;
    }

    /// <inheritdoc/>
    public override AgentSkillFrontmatter Frontmatter { get; }

    /// <inheritdoc/>
    public override string Content { get; }

    /// <summary>
    /// Gets the base cloud endpoint for this skill.
    /// </summary>
    public Uri Endpoint { get; }

    /// <inheritdoc/>
    public override IReadOnlyList<AgentSkillResource>? Resources { get; }

    /// <inheritdoc/>
    public override IReadOnlyList<AgentSkillScript>? Scripts { get; }
}
```

### Step 4 — Define a custom source

A `CloudSkillsSource` discovers skills from a cloud catalog API and constructs `CloudSkill`
instances with their associated resources and scripts:

```csharp
/// <summary>
/// A skill source that discovers and loads skills from a cloud catalog API.
/// </summary>
public sealed class CloudSkillsSource : AgentSkillsSource
{
    private readonly Uri _catalogUri;
    private readonly HttpClient _httpClient;

    public CloudSkillsSource(Uri catalogUri, HttpClient httpClient)
    {
        _catalogUri = catalogUri ?? throw new ArgumentNullException(nameof(catalogUri));
        _httpClient = httpClient ?? throw new ArgumentNullException(nameof(httpClient));
    }

    /// <inheritdoc/>
    public override async Task<IList<AgentSkill>> GetSkillsAsync(
        CancellationToken cancellationToken = default)
    {
        // Fetch the skill catalog from the cloud service.
        var json = await _httpClient.GetStringAsync(_catalogUri, cancellationToken)
            .ConfigureAwait(false);
        var catalog = JsonSerializer.Deserialize<CloudSkillCatalog>(json)!;

        var skills = new List<AgentSkill>();

        foreach (var entry in catalog.Skills)
        {
            var frontmatter = new AgentSkillFrontmatter(entry.Name, entry.Description);

            // Build cloud-backed resources.
            var resources = entry.Resources
                .Select(r => new CloudSkillResource(r.Name, r.BlobUri, _httpClient, r.Description))
                .ToList<AgentSkillResource>();

            // Build cloud-backed scripts.
            var scripts = entry.Scripts
                .Select(s => new CloudSkillScript(s.Name, s.FunctionUri, _httpClient, s.Description))
                .ToList<AgentSkillScript>();

            skills.Add(new CloudSkill(frontmatter, entry.Content, entry.Endpoint, resources, scripts));
        }

        return skills;
    }
}
```

### Step 5 — Register with the builder

Use `UseSource` to wire the custom source into the provider:

```csharp
var httpClient = new HttpClient();

var provider = new AgentSkillsProviderBuilder()
    .UseSource(new CloudSkillsSource(
        new Uri("https://my-service.example.com/skills/catalog"),
        httpClient))
    // Mix with other source types if needed:
    .UseFileSkill("/local/skills", scriptRunner)
    .UseInlineSkills(someInlineSkill)
    .Build();
```

The `AgentSkillsProvider` handles all skill types uniformly — any combination of file-based, inline,
class-based, and custom skills can coexist in the same provider. Custom skills automatically
participate in the model-facing tools (`load_skill`, `read_skill_resource`, `run_skill_script`),
filtering, deduplication, and caching — no additional integration work is required.

## Script Representation: `AgentSkillScript` vs `AIFunction`

Two approaches were considered for representing executable scripts within skills:

### Option A — Custom `AgentSkillScript` abstract base class (original design)

Scripts are modeled as a custom `AgentSkillScript` abstract class with `Name`, `Description`, and
`RunAsync(AgentSkill, AIFunctionArguments, CancellationToken)`. Concrete implementations:
`AgentInlineSkillScript` (wraps a delegate/`AIFunction`) and `AgentFileSkillScript` (wraps a file path + executor delegate).

```csharp
// Base type
public abstract class AgentSkillScript
{
    public string Name { get; }
    public string? Description { get; }
    public abstract Task<object?> RunAsync(AgentSkill skill, AIFunctionArguments arguments, CancellationToken cancellationToken = default);
}

// AgentSkill exposes scripts as:
public abstract IReadOnlyList<AgentSkillScript>? Scripts { get; }

// Inline script wraps an AIFunction internally
var script = new AgentInlineSkillScript(ConvertUnits, "convert");

// Pre-built AIFunction must be wrapped
var script = new AgentInlineSkillScript(myAIFunction);

// Class-based skill declares scripts as:
public override IReadOnlyList<AgentSkillScript>? Scripts { get; } =
[
    new AgentInlineSkillScript(ConvertUnits, "convert"),
];

// Provider executes scripts by passing the owning skill:
await script.RunAsync(skill, arguments, cancellationToken);
```

**Pros:**

- **Explicit skill context at execution time.** `RunAsync` receives the owning `AgentSkill`, so any script can access skill metadata or resources during execution without requiring construction-time wiring.
- **Self-contained abstraction.** A dedicated type communicates clearly that scripts are a skills-framework concept, separate from general-purpose AI functions.
- **Easier extensibility for custom script types.** Third-party implementations can subclass `AgentSkillScript` and access the owning skill in `RunAsync` without special setup.

**Cons:**

- **Wrapper overhead.** `AgentInlineSkillScript` is a thin pass-through around `AIFunction` — it adds a class, a constructor, and an indirection layer for no behavioral difference.
- **Parallel abstraction.** `AgentSkillScript` and `AIFunction` serve overlapping purposes (named callable with arguments), creating two parallel hierarchies for the same concept.
- **Friction for consumers.** Users who already have `AIFunction` instances must wrap them in `AgentInlineSkillScript` to use them as scripts, adding ceremony.

### Option B — Reuse `AIFunction` directly

Scripts are represented as `AIFunction` (from `Microsoft.Extensions.AI`). `AgentSkill.Scripts` returns
`IReadOnlyList<AIFunction>?`. `AgentInlineSkillScript` is eliminated entirely — callers use
`AIFunctionFactory.Create(delegate, name: ...)` or pass `AIFunction` instances directly.
`AgentFileSkillScript` becomes an `AIFunction` subclass that captures its owning `AgentFileSkill` via
an internal back-reference set during construction.

```csharp
// AgentSkill exposes scripts as AIFunction directly:
public abstract IReadOnlyList<AIFunction>? Scripts { get; }

// Inline scripts use AIFunctionFactory — no wrapper class needed
var skill = new AgentInlineSkill("my-skill", "desc", "instructions");
skill.AddScript(ConvertUnits, "convert");           // delegate
skill.AddScript(myAIFunction);                       // pre-built AIFunction — no wrapping

// Class-based skill declares scripts as:
public override IReadOnlyList<AIFunction>? Scripts { get; } =
[
    AIFunctionFactory.Create(ConvertUnits, name: "convert"),
];

// Provider executes scripts via standard AIFunction invocation:
await script.InvokeAsync(arguments, cancellationToken);

// File-based scripts extend AIFunction and capture the owning skill internally:
public sealed class AgentFileSkillScript : AIFunction
{
    internal AgentFileSkill? Skill { get; set; }   // set by AgentFileSkill constructor

    protected override async ValueTask<object?> InvokeCoreAsync(
        AIFunctionArguments arguments, CancellationToken cancellationToken)
    {
        return await _executor(Skill!, this, arguments, cancellationToken);
    }
}
```

**Pros:**

- **Fewer types.** Eliminates `AgentSkillScript` and `AgentInlineSkillScript`, reducing the public API surface by two classes.
- **Seamless interop.** Any `AIFunction` — whether from `AIFunctionFactory`, a custom subclass, or an external library — can be used as a skill script with zero wrapping.
- **Consistent with `Microsoft.Extensions.AI` ecosystem.** Scripts share the same type as tool functions used by `IChatClient` and `FunctionInvokingChatClient`, reducing conceptual overhead for developers already familiar with the ecosystem.

**Cons:**

- **No owning-skill context in invocation signature.** `AIFunction.InvokeAsync` does not accept an `AgentSkill` parameter, so `AgentFileSkillScript` must capture its owning skill via an internal setter during construction. This adds a construction-order dependency: the skill must set the back-reference on its scripts.
- **Custom script types lose automatic skill access.** Third-party `AIFunction` subclasses that need the owning skill must implement their own mechanism (e.g., constructor injection, closure capture) instead of receiving it as a method parameter.
- **Semantic overloading.** `AIFunction` now means both "a tool the model can call" and "a script within a skill", which could blur the distinction for framework users.

## Resource Representation: `AgentSkillResource` vs `AIFunction`

Two approaches were considered for representing skill resources (supplementary content such as references, assets, or dynamic data):

### Option A — Custom `AgentSkillResource` abstract base class (original design)

Resources are modeled as a custom `AgentSkillResource` abstract class with `Name`, `Description`, and
`ReadAsync(IServiceProvider?, CancellationToken)`. Concrete implementations:
`AgentInlineSkillResource` (static value, delegate, or `AIFunction` wrapper) and `AgentFileSkillResource` (reads file content from disk).

```csharp
// Base type
public abstract class AgentSkillResource
{
    public string Name { get; }
    public string? Description { get; }
    public abstract Task<object?> ReadAsync(IServiceProvider? serviceProvider = null, CancellationToken cancellationToken = default);
}

// AgentSkill exposes resources as:
public abstract IReadOnlyList<AgentSkillResource>? Resources { get; }

// Static resource
var resource = new AgentInlineSkillResource("static content", "my-resource");

// Dynamic resource (delegate)
var resource = new AgentInlineSkillResource((IServiceProvider sp) => GetData(sp), "my-resource");

// Pre-built AIFunction must be wrapped
var resource = new AgentInlineSkillResource(myAIFunction);

// Class-based skill declares resources as:
public override IReadOnlyList<AgentSkillResource>? Resources { get; } =
[
    new AgentInlineSkillResource("# Conversion Tables\n...", "conversion-table"),
];

// Provider reads resources via:
await resource.ReadAsync(serviceProvider, cancellationToken);
```

**Pros:**

- **Clear semantic distinction.** A dedicated `AgentSkillResource` type distinguishes resources (data providers) from scripts (executable actions), making the API self-documenting.
- **Purpose-built API.** `ReadAsync` communicates intent better than `InvokeAsync` for a data-access operation.

**Cons:**

- **Wrapper overhead.** `AgentInlineSkillResource` wraps `AIFunction` internally for delegate/function cases — adding a class and indirection for no behavioral difference.
- **Parallel abstraction.** `AgentSkillResource` and `AIFunction` serve overlapping purposes (named callable that returns data), creating two parallel hierarchies.
- **Friction for consumers.** Users who already have `AIFunction` instances must wrap them in `AgentInlineSkillResource`, adding ceremony.

### Option B — Reuse `AIFunction` directly

Resources are represented as `AIFunction`. `AgentSkill.Resources` returns `IReadOnlyList<AIFunction>?`.
`AgentInlineSkillResource` becomes an `AIFunction` subclass (retained as a convenience for the static-value
pattern: `new AgentInlineSkillResource("data", "name")`). `AgentFileSkillResource` becomes an `AIFunction`
subclass that reads file content.

```csharp
// AgentSkill exposes resources as AIFunction directly:
public abstract IReadOnlyList<AIFunction>? Resources { get; }

// Static resource — AgentInlineSkillResource is retained as a convenience AIFunction subclass
var resource = new AgentInlineSkillResource("static content", "my-resource");

// Dynamic resource — AgentInlineSkillResource wraps delegate as AIFunction
var resource = new AgentInlineSkillResource((IServiceProvider sp) => GetData(sp), "my-resource");

// Pre-built AIFunction can be used directly — no wrapping needed
skill.AddResource(myAIFunction);

// Class-based skill declares resources as:
public override IReadOnlyList<AIFunction>? Resources { get; } =
[
    new AgentInlineSkillResource("# Conversion Tables\n...", "conversion-table"),
];

// Provider reads resources via standard AIFunction invocation:
await resource.InvokeAsync(arguments, cancellationToken);

// File-based resources extend AIFunction directly:
internal sealed class AgentFileSkillResource : AIFunction
{
    public string FullPath { get; }

    protected override async ValueTask<object?> InvokeCoreAsync(
        AIFunctionArguments arguments, CancellationToken cancellationToken)
    {
        return await File.ReadAllTextAsync(FullPath, Encoding.UTF8, cancellationToken);
    }
}
```

**Pros:**

- **Fewer base types.** Eliminates the `AgentSkillResource` abstract class, reducing the public API surface.
- **Seamless interop.** Any `AIFunction` can be used as a skill resource with zero wrapping.

**Cons:**

- **Loss of semantic distinction.** Resources and scripts are now both `AIFunction`, which could make it less obvious which list a function belongs to when reading code.
- **Static values require a wrapper.** Unlike the original `ReadAsync` which could return a stored value directly, `AIFunction.InvokeAsync` implies invocation. `AgentInlineSkillResource` is retained as a convenience subclass to handle the static-value case, so this is not eliminated — just moved to a different class.

## Decision Outcome

### 1. Keep `AgentSkillResource` and `AgentSkillScript` (Option A for both sections)

We are staying with the custom `AgentSkillResource` and `AgentSkillScript` model classes instead of reusing `AIFunction`:

- **Resources have no parameters.** If a consumer provides an `AIFunction` with parameters, those parameters will never be advertised to the LLM, and the resulting call will fail.
- **Approval breaks for `AIFunction`-based representations.** When a resource or script represented by an `AIFunction` is configured with approval, the second approval invocation will not work correctly.
- **Injecting the owning skill into an `AIFunction`-based script is problematic.** Constructor injection would introduce a circular reference between the skill and the script. An internal property setter is possible but adds coupling.

### 2. Make all agent skill classes internal

All agent-skill-related classes are made `internal` to minimize the public API surface while the feature matures. We can reconsider and promote types to `public` later based on community signal.

This leaves two public entry points:

- **`AgentSkillsProvider`** — use directly when all skills come from a single source and filtering is not needed.
- **`AgentSkillsProviderBuilder`** — use when mixing skill types or when filtering support is required.

### 3. Caching at provider level

Caching of tools and instructions is implemented inside `AgentSkillsProvider` rather than as an external decorator. Recreating tools and instructions on every provider call is wasteful, and a caching decorator sitting outside the provider would not have the information needed to cache them effectively.
