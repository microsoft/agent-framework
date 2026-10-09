// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using AgentHooks;
using Microsoft.Extensions.AI;
using static Microsoft.Agents.AI.AgentHooks.UnitTests.TestHelpers;

namespace Microsoft.Agents.AI.AgentHooks.UnitTests;

/// <summary>The host declaration path (spec §7.7): options built from a document, not from code.</summary>
public class AgentHooksDeclarationTests
{
    private const string AllowKind = "test.allow";
    private const string DenyOutputKind = "test.deny-output";

    // -------------------------------------------------------------------------
    // Happy path
    // -------------------------------------------------------------------------

    [Fact]
    public async Task DeclarationJsonDrivesTheFullSessionAsync()
    {
        // Arrange
        var client = new MockChatClient()
            .EnqueueFunctionCall("call-1", "get_weather", new() { ["location"] = "Paris" })
            .EnqueueText("It is sunny.");
        var guard = new AllowGuard();
        var records = new ConcurrentQueue<InterceptionRecord>();
        var options = AgentHooksOptions.FromDeclarationJson(
            Document(("allow", AllowKind, null)).ToJsonString(),
            registry => registry.Kind(AllowKind, (_, _) => guard));
        options.RecordSink = records.Enqueue;
        var agent = client.AsAIAgentWithAgentHooks(options, AgentOptionsWithTools(WeatherTool()));

        // Act
        var response = await agent.RunAsync(UserMessage("weather in paris?"));

        // Assert: same session shape as the code path, every record stamped with the contract version.
        Assert.Equal("It is sunny.", response.Text);
        Assert.Equal(
            [
                "agent_startup", "input",
                "pre_model_call", "post_model_call",
                "pre_tool_call", "post_tool_call",
                "pre_model_call", "post_model_call",
                "output", "agent_shutdown",
            ],
            guard.Points);
        Assert.Equal(10, records.Count);
        Assert.All(records, record => Assert.Equal(Declaration.Version, record.Declaration));
        Assert.All(records, record => Assert.Equal(EnforcementMode.Enforce, record.Mode));
        Assert.NotNull(options.ResolvedDeclaration);
        Assert.Equal(ToolSeamPosture.Terminate, options.ResolvedDeclaration!.ToolSeamHostError);
        Assert.Empty(options.Interceptors);
    }

    [Fact]
    public async Task PathJsonAndNodeResolveToTheSameDeclarationAsync()
    {
        // Arrange
        var document = Document(("allow", AllowKind, null));
        var path = Path.Combine(Path.GetTempPath(), $"agent-hooks-{Guid.NewGuid():N}.declaration.json");
        File.WriteAllText(path, document.ToJsonString());
        try
        {
            // Act
            var fromPath = AgentHooksOptions.FromDeclarationPath(path, AllowRegistry(new AllowGuard()));
            var fromJson = AgentHooksOptions.FromDeclarationJson(document.ToJsonString(), AllowRegistry(new AllowGuard()));
            var fromNode = AgentHooksOptions.FromDeclarationNode(document, AllowRegistry(new AllowGuard()));

            // Assert: one canonical resolved form, and the file-built options run.
            var canonical = fromPath.ResolvedDeclaration!.CanonicalJson();
            Assert.Equal(canonical, fromJson.ResolvedDeclaration!.CanonicalJson());
            Assert.Equal(canonical, fromNode.ResolvedDeclaration!.CanonicalJson());

            var client = new MockChatClient().EnqueueText("hi");
            var response = await client.AsAIAgentWithAgentHooks(fromPath).RunAsync(UserMessage("hello"));
            Assert.Equal("hi", response.Text);
        }
        finally
        {
            File.Delete(path);
        }
    }

    [Fact]
    public async Task BindingAtRestrictsThePointsABindingRunsAtAsync()
    {
        // Arrange: an audit binding at every point and a tool-only binding.
        var client = new MockChatClient()
            .EnqueueFunctionCall("call-1", "get_weather", new() { ["location"] = "Paris" })
            .EnqueueText("done");
        var audit = new AllowGuard();
        var toolOnly = new AllowGuard();
        var records = new ConcurrentQueue<InterceptionRecord>();
        var options = AgentHooksOptions.FromDeclarationNode(
            Document(("audit", AllowKind, null), ("tool-guard", "test.tool", ["pre_tool_call"])),
            registry => registry
                .Kind(AllowKind, (_, _) => audit)
                .Kind("test.tool", (_, _) => toolOnly));
        options.RecordSink = records.Enqueue;
        var agent = client.AsAIAgentWithAgentHooks(options, AgentOptionsWithTools(WeatherTool()));

        // Act
        _ = await agent.RunAsync(UserMessage("weather?"));

        // Assert
        Assert.Equal(["pre_tool_call"], toolOnly.Points);
        Assert.Equal(10, audit.Points.Count);
        Assert.Equal(2, records.Single(r => r.InterceptionPoint == InterceptionPoint.PreToolCall).InterceptorsRegistered);
        Assert.Equal(1, records.Single(r => r.InterceptionPoint == InterceptionPoint.Input).InterceptorsRegistered);
    }

