// Copyright (c) Microsoft. All rights reserved.

using Harness.ConsoleReactiveFramework;

namespace Harness.ConsoleReactiveComponents;

/// <summary>
/// Props for <see cref="TextInput"/>.
/// </summary>
public record TextInputProps : ConsoleReactiveProps
{
    /// <summary>Gets the prompt string displayed on the left (e.g. "&gt; " or "user &gt; ").</summary>
    public string Prompt { get; init; } = "> ";

    /// <summary>Gets the text content to render to the right of the prompt.</summary>
    public string Text { get; init; } = "";

    /// <summary>Gets the placeholder text shown in dark grey when <see cref="Text"/> is empty.</summary>
    public string Placeholder { get; init; } = "";
}

/// <summary>
/// A component that renders a prompt with text input. Supports multi-line text
/// where continuation lines are indented to align with the text start position
/// (i.e. the column after the prompt).
/// </summary>
public class TextInput : ConsoleReactiveComponent<TextInputProps, ConsoleReactiveState>
{
    /// <summary>
    /// Calculates the height (in rows) required to render the prompt and text
    /// given the available width.
    /// </summary>
    /// <param name="props">The text input props.</param>
    /// <param name="availableWidth">The total available width in columns.</param>
    /// <returns>The number of rows needed.</returns>
    public static int CalculateHeight(TextInputProps props, int availableWidth)
    {
        int promptLength = props.Prompt.Length;
        int textWidth = availableWidth - promptLength;

        if (textWidth <= 0 || props.Text.Length == 0)
        {
            return 1;
        }

        int lines = 1;
        int remaining = props.Text.Length - textWidth;
        while (remaining > 0)
        {
            lines++;
            remaining -= textWidth;
        }

        return lines;
    }

    /// <inheritdoc />
    public override void RenderCore(TextInputProps props, ConsoleReactiveState state)
    {
        int promptLength = props.Prompt.Length;
        int textWidth = this.Width - promptLength;
        string indent = new(' ', promptLength);

        // First line: prompt + start of text
        Console.Write(AnsiEscapes.MoveCursor(this.Y, this.X));
        Console.Write(AnsiEscapes.EraseEntireLine);
        Console.Write(props.Prompt);

        if (textWidth <= 0 || props.Text.Length == 0)
        {
            // Show placeholder if text is empty
            if (props.Text.Length == 0 && props.Placeholder.Length > 0 && textWidth > 0)
            {
                Console.Write(AnsiEscapes.SetForegroundColor(ConsoleColor.DarkGray));
                Console.Write(" ");
                Console.Write(props.Placeholder[..Math.Min(props.Placeholder.Length, textWidth - 1)]);
                Console.Write(AnsiEscapes.ResetAttributes);
            }

            return;
        }

        int offset = 0;
        int firstChunk = Math.Min(textWidth, props.Text.Length);
        Console.Write(props.Text[offset..firstChunk]);
        offset = firstChunk;

        // Continuation lines: indented to align with text start
        int row = 1;
        while (offset < props.Text.Length)
        {
            int chunk = Math.Min(textWidth, props.Text.Length - offset);
            Console.Write(AnsiEscapes.MoveCursor(this.Y + row, this.X));
            Console.Write(AnsiEscapes.EraseEntireLine);
            Console.Write(indent);
            Console.Write(props.Text[offset..(offset + chunk)]);
            offset += chunk;
            row++;
        }
    }
}
