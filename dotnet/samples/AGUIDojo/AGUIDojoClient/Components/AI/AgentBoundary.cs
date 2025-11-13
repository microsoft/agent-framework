// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.AspNetCore.Components.Rendering;

namespace Microsoft.AspNetCore.Components.AI;

[CascadingTypeParameter(nameof(TState))]
public partial class AgentStateBoundary<TState> : IComponent, IDisposable
{
    private RenderHandle _renderHandle;
    private RenderFragment? _renderWithState;
    private protected AgentBoundaryContext<TState>? _context;
    private AgentThread? _currentThread;
    private AIAgent? _currentAgent;
    private bool _disposed;

    [EditorRequired][Parameter] public AIAgent? Agent { get; set; }

    [Parameter] public AgentThread? Thread { get; set; }

    [Parameter] public TState? State { get; set; }

    [Parameter] public RenderFragment? ChildContent { get; set; }

    /// <summary>
    /// Callback invoked when the boundary context is created or recreated.
    /// Use this to register tools or perform other initialization.
    /// </summary>
    [Parameter] public EventCallback<IAgentBoundaryContext> OnContextCreated { get; set; }

    [Inject] private ILogger<AgentStateBoundary<TState>> Logger { get; set; } = default!;

    public void Attach(RenderHandle renderHandle)
    {
        this._renderHandle = renderHandle;
        this._renderWithState = this.RenderWithState;
        Log.AgentBoundaryAttached(this.Logger);
    }

    // Agent boundary renders once when it receives the initial set of parameters
    // and only ever renders again if the Agent, Thread, or State changes.
    // Re-rendering the agent boundary will dispose the existing context and create
    // a new one.
    public Task SetParametersAsync(ParameterView parameters)
    {
        parameters.SetParameterProperties(this);

        if (this.Agent == null)
        {
            throw new InvalidOperationException("AgentBoundary requires an Agent parameter.");
        }

        // Use Thread parameter if provided, otherwise keep existing thread or create new one
        var thread = this.Thread ?? this._currentThread ?? this.Agent.GetNewThread();

        TState? currentState = this._context != null ? this._context.CurrentState : default;

        bool agentChanged = this.Agent != this._currentAgent;
        bool threadChanged = thread != this._currentThread;
        bool stateChanged = !EqualityComparer<TState?>.Default.Equals(this.State, currentState);

        bool refresh = agentChanged || threadChanged || stateChanged;

        Log.AgentBoundaryRefreshCheck(
            this.Logger,
            refresh,
            agentChanged,
            threadChanged,
            stateChanged,
            this.Agent?.GetHashCode() ?? 0,
            this._currentAgent?.GetHashCode() ?? 0,
            thread?.GetHashCode() ?? 0,
            this._currentThread?.GetHashCode() ?? 0);

        if (refresh)
        {
            this._context?.Dispose();
            this._context = null;
            this._currentThread = null;
        }

        Log.AgentBoundaryParametersSet(this.Logger, refresh);

        this._currentAgent = this.Agent;
        this._currentThread = thread;

        // Agent is validated non-null above, thread is either from Thread parameter or GetNewThread()
        bool isNewContext = this._context == null;
        this._context ??= new AgentBoundaryContext<TState>(this.Agent!, thread!, this.Logger);
        this._context.CurrentState = this.State;

        // Invoke the context created callback if we created a new context
        if (isNewContext && this.OnContextCreated.HasDelegate)
        {
            _ = this.OnContextCreated.InvokeAsync(this._context);
        }

        if (refresh)
        {
            this.Render();
        }

        return Task.CompletedTask;
    }

    private void Render()
    {
        Log.AgentBoundaryRendering(this.Logger);
        this._renderHandle.Render(builder =>
        {
            builder.OpenComponent<CascadingValue<AgentBoundaryContext<TState>>>(0);
            builder.AddComponentParameter(1, "Value", this._context);
            builder.AddComponentParameter(2, "IsFixed", true);
            builder.AddComponentParameter(3, "ChildContent", this._renderWithState);
            builder.CloseComponent();
        });
    }

    protected virtual void RenderWithState(RenderTreeBuilder builder)
    {
        builder.OpenComponent<CascadingValue<TState?>>(0);
        builder.AddComponentParameter(1, "Value", this.State);
        builder.AddComponentParameter(2, "IsFixed", false);
        builder.AddComponentParameter(3, "ChildContent", this.ChildContent);
        builder.CloseComponent();
    }

    public void Dispose()
    {
        this.Dispose(true);
        GC.SuppressFinalize(this);
    }

    protected virtual void Dispose(bool disposing)
    {
        if (!this._disposed)
        {
            if (disposing)
            {
                Log.AgentBoundaryDisposed(this.Logger);
                this._context?.Dispose();
            }
            this._disposed = true;
        }
    }

    private static partial class Log
    {
        [LoggerMessage(Level = LogLevel.Debug, Message = "AgentStateBoundary attached to render handle")]
        public static partial void AgentBoundaryAttached(ILogger logger);

        [LoggerMessage(Level = LogLevel.Debug, Message = "AgentStateBoundary refresh check: refresh={Refresh}, agentChanged={AgentChanged}, threadChanged={ThreadChanged}, stateChanged={StateChanged}, agentHash={AgentHash}, currentAgentHash={CurrentAgentHash}, threadHash={ThreadHash}, currentThreadHash={CurrentThreadHash}")]
        public static partial void AgentBoundaryRefreshCheck(ILogger logger, bool refresh, bool agentChanged, bool threadChanged, bool stateChanged, int agentHash, int currentAgentHash, int threadHash, int currentThreadHash);

        [LoggerMessage(Level = LogLevel.Debug, Message = "AgentStateBoundary parameters set, refresh required: {RefreshRequired}")]
        public static partial void AgentBoundaryParametersSet(ILogger logger, bool refreshRequired);

        [LoggerMessage(Level = LogLevel.Debug, Message = "AgentStateBoundary rendering")]
        public static partial void AgentBoundaryRendering(ILogger logger);

        [LoggerMessage(Level = LogLevel.Debug, Message = "AgentStateBoundary disposed")]
        public static partial void AgentBoundaryDisposed(ILogger logger);
    }
}

public class AgentBoundary : AgentStateBoundary<object?>
{
    protected override void RenderWithState(RenderTreeBuilder builder)
    {
        builder.OpenComponent<CascadingValue<IAgentBoundaryContext>>(0);
        builder.AddComponentParameter(1, "Value", this._context);
        builder.AddComponentParameter(2, "IsFixed", true);
        builder.AddComponentParameter(3, "ChildContent", this.ChildContent);
        builder.CloseComponent();
    }
}
