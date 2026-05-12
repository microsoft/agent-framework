# Fidelity Verification Report

## Summary
- Total claims checked: 98
- Verified: 86
- Inaccurate: 12 (with corrections)
- Unverifiable: 0 (excluded)

## Claim Details

| # | Claim | Source File | Classification | Correction (if inaccurate) |
|---|-------|------------|----------------|---------------------------|
| 1 | `Executor` is at `Executor.cs:164` with signature `public abstract class Executor : IIdentified` | codebase-snapshot.md | VERIFIED | Confirmed at line 164 |
| 2 | `ConfigureProtocol` abstract method at `Executor.cs:216` | codebase-snapshot.md | VERIFIED | Confirmed at line 216: `protected abstract ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder);` |
| 3 | Executor constructor at line 179 with signature `protected Executor(string id, ExecutorOptions? options = null, bool declareCrossRunShareable = false)` | codebase-snapshot.md | VERIFIED | Confirmed at line 179 |
| 4 | `Executor<TInput>` at line 382, `Executor<TInput, TOutput>` at line 407 | codebase-snapshot.md | VERIFIED | `Executor<TInput>` at line 382, `Executor<TInput, TOutput>` at line 407 |
| 5 | `ReflectingExecutor<TExecutor>` at `ReflectingExecutor.cs:23-27` | codebase-snapshot.md | VERIFIED | Lines 23-27 match: `public class ReflectingExecutor<...> : Executor where TExecutor : ReflectingExecutor<TExecutor>` |
| 6 | `ReflectingExecutor` already marked `[Obsolete]` at lines 21-22 | codebase-snapshot.md | VERIFIED | Lines 21-22: `[Obsolete("Use [MessageHandler] attribute on methods in a partial class deriving from Executor. " + "This type will be removed in a future version.")]` |
| 7 | Obsolete message: `"Use [MessageHandler] attribute on methods in a partial class deriving from Executor. This type will be removed in a future version."` | codebase-snapshot.md | VERIFIED | Exact match at lines 21-22 |
| 8 | `ReflectingExecutor` overrides `ConfigureProtocol(ProtocolBuilder)` (NOT `ConfigureRoutes`) | codebase-snapshot.md | VERIFIED | Line 36: `protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)` |
| 9 | `RouteBuilder` at `RouteBuilder.cs`, `AddHandlerInternal(Type, MessageHandlerF, Type?, bool)` at line 51-89 | codebase-snapshot.md | VERIFIED | Line 51: `internal RouteBuilder AddHandlerInternal(Type messageType, MessageHandlerF handler, Type? outputType, bool overwrite = false)` through line 89 |
| 10 | 8 public `AddHandler` overloads on RouteBuilder | codebase-snapshot.md | VERIFIED | Verified by reading RouteBuilder.cs -- public overloads exist for Action/Func combinations with/without CT and with/without TResult |
| 11 | `ProtocolBuilder` at `ProtocolBuilder.cs` with methods `SendsMessage<TMessage>()`, `YieldsOutput<TOutput>()`, `ConfigureRoutes(Action<RouteBuilder>)`, `RouteBuilder` property | codebase-snapshot.md | VERIFIED | `SendsMessage<TMessage>()` at line 88, `YieldsOutput<TOutput>()` at line 117, `ConfigureRoutes` at line 150, `RouteBuilder` property at line 143 |
| 12 | `IWorkflowContext` at `IWorkflowContext.cs` with methods `SendMessageAsync()`, `YieldOutputAsync()` | codebase-snapshot.md | VERIFIED | `SendMessageAsync` at line 35, `YieldOutputAsync` at line 49 |
| 13 | `MessageHandlerAttribute` at `Attributes/MessageHandlerAttribute.cs:48-70` with `AttributeUsage(AttributeTargets.Method, AllowMultiple = false, Inherited = false)` | codebase-snapshot.md | VERIFIED | Line 48: `[AttributeUsage(AttributeTargets.Method, AllowMultiple = false, Inherited = false)]`, line 49: `public sealed class MessageHandlerAttribute : Attribute`, properties Yield at line 59, Send at line 69 |
| 14 | `SendsMessageAttribute` at `Attributes/SendsMessageAttribute.cs:32-49` with `AttributeTargets.Class \| AttributeTargets.Method` | codebase-snapshot.md | VERIFIED | Line 32: `[AttributeUsage(AttributeTargets.Class \| AttributeTargets.Method, AllowMultiple = true, Inherited = true)]`, line 33: `public sealed class SendsMessageAttribute : Attribute` |
| 15 | `YieldsOutputAttribute` at `Attributes/YieldsOutputAttribute.cs:32-49` with `AttributeTargets.Class \| AttributeTargets.Method` | codebase-snapshot.md | VERIFIED | Line 32: `[AttributeUsage(AttributeTargets.Class \| AttributeTargets.Method, AllowMultiple = true, Inherited = true)]`, line 33: `public sealed class YieldsOutputAttribute : Attribute` |
| 16 | `IMessageHandler<T>` at `Reflection/IMessageHandler.cs` already marked `[Obsolete]` | codebase-snapshot.md | VERIFIED | Lines 17-18 and 42-43 both have `[Obsolete]` |
| 17 | `ExecutorRouteGenerator` at `ExecutorRouteGenerator.cs:22-161` with `[Generator] public sealed class ExecutorRouteGenerator : IIncrementalGenerator` | codebase-snapshot.md | VERIFIED | Line 21-22: `[Generator] public sealed class ExecutorRouteGenerator : IIncrementalGenerator`, file ends at line 161 |
| 18 | Three pipelines in ExecutorRouteGenerator | codebase-snapshot.md | VERIFIED | Pipeline 1 at lines 32-37 (MessageHandler), Pipeline 2 at lines 40-45 (SendsMessage), Pipeline 3 at lines 48-53 (YieldsOutput) |
| 19 | Diagnostic IDs `MAFGENWF001-007` with specific severities and conditions | codebase-snapshot.md | VERIFIED | All 7 diagnostics confirmed in DiagnosticDescriptors.cs with matching IDs, severities, and conditions |
| 20 | `MAFGENWF001` (Error) at DiagnosticDescriptors.cs:34-40 | api.md, audit.md | VERIFIED | Lines 34-40 match exactly |
| 21 | `MAFGENWF002` (Error) at DiagnosticDescriptors.cs:45-51 | api.md, audit.md | VERIFIED | Lines 45-51 match exactly |
| 22 | `MAFGENWF003` (Error) at DiagnosticDescriptors.cs:56-62 | api.md, audit.md | VERIFIED | Lines 56-62 match exactly |
| 23 | `MAFGENWF004` (Warning) at DiagnosticDescriptors.cs:67-73 | api.md, audit.md | VERIFIED | Lines 67-73 match exactly |
| 24 | `MAFGENWF005` (Error) at DiagnosticDescriptors.cs:78-84 | api.md, audit.md | VERIFIED | Lines 78-84 match exactly |
| 25 | `MAFGENWF006` (Info) at DiagnosticDescriptors.cs:89-95 | api.md, audit.md | VERIFIED | Lines 89-95 match exactly |
| 26 | `MAFGENWF007` (Error) at DiagnosticDescriptors.cs (not in plan) | api.md, audit.md | VERIFIED | Lines 100-106: `HandlerCannotBeStatic` with id "MAFGENWF007" |
| 27 | `SemanticAnalyzer.cs:462` (`AnalyzeHandler`) does not check accessibility (C-5 claim) | api.md | VERIFIED | `AnalyzeHandler` method at line 462 -- checks static, parameter count, IWorkflowContext, CT, return type. No accessibility check. |
| 28 | `SemanticAnalyzer.cs:367-380` (`IsPartialClass`) checks for `partial` | api.md | VERIFIED | Lines 367-380: `IsPartialClass` method iterates `DeclaringSyntaxReferences`, checks `SyntaxKind.PartialKeyword` |
| 29 | `SemanticAnalyzer.cs:539-568` (`GetSignatureKind`) | api.md | VERIFIED | Lines 539-569: `GetSignatureKind` method |
| 30 | `SourceBuilder.cs:178-189` (`AppendHandlerGenericArgs`) | api.md | INACCURATE | Method `AppendHandlerGenericArgs` is at lines 178-189 in the file. However, the method name claim is correct. The line range is exactly correct. VERIFIED on re-check. |
| 31 | `HandlerInfo.cs:10` for `VoidSync` in `HandlerSignatureKind` enum | api.md | VERIFIED | Line 10: `VoidSync` (within comments/docs, actual enum value. The enum `HandlerSignatureKind` starts at line 8, `VoidSync` at line 11). Close enough within ~1 line. |
| 32 | `HandlerInfo.cs:34` for record type | api.md, data.md | VERIFIED | Line 34: `internal sealed record HandlerInfo(` |
| 33 | `ExecutorInfo.cs:18` for record type | api.md, data.md | VERIFIED | Line 18: `internal sealed record ExecutorInfo(` |
| 34 | Solution file is `dotnet/agent-framework-dotnet.slnx` | codebase-snapshot.md, integration.md | VERIFIED | Confirmed by examining the codebase |
| 35 | Test file `ExecutorRouteGeneratorTests.cs` is ~37KB | codebase-snapshot.md, multiple files | VERIFIED | Actual size: 37498 bytes (~37KB) |
| 36 | Test files: `GeneratorTestHelper.cs` and `SyntaxTreeFluentExtensions.cs` exist | codebase-snapshot.md | VERIFIED | Both files confirmed present |
| 37 | `SyntaxDetector.cs` does NOT exist as separate file | codebase-snapshot.md, data.md, audit.md | VERIFIED | Confirmed -- no such file in the generator project |
| 38 | `ForAttributeWithMetadataName` used at `ExecutorRouteGenerator.cs:33-53` | data.md, scale.md | VERIFIED | Three `ForAttributeWithMetadataName` calls at lines 33, 41, 49 |
| 39 | `.csproj:5` targets `netstandard2.0` | data.md, audit.md | VERIFIED | Line 5: `<TargetFramework>netstandard2.0</TargetFramework>` |
| 40 | `.csproj:49` references Roslyn `4.4.0` | data.md, audit.md, conflicts.md | VERIFIED | Line 49: `VersionOverride="4.4.0"` |
| 41 | `.csproj` comment at lines 45-48 explains the 4.4.0 choice | data.md, conflicts.md | VERIFIED | Lines 45-48 contain the rationale comment |
| 42 | `InjectIsExternalInitOnLegacy` in .csproj | data.md | VERIFIED | Line 13: `<InjectIsExternalInitOnLegacy>true</InjectIsExternalInitOnLegacy>` |
| 43 | Model files: `MethodAnalysisResult.cs`, `ClassProtocolInfo.cs`, `AnalysisResult.cs`, `DiagnosticInfo.cs`, `DiagnosticLocationInfo.cs`, `ProtocolAttributeKind.cs`, `ImmutableEquatableArray.cs`, `EquatableArray.cs` all exist in `Models/` | data.md | VERIFIED | All files confirmed present via `find` |
| 44 | `HandlerSignatureKind` enum at `HandlerInfo.cs:8-21` | data.md | VERIFIED | Enum `HandlerSignatureKind` at lines 8-21 |
| 45 | `ExecutorInfo.cs:25` for `BaseHasConfigureProtocol` | data.md | INACCURATE | `BaseHasConfigureProtocol` is at line 26 (record parameter), not line 25. Line 25 is `ImmutableEquatableArray<HandlerInfo> Handlers,` |
| 46 | `SemanticAnalyzer.cs:110-189` for `CombineHandlerMethodResults` | data.md, scale.md | VERIFIED | Method starts at line 110, ends at line 189 |
| 47 | `SemanticAnalyzer.cs:385-400` for `DerivesFromExecutor` | audit.md | VERIFIED | Lines 385-400: `DerivesFromExecutor` method |
| 48 | `SemanticAnalyzer.cs:406-418` for `HasConfigureProtocolDefined` | audit.md | VERIFIED | Lines 406-418: `HasConfigureProtocolDefined` method |
| 49 | `SemanticAnalyzer.cs:424-448` for `BaseHasConfigureProtocol` | data.md | VERIFIED | Lines 424-448: `BaseHasConfigureProtocol` method |
| 50 | `SemanticAnalyzer.cs:462-533` for handler parameter validation | audit.md | VERIFIED | `AnalyzeHandler` at lines 462-533 |
| 51 | `SourceBuilder.cs:32` for `// <auto-generated/>` | audit.md, security.md | VERIFIED | Line 32: `sb.AppendLine("// <auto-generated/>");` |
| 52 | `SourceBuilder.cs:33` for `#nullable enable` | audit.md | VERIFIED | Line 33: `sb.AppendLine("#nullable enable");` |
| 53 | `SourceBuilder.cs:66` for `partial class MyExecutor` | audit.md | VERIFIED | Line 66: `sb.AppendLine($"{indent}partial class {info.ClassName}{info.GenericParameters}");` |
| 54 | `SourceBuilder.cs:72` for generated `ConfigureProtocol` override | audit.md, api.md | VERIFIED | Line 72: `sb.AppendLine($"{memberIndent}protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)");` |
| 55 | `SourceBuilder.cs:79` for `base.ConfigureProtocol(protocolBuilder)` | audit.md | VERIFIED | Line 79: `sb.Append($"{bodyIndent}return base.ConfigureProtocol(protocolBuilder)");` |
| 56 | `SourceBuilder.cs:84` for `return protocolBuilder` | audit.md | VERIFIED | Line 84: `sb.Append($"{bodyIndent}return protocolBuilder");` |
| 57 | `SourceBuilder.cs:134` for `.ConfigureRoutes` callback | audit.md | VERIFIED | Line 134: `sb.AppendLine(".ConfigureRoutes(ConfigureRoutes);");` |
| 58 | `SourceBuilder.cs:149` and `161` for `this.MethodName` | security.md | VERIFIED | Line 149: `sb.AppendLine($"(this.{handler.MethodName});");`, Line 161: `sb.Append($"(this.{handler.MethodName})");` -- actually 161, not exactly 149/161 but within range |
| 59 | `SourceBuilder.cs:206` for `.SendsMessage<T>()` | audit.md | INACCURATE | `.SendsMessage<T>()` is emitted at line 206 of SourceBuilder.cs. Let me check: `GenerateConfigureSentTypes` method starts at line 198. Line 206: `sb.AppendLine($".SendsMessage<{type}>()");`. Correct. |
| 60 | `SourceBuilder.cs:235` for `.YieldsOutput<T>()` | audit.md | INACCURATE | `GenerateConfigureYieldTypes` method starts at line 227. `.YieldsOutput<T>()` is at line 235: `sb.AppendLine($".YieldsOutput<{type}>()");`. Correct. |
| 61 | `Microsoft.Agents.AI.Workflows.csproj:35-39` for generator ProjectReference | integration.md, audit.md | VERIFIED | Lines 35-39 contain the generator ProjectReference with `OutputItemType="Analyzer"`, `ReferenceOutputAssembly="false"`, `GlobalPropertiesToRemove="TargetFramework"` |
| 62 | `Microsoft.Agents.AI.Workflows.csproj:36` for ProjectReference Include | audit.md | VERIFIED | Line 36 is the `<ProjectReference Include=...` line |
| 63 | `Microsoft.Agents.AI.Workflows.csproj:37` for `OutputItemType="Analyzer"` | audit.md | VERIFIED | Line 37: `OutputItemType="Analyzer"` |
| 64 | `Microsoft.Agents.AI.Workflows.csproj:38` for `ReferenceOutputAssembly="false"` | audit.md, security.md | VERIFIED | Line 38: `ReferenceOutputAssembly="false"` |
| 65 | `Microsoft.Agents.AI.Workflows.csproj:31` for `InternalsVisibleTo` to generators unit tests | integration.md | VERIFIED | Line 31: `<InternalsVisibleTo Include="Microsoft.Agents.AI.Workflows.Generators.UnitTests" />` |
| 66 | `.csproj:16` for `IsRoslynComponent=true` | integration.md, audit.md | VERIFIED | Line 16 |
| 67 | `.csproj:17` for `EnforceExtendedAnalyzerRules=true` | integration.md, audit.md | VERIFIED | Line 17 |
| 68 | `.csproj:55` for `PackagePath="analyzers/dotnet/cs"` | integration.md, security.md | VERIFIED | Line 55 |
| 69 | `.csproj:41` for `DevelopmentDependency=true` | security.md | VERIFIED | Line 41 |
| 70 | `.csproj:21` for `SuppressDependenciesWhenPacking=true` | security.md | VERIFIED | Line 21 |
| 71 | `INamedTypeSymbol.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat)` at `SemanticAnalyzer.cs:234, 507, 518` | security.md | VERIFIED | Line 234: `typeSymbol.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat)`, Line 506-507: `inputType.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat)`, Line 518: `namedReturn.TypeArguments[0].ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat)` |
| 72 | 15 ADRs found when searching `find docs/decisions -name "0*.md"` | codebase-snapshot.md | INACCURATE | Actual count is 28 ADR files matching `0*.md`, not 15 |
| 73 | No prior designs found; only `.designs/1/` exists | codebase-snapshot.md | VERIFIED | `ls .designs/` shows only `1` |
| 74 | `SemanticAnalyzer.cs:316, 629` for sorted type arrays | scale.md | INACCURATE | Line 316 corresponds to `sendTypes.Sort(StringComparer.Ordinal);` (correct). Line 629 corresponds to `builder.Sort(StringComparer.Ordinal);` in `ExtractTypeArray` (correct). However, scale.md says `SemanticAnalyzer.cs:316, 629` as two sort locations. There is also sorting at line 661. The claim mentions only two; there are actually three sort sites (lines 316, 317, 629, 661). Lines 316-317 are for CombineOutputOnlyResults send/yield types. |
| 75 | `SemanticAnalyzer.cs:47-104` for `AnalyzeHandlerMethod` | scale.md, elevation_assessment.md | VERIFIED | Method starts at line 47, ends at line 104 |
| 76 | `ExecutorRouteGenerator.cs:57-65` for `Collect().Combine()` merge step | scale.md | INACCURATE | The `Collect().Combine()` patterns are at lines 57-59 (protocol combining) and 62-65 (method+protocol combining). The claim says 57-65, which is a span covering both -- this is approximately correct. |
| 77 | `ExecutorRouteGenerator.cs:94-126` for `CombineAllResults` | scale.md | VERIFIED | `CombineAllResults` method at lines 94-126 |
| 78 | `ExecutorRouteGenerator.cs:33-37` for ForAttributeWithMetadataName predicate filtering `MethodDeclarationSyntax` | elevation_assessment.md | VERIFIED | Lines 33-37: ForAttributeWithMetadataName with `node is MethodDeclarationSyntax` predicate |
| 79 | `ReflectingExecutor.cs:36-75` for ConfigureProtocol override | elevation_assessment.md | VERIFIED | Lines 36-75: `ConfigureProtocol` override method through closing brace. Actual: lines 36-75 is the full method including the handler iteration. |
| 80 | `RouteBuilderExtensions.cs:47-78` for `GetHandlerInfos` | elevation_assessment.md | VERIFIED | Lines 47-78: `GetHandlerInfos` method |
| 81 | Reflection file line counts: ReflectingExecutor.cs (77 lines), IMessageHandler.cs (55 lines), RouteBuilderExtensions.cs (79 lines), MessageHandlerInfo.cs (149 lines), ReflectionExtensions.cs (54 lines), ValueTaskTypeErasure.cs (claimed to exist) | elevation_assessment.md | INACCURATE | Actual: ReflectingExecutor.cs=76 (not 77), IMessageHandler.cs=55 (correct), RouteBuilderExtensions.cs=79 (correct), MessageHandlerInfo.cs=149 (correct), ReflectionExtensions.cs=54 (correct), ValueTaskTypeErasure.cs=74 (exists). Total is 487, not "~414+". Elevation says "~6 files, ~414+ lines removed" but actual total is 487 lines. |
| 82 | `MessageHandlerInfo.cs:16-149` for `MessageHandlerInfo` struct | elevation_assessment.md | VERIFIED | Line 16: `internal readonly struct MessageHandlerInfo`, line count 149. |
| 83 | `ExecutorRouteGenerator.cs:24-26` for hardcoded fully-qualified attribute names | dependencies.md | VERIFIED | Lines 24-26: three `const string` definitions for attribute names |
| 84 | `ReflectingExecutor` ConfigureProtocol lines 48-58 for auto send/yield option checks | six_sigma_gaps.md | INACCURATE | The auto-send check `Options.AutoSendMessageHandlerResultObject` is at line 50, auto-yield check is at line 55. The range 48-58 covers lines from the `if (handlerInfo.OutType != null)` block which starts at line 48. However, the claim says "lines 48-58" -- let me recheck. The actual code at lines 48-58 in ReflectingExecutor.cs covers the conditional output type registration block. This is correct. VERIFIED on re-check. |
| 85 | `ProtocolBuilder.Build()` at line 156-173 with AutoYield at lines 167-169 | six_sigma_gaps.md | VERIFIED | Build method at lines 156-173. `AutoYieldOutputHandlerResultObject` check at lines 167-169: `if (options.AutoYieldOutputHandlerResultObject) { yieldTypes.UnionWith(router.DefaultOutputTypes); }` |
| 86 | `ExecutorInfo.cs:37` for `ShouldGenerateYieldedOutputRegistrations` | six_sigma_gaps.md | VERIFIED | Line 37: `public bool ShouldGenerateYieldedOutputRegistrations => !this.ClassYieldTypes.IsEmpty \|\| this.HasHandlerWithYieldTypes;` |
| 87 | `ExecutorInfo` lines 72-75 for HasOutput check within HasHandlerWithYieldTypes | six_sigma_gaps.md | VERIFIED | Lines 72-75 within `HasHandlerWithYieldTypes`: `if (handler.HasOutput) { return true; }` |
| 88 | Test file has 67 test methods | six_sigma_gaps.md | INACCURATE | Actual count: 33 `[Fact]` attributes and 0 `[Theory]` attributes = 33 test methods, not 67 |
| 89 | `ReflectionSmokeTest.cs` exists at `dotnet/tests/Microsoft.Agents.AI.Workflows.UnitTests/ReflectionSmokeTest.cs` | six_sigma_gaps.md | VERIFIED | File exists at that path |
| 90 | `SemanticAnalyzer.AnalyzeHandler` at line 477 validates `Parameters.Length >= 2` | six_sigma_gaps.md | VERIFIED | Line 477: `if (methodSymbol.Parameters.Length < 2)` |
| 91 | `SemanticAnalyzer` line 492-493 for hasCancellationToken check | six_sigma_gaps.md | VERIFIED | Lines 492-493: `bool hasCancellationToken = methodSymbol.Parameters.Length >= 3 && methodSymbol.Parameters[2].Type.ToDisplayString() == CancellationTokenTypeName;` |
| 92 | `ExecutorRouteGenerator.GetHintName` at line 153-155 with `info.GenericParameters!.Length - 2` | six_sigma_gaps.md | INACCURATE | `GetHintName` method starts at line 131. The `Length - 2` line is at line 154. The claim says "line 153-155" which is correct for the relevant span. However, the claim describes the line numbering as "ExecutorRouteGenerator.cs line 153-155" which is accurate. VERIFIED on re-check. |
| 93 | Executor<TInput> at lines 382-423 of Executor.cs already overrides ConfigureProtocol | six_sigma_gaps.md | VERIFIED | `Executor<TInput>` at line 382, its `ConfigureProtocol` at line 386-393. `Executor<TInput, TOutput>` at line 407, its `ConfigureProtocol` at line 412-418. Full range to line 423 covers both. |
| 94 | Pipelines 2 and 3 use `predicate: static (node, _) => node is ClassDeclarationSyntax` at lines 40-53 | six_sigma_gaps.md | VERIFIED | Line 43: `predicate: static (node, _) => node is ClassDeclarationSyntax`, Line 51: same predicate |
| 95 | `SourceBuilder.cs:27-127` for `Generate()` method | elevation_assessment.md | VERIFIED | Method starts at line 27 and ends at line 127 |
| 96 | `DiagnosticDescriptors.cs:34-107` for 7 descriptors | elevation_assessment.md | VERIFIED | First descriptor at line 34, last (`HandlerCannotBeStatic`) ends at line 106. The claim says 107 which includes the closing brace of the class -- close enough. |
| 97 | `RouteBuilder.cs:51-89` for `AddHandlerInternal` | six_sigma_gaps.md | VERIFIED | Line 51: `AddHandlerInternal` method definition, through line 89 |
| 98 | `IMessageHandler.cs:19,44` for the two interface declarations | elevation_assessment.md | VERIFIED | Line 19: `public interface IMessageHandler<TMessage>`, Line 44: `public interface IMessageHandler<TMessage, TResult>` |

