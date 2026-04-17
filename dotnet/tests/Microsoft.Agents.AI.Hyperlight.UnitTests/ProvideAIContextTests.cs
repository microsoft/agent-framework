// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
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
        var context = await provider.InvokingAsync(NewInvokingContext()).ConfigureAwait(false);

        // Assert
        Assert.NotNull(context);
        Assert.NotNull(context!.Tools);
        Assert.Single(context.Tools!);
        var function = Assert.IsAssignableFrom<AIFunction>(context.Tools![0]);
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
        var context = await provider.InvokingAsync(NewInvokingContext()).ConfigureAwait(false);

        // Assert
        _ = Assert.IsType<ApprovalRequiredAIFunction>(context!.Tools![0]);
    }

    [Fact]
    public async Task ProvideAIContextAsync_NeverRequireWithApprovalTool_WrapsInApprovalRequiredAsync()
    {
        // Arrange
        var inner = AIFunctionFactory.Create(() => "ok", name: "t");
        using var provider = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions
        {
            ApprovalMode = CodeActApprovalMode.NeverRequire,
            Tools = new[] { (AIFunction)new ApprovalRequiredAIFunction(inner) },
        });

        // Act
        var context = await provider.InvokingAsync(NewInvokingContext()).ConfigureAwait(false);

        // Assert
        _ = Assert.IsType<ApprovalRequiredAIFunction>(context!.Tools![0]);
    }

    [Fact]
    public async Task ProvideAIContextAsync_CapturesSnapshot_MutationsAfterDoNotAffectDescriptionAsync()
    {
        // Arrange
        using var provider = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions());
        provider.AddTools(AIFunctionFactory.Create(() => "one", name: "first_tool"));

        // Act
        var context = await provider.InvokingAsync(NewInvokingContext()).ConfigureAwait(false);
        provider.AddTools(AIFunctionFactory.Create(() => "two", name: "second_tool"));

        // Assert — the returned execute_code description must reflect the first snapshot only.
        var function = Assert.IsAssignableFrom<AIFunction>(context!.Tools![0]);
        Assert.Contains("first_tool", function.Description);
        Assert.DoesNotContain("second_tool", function.Description);
    }
}
