# D5: Security

## Dimension Summary

Security considerations for a Roslyn source generator include: (1) the generator's execution context within the compiler host, (2) the generated code's security properties, (3) supply chain security (NuGet packaging), and (4) the attack surface of the attribute-driven API.

---

## Threat Model

### T1: Malicious Input via Attribute Arguments

**Threat:** A developer (or compromised dependency) places crafted type names in `[MessageHandler(Yield = [...], Send = [...])]` or `[SendsMessage(typeof(...))]` that, when emitted into generated code, produce injection attacks (e.g., type names containing C# code fragments).

**Severity:** Low.

**Analysis:** The generator uses `INamedTypeSymbol.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat)` (SemanticAnalyzer.cs:234, 507, 518) to produce type names. This API returns the Roslyn-resolved symbol name, NOT raw user text. A type name can only be a valid C# identifier that the compiler has already resolved. There is no string interpolation of user-provided raw text into generated code.

**Mitigation (already in place):** Symbol resolution prevents code injection. Only resolved type symbols are emitted.

### T2: Information Leakage via Diagnostic Messages

**Threat:** Diagnostic messages could leak sensitive information (internal type names, paths) to build logs visible to unauthorized parties.

**Severity:** Low.

**Analysis:** Diagnostics (DiagnosticDescriptors.cs) include method names and class names, which are part of the public API surface by definition (they appear in source code). No file paths, connection strings, or secrets are included in diagnostic messages.

**Mitigation (already in place):** Diagnostic messages contain only method/class names already visible in source.

### T3: Supply Chain Attack via NuGet Package

**Threat:** The generator DLL, packaged at `analyzers/dotnet/cs` (Microsoft.Agents.AI.Workflows.Generators.csproj:55), executes inside the compiler process. A compromised generator could run arbitrary code during compilation.

**Severity:** High (if compromised).

**Analysis:** This is an inherent risk of all Roslyn analyzers/generators. The generator runs with full compiler-process permissions. However, this is a first-party Microsoft package built from the same repo, signed, and distributed through official channels.

**Mitigation:**
- Package is built from the same solution with CI/CD controls
- `DevelopmentDependency=true` (Microsoft.Agents.AI.Workflows.Generators.csproj:41) prevents the generator from being a runtime dependency
- `ReferenceOutputAssembly=false` (Microsoft.Agents.AI.Workflows.csproj:38) prevents the generator assembly from being deployed with the application
- `SuppressDependenciesWhenPacking=true` (Microsoft.Agents.AI.Workflows.Generators.csproj:21) prevents pulling in transitive dependencies

### T4: Handler Method Accessibility Bypass

**Threat:** The source generator discovers `private` methods and generates code that references them. Could this expose private methods beyond their intended scope?

**Severity:** Negligible.

**Analysis:** The generated code is emitted into a `partial class` of the same type. A partial class has full access to all members of the same class, including private members. This is standard C# behavior. The generator does NOT make private methods accessible from outside the class -- it only references them via `this.MethodName` within the same class scope (SourceBuilder.cs:149, 161).

**Mitigation (already in place):** Partial class semantics guarantee that generated code has the same access as hand-written code in the same class.

---

## Option SEC1: Current Security Posture (RECOMMENDED)

The existing implementation has appropriate security characteristics for a first-party source generator:

1. **No raw string injection**: All emitted type names go through Roslyn symbol resolution
2. **No file system access**: Generator only reads the compilation model
3. **No network access**: Generator is purely computational
4. **Development dependency**: Generator assembly is compile-time only, not deployed to production
5. **Private member access is scoped**: Generated partial class code references `this.MethodName` within the same type

**Trade-offs:**
- (+) Minimal attack surface
- (+) No additional dependencies introduced
- (+) Standard Roslyn security model
- (-) Inherent analyzer trust model (all analyzers run in compiler process)

**Reversibility:** N/A.

**Constraint compliance:**
- C-3 (analyzer packaging): `DevelopmentDependency=true` and `ReferenceOutputAssembly=false` ensure generator is compile-time only
- C-5 (any accessibility): Private handler access is safe due to partial class semantics

**Dependencies produced:** Security posture assessment consumed by D6 (integration -- deployment).
**Dependencies required:** None.

**Risks:**
- Severity: Low overall.
- Mitigation: Standard supply chain security practices (CI/CD, signing, official distribution).

---

## Option SEC2: Add Input Validation for Type Names in SourceBuilder

Add explicit validation in SourceBuilder.Generate() to reject type names containing suspicious characters before emitting them into generated code.

**Trade-offs:**
- (+) Defense-in-depth against hypothetical symbol resolution bypass
- (-) Roslyn's SymbolDisplayFormat.FullyQualifiedFormat already guarantees valid identifiers
- (-) Any type name that passes Roslyn's symbol resolution is by definition a valid C# type
- (-) Adds unnecessary complexity

**Reversibility:** Easy.

**Constraint compliance:** All constraints met.

**Dependencies produced:** None.
**Dependencies required:** None.

**Risks:**
- Severity: Low. Over-engineering.
- Mitigation: N/A.

---

## Option SEC3: Add Generated Code Markers for Audit Trail

Enhance the generated code header (currently `// <auto-generated/>` in SourceBuilder.cs:32) with a generator version hash and timestamp to enable auditability.

**Trade-offs:**
- (+) Enables auditing which version of the generator produced the code
- (-) Timestamps in generated code would cause false cache misses in the incremental generator pipeline
- (-) Version hashes would require build infrastructure changes
- (-) Generated code is transient (not checked in); auditability has limited value

**Reversibility:** Easy.

**Constraint compliance:** All constraints met.

**Dependencies produced:** None.
**Dependencies required:** None.

**Risks:**
- Severity: Low.
- Mitigation: N/A.

---

## Option SEC4: Restrict Handler Discovery to Explicitly Public Methods Only

Only generate routes for public or internal handler methods, requiring users to explicitly opt-in by making handlers non-private.

**REJECTED: violates C-5 (handler accessibility: any)**

C-5 explicitly states "Handler accessibility: Any (private, protected, internal, public)". Restricting to public methods would violate this constraint.

Additionally, the primary use case for [MessageHandler] is to allow private handler methods (which is more encapsulated than forcing public), so this restriction would actively harm the design intent.

**Trade-offs:**
- (+) Reduces surface area for accidental handler exposure
- (-) Violates C-5
- (-) Forces users to make implementation methods public, breaking encapsulation

**Reversibility:** Easy.

---

## Summary

**Recommended option: SEC1** -- The current security posture is appropriate. The generator operates within the standard Roslyn security model, uses symbol resolution (not raw strings) for code generation, and is correctly packaged as a compile-time-only development dependency.
