// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting.AzureFunctions.UnitTests;

public sealed class BuiltInFunctionsWorkflowRoutingTests
{
    [Theory]
    [InlineData("http-MyWorkflow-status", "-status", "MyWorkflow")]
    [InlineData("http-OrderProcessor-status", "-status", "OrderProcessor")]
    [InlineData("http-MyWorkflow-respond", "-respond", "MyWorkflow")]
    [InlineData("http-Multi-Dash-Name-status", "-status", "Multi-Dash-Name")]
    public void GetWorkflowName_ReturnsCorrectName(string functionName, string suffix, string expectedWorkflowName)
    {
        // Act
        string result = BuiltInFunctions.GetWorkflowName(functionName, suffix);

        // Assert
        Assert.Equal(expectedWorkflowName, result);
    }

    [Theory]
    [InlineData("invalid-name", "-status")]
    [InlineData("http-MyWorkflow-respond", "-status")] // wrong suffix
    [InlineData("mcptool-MyWorkflow-status", "-status")] // wrong prefix
    public void GetWorkflowName_ThrowsForInvalidPattern(string functionName, string suffix)
    {
        // Act & Assert
        Assert.Throws<InvalidOperationException>(() =>
            BuiltInFunctions.GetWorkflowName(functionName, suffix));
    }

    [Theory]
    [InlineData("dafx-MyWorkflow", "http-MyWorkflow-status", "-status", true)]
    [InlineData("dafx-MyWorkflow", "http-MyWorkflow-respond", "-respond", true)]
    [InlineData("dafx-myworkflow", "http-MyWorkflow-status", "-status", true)] // case-insensitive
    [InlineData("dafx-MYWORKFLOW", "http-MyWorkflow-respond", "-respond", true)] // case-insensitive
    [InlineData("dafx-OtherWorkflow", "http-MyWorkflow-status", "-status", false)] // cross-workflow
    [InlineData("dafx-PrivilegedWorkflow", "http-PublicWorkflow-status", "-status", false)] // attack scenario
    [InlineData("dafx-PrivilegedWorkflow", "http-PublicWorkflow-respond", "-respond", false)] // attack scenario
    public void IsOrchestrationOwnedByWorkflow_ValidatesCorrectly(
        string orchestrationName,
        string functionName,
        string suffix,
        bool expectedResult)
    {
        // Act
        bool result = BuiltInFunctions.IsOrchestrationOwnedByWorkflow(orchestrationName, functionName, suffix);

        // Assert
        Assert.Equal(expectedResult, result);
    }
}
