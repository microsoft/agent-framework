// Copyright (c) Microsoft. All rights reserved.

using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests;

public sealed class DeclarativeValidationTests
{
    [Theory]
    [InlineData("SendActivity", "activity", "")]
    [InlineData("Question", "prompt", "property: Local.answer\n      entity: StringPrebuiltEntity")]
    public void Build_UnknownMessagePropertyReportsAction(string kind, string property, string extra)
    {
        // Arrange
        using var reader = new StringReader($"""
            kind: Workflow
            trigger:
              kind: OnConversationStart
              id: start
              actions:
                - kind: {kind}
                  id: invalid_message
                  {property}:
                    kind: Message
                    test: [Hello]
                  {extra}
            """);
        var options = new DeclarativeWorkflowOptions(Mock.Of<ResponseAgentProvider>());

        // Act
        var exception = Assert.Throws<DeclarativeModelException>(() => DeclarativeWorkflowBuilder.Build<string>(reader, options));

        // Assert
        Assert.Contains("test", exception.Message);
        Assert.Contains("invalid_message", exception.Message);
        Assert.Contains(kind, exception.Message);
    }

    [Fact]
    public void Build_PreservesSupportedTemplatePropertiesAndActionExtensions()
    {
        // Arrange
        using var reader = new StringReader("""
            kind: Workflow
            trigger:
              kind: OnConversationStart
              id: start
              actions:
                - kind: Question
                  id: question
                  autoSend: false
                  property: Local.answer
                  entity: StringPrebuiltEntity
                  prompt:
                    kind: Message
                    text:
                      - Hello
                    summary: Summary
            """);

        // Act
        var workflow = DeclarativeWorkflowBuilder.Build<string>(reader, new(Mock.Of<ResponseAgentProvider>()));

        // Assert
        Assert.NotNull(workflow);
    }

    [Theory]
    [InlineData("Text", false)]
    [InlineData("Test", true)]
    public async Task Run_TemplateExpressionReportsUnderlyingErrorAsync(string member, bool fails)
    {
        // Arrange
        using var reader = new StringReader($$"""
            kind: Workflow
            trigger:
              kind: OnConversationStart
              id: start
              actions:
                - kind: SetVariable
                  id: set
                  variable: Topic.ToolResponse
                  value: =System.LastMessage
                - kind: SendActivity
                  id: output
                  activity: "{Local.ToolResponse.{{member}}}"
            """);
        var provider = new Mock<ResponseAgentProvider>();
        provider.Setup(p => p.CreateConversationAsync(It.IsAny<CancellationToken>())).ReturnsAsync("local");
        provider.Setup(p => p.CreateMessageAsync(It.IsAny<string>(), It.IsAny<ChatMessage>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((string _, ChatMessage message, CancellationToken _) => message);
        var workflow = DeclarativeWorkflowBuilder.Build<string>(reader, new(provider.Object));

        // Act
        await using var run = await InProcessExecution.RunStreamingAsync(workflow, "Hello");
        var events = await run.WatchStreamAsync().ToArrayAsync();

        // Assert
        if (fails)
        {
            var failure = Assert.Single(events.OfType<ExecutorFailedEvent>());
            var exception = Assert.IsType<DeclarativeActionException>(failure.Data);
            Assert.Contains("output", exception.Message);
            Assert.Contains("SendActivity", exception.Message);
            Assert.Contains("'Test'", exception.Message);
            Assert.NotNull(exception.InnerException);
        }
        else
        {
            Assert.Empty(events.OfType<ExecutorFailedEvent>());
            Assert.Equal("Hello", Assert.Single(events.OfType<AgentResponseEvent>()).Response.Text);
        }
    }
}
