// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="TodoCompletionLoopEvaluator"/> class.
/// </summary>
public class TodoCompletionLoopEvaluatorTests
{
    /// <summary>
    /// Verify that the constructor throws when a non-null but empty modes collection is supplied.
    /// </summary>
    [Fact]
    public void TodoCompletionLoopEvaluator_EmptyModes_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => new TodoCompletionLoopEvaluator(new TodoCompletionLoopEvaluatorOptions { Modes = [] }));
    }

    /// <summary>
    /// Verify that the constructor throws when a mode name is null, empty, or whitespace.
    /// </summary>
    /// <param name="mode">The invalid mode name.</param>
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void TodoCompletionLoopEvaluator_InvalidModeName_Throws(string? mode)
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => new TodoCompletionLoopEvaluator(new TodoCompletionLoopEvaluatorOptions { Modes = [mode!] }));
    }

    /// <summary>
    /// Verify that the constructor succeeds with null modes (applies in every mode) and with a valid mode set.
    /// </summary>
    [Fact]
    public void TodoCompletionLoopEvaluator_ValidConstruction_Succeeds()
    {
        // Act & Assert
        _ = new TodoCompletionLoopEvaluator();
        _ = new TodoCompletionLoopEvaluator(new TodoCompletionLoopEvaluatorOptions { Modes = ["execute"] });
    }

    /// <summary>
    /// Verify that evaluation throws when no <see cref="TodoProvider"/> can be resolved from the agent.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NoTodoProvider_ThrowsAsync()
    {
        // Arrange — a bare agent that resolves no providers.
        var evaluator = new TodoCompletionLoopEvaluator();
        var context = CreateContext(new Mock<AIAgent>().Object, new ChatClientAgentSession());

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await evaluator.EvaluateAsync(context));
    }

    /// <summary>
    /// Verify that evaluation throws when modes are configured but no <see cref="AgentModeProvider"/> can be resolved.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_ModesConfiguredButNoModeProvider_ThrowsAsync()
    {
        // Arrange — agent has a TodoProvider but no AgentModeProvider.
        var todoProvider = new TodoProvider();
        var session = new ChatClientAgentSession();
        SeedTodos(session, (1, "Task one", null, false));
        AIAgent agent = CreateAgent(todoProvider);
        var evaluator = new TodoCompletionLoopEvaluator(new TodoCompletionLoopEvaluatorOptions { Modes = ["execute"] });
        LoopContext context = CreateContext(agent, session);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await evaluator.EvaluateAsync(context));
    }

    /// <summary>
    /// Verify that, with no modes configured, the evaluator continues while incomplete todos remain and the feedback
    /// lists those todos.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NoModes_RemainingTodos_ContinuesWithFeedbackAsync()
    {
        // Arrange
        var todoProvider = new TodoProvider();
        var session = new ChatClientAgentSession();
        SeedTodos(session, (1, "Write code", null, false), (2, "Add tests", "cover edge cases", false), (3, "Done item", null, true));
        AIAgent agent = CreateAgent(todoProvider);
        var evaluator = new TodoCompletionLoopEvaluator();
        LoopContext context = CreateContext(agent, session);

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.NotNull(evaluation.Feedback);
        Assert.Contains("Write code", evaluation.Feedback!);
        Assert.Contains("Add tests", evaluation.Feedback!);
        Assert.Contains("cover edge cases", evaluation.Feedback!);
        // Completed items must not appear in the feedback list.
        Assert.DoesNotContain("Done item", evaluation.Feedback!);
    }

    /// <summary>
    /// Verify that, with no modes configured, the evaluator stops when there are no incomplete todos.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_NoModes_NoRemainingTodos_StopsAsync()
    {
        // Arrange
        var todoProvider = new TodoProvider();
        var session = new ChatClientAgentSession();
        SeedTodos(session, (1, "Completed", null, true));
        AIAgent agent = CreateAgent(todoProvider);
        var evaluator = new TodoCompletionLoopEvaluator();
        LoopContext context = CreateContext(agent, session);

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.False(evaluation.ShouldReinvoke);
    }

    /// <summary>
    /// Verify that, when the current mode is one of the configured modes and incomplete todos remain, the evaluator
    /// continues.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_ModeMatches_RemainingTodos_ContinuesAsync()
    {
        // Arrange
        var todoProvider = new TodoProvider();
        var modeProvider = new AgentModeProvider();
        var session = new ChatClientAgentSession();
        modeProvider.SetMode(session, "execute");
        SeedTodos(session, (1, "Work item", null, false));
        AIAgent agent = CreateAgent(todoProvider, modeProvider);
        var evaluator = new TodoCompletionLoopEvaluator(new TodoCompletionLoopEvaluatorOptions { Modes = ["execute"] });
        LoopContext context = CreateContext(agent, session);

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
    }

    /// <summary>
    /// Verify that, when the current mode is one of the configured modes but no incomplete todos remain, the evaluator
    /// stops.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_ModeMatches_NoRemainingTodos_StopsAsync()
    {
        // Arrange
        var todoProvider = new TodoProvider();
        var modeProvider = new AgentModeProvider();
        var session = new ChatClientAgentSession();
        modeProvider.SetMode(session, "execute");
        SeedTodos(session, (1, "Already done", null, true));
        AIAgent agent = CreateAgent(todoProvider, modeProvider);
        var evaluator = new TodoCompletionLoopEvaluator(new TodoCompletionLoopEvaluatorOptions { Modes = ["execute"] });
        LoopContext context = CreateContext(agent, session);

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.False(evaluation.ShouldReinvoke);
    }

    /// <summary>
    /// Verify that, when the current mode is not one of the configured modes, the evaluator stops even if incomplete
    /// todos remain.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_ModeDoesNotMatch_StopsEvenWithRemainingTodosAsync()
    {
        // Arrange
        var todoProvider = new TodoProvider();
        var modeProvider = new AgentModeProvider();
        var session = new ChatClientAgentSession();
        modeProvider.SetMode(session, "plan");
        SeedTodos(session, (1, "Still open", null, false));
        AIAgent agent = CreateAgent(todoProvider, modeProvider);
        var evaluator = new TodoCompletionLoopEvaluator(new TodoCompletionLoopEvaluatorOptions { Modes = ["execute"] });
        LoopContext context = CreateContext(agent, session);

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.False(evaluation.ShouldReinvoke);
    }

    /// <summary>
    /// Verify that a custom feedback template with the remaining-todos placeholder is honored.
    /// </summary>
    [Fact]
    public async Task EvaluateAsync_CustomTemplate_IsHonoredAsync()
    {
        // Arrange
        var todoProvider = new TodoProvider();
        var session = new ChatClientAgentSession();
        SeedTodos(session, (1, "Remaining task", null, false));
        AIAgent agent = CreateAgent(todoProvider);
        var options = new TodoCompletionLoopEvaluatorOptions
        {
            FeedbackMessageTemplate = "Keep going. Open:\n" + TodoCompletionLoopEvaluator.RemainingTodosPlaceholder,
        };
        var evaluator = new TodoCompletionLoopEvaluator(options: options);
        LoopContext context = CreateContext(agent, session);

        // Act
        LoopEvaluation evaluation = await evaluator.EvaluateAsync(context);

        // Assert
        Assert.True(evaluation.ShouldReinvoke);
        Assert.StartsWith("Keep going. Open:", evaluation.Feedback);
        Assert.Contains("Remaining task", evaluation.Feedback!);
    }

    private static ChatClientAgent CreateAgent(params AIContextProvider[] providers)
    {
        var chatClient = new Mock<IChatClient>().Object;
        return new ChatClientAgent(chatClient, new ChatClientAgentOptions { AIContextProviders = providers });
    }

    private static LoopContext CreateContext(AIAgent agent, AgentSession session) => new(
        agent,
        session,
        [new ChatMessage(ChatRole.User, "do the work")],
        new AgentResponse([new ChatMessage(ChatRole.Assistant, "in progress")]));

    private static void SeedTodos(AgentSession session, params (int Id, string Title, string? Description, bool IsComplete)[] items)
    {
        var state = new TodoState { NextId = items.Length + 1 };
        foreach ((int id, string title, string? description, bool isComplete) in items)
        {
            state.Items.Add(new TodoItem
            {
                Id = id,
                Title = title,
                Description = description,
                IsComplete = isComplete,
            });
        }

        // Persist under the TodoProvider's state key so the provider reads it back via GetRemainingTodosAsync.
        session.StateBag.SetValue(nameof(TodoProvider), state, AgentJsonUtilities.DefaultOptions);
    }
}
