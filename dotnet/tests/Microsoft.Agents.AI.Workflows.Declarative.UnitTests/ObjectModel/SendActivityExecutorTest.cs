// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

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

        // The executor must also emit an AgentResponseEvent carrying the activity text
        // so workflow consumers (hosting runtime, UIs) can surface it as an agent turn.
        AgentResponseEvent agentEvent = Assert.Single(events.OfType<AgentResponseEvent>());
        Assert.Equal(action.Id, agentEvent.ExecutorId);
        ChatMessage message = Assert.Single(agentEvent.Response.Messages);
        Assert.Equal(ChatRole.Assistant, message.Role);
        Assert.Equal("Test activity message", message.Text);
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
