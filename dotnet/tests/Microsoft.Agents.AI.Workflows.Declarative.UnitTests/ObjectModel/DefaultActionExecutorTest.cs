// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="DefaultActionExecutor"/>.
/// </summary>
public sealed class DefaultActionExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public async Task ExecuteDefaultActionAsync()
    {
        // Arrange, Act & Assert
        await this.ExecuteTestAsync(
                this.FormatDisplayName(nameof(ExecuteDefaultActionAsync)));
    }

    [Fact]
    public async Task ExecuteMultipleTimesAsync()
    {
        // Arrange, Act & Assert
        await this.ExecuteTestAsync(
                this.FormatDisplayName(nameof(ExecuteMultipleTimesAsync)));

        // Execute again to ensure idempotency
        await this.ExecuteTestAsync(
                this.FormatDisplayName(nameof(ExecuteMultipleTimesAsync)));
    }

    [Fact]
    public async Task ExecuteReturnsExpectedEventsAsync()
    {
        // Arrange
        ResetVariable model = this.CreateModel(
            this.FormatDisplayName(nameof(ExecuteReturnsExpectedEventsAsync)));

        // Act
        DefaultActionExecutor action = new(model, this.State);
        WorkflowEvent[] events = await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    [Fact]
    public void ConstructorSetsPropertiesCorrectly()
    {
        // Arrange
        ResetVariable model = this.CreateModel(
            this.FormatDisplayName(nameof(ConstructorSetsPropertiesCorrectly)));

        // Act
        DefaultActionExecutor action = new(model, this.State);

        // Assert
        Assert.Equal(model.Id.Value, action.Id);
        Assert.Equal(model, action.Model);
    }

    private async Task ExecuteTestAsync(string displayName)
    {
        // Arrange
        ResetVariable model = this.CreateModel(displayName);

        // Act
        DefaultActionExecutor action = new(model, this.State);
        WorkflowEvent[] events = await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    private ResetVariable CreateModel(string displayName)
    {
        // Use a simple concrete action type since DialogAction.Builder is abstract
        ResetVariable.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = this.FormatDisplayName(displayName),
                Variable = PropertyPath.Create(FormatVariablePath("TestVariable")),
            };

        return AssignParent<ResetVariable>(actionBuilder);
    }
}
