// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask.Workflows;

namespace Microsoft.Agents.AI.DurableTask.UnitTests.Workflows;

public sealed class WorkflowNamingHelperTests
{
    [Fact]
    public void ToOrchestrationFunctionName_ValidWorkflowName_ReturnsPrefixedName()
    {
        string result = WorkflowNamingHelper.ToOrchestrationFunctionName("MyWorkflow");

        Assert.Equal("dafx-MyWorkflow", result);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    public void ToOrchestrationFunctionName_NullOrEmpty_ThrowsArgumentException(string? workflowName)
    {
        Assert.ThrowsAny<ArgumentException>(() => WorkflowNamingHelper.ToOrchestrationFunctionName(workflowName!));
    }

    [Fact]
    public void ToWorkflowName_ValidOrchestrationFunctionName_ReturnsWorkflowName()
    {
        string result = WorkflowNamingHelper.ToWorkflowName("dafx-MyWorkflow");

        Assert.Equal("MyWorkflow", result);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    public void ToWorkflowName_NullOrEmpty_ThrowsArgumentException(string? orchestrationFunctionName)
    {
        Assert.ThrowsAny<ArgumentException>(() => WorkflowNamingHelper.ToWorkflowName(orchestrationFunctionName!));
    }

    [Theory]
    [InlineData("MyWorkflow")]
    [InlineData("invalid-prefix-MyWorkflow")]
    [InlineData("dafx")]
    [InlineData("dafx-")]
    public void ToWorkflowName_InvalidOrMissingPrefix_ThrowsArgumentException(string orchestrationFunctionName)
    {
        Assert.Throws<ArgumentException>(() => WorkflowNamingHelper.ToWorkflowName(orchestrationFunctionName));
    }

    [Fact]
    public void GetExecutorName_SimpleExecutorId_ReturnsSameName()
    {
        string result = WorkflowNamingHelper.GetExecutorName("OrderParser");

        Assert.Equal("OrderParser", result);
    }

    [Fact]
    public void GetExecutorName_ExecutorIdWithGuidSuffix_ReturnsNameWithoutSuffix()
    {
        string result = WorkflowNamingHelper.GetExecutorName("Physicist_8884e71021334ce49517fa2b17b1695b");

        Assert.Equal("Physicist", result);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    public void GetExecutorName_NullOrEmpty_ThrowsArgumentException(string? executorId)
    {
        Assert.ThrowsAny<ArgumentException>(() => WorkflowNamingHelper.GetExecutorName(executorId!));
    }
}
