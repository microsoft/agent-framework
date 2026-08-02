// Copyright (c) Microsoft. All rights reserved.

using Harness.ConsoleReactiveFramework;

namespace Harness.ConsoleReactiveComponents;

/// <summary>
/// Props for <see cref="TextPanel"/>.
/// </summary>
public record TextPanelProps : ConsoleReactiveProps
{
    /// <summary>Gets the items to render in the panel. Each item is a pre-rendered
    /// console string (may include ANSI escape sequences and newlines).</summary>
    public IReadOnlyList<string> Items { get; init; } = [];
}

/// <summary>
/// A component that renders a list of pre-rendered string items vertically.
/// Designed for rendering dynamic items in a non-scroll region that may be
/// re-rendered on each update. If the component's <see cref="ConsoleReactiveProps.Height"/>
/// exceeds the number of output lines, leftover lines are erased.
/// </summary>
public class TextPanel : ConsoleReactiveComponent<TextPanelProps, ConsoleReactiveState>
{
    /// <summary>
    /// Calculates the height (in lines) needed to render all items,
    /// accounting for terminal line wrapping at the specified width.
    /// </summary>
    /// <param name="items">The items to measure.</param>
    /// <param name="terminalWidth">The terminal width in columns. When 0 or negative, wrapping is ignored.</param>
    /// <returns>The total number of physical lines all items will occupy.</returns>
    public static int CalculateHeight(IReadOnlyList<string> items, int terminalWidth = 0)
    {
        int total = 0;
        for (int i = 0; i < items.Count; i++)
        {
            total += AnsiEscapes.CountPhysicalLines(items[i], terminalWidth);
        }

        return total;
    }

    /// <inheritdoc />
    public override void RenderCore(TextPanelProps props, ConsoleReactiveState state)
    {
        int currentRow = 0;

        for (int i = 0; i < props.Items.Count; i++)
        {
            string text = props.Items[i];
            string[] lines = text.Split('\n');
            int itemLineCount = AnsiEscapes.CountPhysicalLines(text, props.Width);
            int itemRow = 0;

            for (int j = 0; j < lines.Length && itemRow < itemLineCount; j++)
            {
                int linePhysicalRows = props.Width > 0
                    ? Math.Max(1, (AnsiEscapes.VisibleLength(lines[j]) - 1) / props.Width + 1)
                    : 1;

                Console.Write(AnsiEscapes.MoveAndEraseLine(props.Y + currentRow));
                Console.Write(lines[j]);

                currentRow += linePhysicalRows;
                itemRow += linePhysicalRows;
            }
        }

        // If the component height exceeds the output, erase leftover lines
        if (props.Height > currentRow)
        {
            for (int i = currentRow; i < props.Height; i++)
            {
                Console.Write(AnsiEscapes.MoveAndEraseLine(props.Y + i));
            }
        }
    }
}