    [Fact]
    public async Task DeclaredEvaluateOnlyModeRecordsDeniesWithoutBlockingAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("secret payload");
        var document = Document(("deny", DenyOutputKind, null));
        document["configuration"]!["mode"] = "evaluate_only";
        var records = new ConcurrentQueue<InterceptionRecord>();
        var options = AgentHooksOptions.FromDeclarationNode(
            document,
            registry => registry.Kind(DenyOutputKind, (_, _) => new PointGuard(InterceptionPoint.Output, Verdict.Deny("policy"))));
        options.RecordSink = records.Enqueue;
        Assert.Equal(EnforcementMode.EvaluateOnly, options.Mode);

        // Act
        var response = await client.AsAIAgentWithAgentHooks(options).RunAsync(UserMessage("hello"));

        // Assert: the deny is recorded, the run egresses.
        Assert.Equal("secret payload", response.Text);
        var output = records.Single(r => r.InterceptionPoint == InterceptionPoint.Output);
        Assert.Equal(EnforcementMode.EvaluateOnly, output.Mode);
        Assert.Equal(Decision.Deny, output.Verdict.Decision);
    }

    [Fact]
    public async Task DeclaredEnforceModeBlocksOnDenyAsync()
    {
        // Arrange
        var client = new MockChatClient().EnqueueText("secret payload");
        var options = AgentHooksOptions.FromDeclarationNode(
            Document(("deny", DenyOutputKind, null)),
            registry => registry.Kind(DenyOutputKind, (_, _) => new PointGuard(InterceptionPoint.Output, Verdict.Deny("policy"))));

        // Act / Assert
        var blocked = await Assert.ThrowsAsync<InterceptionBlockedException>(
            () => client.AsAIAgentWithAgentHooks(options).RunAsync(UserMessage("hello")));
        Assert.Equal("policy", blocked.Result.Verdict.Reason);
    }

    [Fact]
    public void CodePathIsUnchanged()
    {
        // Arrange / Act
        var options = new AgentHooksOptions(new AllowGuard()) { Mode = EnforcementMode.EvaluateOnly, Timeout = TimeSpan.FromSeconds(1) };

        // Assert
        Assert.Null(options.Declaration);
        Assert.Null(options.ResolvedDeclaration);
        Assert.Single(options.Interceptors);
        Assert.Equal(EnforcementMode.EvaluateOnly, options.Mode);
        Assert.Equal(TimeSpan.FromSeconds(1), options.Timeout);
    }

    // -------------------------------------------------------------------------
    // Refusals, all before any agent exists
    // -------------------------------------------------------------------------

    [Fact]
    public void UnknownKindIsRefused()
    {
        // Act
        var refused = Assert.Throws<DeclarationException>(
            () => AgentHooksOptions.FromDeclarationNode(Document(("x", "test.unknown", null)), _ => { }));

        // Assert
        Assert.Equal(DeclarationErrorClass.KindUnknown, refused.Class);
        Assert.Contains(refused.Findings, f => f.Pointer == "/bindings/0/kind");
    }

    [Fact]
    public void ContractDefaultPostureIsRefusedBecauseThisHostTerminates()
    {
        // Arrange: no posture block, so the document defaults to `continue`.
        var document = Document(("allow", AllowKind, null));
        document["configuration"] = new JsonObject();

        // Act
        var refused = Assert.Throws<DeclarationException>(
            () => AgentHooksOptions.FromDeclarationNode(document, AllowRegistry(new AllowGuard())));

        // Assert
        Assert.Equal(DeclarationErrorClass.SurfaceUnsupported, refused.Class);
        Assert.Contains(refused.Findings, f => f.Pointer == "/configuration/posture/tool_seam_host_error");
    }

    [Fact]
    public void BindingRejectedByItsResolverIsRefused()
    {
        // Act
        var refused = Assert.Throws<DeclarationException>(
            () => AgentHooksOptions.FromDeclarationNode(
                Document(("bad", AllowKind, null)),
                registry => registry.Kind(AllowKind, (_, _) => throw new InvalidOperationException("no such policy"))));

        // Assert
        Assert.Equal(DeclarationErrorClass.BindingRejected, refused.Class);
        Assert.Contains(refused.Findings, f => f.Pointer == "/bindings/0" && f.Detail.Contains("no such policy", StringComparison.Ordinal));
    }

    [Fact]
    public void MissingFileIsRefusedAsUnreadable()
    {
        // Act
        var refused = Assert.Throws<DeclarationException>(
            () => AgentHooksOptions.FromDeclarationPath(
                Path.Combine(Path.GetTempPath(), $"missing-{Guid.NewGuid():N}.json"), AllowRegistry(new AllowGuard())));

        // Assert
        Assert.Equal(DeclarationErrorClass.Unreadable, refused.Class);
    }

    [Fact]
    public void MalformedJsonIsRefused()
    {
        // Act
        var refused = Assert.Throws<DeclarationException>(
            () => AgentHooksOptions.FromDeclarationJson("{ not json", AllowRegistry(new AllowGuard())));

        // Assert
        Assert.Equal(DeclarationErrorClass.Malformed, refused.Class);
    }

    [Fact]
    public void DocumentWithoutBindingsIsRejected()
    {
        // Act / Assert
        var rejected = Assert.Throws<ArgumentException>(
            () => AgentHooksOptions.FromDeclarationNode(Document(), AllowRegistry(new AllowGuard())));
        Assert.Equal("declaration", rejected.ParamName);
    }

    [Fact]
    public void DeclaredOptionsAreSealedExceptTheRecordSink()
    {
        // Arrange
        var options = AgentHooksOptions.FromDeclarationNode(Document(("allow", AllowKind, null)), AllowRegistry(new AllowGuard()));

        // Assert: the readers mirror the document where the type is the same, and stay
        // null where the document holds names or two values (ResolvedDeclaration has them).
        var resolved = options.ResolvedDeclaration!;
        Assert.Equal(resolved.Mode, options.Mode);
        Assert.Same(resolved.Composition, options.Composition);
        Assert.Null(options.Resolver);
        Assert.Null(options.IdentityProvider);
        Assert.Null(options.Timeout);
        Assert.Null(resolved.ApprovalResolver);
        Assert.Equal("jcs-sha256", resolved.IdentityProvider);

        // Act / Assert
        _ = Assert.Throws<InvalidOperationException>(() => options.Mode = EnforcementMode.EvaluateOnly);
        _ = Assert.Throws<InvalidOperationException>(() => options.Resolver = new NeverResolver());
        _ = Assert.Throws<InvalidOperationException>(() => options.Composition = CompositionConfig.RunAll());
        _ = Assert.Throws<InvalidOperationException>(() => options.IdentityProvider = IdentityProvider.Null);
        _ = Assert.Throws<InvalidOperationException>(() => options.Timeout = TimeSpan.FromSeconds(1));
        _ = Assert.Throws<InvalidOperationException>(() => options.AddInterceptor(new AllowGuard()));
        options.RecordSink = _ => { };
        Assert.NotNull(options.RecordSink);
    }

    [Fact]
    public void NullArgumentsAreRejected()
    {
        _ = Assert.Throws<ArgumentNullException>(() => AgentHooksOptions.FromDeclaration(null!, _ => { }));
        _ = Assert.Throws<ArgumentNullException>(() => AgentHooksOptions.FromDeclaration(HostDeclaration.FromNode(Document()), null!));
        _ = Assert.Throws<ArgumentNullException>(() => AgentHooksOptions.FromDeclarationPath(null!, _ => { }));
        _ = Assert.Throws<ArgumentNullException>(() => AgentHooksOptions.FromDeclarationJson(null!, _ => { }));
    }

    // -------------------------------------------------------------------------
    // Surface capabilities: int64_json and bigint_json
    // -------------------------------------------------------------------------

    [Theory]
    [InlineData("9007199254740993")] // 2^53 + 1: int64_json (AH-CTK-090)
    [InlineData("18446744073709551616")] // 2^64: bigint_json (AH-CTK-091)
    public async Task LargeIntegerToolArgumentsReachTheCoreAsTheModelWroteThemAsync(string literal)
    {
        // Arrange: a provider hands tool-call arguments over as JsonElement values. The
        // surface claims that such a token reaches the core as written, so the jcs-sha256
        // provider sees it and refuses the context (spec 4.4, 10.2) before any interceptor
        // runs. A projection that rounded it to a double would let the run through.
        using var parsed = JsonDocument.Parse(literal);
        bool toolInvoked = false;
        var tool = AIFunctionFactory.Create((string id) => { toolInvoked = true; return "sent"; }, "wire_transfer");
        var client = new MockChatClient()
            .EnqueueFunctionCall("call-1", "wire_transfer", new() { ["id"] = parsed.RootElement.Clone() })
            .EnqueueText("sent");
        var guard = new AllowGuard();
        var records = new ConcurrentQueue<InterceptionRecord>();
        var options = AgentHooksOptions.FromDeclarationNode(Document(("allow", AllowKind, null)), AllowRegistry(guard));
        options.RecordSink = records.Enqueue;
        var agent = client.AsAIAgentWithAgentHooks(options, AgentOptionsWithTools(tool));

        // Act
        var blocked = await Assert.ThrowsAsync<InterceptionBlockedException>(() => agent.RunAsync(UserMessage("go")));

        // Assert: denied at post_model_call, the first emission whose preimage carries the integer.
        Assert.Equal(HostError.ContextInvalid, blocked.Result.Verdict.Reason);
        var post = records.Single(r => r.InterceptionPoint == InterceptionPoint.PostModelCall);
        Assert.Equal(Decision.Deny, post.Verdict.Decision);
        Assert.Equal(HostError.ContextInvalid, post.Verdict.Reason);
        Assert.Null(post.InputIdentity);
        Assert.Equal("jcs-sha256", post.IdentityProvider);
        Assert.Empty(post.Verdicts);
        Assert.DoesNotContain("post_model_call", guard.Points);
        Assert.DoesNotContain("pre_tool_call", guard.Points);
        Assert.False(toolInvoked);
        Assert.Contains("int64_json", AgentHooksHostSurface.Surface.Capabilities);
        Assert.Contains("bigint_json", AgentHooksHostSurface.Surface.Capabilities);
    }

    [Fact]
    public async Task Int64ToolArgumentReachesTheCoreUnroundedAsync()
    {
        // Arrange: the same token as a native long, the other shape arguments take in process.
        var client = new MockChatClient()
            .EnqueueFunctionCall("call-1", "wire_transfer", new() { ["id"] = 9_007_199_254_740_993L })
            .EnqueueText("sent");
        var records = new ConcurrentQueue<InterceptionRecord>();
        var options = AgentHooksOptions.FromDeclarationNode(Document(("allow", AllowKind, null)), AllowRegistry(new AllowGuard()));
        options.RecordSink = records.Enqueue;
        var agent = client.AsAIAgentWithAgentHooks(options, AgentOptionsWithTools(WeatherTool()));

        // Act
        var blocked = await Assert.ThrowsAsync<InterceptionBlockedException>(() => agent.RunAsync(UserMessage("go")));

        // Assert
        Assert.Equal(HostError.ContextInvalid, blocked.Result.Verdict.Reason);
        Assert.Equal(InterceptionPoint.PostModelCall, blocked.Result.InterceptionPoint);
        Assert.DoesNotContain(records, r => r.InterceptionPoint == InterceptionPoint.PreToolCall);
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    /// <summary>A minimal document for this host: the posture must be stated because the contract default is `continue`.</summary>
    private static JsonObject Document(params (string Id, string Kind, string[]? At)[] bindings) => new()
    {
        ["declaration"] = Declaration.Version,
        ["configuration"] = new JsonObject
        {
            ["posture"] = new JsonObject { ["tool_seam_host_error"] = "terminate" },
        },
        ["bindings"] = new JsonArray(bindings.Select(JsonNode (b) =>
        {
            var binding = new JsonObject { ["id"] = b.Id, ["kind"] = b.Kind };
            if (b.At is not null)
            {
                binding["at"] = new JsonArray(b.At.Select(JsonNode? (a) => a).ToArray());
            }

            return binding;
        }).ToArray()),
    };

    private static Action<HostRegistry> AllowRegistry(IInterceptor interceptor) =>
        registry => registry.Kind(AllowKind, (_, _) => interceptor);

    private sealed class NeverResolver : IApprovalResolver
    {
        public ValueTask<ApprovalResolution> ResolveAsync(ApprovalRequest request, CancellationToken ct = default) =>
            throw new NotSupportedException();
    }
}
