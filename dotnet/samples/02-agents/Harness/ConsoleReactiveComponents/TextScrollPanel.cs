// Copyright (c) Microsoft. All rights reserved.

using Harness.ConsoleReactiveFramework;

namespace Harness.ConsoleReactiveComponents;

/// <summary>
/// Props for <see cref="TextScrollPanel"/>.
/// </summary>
public record TextScrollPanelProps : ConsoleReactiveProps
{
    /// <summary>Gets the items to render in the scroll panel. Each item is a pre-rendered
    /// console string (may include ANSI escape sequences and newlines).</summary>
    public IReadOnlyList<string> Items { get; init; } = [];
}

/// <summary>
/// State for <see cref="TextScrollPanel"/>.
/// </summary>
public record TextScrollPanelState : ConsoleReactiveState;

/// <summary>
/// A component that renders pre-rendered string items within a scroll area.
/// The last rendered item is considered dynamic and will be re-rendered on each call.
/// All prior items are considered finalized and are not re-rendered.
/// Use <see cref="Invalidate"/> to force a full re-render.
/// </summary>
public class TextScrollPanel : ConsoleReactiveComponent<TextScrollPanelProps, TextScrollPanelState>
{
    private int _renderedCount;
    private int _lastItemOffsetFromBottom;

    /// <summary>
    /// Initializes a new instance of the <see cref="TextScrollPanel"/> class.
    /// </summary>
    public TextScrollPanel()
    {
        this.State = new TextScrollPanelState();
    }

    /// <inheritdoc />
    public override void Invalidate()
    {
        this._renderedCount = 0;
        this._lastItemOffsetFromBottom = 0;
        base.Invalidate();
    }

    /// <inheritdoc />
    public override void RenderCore(TextScrollPanelProps props, TextScrollPanelState state)
    {
        if (props.Items.Count == 0)
        {
            return;
        }

        int bottomRow = props.Y + props.Height - 1;

        // Determine the first item to render. If we previously rendered items,
        // re-render the last one (it may have changed/grown) from its stored position.
        int startIndex = this._renderedCount > 0 ? this._renderedCount - 1 : 0;

        if (this._renderedCount > 0 && this._lastItemOffsetFromBottom > 0)
        {
            // Reposition cursor to where the last rendered item began
            Console.Write(AnsiEscapes.MoveCursor(bottomRow - this._lastItemOffsetFromBottom, props.X));
        }
        else
        {
            // First render — position at the bottom of the scroll area
            Console.Write(AnsiEscapes.MoveCursor(bottomRow, props.X));
        }

        // Render from startIndex onwards
        for (int i = startIndex; i < props.Items.Count; i++)
        {
            Console.Write(props.Items[i]);
        }

        // Calculate the offset from bottom for the start of the new last item,
        // accounting for terminal line wrapping at the available width.
        int lastItemLines = AnsiEscapes.CountPhysicalLines(props.Items[^1], props.Width);
        this._lastItemOffsetFromBottom = lastItemLines > 0 ? lastItemLines - 1 : 0;

        // Update rendered count
        this._renderedCount = props.Items.Count;
    }
}
