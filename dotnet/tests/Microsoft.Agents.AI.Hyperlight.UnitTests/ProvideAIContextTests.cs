// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hyperlight.Internal;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Hyperlight.UnitTests;

public sealed class ProvideAIContextTests
{
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;

    private static AIContextProvider.InvokingContext NewInvokingContext() => new(s_mockAgent, session: null, new AIContext());

    [Fact]
    public async Task ProvideAIContextAsync_ReturnsExecuteCodeToolAndInstructionsAsync()
    {
        // Arrange
        using var provider = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions());

        // Act
        var context = await provider.InvokingAsync(NewInvokingContext());

        // Assert
        Assert.NotNull(context);
        Assert.NotNull(context!.Tools);
        var tools = context.Tools!.ToList();
        Assert.Single(tools);
        var function = Assert.IsAssignableFrom<AIFunction>(tools[0]);
        Assert.Equal("execute_code", function.Name);
        Assert.False(string.IsNullOrWhiteSpace(context.Instructions));
    }

    [Fact]
    public async Task ProvideAIContextAsync_AlwaysRequire_WrapsInApprovalRequiredAsync()
    {
        // Arrange
        using var provider = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions
        {
            ApprovalMode = CodeActApprovalMode.AlwaysRequire,
        });

        // Act
        var context = await provider.InvokingAsync(NewInvokingContext());

        // Assert
        _ = Assert.IsType<ApprovalRequiredAIFunction>(context!.Tools!.First());
    }

    [Fact]
    public async Task ProvideAIContextAsync_NeverRequireWithApprovalTool_WrapsInApprovalRequiredAsync()
    {
        // Arrange
        var inner = AIFunctionFactory.Create(() => "ok", name: "t");
        using var provider = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions
        {
            ApprovalMode = CodeActApprovalMode.NeverRequire,
            Tools = [new ApprovalRequiredAIFunction(inner)],
        });

        // Act
        var context = await provider.InvokingAsync(NewInvokingContext());

        // Assert
        _ = Assert.IsType<ApprovalRequiredAIFunction>(context!.Tools!.First());
    }

    [Fact]
    public async Task ProvideAIContextAsync_CapturesSnapshot_MutationsAfterDoNotAffectDescriptionAsync()
    {
        // Arrange
        using var provider = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions());
        provider.AddTools(AIFunctionFactory.Create(() => "one", name: "first_tool"));

        // Act
        var context = await provider.InvokingAsync(NewInvokingContext());
        provider.AddTools(AIFunctionFactory.Create(() => "two", name: "second_tool"));

        // Assert — the returned execute_code description must reflect the first snapshot only.
        var function = Assert.IsAssignableFrom<AIFunction>(context!.Tools!.First());
        Assert.Contains("first_tool", function.Description);
        Assert.DoesNotContain("second_tool", function.Description);
    }

    [Fact]
    public async Task ProvideAIContextAsync_AddToolsSameNameReplacement_ChangesSnapshotFingerprintAsync()
    {
        // Arrange
        using var provider = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions());
        provider.AddTools(AIFunctionFactory.Create(() => "one", name: "same_tool"));

        // Act
        var firstContext = await provider.InvokingAsync(NewInvokingContext());
        provider.AddTools(AIFunctionFactory.Create(() => "two", name: "same_tool"));
        var secondContext = await provider.InvokingAsync(NewInvokingContext());

        // Assert
        var firstFunction = Assert.IsType<ExecuteCodeFunction>(firstContext!.Tools!.First());
        var secondFunction = Assert.IsType<ExecuteCodeFunction>(secondContext!.Tools!.First());
        Assert.NotEqual(firstFunction.ConfigFingerprint, secondFunction.ConfigFingerprint);
    }

    [Fact]
    public async Task ProvideAIContextAsync_ToolAddRemoveAndClear_ChangeSnapshotFingerprintAsync()
    {
        // Arrange
        using var provider = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions());
        var firstTool = AIFunctionFactory.Create(() => "one", name: "first_tool");
        var secondTool = AIFunctionFactory.Create(() => "two", name: "second_tool");
        var fingerprints = new List<string>();

        // Act
        fingerprints.Add(await GetFingerprintAsync(provider));
        provider.AddTools(firstTool);
        fingerprints.Add(await GetFingerprintAsync(provider));
        provider.RemoveTools(firstTool.Name);
        fingerprints.Add(await GetFingerprintAsync(provider));
        provider.AddTools(firstTool, secondTool);
        fingerprints.Add(await GetFingerprintAsync(provider));
        provider.ClearTools();
        fingerprints.Add(await GetFingerprintAsync(provider));

        // Assert
        AssertFingerprintsChanged(fingerprints);
    }

    [Fact]
    public async Task ProvideAIContextAsync_FileMountAddReplaceRemoveAndClear_ChangeSnapshotFingerprintAsync()
    {
        // Arrange
        using var provider = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions());
        var fingerprints = new List<string>();

        // Act
        fingerprints.Add(await GetFingerprintAsync(provider));
        provider.AddFileMounts(new FileMount("/host/one", "/input/data"));
        fingerprints.Add(await GetFingerprintAsync(provider));
        provider.AddFileMounts(new FileMount("/host/two", "/input/data"));
        fingerprints.Add(await GetFingerprintAsync(provider));
        provider.RemoveFileMounts("/input/data");
        fingerprints.Add(await GetFingerprintAsync(provider));
        provider.AddFileMounts(new FileMount("/host/three", "/input/other"));
        fingerprints.Add(await GetFingerprintAsync(provider));
        provider.ClearFileMounts();
        fingerprints.Add(await GetFingerprintAsync(provider));

        // Assert
        AssertFingerprintsChanged(fingerprints);
    }

    [Fact]
    public async Task ProvideAIContextAsync_AllowedDomainAddReplaceRemoveAndClear_ChangeSnapshotFingerprintAsync()
    {
        // Arrange
        using var provider = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions());
        var fingerprints = new List<string>();

        // Act
        fingerprints.Add(await GetFingerprintAsync(provider));
        provider.AddAllowedDomains(new AllowedDomain("https://example.com", ["GET"]));
        fingerprints.Add(await GetFingerprintAsync(provider));
        provider.AddAllowedDomains(new AllowedDomain("https://example.com", ["POST"]));
        fingerprints.Add(await GetFingerprintAsync(provider));
        provider.RemoveAllowedDomains("https://example.com");
        fingerprints.Add(await GetFingerprintAsync(provider));
        provider.AddAllowedDomains(new AllowedDomain("https://contoso.com"));
        fingerprints.Add(await GetFingerprintAsync(provider));
        provider.ClearAllowedDomains();
        fingerprints.Add(await GetFingerprintAsync(provider));

        // Assert
        AssertFingerprintsChanged(fingerprints);
    }

    [Fact]
    public async Task ProvideAIContextAsync_SandboxOptionMutation_ChangesSnapshotFingerprintAsync()
    {
        // Arrange
        var options = new HyperlightCodeActProviderOptions { HeapSize = "10Mi", StackSize = "5Mi" };
        using var provider = new HyperlightCodeActProvider(options);

        // Act
        var firstFingerprint = await GetFingerprintAsync(provider);
        options.HeapSize = "20Mi";
        options.StackSize = "10Mi";
        var secondFingerprint = await GetFingerprintAsync(provider);

        // Assert
        Assert.NotEqual(firstFingerprint, secondFingerprint);
    }

    private static void AssertFingerprintsChanged(List<string> fingerprints)
    {
        for (var index = 1; index < fingerprints.Count; index++)
        {
            Assert.NotEqual(fingerprints[index - 1], fingerprints[index]);
        }
    }

    private static async Task<string> GetFingerprintAsync(HyperlightCodeActProvider provider)
    {
        var context = await provider.InvokingAsync(NewInvokingContext());
        return Assert.IsType<ExecuteCodeFunction>(context!.Tools!.First()).ConfigFingerprint;
    }
}
