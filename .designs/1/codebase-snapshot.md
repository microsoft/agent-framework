# codebase-snapshot.md — Verified Ground Truth

Snapshot taken: 2026-05-12T03:32Z
Branch: af/soldesign-plan-5414a7 (identical to origin/main at time of snapshot)

## 1. Project Tree (Source Generator)

```
dotnet/src/Microsoft.Agents.AI.Workflows.Generators/
├── Analysis/
│   ├── SemanticAnalyzer.cs
│   └── (SyntaxDetector.cs - NOT present; detection is inline in ExecutorRouteGenerator.cs)
├── Diagnostics/
│   └── DiagnosticDescriptors.cs
├── Directory.Build.targets
├── ExecutorRouteGenerator.cs
├── Generation/
│   └── SourceBuilder.cs
├── Microsoft.Agents.AI.Workflows.Generators.csproj
├── Models/
│   ├── ExecutorInfo.cs
│   ├── HandlerInfo.cs
│   └── (additional model files for analysis pipeline)
└── SkipIncompatibleBuild.targets
```

## 2. Module Identity

Solution: `dotnet/agent-framework-dotnet.slnx`
Primary project: `dotnet/src/Microsoft.Agents.AI.Workflows/Microsoft.Agents.AI.Workflows.csproj`
Generator project: `dotnet/src/Microsoft.Agents.AI.Workflows.Generators/Microsoft.Agents.AI.Workflows.Generators.csproj`

## 3. Referenced Types and Functions — Verified Locations

### Executor (base class)
- **File**: `dotnet/src/Microsoft.Agents.AI.Workflows/Executor.cs:164`
- **Signature**: `public abstract class Executor : IIdentified`
- **Abstract method**: `protected abstract ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder);` (line 216)
- **Constructor**: `protected Executor(string id, ExecutorOptions? options = null, bool declareCrossRunShareable = false)` (line 179)
- **Generic variants**: `Executor<TInput>` (line 382), `Executor<TInput, TOutput>` (line 407)

### ReflectingExecutor<TExecutor>
- **File**: `dotnet/src/Microsoft.Agents.AI.Workflows/Reflection/ReflectingExecutor.cs:23-27`
- **Signature**: `public class ReflectingExecutor<[DynamicallyAccessedMembers(...)] TExecutor> : Executor where TExecutor : ReflectingExecutor<TExecutor>`
- **Status**: Already marked `[Obsolete]` (lines 21-22)
- **Obsolete message**: `"Use [MessageHandler] attribute on methods in a partial class deriving from Executor. This type will be removed in a future version."`
- **Overrides**: `ConfigureProtocol(ProtocolBuilder)` (NOT `ConfigureRoutes`)

### RouteBuilder
- **File**: `dotnet/src/Microsoft.Agents.AI.Workflows/RouteBuilder.cs`
- **AddHandler overloads** (8 public overloads):
  - `AddHandler<TInput>(Action<TInput, IWorkflowContext, CancellationToken>)`
  - `AddHandler<TInput>(Action<TInput, IWorkflowContext>)`
  - `AddHandler<TInput>(Func<TInput, IWorkflowContext, CancellationToken, ValueTask>)`
  - `AddHandler<TInput>(Func<TInput, IWorkflowContext, ValueTask>)`
  - `AddHandler<TInput, TResult>(Func<TInput, IWorkflowContext, CancellationToken, TResult>)`
  - `AddHandler<TInput, TResult>(Func<TInput, IWorkflowContext, TResult>)`
  - `AddHandler<TInput, TResult>(Func<TInput, IWorkflowContext, CancellationToken, ValueTask<TResult>>)`
  - `AddHandler<TInput, TResult>(Func<TInput, IWorkflowContext, ValueTask<TResult>>)`
- **Internal method**: `AddHandlerInternal(Type, MessageHandlerF, Type?, bool)` (line 51-89)

