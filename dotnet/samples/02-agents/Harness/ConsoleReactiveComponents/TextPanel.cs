// Copyright (c) Microsoft. All rights reserved.

using Harness.ConsoleReactiveFramework;

namespace Harness.ConsoleReactiveComponents;

/// <summary>
/// Props for <see cref="TextPanel"/>.
/// </summary>
public record TextPanelProps : ConsoleReactiveProps
{
    /// <summary>Gets the items to render in the panel.</summary>
    public IReadOnlyList<object> Items { get; init; } = [];
}

/// <summary>
/// A component that renders a list of items vertically using a custom render delegate.
/// Designed for rendering dynamic items in a non-scroll region that may be
/// re-rendered on each update. If the component's <see cref="ConsoleReactiveComponent.Height"/>
/// exceeds the number of output lines, leftover lines are erased.
/// </summary>
public class TextPanel : ConsoleReactiveComponent<TextPanelProps, ConsoleReactiveState>
{
    private readonly Func<object, string> _renderItem;

    /// <summary>
    /// Initializes a new instance of the <see cref="TextPanel"/> class.
    /// </summary>
    /// <param name="renderItem">A delegate that renders an item and returns the text to display (may contain newlines).</param>
    public TextPanel(Func<object, string> renderItem)
    {
        this._renderItem = renderItem;
    }

    /// <summary>
    /// Calculates the height (in lines) needed to render all items.
    /// </summary>
    /// <param name="items">The items to measure.</param>
    /// <param name="renderItem">The render delegate to use for measuring.</param>
    /// <returns>The total number of lines all items will occupy.</returns>
    public static int CalculateHeight(IReadOnlyList<object> items, Func<object, string> renderItem)
    {
        int total = 0;
        for (int i = 0; i < items.Count; i++)
        {
            string text = renderItem(items[i]);
            total += CountLines(text);
        }

        return total;
    }

    /// <inheritdoc />
    public override void RenderCore(TextPanelProps props, ConsoleReactiveState state)
    {
        int currentRow = 0;

        for (int i = 0; i < props.Items.Count; i++)
        {
            string text = this._renderItem(props.Items[i]);
            string[] lines = text.Split('\n');
            int lineCount = CountLines(text);

            for (int j = 0; j < lineCount; j++)
            {
                Console.Write(AnsiEscapes.MoveAndEraseLine(this.Y + currentRow));
                Console.Write(lines[j]);
                currentRow++;
            }
        }

        // If the component height exceeds the output, erase leftover lines
        if (this.Height > currentRow)
        {
            for (int i = currentRow; i < this.Height; i++)
            {
                Console.Write(AnsiEscapes.MoveAndEraseLine(this.Y + i));
            }
        }
    }

    private static int CountLines(string text)
    {
        if (string.IsNullOrEmpty(text))
        {
            return 0;
        }

        int count = 1;
        for (int i = 0; i < text.Length; i++)
        {
            if (text[i] == '\n')
            {
                count++;
            }
        }

        // If text ends with a newline, don't count the trailing empty line
        if (text[text.Length - 1] == '\n')
        {
            count--;
        }

        return count;
    }
}
