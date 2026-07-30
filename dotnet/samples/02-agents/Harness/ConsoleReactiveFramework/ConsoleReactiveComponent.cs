// Copyright (c) Microsoft. All rights reserved.

namespace Harness.ConsoleReactiveFramework;

/// <summary>
/// Abstract base class for all console UI components. Provides access to layout
/// through <see cref="BaseProps"/> and a <see cref="Render"/> method for drawing to the console.
/// Derive from <see cref="ConsoleReactiveComponent{TProps, TState}"/> instead of this class directly.
/// </summary>
public abstract class ConsoleReactiveComponent
{
    internal ConsoleReactiveComponent()
    {
    }

    /// <summary>
    /// Gets the shared render lock across all component types to prevent ANSI escape sequence interleaving.
    /// </summary>
    protected static object RenderLock { get; } = new();

    /// <summary>
    /// Gets or sets the component's props as the base <see cref="ConsoleReactiveProps"/> type.
    /// Used by parent components to set layout (X, Y, Width, Height) on children without
    /// knowing the concrete props type.
    /// </summary>
    public abstract ConsoleReactiveProps? BaseProps { get; set; }

    /// <summary>Renders the component to the console at its current position.</summary>
    public abstract void Render();

    /// <summary>
    /// Invalidates the component's cached render state, causing the next <see cref="Render"/> call
    /// to proceed even if props and state have not changed. Use after a screen erase to force repaint.
    /// </summary>
    public abstract void Invalidate();
}

/// <summary>
/// Generic base class for console UI components with typed props and state.
/// Props represent externally supplied configuration; state represents internal mutable data.
/// </summary>
/// <typeparam name="TProps">The type of the component's props (external configuration).</typeparam>
/// <typeparam name="TState">The type of the component's internal state.</typeparam>
public abstract class ConsoleReactiveComponent<TProps, TState> : ConsoleReactiveComponent
    where TProps : ConsoleReactiveProps
    where TState : ConsoleReactiveState
{
    private TProps? _lastRenderedProps;
    private TState? _lastRenderedState;

    /// <summary>Gets or sets the component's props (external configuration).</summary>
    public TProps? Props { get; set; }

    /// <inheritdoc/>
    public override ConsoleReactiveProps? BaseProps
    {
        get => this.Props;
        set => this.Props = (TProps?)value;
    }

    /// <summary>Gets or sets the component's internal state.</summary>
    protected TState? State { get; set; }

    /// <summary>
    /// Updates the component's state and triggers a re-render.
    /// </summary>
    /// <param name="newState">The new state value.</param>
    public void SetState(TState newState)
    {
        this.State = newState;
        this.Render();
    }

    /// <summary>
    /// Renders the component using the current props and state.
    /// Uses a lock to prevent concurrent renders from multiple sources.
    /// Skips rendering if neither props nor state have changed since the last render.
    /// </summary>
    public override void Render()
    {
        lock (RenderLock)
        {
            if (this.Props is null)
            {
                return;
            }

            if (EqualityComparer<TProps>.Default.Equals(this.Props, this._lastRenderedProps)
                && EqualityComparer<TState>.Default.Equals(this.State, this._lastRenderedState))
            {
                return;
            }

            this.RenderCore(this.Props, this.State!);

            this._lastRenderedProps = this.Props;
            this._lastRenderedState = this.State;
        }
    }

    /// <inheritdoc/>
    public override void Invalidate()
    {
        lock (RenderLock)
        {
            this._lastRenderedProps = default;
            this._lastRenderedState = default;
        }
    }

    /// <summary>
    /// Called by <see cref="Render"/> to perform the actual rendering. Override this in derived classes.
    /// </summary>
    /// <param name="props">The current props.</param>
    /// <param name="state">The current state.</param>
    public abstract void RenderCore(TProps props, TState state);
}

/// <summary>
/// Base record for component props. Provides layout properties (position and size)
/// and an optional <see cref="Children"/> collection for composing child components.
/// </summary>
public record ConsoleReactiveProps
{
    /// <summary>Gets the 1-based column position of the component.</summary>
    public int X { get; init; }

    /// <summary>Gets the 1-based row position of the component.</summary>
    public int Y { get; init; }

    /// <summary>Gets the width of the component in columns.</summary>
    public int Width { get; init; }

    /// <summary>Gets the height of the component in rows.</summary>
    public int Height { get; init; }

    /// <summary>Gets the child components to render within this component.</summary>
    public IReadOnlyList<ConsoleReactiveComponent> Children { get; init; } = [];
}

/// <summary>
/// Base record for component state.
/// </summary>
public record ConsoleReactiveState;