### ProtocolBuilder
- **File**: `dotnet/src/Microsoft.Agents.AI.Workflows/ProtocolBuilder.cs`
- **Key methods**:
  - `SendsMessage<TMessage>()` — fluent registration
  - `YieldsOutput<TOutput>()` — fluent registration
  - `ConfigureRoutes(Action<RouteBuilder>)` — route delegation
  - `RouteBuilder` property — direct access

### IWorkflowContext
- **File**: `dotnet/src/Microsoft.Agents.AI.Workflows/IWorkflowContext.cs`
- **Key methods**: `SendMessageAsync()`, `YieldOutputAsync()`, state management

### MessageHandlerAttribute
- **File**: `dotnet/src/Microsoft.Agents.AI.Workflows/Attributes/MessageHandlerAttribute.cs:48-70`
- **Signature**: `[AttributeUsage(AttributeTargets.Method, AllowMultiple = false, Inherited = false)] public sealed class MessageHandlerAttribute : Attribute`
- **Properties**: `Type[]? Yield`, `Type[]? Send`
- **Status**: EXISTS — matches plan exactly

### SendsMessageAttribute
- **File**: `dotnet/src/Microsoft.Agents.AI.Workflows/Attributes/SendsMessageAttribute.cs:32-49`
- **Signature**: `[AttributeUsage(AttributeTargets.Class | AttributeTargets.Method, AllowMultiple = true, Inherited = true)] public sealed class SendsMessageAttribute : Attribute`
- **Property**: `Type Type` (constructor parameter)
- **Status**: EXISTS — plan says `AttributeTargets.Class` only, actual allows `Class | Method`

### YieldsOutputAttribute (plan says "YieldsMessageAttribute")
- **File**: `dotnet/src/Microsoft.Agents.AI.Workflows/Attributes/YieldsOutputAttribute.cs:32-49`
- **Signature**: `[AttributeUsage(AttributeTargets.Class | AttributeTargets.Method, AllowMultiple = true, Inherited = true)] public sealed class YieldsOutputAttribute : Attribute`
- **Property**: `Type Type` (constructor parameter)
- **Status**: EXISTS but NAMED DIFFERENTLY — plan calls it `YieldsMessageAttribute`, actual is `YieldsOutputAttribute`

### IMessageHandler<T> Interfaces
- **File**: `dotnet/src/Microsoft.Agents.AI.Workflows/Reflection/IMessageHandler.cs`
- **Status**: Already marked `[Obsolete]`

### ExecutorRouteGenerator
- **File**: `dotnet/src/Microsoft.Agents.AI.Workflows.Generators/ExecutorRouteGenerator.cs:22-161`
- **Signature**: `[Generator] public sealed class ExecutorRouteGenerator : IIncrementalGenerator`
- **Three pipelines**: MessageHandler methods, SendsMessage classes, YieldsOutput classes
- **Status**: EXISTS — fully implemented

### DiagnosticDescriptors
- **File**: `dotnet/src/Microsoft.Agents.AI.Workflows.Generators/Diagnostics/DiagnosticDescriptors.cs`
- **Actual IDs** (different from plan):
  - `MAFGENWF001` (Error) — Handler missing IWorkflowContext parameter
  - `MAFGENWF002` (Error) — Handler has invalid return type
  - `MAFGENWF003` (Error) — Executor with [MessageHandler] must be partial
  - `MAFGENWF004` (Warning) — [MessageHandler] on non-Executor class
  - `MAFGENWF005` (Error) — Handler has insufficient parameters
  - `MAFGENWF006` (Info) — ConfigureProtocol already defined
  - `MAFGENWF007` (Error) — Handler cannot be static (NOT in plan)
- **Plan uses**: `WFGEN001-006` — actual uses `MAFGENWF001-007`

## 4. Key Discrepancies: Plan vs. Implementation