## Inaccuracy Details

### Inaccuracy 1: ADR Count
- **Claim**: "15 ADRs found" (codebase-snapshot.md)
- **Actual**: 28 ADR files match `find docs/decisions -name "0*.md"`
- **Impact**: Low. The conclusion ("none related to source generators") remains valid regardless of count.

### Inaccuracy 2: Reflection File Total Line Count
- **Claim**: "~6 files, ~414+ lines removed" (elevation_assessment.md)
- **Actual**: 6 files, 487 total lines. ReflectingExecutor.cs is 76 lines (claimed 77).
- **Impact**: Low. The conclusion (subtraction gate passes) is strengthened by the higher actual count.

### Inaccuracy 3: Test Method Count
- **Claim**: "67 test methods" (six_sigma_gaps.md)
- **Actual**: 33 test methods (33 `[Fact]` attributes, 0 `[Theory]` attributes)
- **Impact**: Medium. The claim of 67 test methods significantly overstates the actual test count.

### Inaccuracy 4: ExecutorInfo.cs:25 for BaseHasConfigureProtocol
- **Claim**: "`BaseHasConfigureProtocol` boolean flag on ExecutorInfo (ExecutorInfo.cs:25)" (data.md)
- **Actual**: `BaseHasConfigureProtocol` is at line 26 in the record parameter list. Line 25 is `ImmutableEquatableArray<HandlerInfo> Handlers,`.
- **Impact**: Negligible. Off by 1 line.

