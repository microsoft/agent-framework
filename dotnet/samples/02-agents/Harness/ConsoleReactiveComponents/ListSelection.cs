// Copyright (c) Microsoft. All rights reserved.

using Harness.ConsoleReactiveFramework;

namespace Harness.ConsoleReactiveComponents;

/// <summary>
/// A component that renders a selectable list of items with a cursor indicator.
/// The selected item is indicated with a "&gt;" prefix and rendered in the highlight color.
/// Optionally includes a title above the list and a custom text input option at the bottom.
/// </summary>
public class ListSelection : ConsoleReactiveComponent<ListSelectionProps, ConsoleReactiveState>
{
    /// <summary>
    /// Calculates the height (in rows) required to render the list,
    /// including the optional title and custom text input row.
    /// </summary>
    /// <param name="props">The list selection props.</param>
    /// <returns>The number of rows needed.</returns>
    public static int CalculateHeight(ListSelectionProps props)
    {
        int height = props.Items.Count;
        if (props.CustomTextPlaceholder != null)
        {
            height++;
        }

        height += GetTitleLineCount(props.Title);
        return height;
    }

    /// <inheritdoc />
    public override void RenderCore(ListSelectionProps props, ConsoleReactiveState state)
    {
        int row = 0;

        // Render the title lines (if any)
        if (props.Title is not null)
        {
            foreach (string line in props.Title.Split('\n'))
            {
                Console.Write(AnsiEscapes.MoveCursor(this.Y + row, this.X));
                Console.Write(AnsiEscapes.EraseEntireLine);
                Console.Write(line);
                row++;
            }
        }

        // Render the list items + optional custom text row
        int totalItems = props.Items.Count + (props.CustomTextPlaceholder != null ? 1 : 0);

        for (int i = 0; i < totalItems; i++)
        {
            Console.Write(AnsiEscapes.MoveCursor(this.Y + row, this.X));
            Console.Write(AnsiEscapes.EraseEntireLine);

            bool isSelected = i == props.SelectedIndex;
            bool isCustomTextOption = props.CustomTextPlaceholder != null && i == props.Items.Count;

            // Cursor indicator
            Console.Write(isSelected ? "> " : "  ");

            if (isCustomTextOption)
            {
                this.RenderCustomTextOption(props, isSelected);
            }
            else
            {
                if (isSelected)
                {
                    Console.Write(AnsiEscapes.SetForegroundColor(props.HighlightColor));
                }

                Console.Write(props.Items[i]);

                if (isSelected)
                {
                    Console.Write(AnsiEscapes.ResetAttributes);
                }
            }

            Console.WriteLine();
            row++;
        }
    }

    /// <summary>
    /// Gets the number of lines the title occupies, or 0 if no title is set.
    /// </summary>
    private static int GetTitleLineCount(string? title) =>
        title is null ? 0 : title.Split('\n').Length;

    private void RenderCustomTextOption(ListSelectionProps props, bool isSelected)
    {
        if (props.CustomText.Length > 0)
        {
            // User has typed text — render in highlight color if selected
            if (isSelected)
            {
                Console.Write(AnsiEscapes.SetForegroundColor(props.HighlightColor));
            }

            Console.Write(props.CustomText);

            if (isSelected)
            {
                Console.Write(AnsiEscapes.ResetAttributes);
            }
        }
        else if (!string.IsNullOrWhiteSpace(props.CustomTextPlaceholder))
        {
            // No text — show placeholder in dark grey (or highlight color if selected)
            if (isSelected)
            {
                Console.Write(AnsiEscapes.SetForegroundColor(props.HighlightColor));
            }
            else
            {
                Console.Write(AnsiEscapes.SetForegroundColor(ConsoleColor.DarkGray));
            }

            Console.Write(" ");
            Console.Write(props.CustomTextPlaceholder);
            Console.Write(AnsiEscapes.ResetAttributes);
        }
    }
}

/// <summary>
/// Props for <see cref="ListSelection"/>.
/// </summary>
public record ListSelectionProps : ConsoleReactiveProps
{
    /// <summary>Gets the title text displayed above the list items. May contain newlines for multi-line titles.</summary>
    public string? Title { get; init; }

    /// <summary>Gets the items to display in the list.</summary>
    public IReadOnlyList<string> Items { get; init; } = Array.Empty<string>();

    /// <summary>Gets the zero-based index of the currently selected item.</summary>
    public int SelectedIndex { get; init; }

    /// <summary>Gets the highlight color for the active item. Defaults to <see cref="ConsoleColor.Cyan"/>.</summary>
    public ConsoleColor HighlightColor { get; init; } = ConsoleColor.Cyan;

    /// <summary>Gets the placeholder text for the custom text input option. If <c>null</c>, no custom option is shown.</summary>
    public string? CustomTextPlaceholder { get; init; }

    /// <summary>Gets the text being typed into the custom text input option.</summary>
    public string CustomText { get; init; } = "";
}
