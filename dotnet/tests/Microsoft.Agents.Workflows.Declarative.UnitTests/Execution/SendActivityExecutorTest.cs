// Copyright (c) Microsoft. All rights reserved.

using System.IO;
using System.Threading.Tasks;
using Microsoft.Bot.ObjectModel;
using Microsoft.Agents.Workflows.Declarative.Execution;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.Execution;

/// <summary>
/// Tests for <see cref="SendActivityExecutor"/>.
/// </summary>
public sealed class SendActivityExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public async Task CaptureActivity()
    {
        // Arrange
        SendActivity model =
            this.CreateModel(
                this.FormatDisplayName(nameof(CaptureActivity)),
                "Test activity message");
        using StringWriter activityWriter = new();

        // Act
        SendActivityExecutor action = new(model, activityWriter);
        await this.Execute(action);
        activityWriter.Flush();

        // Assert
        this.VerifyModel(model, action);
        Assert.NotEmpty(activityWriter.ToString());
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

        SendActivity model = this.AssignParent<SendActivity>(actionBuilder);

        return model;
    }
}
