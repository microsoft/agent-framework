// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// An <see cref="AIContextProvider"/> that provides todo management tools and instructions
/// to an agent for tracking work items during long-running complex tasks.
/// </summary>
/// <remarks>
/// <para>
/// The <see cref="TodoProvider"/> enables agents to create, complete, remove, and query todo items
/// as part of their planning and execution workflow. Todo state is stored in the session's
/// <see cref="AgentSessionStateBag"/> and persists across agent invocations within the same session.
/// </para>
/// <para>
/// This provider exposes the following tools to the agent:
/// <list type="bullet">
/// <item><description><c>TodoList_Add</c> — Add one or more todo items, each with a title and optional description.</description></item>
/// <item><description><c>TodoList_Complete</c> — Mark one or more todo items as complete by their IDs.</description></item>
/// <item><description><c>TodoList_Remove</c> — Remove one or more todo items by their IDs.</description></item>
/// <item><description><c>TodoList_GetRemaining</c> — Retrieve only incomplete todo items.</description></item>
/// <item><description><c>TodoList_GetAll</c> — Retrieve all todo items (complete and incomplete).</description></item>
/// </list>
/// </para>
/// <para>
/// All operations are thread-safe; concurrent reads and mutations on the same session are serialized
/// using a per-session lock to prevent duplicate IDs, lost updates, or inconsistent reads.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class TodoProvider : AIContextProvider, IDisposable
{
    private const string DefaultInstructions =
        """
        ## Todo Items

        You have access to a todo list for tracking work items.
        While planning, make sure that you break down complex tasks into manageable todo items and add them to the list.
        Ask questions from the user where clarification is needed to create effective todos.
        If the user provides feedback on your plan, adjust your todos accordingly by adding new items or removing irrelevant ones.
        During execution, use the todo list to keep track of what needs to be done, mark items as complete when finished, and remove any items that are no longer needed.
        When a user changes the topic or changes their mind, ensure that you update the todo list accordingly by removing irrelevant items or adding new ones as needed.
        
        Use these tools to manage your tasks:
        - Use TodoList_Add to break down complex work into trackable items (supports adding one or many at once).
        - Use TodoList_Complete to mark items as done when finished (supports one or many at once).
        - Use TodoList_GetRemaining to check what work is still pending.
        - Use TodoList_GetAll to review the full list including completed items.
        - Use TodoList_Remove to remove items that are no longer needed (supports one or many at once).
        """;

    private readonly ProviderSessionState<TodoState> _sessionState;
    private readonly string _instructions;
    private readonly bool _suppressTodoListMessage;
    private readonly Func<IReadOnlyList<TodoItem>, string>? _todoListMessageBuilder;
    private readonly ConditionalWeakTable<AgentSession, SemaphoreSlim> _sessionLocks = new();
    private readonly SemaphoreSlim _nullSessionLock = new(1, 1);
    private IReadOnlyList<string>? _stateKeys;

    /// <summary>
    /// Initializes a new instance of the <see cref="TodoProvider"/> class.
    /// </summary>
    /// <param name="options">Optional settings that control provider behavior. When <see langword="null"/>, defaults are used.</param>
    public TodoProvider(TodoProviderOptions? options = null)
    {
        this._instructions = options?.Instructions ?? DefaultInstructions;
        this._suppressTodoListMessage = options?.SuppressTodoListMessage ?? false;
        this._todoListMessageBuilder = options?.TodoListMessageBuilder;
        this._sessionState = new ProviderSessionState<TodoState>(
            _ => new TodoState(),
            this.GetType().Name,
            AgentJsonUtilities.DefaultOptions);
    }

    /// <inheritdoc />
    public override IReadOnlyList<string> StateKeys => this._stateKeys ??= [this._sessionState.StateKey];

    /// <inheritdoc />
    public void Dispose()
    {
        this._nullSessionLock.Dispose();
    }

    /// <summary>
    /// Gets all todo items from the session state.
    /// </summary>
    /// <remarks>
    /// The returned <see cref="TodoItem"/> instances are the live objects from internal state.
    /// Modifying their properties will mutate the provider's state directly.
    /// </remarks>
    /// <param name="session">The agent session to read todos from.</param>
    /// <returns>A list of all todo items. The items are live references to internal state.</returns>
    public async Task<IReadOnlyList<TodoItem>> GetAllTodosAsync(AgentSession? session)
    {
        SemaphoreSlim sessionLock = this.GetSessionLock(session);
        await sessionLock.WaitAsync().ConfigureAwait(false);
        try
        {
            TodoState state = this._sessionState.GetOrInitializeState(session);
            return state.Items.ToList();
        }
        finally
        {
            sessionLock.Release();
        }
    }

    /// <summary>
    /// Gets the remaining (incomplete) todo items from the session state.
    /// </summary>
    /// <remarks>
    /// The returned <see cref="TodoItem"/> instances are the live objects from internal state.
    /// Modifying their properties will mutate the provider's state directly.
    /// </remarks>
    /// <param name="session">The agent session to read todos from.</param>
    /// <returns>A list of incomplete todo items. The items are live references to internal state.</returns>
    public async Task<List<TodoItem>> GetRemainingTodosAsync(AgentSession? session)
    {
        SemaphoreSlim sessionLock = this.GetSessionLock(session);
        await sessionLock.WaitAsync().ConfigureAwait(false);
        try
        {
            TodoState state = this._sessionState.GetOrInitializeState(session);
            return state.Items.Where(t => !t.IsComplete).ToList();
        }
        finally
        {
            sessionLock.Release();
        }
    }

    /// <inheritdoc />
    protected override async ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        var aiContext = new AIContext
        {
            Instructions = this._instructions,
            Tools = this.CreateTools(context.Session),
        };

        if (!this._suppressTodoListMessage)
        {
            // Inject a synthetic user message summarizing the current todo list so the agent
            // is aware of outstanding work at the start of each invocation.
            SemaphoreSlim sessionLock = this.GetSessionLock(context.Session);
            await sessionLock.WaitAsync(cancellationToken).ConfigureAwait(false);
            List<TodoItem> currentItems;
            try
            {
                TodoState state = this._sessionState.GetOrInitializeState(context.Session);
                currentItems = state.Items.ToList();
            }
            finally
            {
                sessionLock.Release();
            }

            string message = this._todoListMessageBuilder is not null
                ? this._todoListMessageBuilder(currentItems)
                : FormatTodoListMessage(currentItems);

            aiContext.Messages =
            [
                new ChatMessage(ChatRole.User, message),
            ];
        }

        return aiContext;
    }

    /// <summary>
    /// Returns the per-session semaphore used to serialize all todo operations.
    /// </summary>
    private SemaphoreSlim GetSessionLock(AgentSession? session)
    {
        if (session is null)
        {
            return this._nullSessionLock;
        }

        return this._sessionLocks.GetValue(session, _ => new SemaphoreSlim(1, 1));
    }

    private AITool[] CreateTools(AgentSession? session)
    {
        var serializerOptions = AgentJsonUtilities.DefaultOptions;

        return
        [
            AIFunctionFactory.Create(
                async (List<TodoItemInput> todos) =>
                {
                    SemaphoreSlim sessionLock = this.GetSessionLock(session);
                    await sessionLock.WaitAsync().ConfigureAwait(false);
                    try
                    {
                        TodoState state = this._sessionState.GetOrInitializeState(session);
                        var created = new List<TodoItem>();
                        foreach (var input in todos)
                        {
                            var item = new TodoItem
                            {
                                Id = state.NextId++,
                                Title = input.Title.Trim(),
                                Description = input.Description?.Trim(),
                            };
                            state.Items.Add(item);
                            created.Add(item);
                        }

                        this._sessionState.SaveState(session, state);
                        return created;
                    }
                    finally
                    {
                        sessionLock.Release();
                    }
                },
                new AIFunctionFactoryOptions
                {
                    Name = "TodoList_Add",
                    Description = "Add one or more todo items. Each item has a title and an optional description. Returns the list of created todo items.",
                    SerializerOptions = serializerOptions,
                }),

            AIFunctionFactory.Create(
                async (List<int> ids) =>
                {
                    SemaphoreSlim sessionLock = this.GetSessionLock(session);
                    await sessionLock.WaitAsync().ConfigureAwait(false);
                    try
                    {
                        TodoState state = this._sessionState.GetOrInitializeState(session);
                        var idSet = new HashSet<int>(ids);
                        int completed = 0;
                        foreach (TodoItem item in state.Items)
                        {
                            if (!item.IsComplete && idSet.Contains(item.Id))
                            {
                                item.IsComplete = true;
                                completed++;
                            }
                        }

                        if (completed > 0)
                        {
                            this._sessionState.SaveState(session, state);
                        }

                        return completed;
                    }
                    finally
                    {
                        sessionLock.Release();
                    }
                },
                new AIFunctionFactoryOptions
                {
                    Name = "TodoList_Complete",
                    Description = "Mark one or more todo items as complete by their IDs. Returns the number of items that were found and marked complete.",
                    SerializerOptions = serializerOptions,
                }),

            AIFunctionFactory.Create(
                async (List<int> ids) =>
                {
                    SemaphoreSlim sessionLock = this.GetSessionLock(session);
                    await sessionLock.WaitAsync().ConfigureAwait(false);
                    try
                    {
                        TodoState state = this._sessionState.GetOrInitializeState(session);
                        var idSet = new HashSet<int>(ids);
                        int removed = state.Items.RemoveAll(t => idSet.Contains(t.Id));

                        if (removed > 0)
                        {
                            this._sessionState.SaveState(session, state);
                        }

                        return removed;
                    }
                    finally
                    {
                        sessionLock.Release();
                    }
                },
                new AIFunctionFactoryOptions
                {
                    Name = "TodoList_Remove",
                    Description = "Remove one or more todo items by their IDs. Returns the number of items that were found and removed.",
                    SerializerOptions = serializerOptions,
                }),

            AIFunctionFactory.Create(
                async () =>
                {
                    SemaphoreSlim sessionLock = this.GetSessionLock(session);
                    await sessionLock.WaitAsync().ConfigureAwait(false);
                    try
                    {
                        TodoState state = this._sessionState.GetOrInitializeState(session);
                        return state.Items.Where(t => !t.IsComplete).ToList();
                    }
                    finally
                    {
                        sessionLock.Release();
                    }
                },
                new AIFunctionFactoryOptions
                {
                    Name = "TodoList_GetRemaining",
                    Description = "Retrieve the list of incomplete todo items.",
                    SerializerOptions = serializerOptions,
                }),

            AIFunctionFactory.Create(
                async () =>
                {
                    SemaphoreSlim sessionLock = this.GetSessionLock(session);
                    await sessionLock.WaitAsync().ConfigureAwait(false);
                    try
                    {
                        TodoState state = this._sessionState.GetOrInitializeState(session);
                        return state.Items.ToList();
                    }
                    finally
                    {
                        sessionLock.Release();
                    }
                },
                new AIFunctionFactoryOptions
                {
                    Name = "TodoList_GetAll",
                    Description = "Retrieve the full list of todo items, both complete and incomplete.",
                    SerializerOptions = serializerOptions,
                }),
        ];
    }

    internal static string FormatTodoListMessage(List<TodoItem> items)
    {
        if (items.Count == 0)
        {
            return "### Current todo list\n- none yet";
        }

        var sb = new StringBuilder("### Current todo list\n");
        foreach (var item in items)
        {
            string status = item.IsComplete ? "done" : "open";
            sb.Append($"- {item.Id} [{status}] {item.Title}");
            if (!string.IsNullOrWhiteSpace(item.Description))
            {
                sb.Append($": {item.Description}");
            }

            sb.AppendLine();
        }

        return sb.ToString().TrimEnd();
    }
}
