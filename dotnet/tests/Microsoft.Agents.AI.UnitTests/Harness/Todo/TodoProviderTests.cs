// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="TodoProvider"/> class.
/// </summary>
public class TodoProviderTests
{
    #region ProvideAIContextAsync Tests

    /// <summary>
    /// Verify that the provider returns tools and instructions.
    /// </summary>
    [Fact]
    public async Task ProvideAIContextAsync_ReturnsToolsAndInstructionsAsync()
    {
        // Arrange
        var provider = new TodoProvider();
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.NotNull(result.Tools);
        Assert.Equal(5, result.Tools!.Count());
    }

    #endregion

    #region AddTodos Tests

    /// <summary>
    /// Verify that AddTodos creates a new todo item when given a single item.
    /// </summary>
    [Fact]
    public async Task AddTodos_CreatesSingleItemAsync()
    {
        // Arrange
        var (tools, state) = await CreateToolsWithStateAsync();
        AIFunction addTodos = GetTool(tools, "TodoList_Add");

        // Act
        await addTodos.InvokeAsync(new AIFunctionArguments()
        {
            ["todos"] = new List<TodoItemInput> { new() { Title = "Test todo", Description = "A test description" } },
        });

        // Assert
        Assert.Single(state.Items);
        Assert.Equal("Test todo", state.Items[0].Title);
        Assert.Equal("A test description", state.Items[0].Description);
        Assert.False(state.Items[0].IsComplete);
        Assert.Equal(1, state.Items[0].Id);
    }

    /// <summary>
    /// Verify that AddTodos creates multiple items with incrementing IDs.
    /// </summary>
    [Fact]
    public async Task AddTodos_CreatesMultipleItemsWithIncrementingIdsAsync()
    {
        // Arrange
        var (tools, state) = await CreateToolsWithStateAsync();
        AIFunction addTodos = GetTool(tools, "TodoList_Add");

        // Act
        await addTodos.InvokeAsync(new AIFunctionArguments()
        {
            ["todos"] = new List<TodoItemInput>
            {
                new() { Title = "First", Description = null },
                new() { Title = "Second", Description = null },
                new() { Title = "Third", Description = "With description" },
            },
        });

        // Assert
        Assert.Equal(3, state.Items.Count);
        Assert.Equal(1, state.Items[0].Id);
        Assert.Equal("First", state.Items[0].Title);
        Assert.Equal(2, state.Items[1].Id);
        Assert.Equal("Second", state.Items[1].Title);
        Assert.Equal(3, state.Items[2].Id);
        Assert.Equal("Third", state.Items[2].Title);
        Assert.Equal("With description", state.Items[2].Description);
    }

    #endregion

    #region CompleteTodos Tests

    /// <summary>
    /// Verify that CompleteTodos marks an item as complete.
    /// </summary>
    [Fact]
    public async Task CompleteTodos_MarksItemCompleteAsync()
    {
        // Arrange
        var (tools, state) = await CreateToolsWithStateAsync();
        AIFunction addTodos = GetTool(tools, "TodoList_Add");
        AIFunction completeTodos = GetTool(tools, "TodoList_Complete");
        await addTodos.InvokeAsync(new AIFunctionArguments() { ["todos"] = new List<TodoItemInput> { new() { Title = "Test", Description = null } } });

        // Act
        object? result = await completeTodos.InvokeAsync(new AIFunctionArguments() { ["ids"] = new List<int> { 1 } });

        // Assert
        Assert.True(state.Items[0].IsComplete);
        Assert.Equal(1, GetIntResult(result));
    }

    /// <summary>
    /// Verify that CompleteTodos marks multiple items as complete.
    /// </summary>
    [Fact]
    public async Task CompleteTodos_MarksMultipleItemsCompleteAsync()
    {
        // Arrange
        var (tools, state) = await CreateToolsWithStateAsync();
        AIFunction addTodos = GetTool(tools, "TodoList_Add");
        AIFunction completeTodos = GetTool(tools, "TodoList_Complete");
        await addTodos.InvokeAsync(new AIFunctionArguments()
        {
            ["todos"] = new List<TodoItemInput> { new() { Title = "First" }, new() { Title = "Second" }, new() { Title = "Third" } },
        });

        // Act
        object? result = await completeTodos.InvokeAsync(new AIFunctionArguments() { ["ids"] = new List<int> { 1, 3 } });

        // Assert
        Assert.True(state.Items[0].IsComplete);
        Assert.False(state.Items[1].IsComplete);
        Assert.True(state.Items[2].IsComplete);
        Assert.Equal(2, GetIntResult(result));
    }

    /// <summary>
    /// Verify that CompleteTodos returns zero for non-existent IDs.
    /// </summary>
    [Fact]
    public async Task CompleteTodos_ReturnsZeroForMissingIdsAsync()
    {
        // Arrange
        var (tools, _) = await CreateToolsWithStateAsync();
        AIFunction completeTodos = GetTool(tools, "TodoList_Complete");

        // Act
        object? result = await completeTodos.InvokeAsync(new AIFunctionArguments() { ["ids"] = new List<int> { 999 } });

        // Assert
        Assert.Equal(0, GetIntResult(result));
    }

