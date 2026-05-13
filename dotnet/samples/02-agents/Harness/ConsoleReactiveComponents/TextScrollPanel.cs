// Copyright (c) Microsoft. All rights reserved.

using Harness.ConsoleReactiveFramework;

namespace Harness.ConsoleReactiveComponents;

/// <summary>
/// Props for <see cref="TextScrollPanel"/>.
/// </summary>
public record TextScrollPanelProps : ConsoleReactiveProps
{
    /// <summary>Gets the items to render in the scroll panel.</summary>
    public IReadOnlyList<object> Items { get; init; } = [];
}

/// <summary>
/// State for <see cref="TextScrollPanel"/>.
/// </summary>
/// <param name="RenderedCount">The number of items already rendered.</param>
public record TextScrollPanelState(int RenderedCount = 0) : ConsoleReactiveState;

/// <summary>
/// A component that renders items within a scroll area using a custom render delegate.
/// All items are considered finalized — only new items since the last render are output.
/// Use <see cref="Reset"/> to force a full re-render.
/// </summary>
public class TextScrollPanel : ConsoleReactiveComponent<TextScrollPanelProps, TextScrollPanelState>
{
    private readonly Func<object, string> _renderItem;

    /// <summary>
    /// Initializes a new instance of the <see cref="TextScrollPanel"/> class.
    /// </summary>
    /// <param name="renderItem">A delegate that renders a single item and returns the text to display (may contain newlines).</param>
    public TextScrollPanel(Func<object, string> renderItem)
    {
        this._renderItem = renderItem;
        this.State = new TextScrollPanelState();
    }

    /// <summary>
    /// Resets the panel so all items will be re-rendered on the next Render call.
    /// </summary>
    public void Reset()
    {
        this.State = new TextScrollPanelState();
    }

    /// <inheritdoc />
    public override void RenderCore(TextScrollPanelProps props, TextScrollPanelState state)
    {
        if (props.Items.Count == 0)
        {
            return;
        }

        // Move cursor to the bottom of the scroll area
        Console.Write(AnsiEscapes.MoveCursor(this.Y + this.Height - 1, this.X));

        // Output only new items since last rendered
        for (int i = state.RenderedCount; i < props.Items.Count; i++)
        {
            string text = this._renderItem(props.Items[i]);
            Console.Write(text);
        }

        // Update state to track what we've rendered
        this.State = new TextScrollPanelState(props.Items.Count);
    }
}
