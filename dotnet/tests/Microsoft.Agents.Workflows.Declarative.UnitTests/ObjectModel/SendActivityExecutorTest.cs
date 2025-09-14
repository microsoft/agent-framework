// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.ObjectModel;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="SendActivityExecutor"/>.
/// </summary>
public sealed class SendActivityExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public async Task CaptureActivityAsync()
    {
        // Arrange
        SendActivity model =
            this.CreateModel(
                this.FormatDisplayName(nameof(CaptureActivityAsync)),
                "Test activity message");

        // Act
        SendActivityExecutor action = new(model, this.State);
        WorkflowEvent[] events = await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        Assert.Contains(events, e => e is MessageActivityEvent);
    }

    private SendActivity CreateModel(string displayName, string activityMessage, string? summary = null)
    {
        MessageActivityTemplate.Builder activityBuilder =
            new()
            {
                Summary = summary,
                Text = { TemplateLine.Parse(activityMessage) },
            };
        SendActivity.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = this.FormatDisplayName(displayName),
                Activity = activityBuilder.Build(),
            };

        return AssignParent<SendActivity>(actionBuilder);
    }
}
