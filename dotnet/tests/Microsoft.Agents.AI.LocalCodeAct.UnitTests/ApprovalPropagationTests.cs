// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.LocalCodeAct.UnitTests;

/// <summary>
/// Regression tests for approval propagation from provider-owned CodeAct tools to the
/// model-facing <c>execute_code</c> function.
/// </summary>
/// <remarks>
/// Generated code reaches registered tools through <c>call_tool(...)</c>, which invokes them
/// directly and therefore cannot surface a per-tool approval interaction. Approval must be
/// bundled onto <c>execute_code</c> instead.
/// </remarks>
public sealed class ApprovalPropagationTests
{
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;

    private static AIContextProvider.InvokingContext NewInvokingContext() =>
        new(s_mockAgent, session: null, new AIContext());

    private static ApprovalRequiredAIFunction GatedTool() =>
        new(AIFunctionFactory.Create(() => "ok", name: "approval_gated_shell"));

    [Fact]
    public void ComputeApprovalRequired_AlwaysRequire_NoTools_ReturnsTrue()
    {
        // Act / Assert
        Assert.True(LocalCodeActProvider.ComputeApprovalRequired(LocalCodeActApprovalMode.AlwaysRequire, tools: []));
    }

    [Fact]
    public void ComputeApprovalRequired_AlwaysRequire_WithoutGatedTool_ReturnsTrue()
    {
        // Arrange
        var tool = AIFunctionFactory.Create(() => "ok", name: "t");

        // Act / Assert
        Assert.True(LocalCodeActProvider.ComputeApprovalRequired(LocalCodeActApprovalMode.AlwaysRequire, tools: [tool]));
    }

    [Fact]
    public void ComputeApprovalRequired_NeverRequire_NoTools_ReturnsFalse()
    {
        // Act / Assert
        Assert.False(LocalCodeActProvider.ComputeApprovalRequired(LocalCodeActApprovalMode.NeverRequire, tools: []));
    }

    [Fact]
    public void ComputeApprovalRequired_NeverRequire_WithoutGatedTool_ReturnsFalse()
    {
        // Arrange
        var tool = AIFunctionFactory.Create(() => "ok", name: "t");

        // Act / Assert
        Assert.False(LocalCodeActProvider.ComputeApprovalRequired(LocalCodeActApprovalMode.NeverRequire, tools: [tool]));
    }

    [Fact]
    public void ComputeApprovalRequired_NeverRequire_WithGatedTool_ReturnsTrue()
    {
        // Arrange
        var tool = GatedTool();

        // Act / Assert
        Assert.True(LocalCodeActProvider.ComputeApprovalRequired(LocalCodeActApprovalMode.NeverRequire, tools: [tool]));
    }

    [Fact]
    public async Task ProvideAIContextAsync_WithGatedTool_WrapsExecuteCodeInApprovalRequiredAsync()
    {
        // Arrange
        using var provider = new LocalCodeActProvider(
            "/usr/bin/python3",
            new LocalCodeActProviderOptions
            {
                ValidationDisabled = true,
                Tools = [GatedTool()],
            });

        // Act
        var context = await provider.InvokingAsync(NewInvokingContext());

        // Assert
        var tool = Assert.IsType<ApprovalRequiredAIFunction>(context!.Tools!.Single());
        Assert.Equal("execute_code", tool.Name);
        Assert.NotNull(tool.GetService<ApprovalRequiredAIFunction>());
    }

    [Fact]
    public async Task ProvideAIContextAsync_ToolAddedAfterConstruction_WrapsExecuteCodeInApprovalRequiredAsync()
    {
        // Arrange
        using var provider = new LocalCodeActProvider(
            "/usr/bin/python3",
            new LocalCodeActProviderOptions { ValidationDisabled = true });
        provider.AddTools(GatedTool());

        // Act
        var context = await provider.InvokingAsync(NewInvokingContext());

        // Assert
        _ = Assert.IsType<ApprovalRequiredAIFunction>(context!.Tools!.Single());
    }

    [Fact]
    public async Task ProvideAIContextAsync_AlwaysRequire_WrapsExecuteCodeInApprovalRequiredAsync()
    {
        // Arrange
        using var provider = new LocalCodeActProvider(
            "/usr/bin/python3",
            new LocalCodeActProviderOptions
            {
                ValidationDisabled = true,
                ApprovalMode = LocalCodeActApprovalMode.AlwaysRequire,
            });

        // Act
        var context = await provider.InvokingAsync(NewInvokingContext());

        // Assert
        _ = Assert.IsType<ApprovalRequiredAIFunction>(context!.Tools!.Single());
    }

    [Fact]
    public async Task ProvideAIContextAsync_WithoutGatedTool_DoesNotRequireApprovalAsync()
    {
        // Arrange
        using var provider = new LocalCodeActProvider(
            "/usr/bin/python3",
            new LocalCodeActProviderOptions
            {
                ValidationDisabled = true,
                Tools = [AIFunctionFactory.Create(() => "ok", name: "ping")],
            });

        // Act
        var context = await provider.InvokingAsync(NewInvokingContext());

        // Assert
        var tool = Assert.IsAssignableFrom<AIFunction>(context!.Tools!.Single());
        Assert.IsNotType<ApprovalRequiredAIFunction>(tool);
        Assert.Null(tool.GetService<ApprovalRequiredAIFunction>());
    }

    [Fact]
    public void LocalExecuteCodeFunction_WithGatedTool_ExposesApprovalRequiredService()
    {
        // Arrange
        var function = new LocalExecuteCodeFunction(
            "/usr/bin/python3",
            new LocalCodeActProviderOptions
            {
                ValidationDisabled = true,
                Tools = [GatedTool()],
            });

        // Act
        var marker = function.GetService<ApprovalRequiredAIFunction>();

        // Assert
        Assert.NotNull(marker);
        Assert.Same(marker, function.GetService<ApprovalRequiredAIFunction>());
        Assert.Equal("execute_code", marker!.Name);
    }

    [Fact]
    public void LocalExecuteCodeFunction_AlwaysRequire_ExposesApprovalRequiredService()
    {
        // Arrange
        var function = new LocalExecuteCodeFunction(
            "/usr/bin/python3",
            new LocalCodeActProviderOptions
            {
                ValidationDisabled = true,
                ApprovalMode = LocalCodeActApprovalMode.AlwaysRequire,
            });

        // Act / Assert
        Assert.NotNull(function.GetService<ApprovalRequiredAIFunction>());
    }

    [Fact]
    public void LocalExecuteCodeFunction_WithoutGatedTool_DoesNotExposeApprovalRequiredService()
    {
        // Arrange
        var function = new LocalExecuteCodeFunction(
            "/usr/bin/python3",
            new LocalCodeActProviderOptions
            {
                ValidationDisabled = true,
                Tools = [AIFunctionFactory.Create(() => "ok", name: "ping")],
            });

        // Act / Assert
        Assert.Null(function.GetService<ApprovalRequiredAIFunction>());
    }

    [Fact]
    public void LocalExecuteCodeFunction_WithServiceKey_DoesNotExposeApprovalRequiredService()
    {
        // Arrange
        var function = new LocalExecuteCodeFunction(
            "/usr/bin/python3",
            new LocalCodeActProviderOptions
            {
                ValidationDisabled = true,
                Tools = [GatedTool()],
            });

        // Act / Assert
        Assert.Null(function.GetService(typeof(ApprovalRequiredAIFunction), serviceKey: "key"));
    }
}