    #endregion

    #region RemoveTodos Tests

    /// <summary>
    /// Verify that RemoveTodos removes an item.
    /// </summary>
    [Fact]
    public async Task RemoveTodos_RemovesItemAsync()
    {
        // Arrange
        var (tools, state) = await CreateToolsWithStateAsync();
        AIFunction addTodos = GetTool(tools, "TodoList_Add");
        AIFunction removeTodos = GetTool(tools, "TodoList_Remove");
        await addTodos.InvokeAsync(new AIFunctionArguments() { ["todos"] = new List<TodoItemInput> { new() { Title = "Test", Description = null } } });

        // Act
        object? result = await removeTodos.InvokeAsync(new AIFunctionArguments() { ["ids"] = new List<int> { 1 } });

        // Assert
        Assert.Empty(state.Items);
        Assert.Equal(1, GetIntResult(result));
    }

    /// <summary>
    /// Verify that RemoveTodos removes multiple items.
    /// </summary>
    [Fact]
    public async Task RemoveTodos_RemovesMultipleItemsAsync()
    {
        // Arrange
        var (tools, state) = await CreateToolsWithStateAsync();
        AIFunction addTodos = GetTool(tools, "TodoList_Add");
        AIFunction removeTodos = GetTool(tools, "TodoList_Remove");
        await addTodos.InvokeAsync(new AIFunctionArguments()
        {
            ["todos"] = new List<TodoItemInput> { new() { Title = "First" }, new() { Title = "Second" }, new() { Title = "Third" } },
        });

        // Act
        object? result = await removeTodos.InvokeAsync(new AIFunctionArguments() { ["ids"] = new List<int> { 1, 3 } });

        // Assert
        Assert.Single(state.Items);
        Assert.Equal("Second", state.Items[0].Title);
        Assert.Equal(2, GetIntResult(result));
    }

    /// <summary>
    /// Verify that RemoveTodos returns zero for non-existent IDs.
    /// </summary>
    [Fact]
    public async Task RemoveTodos_ReturnsZeroForMissingIdsAsync()
    {
        // Arrange
        var (tools, _) = await CreateToolsWithStateAsync();
        AIFunction removeTodos = GetTool(tools, "TodoList_Remove");

        // Act
        object? result = await removeTodos.InvokeAsync(new AIFunctionArguments() { ["ids"] = new List<int> { 999 } });

        // Assert
        Assert.Equal(0, GetIntResult(result));
    }

    #endregion

    #region GetRemainingTodos Tests

    /// <summary>
    /// Verify that GetRemainingTodos returns only incomplete items.
    /// </summary>
    [Fact]
    public async Task GetRemainingTodos_ReturnsOnlyIncompleteAsync()
    {
        // Arrange
        var (tools, _) = await CreateToolsWithStateAsync();
        AIFunction addTodos = GetTool(tools, "TodoList_Add");
        AIFunction completeTodos = GetTool(tools, "TodoList_Complete");
        AIFunction getRemainingTodos = GetTool(tools, "TodoList_GetRemaining");
        await addTodos.InvokeAsync(new AIFunctionArguments()
        {
            ["todos"] = new List<TodoItemInput> { new() { Title = "Done", Description = null }, new() { Title = "Pending", Description = null } },
        });
        await completeTodos.InvokeAsync(new AIFunctionArguments() { ["ids"] = new List<int> { 1 } });

        // Act
        object? result = await getRemainingTodos.InvokeAsync(new AIFunctionArguments());

        // Assert
        var remaining = GetArrayResult(result);
        Assert.Single(remaining);
        Assert.Equal("Pending", remaining[0].GetProperty("title").GetString());
    }

    #endregion

    #region GetAllTodos Tests

    /// <summary>
    /// Verify that GetAllTodos returns all items.
    /// </summary>
    [Fact]
    public async Task GetAllTodos_ReturnsAllItemsAsync()
    {
        // Arrange
        var (tools, _) = await CreateToolsWithStateAsync();
        AIFunction addTodos = GetTool(tools, "TodoList_Add");
        AIFunction completeTodos = GetTool(tools, "TodoList_Complete");
        AIFunction getAllTodos = GetTool(tools, "TodoList_GetAll");
        await addTodos.InvokeAsync(new AIFunctionArguments()
        {
            ["todos"] = new List<TodoItemInput> { new() { Title = "Done", Description = null }, new() { Title = "Pending", Description = null } },
        });
        await completeTodos.InvokeAsync(new AIFunctionArguments() { ["ids"] = new List<int> { 1 } });

        // Act
        object? result = await getAllTodos.InvokeAsync(new AIFunctionArguments());

        // Assert
        var all = GetArrayResult(result);
        Assert.Equal(2, all.Count);
    }

    #endregion

    #region State Persistence Tests