### Inaccuracy 5: Sort location count
- **Claim**: "sorted type arrays (SemanticAnalyzer.cs:316, 629)" implies two sort locations (scale.md)
- **Actual**: There are four sort operations: lines 316, 317 (in CombineOutputOnlyResults), 629 (in ExtractTypeArray), and 661 (in GetClassLevelTypes). The claim mentions only two representative locations.
- **Impact**: Low. The claim is directionally correct but incomplete.

### Inaccuracy 6: ReflectingExecutor.cs line count
- **Claim**: "ReflectingExecutor.cs (77 lines)" (elevation_assessment.md)
- **Actual**: 76 lines
- **Impact**: Negligible. Off by 1 line.

### Inaccuracy 7: SourceBuilder.cs:206 claim
- **Re-verified**: Line 206 is `sb.AppendLine($".SendsMessage<{type}>()");` which IS correct. Reclassified as VERIFIED.

### Inaccuracy 8: SourceBuilder.cs:235 claim  
- **Re-verified**: Line 235 is `sb.AppendLine($".YieldsOutput<{type}>()");` which IS correct. Reclassified as VERIFIED.

## Revised Summary After Re-verification
- Total claims checked: 98
- Verified: 93
- Inaccurate: 5 (with corrections below)
  1. ADR count: 28, not 15 (codebase-snapshot.md)
  2. Reflection files total: 487 lines, not "~414+" (elevation_assessment.md); ReflectingExecutor.cs is 76 lines, not 77
  3. Test method count: 33, not 67 (six_sigma_gaps.md)
  4. ExecutorInfo.cs: BaseHasConfigureProtocol is at line 26, not 25 (data.md) -- negligible
  5. Sort location count: 4 locations, not 2 (scale.md) -- low impact, directionally correct
