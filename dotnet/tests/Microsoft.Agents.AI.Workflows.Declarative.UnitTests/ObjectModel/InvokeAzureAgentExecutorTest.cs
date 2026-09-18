// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="InvokeAzureAgentExecutor"/>.
/// </summary>
public sealed class InvokeAzureAgentExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public void InvokeAzureAgentThrowsWhenModelInvalid() =>
        // Arrange, Act & Assert
        Assert.Throws<DeclarativeModelException>(() => new InvokeAzureAgentExecutor(new InvokeAzureAgent(), new CapturingAgentProvider("text"), this.State));

    [Theory]
    [InlineData(null, true)]
    [InlineData(true, true)]
    [InlineData(false, false)]
    public async Task AutoSendDefaultsToTrueAndHonorsExplicitValueAsync(bool? autoSend, bool expectResponseEvents)
    {
        // Arrange
        this.State.InitializeSystem();
        CapturingAgentProvider provider = new("response");
        InvokeAzureAgent model = this.CreateAutoSendModel(
            nameof(AutoSendDefaultsToTrueAndHonorsExplicitValueAsync),
            autoSend);

        // Act
        WorkflowEvent[] events =
            await this.ExecuteAsync(new InvokeAzureAgentExecutor(model, provider, this.State), isDiscrete: false);

        // Assert
        Assert.Equal(expectResponseEvents ? 1 : 0, events.OfType<AgentResponseUpdateEvent>().Count());
        Assert.Equal(expectResponseEvents ? 1 : 0, events.OfType<AgentResponseEvent>().Count());
    }

    #region Input argument binding

    [Fact]
    public async Task MultipleNamedArgumentsAreAllBoundAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        CapturingAgentProvider provider = new("acknowledged");
        InvokeAzureAgent model =
            this.CreateModel(
                displayName: nameof(MultipleNamedArgumentsAreAllBoundAsync),
                agentName: "BrainCombine",
                arguments:
                [
                    ("a", ValueExpression.Literal(new StringDataValue("alpha"))),
                    ("b", ValueExpression.Literal(new StringDataValue("beta"))),
                ]);

        // Act
        await this.ExecuteAsync(new InvokeAzureAgentExecutor(model, provider, this.State), isDiscrete: false);

        // Assert
        Assert.NotNull(provider.CapturedArguments);
        Assert.Equal("alpha", provider.CapturedArguments!["a"]);
        Assert.Equal("beta", provider.CapturedArguments!["b"]);
    }

    [Fact]
    public async Task RecordValuedArgumentIsBoundAsRecordAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        this.State.Set(
            "R",
            FormulaValue.NewRecordFromFields(
                new NamedValue("a", FormulaValue.New("alpha")),
                new NamedValue("b", FormulaValue.New("beta"))));
        CapturingAgentProvider provider = new("acknowledged");
        InvokeAzureAgent model =
            this.CreateModel(
                displayName: nameof(RecordValuedArgumentIsBoundAsRecordAsync),
                agentName: "BrainTest",
                arguments:
                [
                    ("input", ValueExpression.Variable(PropertyPath.TopicVariable("R"))),
                ]);

        // Act
        await this.ExecuteAsync(new InvokeAzureAgentExecutor(model, provider, this.State), isDiscrete: false);

        // Assert
        Assert.NotNull(provider.CapturedArguments);
        IDictionary<string, object?> record = Assert.IsAssignableFrom<IDictionary<string, object?>>(provider.CapturedArguments!["input"]);
        Assert.Equal("alpha", record["a"]);
        Assert.Equal("beta", record["b"]);
    }

    [Fact]
    public async Task InlineRecordExpressionArgumentIsBoundAsRecordAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        CapturingAgentProvider provider = new("acknowledged");
        InvokeAzureAgent model =
            this.CreateModel(
                displayName: nameof(InlineRecordExpressionArgumentIsBoundAsRecordAsync),
                agentName: "BrainInlineRecord",
                arguments:
                [
                    ("input", ValueExpression.Expression("""{ a: "alpha", b: "beta" }""")),
                ]);

        // Act (reporter repro (b): a single argument whose value is an inline record literal)
        await this.ExecuteAsync(new InvokeAzureAgentExecutor(model, provider, this.State), isDiscrete: false);

        // Assert
        Assert.NotNull(provider.CapturedArguments);
        IDictionary<string, object?> record = Assert.IsAssignableFrom<IDictionary<string, object?>>(provider.CapturedArguments!["input"]);
        Assert.Equal("alpha", record["a"]);
        Assert.Equal("beta", record["b"]);
    }

    #endregion

    #region Response object parsing

    [Fact]
    public async Task JsonObjectOutputAssignsRecordAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        CapturingAgentProvider provider = new("""{ "a": "alpha", "b": "beta" }""");
        InvokeAzureAgent model =
            this.CreateModel(
                displayName: nameof(JsonObjectOutputAssignsRecordAsync),
                agentName: "BrainObject",
                responseObjectVariable: "Result");

        // Act
        await this.ExecuteAsync(new InvokeAzureAgentExecutor(model, provider, this.State), isDiscrete: false);

        // Assert
        RecordValue record = Assert.IsAssignableFrom<RecordValue>(this.State.Get("Result"));
        Assert.Equal("alpha", ((StringValue)record.GetField("a")).Value);
    }

    [Fact]
    public async Task JsonArrayOutputAssignsListAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        CapturingAgentProvider provider = new("""["alpha","beta"]""");
        InvokeAzureAgent model =
            this.CreateModel(
                displayName: nameof(JsonArrayOutputAssignsListAsync),
                agentName: "BrainArray",
                responseObjectVariable: "Result");

        // Act
        await this.ExecuteAsync(new InvokeAzureAgentExecutor(model, provider, this.State), isDiscrete: false);

        // Assert
        TableValue table = Assert.IsAssignableFrom<TableValue>(this.State.Get("Result"));
        Assert.Equal(2, table.Rows.Count());
    }

    [Fact]
    public async Task EmptyJsonArrayOutputAssignsEmptyListAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        CapturingAgentProvider provider = new("[]");
        InvokeAzureAgent model =
            this.CreateModel(
                displayName: nameof(EmptyJsonArrayOutputAssignsEmptyListAsync),
                agentName: "BrainEmptyArray",
                responseObjectVariable: "Result");

        // Act
        await this.ExecuteAsync(new InvokeAzureAgentExecutor(model, provider, this.State), isDiscrete: false);

        // Assert
        TableValue table = Assert.IsAssignableFrom<TableValue>(this.State.Get("Result"));
        Assert.Empty(table.Rows);
    }

    [Fact]
    public async Task JsonScalarOutputAssignsScalarAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        CapturingAgentProvider provider = new("42");
        InvokeAzureAgent model =
            this.CreateModel(
                displayName: nameof(JsonScalarOutputAssignsScalarAsync),
                agentName: "BrainScalar",
                responseObjectVariable: "Result");

        // Act
        await this.ExecuteAsync(new InvokeAzureAgentExecutor(model, provider, this.State), isDiscrete: false);

        // Assert
        NumberValue number = Assert.IsAssignableFrom<NumberValue>(this.State.Get("Result"));
        Assert.Equal(42d, number.Value);
    }

    [Fact]
    public async Task MixedJsonArrayOutputSkipsAssignmentAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        CapturingAgentProvider provider = new("""["alpha",1]""");
        InvokeAzureAgent model =
            this.CreateModel(
                displayName: nameof(MixedJsonArrayOutputSkipsAssignmentAsync),
                agentName: "BrainMixedArray",
                responseObjectVariable: "Result");

        // Act (must not throw despite non-convertible JSON)
        await this.ExecuteAsync(new InvokeAzureAgentExecutor(model, provider, this.State), isDiscrete: false);

        // Assert
        this.VerifyUndefined("Result");
    }

    [Fact]
    public async Task NestedJsonArrayOutputSkipsAssignmentAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        CapturingAgentProvider provider = new("[[1,2],[3,4]]");
        InvokeAzureAgent model =
            this.CreateModel(
                displayName: nameof(NestedJsonArrayOutputSkipsAssignmentAsync),
                agentName: "BrainNestedArray",
                responseObjectVariable: "Result");

        // Act (a nested array parses but is not convertible to a workflow value — must not throw)
        await this.ExecuteAsync(new InvokeAzureAgentExecutor(model, provider, this.State), isDiscrete: false);

        // Assert
        this.VerifyUndefined("Result");
    }

    [Fact]
    public async Task PlainTextOutputSkipsAssignmentAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        CapturingAgentProvider provider = new("hello world");
        InvokeAzureAgent model =
            this.CreateModel(
                displayName: nameof(PlainTextOutputSkipsAssignmentAsync),
                agentName: "BrainText",
                responseObjectVariable: "Result");

        // Act
        await this.ExecuteAsync(new InvokeAzureAgentExecutor(model, provider, this.State), isDiscrete: false);

        // Assert
        this.VerifyUndefined("Result");
    }

    [Fact]
    public async Task NonObjectJsonOutputWithoutResponseObjectDoesNotThrowAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        CapturingAgentProvider provider = new("""["alpha","beta"]""");
        InvokeAzureAgent model =
            this.CreateModel(
                displayName: nameof(NonObjectJsonOutputWithoutResponseObjectDoesNotThrowAsync),
                agentName: "BrainNoOutput");

        // Act & Assert (reporter repro shape — no output block; must not throw)
        await this.ExecuteAsync(new InvokeAzureAgentExecutor(model, provider, this.State), isDiscrete: false);
    }

    #endregion

    #region Helpers

    private InvokeAzureAgent CreateModel(
        string displayName,
        string agentName,
        IReadOnlyList<(string Key, ValueExpression Value)>? arguments = null,
        string? responseObjectVariable = null)
    {
        InvokeAzureAgent.Builder builder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = this.FormatDisplayName(displayName),
                Agent =
                    new AzureAgentUsage.Builder
                    {
                        Name = new StringExpression.Builder(StringExpression.Literal(agentName)),
                    },
            };

        if (arguments is not null)
        {
            AzureAgentInput.Builder inputBuilder = new();
            foreach ((string key, ValueExpression value) in arguments)
            {
                inputBuilder.Arguments.Add(key, value);
            }
            builder.Input = inputBuilder;
        }

        if (responseObjectVariable is not null)
        {
            builder.Output =
                new AzureAgentOutput.Builder
                {
                    AutoSend = new BoolExpression.Builder(BoolExpression.Literal(false)),
                    ResponseObject = new InitializablePropertyPath(PropertyPath.TopicVariable(responseObjectVariable), isInitializer: false),
                };
        }

        return AssignParent<InvokeAzureAgent>(builder);
    }

    private InvokeAzureAgent CreateAutoSendModel(string displayName, bool? autoSend)
    {
        AzureAgentOutput.Builder outputBuilder = new();
        if (autoSend.HasValue)
        {
            outputBuilder.AutoSend = new BoolExpression.Builder(BoolExpression.Literal(autoSend.Value));
        }

        InvokeAzureAgent.Builder builder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = this.FormatDisplayName(displayName),
                Agent =
                    new AzureAgentUsage.Builder
                    {
                        Name = new StringExpression.Builder(StringExpression.Literal("BrainAutoSend")),
                    },
                Output = outputBuilder,
            };

        return AssignParent<InvokeAzureAgent>(builder);
    }

    /// <summary>
    /// Minimal <see cref="ResponseAgentProvider"/> that returns a single configured text response and
    /// captures the input arguments supplied to <see cref="InvokeAgentAsync"/>.
    /// </summary>
    private sealed class CapturingAgentProvider(string responseText) : ResponseAgentProvider
    {
        public IDictionary<string, object?>? CapturedArguments { get; private set; }

        public override IAsyncEnumerable<AgentResponseUpdate> InvokeAgentAsync(
            string agentId,
            string? agentVersion,
            string? conversationId,
            IEnumerable<ChatMessage>? messages,
            IDictionary<string, object?>? inputArguments,
            CancellationToken cancellationToken = default)
        {
            this.CapturedArguments = inputArguments;
            return YieldAsync(responseText);
        }

        public override Task<string> CreateConversationAsync(CancellationToken cancellationToken = default) =>
            Task.FromResult(Guid.NewGuid().ToString("N"));

        public override Task<ChatMessage> CreateMessageAsync(string conversationId, ChatMessage conversationMessage, CancellationToken cancellationToken = default) =>
            Task.FromResult(conversationMessage);

        public override Task<ChatMessage> GetMessageAsync(string conversationId, string messageId, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public override async IAsyncEnumerable<ChatMessage> GetMessagesAsync(
            string conversationId,
            int? limit = null,
            string? after = null,
            string? before = null,
            bool newestFirst = false,
            [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.CompletedTask.ConfigureAwait(false);
            yield break;
        }

        private static async IAsyncEnumerable<AgentResponseUpdate> YieldAsync(string text)
        {
            yield return new AgentResponseUpdate(ChatRole.Assistant, text);
            await Task.CompletedTask.ConfigureAwait(false);
        }
    }

    #endregion
}