    /// <summary>
    /// Verify that state persists in the session StateBag.
    /// </summary>
    [Fact]
    public async Task State_PersistsInSessionStateBagAsync()
    {
        // Arrange
        var provider = new TodoProvider();
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act — first invocation adds a todo
        AIContext result1 = await provider.InvokingAsync(context);
        AIFunction addTodos = (AIFunction)result1.Tools!.First(t => t is AIFunction f && f.Name == "TodoList_Add");
        await addTodos.InvokeAsync(new AIFunctionArguments() { ["todos"] = new List<TodoItemInput> { new() { Title = "Persisted", Description = null } } });

        // Second invocation should see the same state
        AIContext result2 = await provider.InvokingAsync(context);
        AIFunction getAllTodos = (AIFunction)result2.Tools!.First(t => t is AIFunction f && f.Name == "TodoList_GetAll");
        object? allResult = await getAllTodos.InvokeAsync(new AIFunctionArguments());

        // Assert
        var all = GetArrayResult(allResult);
        Assert.Single(all);
        Assert.Equal("Persisted", all[0].GetProperty("title").GetString());
    }

    #endregion

    #region Public Helper Method Tests

    /// <summary>
    /// Verify that GetAllTodos returns all items after adding via tools.
    /// </summary>
    [Fact]
    public async Task PublicGetAllTodos_ReturnsAllItemsAsync()
    {
        // Arrange
        var provider = new TodoProvider();
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001
        AIContext result = await provider.InvokingAsync(context);
        AIFunction addTodos = GetTool(result.Tools!, "TodoList_Add");
        await addTodos.InvokeAsync(new AIFunctionArguments()
        {
            ["todos"] = new List<TodoItemInput> { new() { Title = "First", Description = null }, new() { Title = "Second", Description = null } },
        });

        // Act
        var todos = provider.GetAllTodos(session);

        // Assert
        Assert.Equal(2, todos.Count);
        Assert.Equal("First", todos[0].Title);
        Assert.Equal("Second", todos[1].Title);
    }

    /// <summary>
    /// Verify that GetRemainingTodos returns only incomplete items.
    /// </summary>
    [Fact]
    public async Task PublicGetRemainingTodos_ReturnsOnlyIncompleteAsync()
    {
        // Arrange
        var provider = new TodoProvider();
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001
        AIContext result = await provider.InvokingAsync(context);
        AIFunction addTodos = GetTool(result.Tools!, "TodoList_Add");
        AIFunction completeTodos = GetTool(result.Tools!, "TodoList_Complete");
        await addTodos.InvokeAsync(new AIFunctionArguments()
        {
            ["todos"] = new List<TodoItemInput> { new() { Title = "Done", Description = null }, new() { Title = "Pending", Description = null } },
        });
        await completeTodos.InvokeAsync(new AIFunctionArguments() { ["ids"] = new List<int> { 1 } });

        // Act
        var remaining = provider.GetRemainingTodos(session);

        // Assert
        Assert.Single(remaining);
        Assert.Equal("Pending", remaining[0].Title);
    }

    /// <summary>
    /// Verify that GetAllTodos returns empty list for a new session.
    /// </summary>
    [Fact]
    public void PublicGetAllTodos_ReturnsEmptyForNewSession()
    {
        // Arrange
        var provider = new TodoProvider();
        var session = new ChatClientAgentSession();

        // Act
        var todos = provider.GetAllTodos(session);

        // Assert
        Assert.Empty(todos);
    }

    #endregion

    #region Helper Methods

    private static async Task<(IEnumerable<AITool> Tools, TodoState State)> CreateToolsWithStateAsync()
    {
        var provider = new TodoProvider();
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        AIContext result = await provider.InvokingAsync(context);

        // Retrieve the state from the session to verify mutations
        session.StateBag.TryGetValue<TodoState>("TodoProvider", out var state, AgentJsonUtilities.DefaultOptions);

        return (result.Tools!, state!);
    }

    private static AIFunction GetTool(IEnumerable<AITool> tools, string name)
    {
        return (AIFunction)tools.First(t => t is AIFunction f && f.Name == name);
    }

    private static int GetIntResult(object? result)
    {
        var element = Assert.IsType<JsonElement>(result);
        return element.GetInt32();
    }

    private static List<JsonElement> GetArrayResult(object? result)
    {
        var element = Assert.IsType<JsonElement>(result);
        return element.EnumerateArray().ToList();
    }

    #endregion

    #region Options Tests

    /// <summary>
    /// Verify that custom instructions override the default.
    /// </summary>
    [Fact]
    public async Task Options_CustomInstructions_OverridesDefaultAsync()
    {
        // Arrange
        var options = new TodoProviderOptions { Instructions = "Custom todo instructions." };
        var provider = new TodoProvider(options);
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.Equal("Custom todo instructions.", result.Instructions);
    }

    /// <summary>
    /// Verify that null options uses default instructions.
    /// </summary>
    [Fact]
    public async Task Options_Null_UsesDefaultInstructionsAsync()
    {
        // Arrange
        var provider = new TodoProvider();
        var agent = new Mock<AIAgent>().Object;
        var session = new ChatClientAgentSession();
#pragma warning disable MAAI001
        var context = new AIContextProvider.InvokingContext(agent, session, new AIContext());
#pragma warning restore MAAI001

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.Contains("todo list", result.Instructions);
    }

    #endregion
}
