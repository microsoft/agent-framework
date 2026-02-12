// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.ObjectModel;
using Moq;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="RequestExternalInputExecutor"/>.
/// </summary>
public sealed class RequestExternalInputExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public void RequestExternalInputNamingConvention()
    {
        // Arrange
        string testId = this.CreateActionId().Value;

        // Act
        string inputStep = RequestExternalInputExecutor.Steps.Input(testId);
        string captureStep = RequestExternalInputExecutor.Steps.Capture(testId);

        // Assert
        Assert.Equal($"{testId}_{nameof(RequestExternalInputExecutor.Steps.Input)}", inputStep);
        Assert.Equal($"{testId}_{nameof(RequestExternalInputExecutor.Steps.Capture)}", captureStep);
    }

    [Fact]
    public async Task RequestExternalInputWithoutVariableAsync()
    {
        // Arrange & Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(RequestExternalInputWithoutVariableAsync),
            variablePath: null);
    }

    [Fact]
    public async Task RequestExternalInputWithVariableAsync()
    {
        // Arrange & Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(RequestExternalInputWithVariableAsync),
            variablePath: "InputVariable");
    }

    [Fact]
    public async Task ExecuteIsNotDiscreteActionAsync()
    {
        // Arrange
        RequestExternalInput model = this.CreateModel(
            nameof(ExecuteIsNotDiscreteActionAsync),
            null);
        Mock<WorkflowAgentProvider> mockProvider = new(MockBehavior.Strict);
        RequestExternalInputExecutor action = new(model, mockProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);

        // Verify IsDiscreteAction is false
        Assert.Equal(
            false,
            action.GetType().BaseType?
                .GetProperty("IsDiscreteAction", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)?
                .GetValue(action));

        // Verify EmitResultEvent is false
        Assert.Equal(
            false,
            action.GetType().BaseType?
                .GetProperty("EmitResultEvent", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)?
                .GetValue(action));
    }

    private async Task ExecuteTestAsync(
        string displayName,
        string? variablePath)
    {
        // Arrange
        RequestExternalInput model = this.CreateModel(displayName, variablePath);
        Mock<WorkflowAgentProvider> mockProvider = new(MockBehavior.Strict);
        RequestExternalInputExecutor action = new(model, mockProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);
    }

    private RequestExternalInput CreateModel(string displayName, string? variablePath)
    {
        RequestExternalInput.Builder actionBuilder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
        };

        if (variablePath != null)
        {
            actionBuilder.Variable = PropertyPath.Create(FormatVariablePath(variablePath));
        }

        return AssignParent<RequestExternalInput>(actionBuilder);
    }
}