| Plan States | Actual Implementation | Impact |
|-------------|----------------------|--------|
| `YieldsMessageAttribute` | `YieldsOutputAttribute` | Name differs; same functionality |
| `ConfigureRoutes(RouteBuilder)` as generated method | `ConfigureProtocol(ProtocolBuilder)` as generated method | API evolved to unified fluent builder |
| Separate `ConfigureSentTypes()` / `ConfigureYieldTypes()` methods | Single `ConfigureProtocol()` with fluent `.SendsMessage<T>()` / `.YieldsOutput<T>()` | Cleaner API, single override point |
| `WFGEN001-006` diagnostic IDs | `MAFGENWF001-007` IDs | 7 diagnostics, not 6 |
| `AttributeTargets.Class` for SendsMessage/YieldsMessage | `AttributeTargets.Class \| AttributeTargets.Method` | Broader applicability than planned |
| `SyntaxDetector.cs` as separate file | Detection inline in `ExecutorRouteGenerator.cs` via `ForAttributeWithMetadataName` | Simpler architecture |
| Files listed as "to create" | All files ALREADY EXIST | Plan describes already-implemented work |

## 5. Existing Test Coverage

**Path**: `dotnet/tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/`

Files:
- `ExecutorRouteGeneratorTests.cs` (~37KB)
- `GeneratorTestHelper.cs`
- `SyntaxTreeFluentExtensions.cs`

Test cases covering:
- Single handler (void, ValueTask, ValueTask<T>)
- Multiple handlers on one class
- CancellationToken parameter variants
- Yield/Send type attributes on handlers
- Class-level [SendsMessage] and [YieldsOutput] attributes
- Nested classes
- Generic executors
- Inheritance chains
- ConfigureProtocol already defined (skip generation)
- Invalid signatures (diagnostic verification)

## 6. Recent Deliberate Changes

```
$ git log --oneline -30 -- src/Microsoft.Agents.AI.Workflows/

27324a80 .NET: Mark Magentic Orchestration Experimental (#5704)
ce70ca1a .NET: feat: Implement Magentic Orchestration for .NET (#5595)
9f3f7fd0 fix: JSON Serialization issue with MultiPartyConversation (#5653)
162985f2 .NET: feat: Implement message filtering to exclude non-portable content typ… (#5410)
4b5a8478 .NET: Hosting updates to declarative workflows (#5589)
69adf6d9 .NET: Fix off-thread RunStatus race where GetStatusAsync can return Running after ResumeAsync halts (#5412)
267351b7 .NET: Expand Workflow Unit Test Coverage (#5390)
d5777bc5 fix: Duplicate CallIds cause Handoff Message Filtering to fail (#5359)
5777ed26 .NET: fix: Add session support for Handoff-hosted Agents (#5280)

$ git log --oneline -30 -- src/Microsoft.Agents.AI.Workflows.Generators/

267351b7 .NET: Expand Workflow Unit Test Coverage (#5390)
524c0216 .NET: Update release versions (#5059)
0756c457 .NET: [BREAKING] Update type names and source generator to reduce conflicts (#4903)
5374dd47 .NET: Fix source generator bug that silently drops base class handler registrations for protocol-only partial executors (#4751)
6c32e869 .NET: Updated package versions for RC release (#4067)
```

Key deliberate changes:
- `0756c457`: Renamed `Config` → `ExecutorConfig`, made `RouteBuilder` usage explicit in generated code to avoid naming conflicts
- `5374dd47`: Fixed bug where base class handler registrations were silently dropped for protocol-only partial executors
- `267351b7`: Expanded unit test coverage

## Decision History

### ADRs
No ADRs found specifically addressing the source generator or Workflows architecture.
Searched: `find docs/decisions -name "0*.md"` — 15 ADRs found, none related to source generators, Roslyn, or workflow executor patterns.

### Prior Designs
No prior designs found for this problem domain.
Searched: `ls .designs/` — only the current `.designs/1/` directory exists (created by this session).

### Recent Deliberate Changes
See section 6 above. Key pattern: the API evolved from the plan's `ConfigureRoutes`/`ConfigureSentTypes`/`ConfigureYieldTypes` pattern to a unified `ConfigureProtocol(ProtocolBuilder)` with fluent chaining. This was a deliberate architectural decision reflected in the existing implementation.
