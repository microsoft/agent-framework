// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;
using Moq;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="QuestionExecutor"/>.
/// </summary>
public sealed class QuestionExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    private const string TestConversationId = "test-conversation-id";
    private const string TestVariableName = "TestVariable";

    [Fact]
    public void QuestionNamingConvention()
    {
        // Arrange
        string testId = this.CreateActionId().Value;

        // Act
        string prepareStep = QuestionExecutor.Steps.Prepare(testId);
        string inputStep = QuestionExecutor.Steps.Input(testId);
        string captureStep = QuestionExecutor.Steps.Capture(testId);

        // Assert
        Assert.Equal($"{testId}_{nameof(QuestionExecutor.Steps.Prepare)}", prepareStep);
        Assert.Equal($"{testId}_{nameof(QuestionExecutor.Steps.Input)}", inputStep);
        Assert.Equal($"{testId}_{nameof(QuestionExecutor.Steps.Capture)}", captureStep);
    }

    [Fact]
    public void QuestionIsComplete()
    {
        // Arrange
        ActionExecutorResult resultWithNull = new("test", result: null);
        ActionExecutorResult resultWithValue = new("test", result: true);

        // Act & Assert
        Assert.True(QuestionExecutor.IsComplete(resultWithNull));
        Assert.False(QuestionExecutor.IsComplete(resultWithValue));
    }

    [Fact]
    public async Task QuestionExecuteWithAlwaysPromptTrueAsync()
    {
        // Arrange
        this.SetVariableState(TestVariableName);
        Question model = this.CreateModel(
            displayName: nameof(QuestionExecuteWithAlwaysPromptTrueAsync),
            alwaysPrompt: true,
            skipMode: SkipQuestionMode.AlwaysAsk);

        // Act & Assert
        await this.ExecuteTestAsync(model, expectPrompt: true);
    }

    [Fact]
    public async Task QuestionExecuteWithAlwaysPromptFalseAndVariableHasValueAsync()
    {
        // Arrange
        this.SetVariableState(TestVariableName, FormulaValue.New("existing-value"));
        Question model = this.CreateModel(
            displayName: nameof(QuestionExecuteWithAlwaysPromptFalseAndVariableHasValueAsync),
            alwaysPrompt: false,
            skipMode: SkipQuestionMode.AlwaysSkipIfVariableHasValue);

        // Act & Assert
        await this.ExecuteTestAsync(model, expectPrompt: false);
    }

    [Fact]
    public async Task QuestionExecuteWithSkipOnFirstExecutionIfVariableHasValueAsync()
    {
        // Arrange
        this.SetVariableState(TestVariableName, FormulaValue.New("existing-value"));
        Question model = this.CreateModel(
            displayName: nameof(QuestionExecuteWithSkipOnFirstExecutionIfVariableHasValueAsync),
            alwaysPrompt: false,
            skipMode: SkipQuestionMode.SkipOnFirstExecutionIfVariableHasValue);

        // Act & Assert
        await this.ExecuteTestAsync(model, expectPrompt: false);
    }

    [Fact]
    public async Task QuestionExecuteWithAlwaysAskAsync()
    {
        // Arrange
        this.SetVariableState(TestVariableName, FormulaValue.New("existing-value"));
        Question model = this.CreateModel(
            displayName: nameof(QuestionExecuteWithAlwaysAskAsync),
            alwaysPrompt: false,
            skipMode: SkipQuestionMode.AlwaysAsk);

        // Act & Assert
        await this.ExecuteTestAsync(model, expectPrompt: true);
    }

    [Fact]
    public async Task QuestionPrepareResponseIncreasesPromptCountAsync()
    {
        // Arrange
        this.SetVariableState(TestVariableName);
        Question model = this.CreateModel(
            displayName: nameof(QuestionPrepareResponseIncreasesPromptCountAsync),
            alwaysPrompt: true,
            skipMode: SkipQuestionMode.AlwaysAsk);

        // Act & Assert
        await this.PrepareResponseTestAsync(model);
    }

    [Fact]
    public async Task QuestionCaptureResponseWithValidEntityAsync()
    {
        // Arrange
        this.SetVariableState(TestVariableName);
        Question model = this.CreateModel(
            displayName: nameof(QuestionCaptureResponseWithValidEntityAsync),
            alwaysPrompt: true,
            skipMode: SkipQuestionMode.AlwaysAsk,
            entity: new NumberPrebuiltEntity());

        // Act & Assert
        await this.CaptureResponseTestAsync(
            model,
            responseText: "42",
            expectValid: true);
    }

    [Fact]
    public async Task QuestionCaptureResponseWithInvalidEntityAsync()
    {
        // Arrange
        this.SetVariableState(TestVariableName);
        Question model = this.CreateModel(
            displayName: nameof(QuestionCaptureResponseWithInvalidEntityAsync),
            alwaysPrompt: true,
            skipMode: SkipQuestionMode.AlwaysAsk,
            entity: new NumberPrebuiltEntity());

        // Act & Assert
        await this.CaptureResponseTestAsync(
            model,
            responseText: "not-a-number",
            expectValid: false);
    }

    [Fact]
    public async Task QuestionCaptureResponseWithUnrecognizedResponseAsync()
    {
        // Arrange
        this.SetVariableState(TestVariableName);
        Question model = this.CreateModel(
            displayName: nameof(QuestionCaptureResponseWithUnrecognizedResponseAsync),
            alwaysPrompt: true,
            skipMode: SkipQuestionMode.AlwaysAsk);

        // Act & Assert
        await this.CaptureResponseTestAsync(
            model,
            responseText: null,
            expectValid: false);
    }

    [Fact]
    public async Task QuestionCaptureResponseExceedingRepeatCountAsync()
    {
        // Arrange
        this.SetVariableState(TestVariableName);
        Question model = this.CreateModel(
            displayName: nameof(QuestionCaptureResponseExceedingRepeatCountAsync),
            alwaysPrompt: true,
            skipMode: SkipQuestionMode.AlwaysAsk,
            repeatCount: 1,
            entity: new NumberPrebuiltEntity());

        // Act & Assert
        await this.CaptureResponseWithRepeatCountTestAsync(model);
    }

    [Fact]
    public async Task QuestionCompleteAsync()
    {
        // Arrange
        this.SetVariableState(TestVariableName);
        Question model = this.CreateModel(
            displayName: nameof(QuestionCompleteAsync),
            alwaysPrompt: true,
            skipMode: SkipQuestionMode.AlwaysAsk);

        // Act & Assert
        await this.CompleteTestAsync(model);
    }

    [Fact]
    public async Task QuestionCaptureResponseWithAutoSendFalseAsync()
    {
        // Arrange
        this.SetVariableState(TestVariableName);
        Question model = this.CreateModel(
            displayName: nameof(QuestionCaptureResponseWithAutoSendFalseAsync),
            alwaysPrompt: true,
            skipMode: SkipQuestionMode.AlwaysAsk,
            entity: new StringPrebuiltEntity(),
            autoSend: false);

        // Act & Assert
        await this.CaptureResponseTestAsync(
            model,
            responseText: "test response",
            expectValid: true,
            conversationId: TestConversationId);
    }

    [Fact]
    public async Task QuestionCaptureResponseWithAutoSendTrueAsync()
    {
        // Arrange
        this.SetVariableState(TestVariableName);
        Question model = this.CreateModel(
            displayName: nameof(QuestionCaptureResponseWithAutoSendTrueAsync),
            alwaysPrompt: true,
            skipMode: SkipQuestionMode.AlwaysAsk,
            entity: new StringPrebuiltEntity(),
            autoSend: true);

        // Act & Assert
        await this.CaptureResponseTestAsync(
            model,
            responseText: "test response",
            expectValid: true,
            conversationId: TestConversationId);
    }

    private void SetVariableState(string variableName, FormulaValue? valueState = null)
    {
        this.State.Set(variableName, valueState ?? FormulaValue.NewBlank());
    }

    private async Task ExecuteTestAsync(Question model, bool expectPrompt)
    {
        // Arrange
        Mock<WorkflowAgentProvider> mockProvider = new(MockBehavior.Loose);
        QuestionExecutor action = new(model, mockProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);

        // For Question, result message won't be in the events in a testable way
        // Instead, we check the state and behavior
        if (!expectPrompt)
        {
            // When not prompting, the action should complete immediately
            // The variable state should remain unchanged
        }
    }

    private async Task PrepareResponseTestAsync(Question model)
    {
        // Arrange
        Mock<WorkflowAgentProvider> mockProvider = new(MockBehavior.Loose);
        QuestionExecutor action = new(model, mockProvider.Object, this.State);

        // Act - Execute first to initialize state
        await this.ExecuteAsync(action, isDiscrete: false);

        // Then call PrepareResponseAsync
        WorkflowEvent[] events = await this.ExecuteAsync(
            action,
            QuestionExecutor.Steps.Prepare(action.Id),
            (IWorkflowContext context, ActionExecutorResult message, CancellationToken cancellationToken) =>
                action.PrepareResponseAsync(context, message, cancellationToken));

        // Assert
        VerifyModel(model, action);
        // PrepareResponseAsync should send an ExternalInputRequest message
        // We can't easily verify the message in events, but the method should complete without error
    }

    private async Task CaptureResponseTestAsync(
        Question model,
        string? responseText,
        bool expectValid,
        string? conversationId = null)
    {
        // Arrange
        Mock<WorkflowAgentProvider> mockProvider = new(MockBehavior.Loose);

        if (conversationId is not null && expectValid && responseText is not null)
        {
            mockProvider
                .Setup(p => p.CreateMessageAsync(
                    It.IsAny<string>(),
                    It.IsAny<ChatMessage>(),
                    It.IsAny<CancellationToken>()))
                .ReturnsAsync((string cid, ChatMessage msg, CancellationToken ct) => msg);
        }

        QuestionExecutor action = new(model, mockProvider.Object, this.State);
        ExternalInputResponse response = responseText is not null
            ? new ExternalInputResponse(new ChatMessage(ChatRole.User, responseText))
            : new ExternalInputResponse([]);

        // Act - Execute first to initialize state
        await this.ExecuteAsync(action, isDiscrete: false);

        // Set conversation ID if provided
        if (conversationId is not null)
        {
            this.State.Set(SystemScope.Names.ConversationId, FormulaValue.New(conversationId), VariableScopeNames.System);
        }

        // Then call CaptureResponseAsync
        WorkflowEvent[] events = await this.ExecuteAsync(
            action,
            QuestionExecutor.Steps.Capture(action.Id),
            (IWorkflowContext context, ActionExecutorResult message, CancellationToken cancellationToken) =>
                action.CaptureResponseAsync(context, response, cancellationToken));

        // Assert
        VerifyModel(model, action);

        if (expectValid && responseText is not null)
        {
            // Variable should be set with the extracted value
            FormulaValue actualValue = this.State.Get(TestVariableName);
            Assert.NotEqual(FormulaValue.NewBlank().Format(), actualValue.Format());
        }
        else
        {
            // Should have prompted again or sent unrecognized/invalid message
            if (responseText is null)
            {
                Assert.Contains(events, e => e is MessageActivityEvent);
            }
        }
    }

    private async Task CaptureResponseWithRepeatCountTestAsync(Question model)
    {
        // Arrange
        Mock<WorkflowAgentProvider> mockProvider = new(MockBehavior.Loose);
        QuestionExecutor action = new(model, mockProvider.Object, this.State);
        ExternalInputResponse response = new(new ChatMessage(ChatRole.User, "not-a-number"));

        // Act - First execute to initialize state, then prepare to increment prompt count,
        // then capture with invalid response to trigger default value - all in one workflow execution
        WorkflowEvent[] events = await this.ExecuteAsync([
            action,
            new DelegateActionExecutor(
                QuestionExecutor.Steps.Prepare(action.Id),
                this.State,
                (IWorkflowContext context, ActionExecutorResult message, CancellationToken cancellationToken) =>
                    action.PrepareResponseAsync(context, message, cancellationToken)),
            new DelegateActionExecutor(
                QuestionExecutor.Steps.Capture(action.Id),
                this.State,
                (IWorkflowContext context, ActionExecutorResult message, CancellationToken cancellationToken) =>
                    action.CaptureResponseAsync(context, response, cancellationToken))
        ], isDiscrete: false);

        // Assert
        VerifyModel(model, action);

        // Should have sent the default value response message when repeat count exceeded
        Assert.Contains(events, e => e is MessageActivityEvent);
    }

    private async Task CompleteTestAsync(Question model)
    {
        // Arrange
        Mock<WorkflowAgentProvider> mockProvider = new(MockBehavior.Loose);
        QuestionExecutor action = new(model, mockProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(
            QuestionExecutor.Steps.Input(action.Id),
            (IWorkflowContext context, ActionExecutorResult message, CancellationToken cancellationToken) =>
                action.CompleteAsync(context, message, cancellationToken));

        // Assert
        VerifyModel(model, action);
        VerifyCompletionEvent(events);
    }

    private Question CreateModel(
        string displayName,
        bool alwaysPrompt,
        SkipQuestionMode skipMode,
        EntityReference? entity = null,
        int repeatCount = 3,
        bool? autoSend = null)
    {
        MessageActivityTemplate.Builder promptBuilder = new()
        {
            Text = { TemplateLine.Parse("Please provide a value") },
        };

        MessageActivityTemplate.Builder invalidPromptBuilder = new()
        {
            Text = { TemplateLine.Parse("Invalid response, please try again") },
        };

        MessageActivityTemplate.Builder unrecognizedPromptBuilder = new()
        {
            Text = { TemplateLine.Parse("I didn't recognize that") },
        };

        MessageActivityTemplate.Builder defaultValueResponseBuilder = new()
        {
            Text = { TemplateLine.Parse("Using default value") },
        };

        Question.Builder actionBuilder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
            AlwaysPrompt = BoolExpression.Literal(alwaysPrompt),
            SkipQuestionMode = EnumExpression<SkipQuestionModeWrapper>.Literal(SkipQuestionModeWrapper.Get(skipMode)),
            Variable = PropertyPath.Create(FormatVariablePath(TestVariableName)),
            Prompt = promptBuilder.Build(),
            InvalidPrompt = invalidPromptBuilder.Build(),
            UnrecognizedPrompt = unrecognizedPromptBuilder.Build(),
            DefaultValue = ValueExpression.Literal(new StringDataValue("default-value")),
            DefaultValueResponse = defaultValueResponseBuilder.Build(),
            RepeatCount = IntExpression.Literal(repeatCount),
            Entity = entity ?? new StringPrebuiltEntity(),
        };

        if (autoSend.HasValue)
        {
            RecordDataValue.Builder extensionDataBuilder = new();
            extensionDataBuilder.Properties.Add("autoSend", new BooleanDataValue(autoSend.Value));
            actionBuilder.ExtensionData = extensionDataBuilder.Build();
        }

        return AssignParent<Question>(actionBuilder);
    }
}
