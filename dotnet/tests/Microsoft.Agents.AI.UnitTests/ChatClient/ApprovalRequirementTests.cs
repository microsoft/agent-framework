// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Tests for <see cref="ApprovalRequirement"/>, the shared rule that decides whether a tool call is
/// subject to human approval.
/// </summary>
public class ApprovalRequirementTests
{
    [Fact]
    public void GetApprovalNotRequiredToolNames_ApprovalFreeTool_IsIncluded()
    {
        // Arrange
        var normalTool = AIFunctionFactory.Create(() => "result", "normalTool");
        var options = new ChatOptions { Tools = [normalTool] };

        // Act
        var names = ApprovalRequirement.GetApprovalNotRequiredToolNames(CreateClient(), options);

        // Assert
        Assert.Equal(["normalTool"], names);
    }

    [Fact]
    public void GetApprovalNotRequiredToolNames_ApprovalRequiredTool_IsExcluded()
    {
        // Arrange
        var approvalTool = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "result", "approvalTool"));
        var options = new ChatOptions { Tools = [approvalTool] };

        // Act
        var names = ApprovalRequirement.GetApprovalNotRequiredToolNames(CreateClient(), options);

        // Assert
        Assert.Empty(names);
    }

    [Fact]
    public void GetApprovalNotRequiredToolNames_SameNameGatedAndFree_Throws()
    {
        // Arrange — a gated tool and an approval-free tool sharing one name, as happens when an MCP
        // server advertises a tool whose name collides with a locally gated one.
        var gated = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "gated", "deploy"));
        var free = AIFunctionFactory.Create(() => "free", "deploy");
        var options = new ChatOptions { Tools = [gated, free] };

        // Act & Assert — the call is ambiguous, so it is rejected rather than resolved.
        var exception = Assert.Throws<InvalidOperationException>(
            () => ApprovalRequirement.GetApprovalNotRequiredToolNames(CreateClient(), options));
        Assert.Equal("Duplicate tool name 'deploy'. Tool names must be unique.", exception.Message);
    }

    [Fact]
    public void GetApprovalNotRequiredToolNames_SameNameFreeListedFirst_Throws()
    {
        // Arrange — same collision, opposite ordering, to show the answer does not depend on enumeration order.
        var free = AIFunctionFactory.Create(() => "free", "deploy");
        var gated = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "gated", "deploy"));
        var options = new ChatOptions { Tools = [free, gated] };

        // Act & Assert
        Assert.Throws<InvalidOperationException>(
            () => ApprovalRequirement.GetApprovalNotRequiredToolNames(CreateClient(), options));
    }

    [Fact]
    public void GetApprovalNotRequiredToolNames_TwoApprovalFreeToolsShareName_Throws()
    {
        // Arrange — the ambiguity is rejected whether or not approval is involved.
        var first = AIFunctionFactory.Create(() => "first", "deploy");
        var second = AIFunctionFactory.Create(() => "second", "deploy");
        var options = new ChatOptions { Tools = [first, second] };

        // Act & Assert
        Assert.Throws<InvalidOperationException>(
            () => ApprovalRequirement.GetApprovalNotRequiredToolNames(CreateClient(), options));
    }

    [Fact]
    public void GetApprovalNotRequiredToolNames_SameInstanceListedTwice_DoesNotThrow()
    {
        // Arrange — one instance offered twice names a single tool, so nothing is ambiguous.
        var tool = AIFunctionFactory.Create(() => "result", "deploy");
        var options = new ChatOptions { Tools = [tool, tool] };

        // Act
        var names = ApprovalRequirement.GetApprovalNotRequiredToolNames(CreateClient(), options);

        // Assert
        Assert.Equal(["deploy"], names);
    }

    [Fact]
    public void GetApprovalNotRequiredToolNames_GatedInToolsFreeInAdditionalTools_Throws()
    {
        // Arrange — a tool the model never sees must not be able to cancel a gated tool's approval prompt.
        var gated = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "gated", "deploy"));
        var free = AIFunctionFactory.Create(() => "free", "deploy");
        var client = CreateClientWithAdditionalTools(free);
        var options = new ChatOptions { Tools = [gated] };

        // Act & Assert
        Assert.Throws<InvalidOperationException>(
            () => ApprovalRequirement.GetApprovalNotRequiredToolNames(client, options));
    }

    [Fact]
    public void GetApprovalNotRequiredToolNames_FreeInToolsGatedInAdditionalTools_Throws()
    {
        // Arrange
        var free = AIFunctionFactory.Create(() => "free", "deploy");
        var gated = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "gated", "deploy"));
        var client = CreateClientWithAdditionalTools(gated);
        var options = new ChatOptions { Tools = [free] };

        // Act & Assert
        Assert.Throws<InvalidOperationException>(
            () => ApprovalRequirement.GetApprovalNotRequiredToolNames(client, options));
    }

    [Fact]
    public void GetApprovalNotRequiredToolNames_ApprovalFreeAdditionalTool_IsIncluded()
    {
        // Arrange — AdditionalTools are invocable by FunctionInvokingChatClient, so an uncontested
        // approval-free one is still auto-approvable.
        var free = AIFunctionFactory.Create(() => "free", "lookup");
        var client = CreateClientWithAdditionalTools(free);

        // Act
        var names = ApprovalRequirement.GetApprovalNotRequiredToolNames(client, options: null);

        // Assert
        Assert.Equal(["lookup"], names);
    }

    [Fact]
    public void GetApprovalNotRequiredToolNames_NoTools_ReturnsEmpty()
    {
        // Act
        var names = ApprovalRequirement.GetApprovalNotRequiredToolNames(CreateClient(), options: null);

        // Assert
        Assert.Empty(names);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public void GetApprovalNotRequiredToolNames_DeclarationAndImplementation_UsesImplementation(bool requiresApproval, bool declarationFirst)
    {
        // Arrange
        AIFunction function = AIFunctionFactory.Create(() => "result", "lookup");
        var declaration = function.AsDeclarationOnly();
        if (requiresApproval)
        {
            function = new ApprovalRequiredAIFunction(function);
        }

        var options = new ChatOptions
        {
            Tools = declarationFirst ? [declaration, function] : [function, declaration]
        };

        // Act
        var names = ApprovalRequirement.GetApprovalNotRequiredToolNames(CreateClient(), options);

        // Assert
        Assert.Equal(!requiresApproval, names.Contains("lookup"));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void GetApprovalNotRequiredToolNames_DeclarationWithAdditionalImplementation_UsesImplementation(bool requiresApproval)
    {
        // Arrange
        AIFunction function = AIFunctionFactory.Create(() => "result", "lookup");
        var options = new ChatOptions { Tools = [function.AsDeclarationOnly()] };
        if (requiresApproval)
        {
            function = new ApprovalRequiredAIFunction(function);
        }

        var client = CreateClientWithAdditionalTools(function);

        // Act
        var names = ApprovalRequirement.GetApprovalNotRequiredToolNames(client, options);

        // Assert
        Assert.Equal(!requiresApproval, names.Contains("lookup"));
    }

    [Fact]
    public void GetApprovalNotRequiredToolNames_DeclarationOnly_IsExcluded()
    {
        // Arrange
        var options = new ChatOptions
        {
            Tools = [AIFunctionFactory.Create(() => "result", "lookup").AsDeclarationOnly()]
        };

        // Act
        var names = ApprovalRequirement.GetApprovalNotRequiredToolNames(CreateClient(), options);

        // Assert
        Assert.Empty(names);
    }

    [Fact]
    public void IsApprovalNotRequired_UnknownTool_RequiresApproval()
    {
        // Arrange
        var names = new HashSet<string>(["normalTool"]);
        var call = new FunctionCallContent("call1", "unknownTool");

        // Act
        var result = ApprovalRequirement.IsApprovalNotRequired(call, names);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public void IsApprovalNotRequired_KnownApprovalFreeTool_DoesNotRequireApproval()
    {
        // Arrange
        var names = new HashSet<string>(["normalTool"]);
        var call = new FunctionCallContent("call1", "normalTool");

        // Act
        var result = ApprovalRequirement.IsApprovalNotRequired(call, names);

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void IsApprovalNotRequired_NonFunctionCallContent_RequiresApproval()
    {
        // Arrange
        var names = new HashSet<string>(["normalTool"]);

        // Act
        var result = ApprovalRequirement.IsApprovalNotRequired(new TextContent("normalTool"), names);

        // Assert
        Assert.False(result);
    }

    #region Helpers

    private static IChatClient CreateClient() => new Mock<IChatClient>().Object;

    private static FunctionInvokingChatClient CreateClientWithAdditionalTools(params AITool[] additionalTools)
        => new(CreateClient())
        {
            AdditionalTools = [.. additionalTools]
        };

    #endregion
}
