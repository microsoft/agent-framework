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

    [Theory]
    [InlineData(true, false)]
    [InlineData("anything", false)]
    [InlineData(null, true)]
    public void QuestionIsComplete(object? result, bool expectIsComplete)
    {
        // Arrange - "Complete" result corresponds to null value
        ActionExecutorResult executorResult = new(nameof(QuestionIsComplete), result);

        // Act
        bool isComplete = QuestionExecutor.IsComplete(executorResult);

        // Assert
        Assert.Equal(expectIsComplete, isComplete);
    }

    [Fact]
    public async Task QuestionExecuteWithResultUndefinedAsync()
    {
        // Arrange
        Question model = this.CreateModel(
            displayName: nameof(QuestionExecuteWithResultUndefinedAsync),
            "TestVariable");

        // Act & Assert
        await this.ExecuteTestAsync(model, expectPrompt: true);
    }

    [Fact]
    public async Task QuestionExecuteWithAlwaysPromptAsync()
    {
        // Arrange
        this.State.Set("TestVariable", FormulaValue.New("existing-value"));
        Question model = this.CreateModel(
            displayName: nameof(QuestionExecuteWithAlwaysPromptAsync),
            "TestVariable",
            alwaysPrompt: true);

        // Act & Assert
        await this.ExecuteTestAsync(model, expectPrompt: true);
    }

    [Theory]
    [InlineData(SkipQuestionMode.AlwaysSkipIfVariableHasValue)]
    [InlineData(SkipQuestionMode.SkipOnFirstExecutionIfVariableHasValue)]
    [InlineData(SkipQuestionMode.AlwaysAsk)]
    public async Task QuestionExecuteWithSkipModeAsyncWithResultUndefinedAsync(SkipQuestionMode skipMode)
    {
        // Arrange
        Question model = this.CreateModel(
            displayName: nameof(QuestionExecuteWithSkipModeAsyncWithResultUndefinedAsync),
            variableName: "TestVariable",
            skipMode: skipMode);

        // Act & Assert
        await this.ExecuteTestAsync(model, expectPrompt: true);
    }

    [Theory]
    [InlineData(SkipQuestionMode.AlwaysSkipIfVariableHasValue, false)]
    [InlineData(SkipQuestionMode.SkipOnFirstExecutionIfVariableHasValue, false)]
    [InlineData(SkipQuestionMode.AlwaysAsk, true)]
    public async Task QuestionExecuteWithSkipModeAsyncWithResultDefinedAsync(SkipQuestionMode skipMode, bool expectPrompt)
    {
        // Arrange
        this.State.Set("TestVariable", FormulaValue.New("existing-value"));
        Question model = this.CreateModel(
            displayName: nameof(QuestionExecuteWithSkipModeAsyncWithResultDefinedAsync),
            variableName: "TestVariable",
            skipMode: skipMode);

        // Act & Assert
        await this.ExecuteTestAsync(model, expectPrompt);
    }

    [Fact]
    public async Task QuestionPrepareResponseAsync()
    {
        // Arrange
        Question model = this.CreateModel(
            displayName: nameof(QuestionPrepareResponseAsync),
            variableName: "TestVariable",
            promptText: "Provide input:");

        // Act & Assert
        await this.PrepareResponseTestAsync(model, expectedPrompt: "Provide input:");
    }

    [Fact]
    public async Task QuestionCaptureResponseWithValidEntityAsync()
    {
        // Arrange
        Question model = this.CreateModel(
            displayName: nameof(QuestionCaptureResponseWithValidEntityAsync),
            variableName: "TestVariable",
            alwaysPrompt: true,
            skipMode: SkipQuestionMode.AlwaysAsk,
            entity: new NumberPrebuiltEntity());

        // Act & Assert
        await this.CaptureResponseTestAsync(
            model,
            variableName: "TestVariable",
            responseText: "42",
            expectAutoSend: true);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("Invalid input, please try again.")]
    public async Task QuestionCaptureResponseWithInvalidEntityAsync(string? invalidResponse)
    {
        // Arrange
        Question model = this.CreateModel(
            displayName: nameof(QuestionCaptureResponseWithInvalidEntityAsync),
            variableName: "TestVariable",
            invalidResponseText: invalidResponse,
            entity: new NumberPrebuiltEntity());

        // Act & Assert
        await this.CaptureResponseTestAsync(
            model,
            variableName: "TestVariable",
            responseText: "not-a-number",
            expectResponse: false);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("Invalid input, please try again.")]
    public async Task QuestionCaptureResponseWithUnrecognizedResponseAsync(string? unrecognizedResponse)
    {
        // Arrange
        Question model = this.CreateModel(
            displayName: nameof(QuestionCaptureResponseWithUnrecognizedResponseAsync),
            variableName: "TestVariable",
            unrecognizedResponseText: unrecognizedResponse);

        // Act & Assert
        await this.CaptureResponseTestAsync(
            model,
            variableName: "TestVariable",
            responseText: null,
            expectResponse: false);
    }

    [Fact]
    public async Task QuestionCaptureResponseWithUnsupportedPromptAsync()
    {
        // Arrange
        Question.Builder actionBuilder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(nameof(QuestionCaptureResponseWithUnsupportedPromptAsync)),
            Variable = PropertyPath.Create(FormatVariablePath("TestVariable")),
            Prompt = new UnknownActivityTemplateBase.Builder(),
            UnrecognizedPrompt = new UnknownActivityTemplateBase.Builder(),
            Entity = new StringPrebuiltEntity(),
        };

        Question model = actionBuilder.Build();

        // Act & Assert
        await this.CaptureResponseTestAsync(
            model,
            variableName: "TestVariable",
            responseText: null,
            expectResponse: false);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task QuestionCaptureResponseExceedingRepeatCountAsync(bool hasDefault)
    {
        // Arrange
        Question model = this.CreateModel(
            displayName: nameof(QuestionCaptureResponseExceedingRepeatCountAsync),
            variableName: "TestVariable",
            repeatCount: 0,
            defaultValue: hasDefault ? new NumberDataValue(0) : null,
            entity: new NumberPrebuiltEntity());

        // Act & Assert
        await this.CaptureResponseTestAsync(
            model,
            variableName: "TestVariable",
            responseText: "not-a-number",
            expectResponse: false);
    }

    [Fact]
    public async Task QuestionCaptureResponseWithAutoSendFalseAsync()
    {
        // Arrange
        Question model = this.CreateModel(
            displayName: nameof(QuestionCaptureResponseWithAutoSendFalseAsync),
            variableName: "TestVariable",
            autoSend: new BooleanDataValue(false));

        // Act & Assert
        await this.CaptureResponseTestAsync(
            model,
            variableName: "TestVariable",
            responseText: "test response");
    }

    [Fact]
    public async Task QuestionCaptureResponseWithAutoSendTrueAsync()
    {
        // Arrange
        Question model = this.CreateModel(
            displayName: nameof(QuestionCaptureResponseWithAutoSendTrueAsync),
            variableName: "TestVariable",
            autoSend: new BooleanDataValue(true));

        // Act & Assert
        await this.CaptureResponseTestAsync(
            model,
            variableName: "TestVariable",
            responseText: "test response",
            expectAutoSend: true);
    }

    [Fact]
    public async Task QuestionCaptureResponseWithAutoSendInvalidAsync()
    {
        // Arrange
        Question model = this.CreateModel(
            displayName: nameof(QuestionCaptureResponseWithAutoSendInvalidAsync),
            variableName: "TestVariable",
            autoSend: new NumberDataValue(33));

        // Act & Assert
        await this.CaptureResponseTestAsync(
            model,
            variableName: "TestVariable",
            responseText: "test response");
    }

    [Fact]
    public async Task QuestionCompleteAsync()
    {
        // Arrange
        Question model =
            this.CreateModel(
                displayName: nameof(QuestionCompleteAsync),
                variableName: "TestVariable");

        // Act & Assert
        await this.CompleteTestAsync(model);
    }

    private async Task ExecuteTestAsync(Question model, bool expectPrompt)
    {
        // Arrange
        bool? sentMessage = null;
        Mock<ResponseAgentProvider> mockProvider = new(MockBehavior.Loose);
        QuestionExecutor action = new(model, mockProvider.Object, this.State);

        // Act
        WorkflowEvent[] events =
            await this.ExecuteAsync(
                action,
                QuestionExecutor.Steps.Capture(action.Id),
                CaptureResultAsync);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);
        Assert.NotNull(sentMessage);
        Assert.Equal(expectPrompt, sentMessage);

        ValueTask CaptureResultAsync(IWorkflowContext context, ActionExecutorResult message, CancellationToken cancellationToken)
        {
            Assert.Null(sentMessage); // Should only be called once
            sentMessage = message.Result is not null;
            return default;
        }
    }

    private async Task PrepareResponseTestAsync(
        Question model,
        string expectedPrompt)
    {
        // Arrange
        Mock<ResponseAgentProvider> mockProvider = new(MockBehavior.Loose);
        QuestionExecutor action = new(model, mockProvider.Object, this.State);
        string? capturedPrompt = null;

        // Act
        await this.ExecuteAsync(
            [
                action,
                new DelegateActionExecutor(
                    QuestionExecutor.Steps.Prepare(action.Id),
                    this.State,
                    action.PrepareResponseAsync),
                new DelegateActionExecutor<ExternalInputRequest>(
                    QuestionExecutor.Steps.Capture(action.Id),
                    this.State,
                    CaptureExternalRequestAsync)
            ],
            isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        Assert.NotNull(capturedPrompt);
        Assert.Equal(expectedPrompt, capturedPrompt);

        ValueTask CaptureExternalRequestAsync(IWorkflowContext context, ExternalInputRequest request, CancellationToken cancellationToken)
        {
            Assert.Null(capturedPrompt);
            capturedPrompt = request.AgentResponse.Text;
            return default;
        }
    }

    private async Task CaptureResponseTestAsync(
        Question model,
        string variableName,
        string? responseText,
        bool expectResponse = true,
        bool expectAutoSend = false)
    {
        // Arrange
        this.State.Set(SystemScope.Names.ConversationId, FormulaValue.New("ExternalConversationId"), VariableScopeNames.System);

        Mock<ResponseAgentProvider> mockProvider = new(MockBehavior.Loose);
        mockProvider
            .Setup(p => p.CreateMessageAsync(
                It.IsAny<string>(),
                It.IsAny<ChatMessage>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync((string cid, ChatMessage msg, CancellationToken ct) => msg);

        QuestionExecutor action = new(model, mockProvider.Object, this.State);
        ExternalInputResponse response = responseText is not null
            ? new ExternalInputResponse(new ChatMessage(ChatRole.User, responseText))
            : new ExternalInputResponse([]);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(
            action,
            QuestionExecutor.Steps.Capture(action.Id),
            (context, message, cancellationToken) =>
                action.CaptureResponseAsync(context, response, cancellationToken));

        // Assert
        VerifyModel(model, action);

        if (expectResponse)
        {
            // Variable should be set with the extracted value
            FormulaValue actualValue = this.State.Get(variableName);
            Assert.Equal(responseText, actualValue.Format());
        }
        else
        {
            // Should have prompted again or sent unrecognized/invalid message
            Assert.Contains(events, e => e is MessageActivityEvent);
        }

        if (expectAutoSend)
        {
            this.VerifyState(SystemScope.Names.LastMessageText, VariableScopeNames.System, FormulaValue.New(responseText ?? string.Empty));
        }
        else
        {
            this.VerifyUndefined(SystemScope.Names.LastMessageText, VariableScopeNames.System);
        }
    }

    private async Task CompleteTestAsync(Question model)
    {
        // Arrange
        Mock<ResponseAgentProvider> mockProvider = new(MockBehavior.Loose);
        QuestionExecutor action = new(model, mockProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(
            QuestionExecutor.Steps.Input(action.Id),
            action.CompleteAsync);

        // Assert
        VerifyModel(model, action);
        VerifyCompletionEvent(events);
    }

    private Question CreateModel(
        string displayName,
        string variableName,
        string promptText = "Please provide a value",
        string? invalidResponseText = null,
        string? unrecognizedResponseText = null,
        string? defaultValueResponseText = null,
        DataValue? defaultValue = null,
        bool? alwaysPrompt = null,
        SkipQuestionMode? skipMode = null,
        int? repeatCount = null,
        EntityReference? entity = null,
        DataValue? autoSend = null)
    {
        BoolExpression.Builder? alwaysPromptExpression = null;
        if (alwaysPrompt is not null)
        {
            alwaysPromptExpression = BoolExpression.Literal(alwaysPrompt.Value).ToBuilder();
        }

        IntExpression.Builder? repeatCountExpression = null;
        if (repeatCount is not null)
        {
            repeatCountExpression = IntExpression.Literal(repeatCount.Value).ToBuilder();
        }

        ValueExpression.Builder? defaultValueExpression = null;
        if (defaultValue is not null)
        {
            defaultValueExpression = ValueExpression.Literal(defaultValue).ToBuilder();
        }

        EnumExpression<SkipQuestionModeWrapper>.Builder? skipModeExpression = null;
        if (skipMode is not null)
        {
            skipModeExpression = EnumExpression<SkipQuestionModeWrapper>.Literal(skipMode).ToBuilder();
        }

        Question.Builder actionBuilder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
            AlwaysPrompt = alwaysPromptExpression,
            SkipQuestionMode = skipModeExpression,
            Variable = PropertyPath.Create(FormatVariablePath(variableName)),
            Prompt = CreateMessageActivity(promptText),
            InvalidPrompt = CreateOptionalMessageActivity(invalidResponseText),
            UnrecognizedPrompt = CreateOptionalMessageActivity(unrecognizedResponseText),
            DefaultValue = defaultValueExpression,
            DefaultValueResponse = CreateOptionalMessageActivity(defaultValueResponseText),
            RepeatCount = repeatCountExpression,
            Entity = entity ?? new StringPrebuiltEntity(),
        };

        if (autoSend is not null)
        {
            RecordDataValue.Builder extensionDataBuilder = new();
            extensionDataBuilder.Properties.Add("autoSend", autoSend);
            actionBuilder.ExtensionData = extensionDataBuilder.Build();
        }

        return AssignParent<Question>(actionBuilder);
    }

    private static MessageActivityTemplate.Builder? CreateOptionalMessageActivity(string? text) =>
        text is null ? null : CreateMessageActivity(text);

    private static MessageActivityTemplate.Builder CreateMessageActivity(string text) =>
        new()
        {
            Text = { TemplateLine.Parse(text) },
        };
}
