// Copyright (c) Microsoft. All rights reserved.

namespace Harness.ConsoleReactiveComponents;

/// <summary>
/// Provides descriptive helpers for common ANSI/VT100 escape sequences used
/// in the split-console layout (DECSTBM scroll regions, cursor movement, line erasure).
/// </summary>
public static class AnsiEscapes
{
    /// <summary>
    /// Sets the scrollable region to rows 1 through <paramref name="bottom"/> (DECSTBM).
    /// Content outside this region will not scroll.
    /// </summary>
    public static string SetScrollRegion(int bottom) => $"\x1b[1;{bottom}r";

    /// <summary>
    /// Resets the scroll region to the full terminal height (DECSTBM reset).
    /// </summary>
    public static string ResetScrollRegion => "\x1b[r";

    /// <summary>
    /// Moves the cursor to the specified 1-based <paramref name="row"/> and <paramref name="column"/> (CUP).
    /// </summary>
    public static string MoveCursor(int row, int column) => $"\x1b[{row};{column}H";

    /// <summary>
    /// Erases the current line from the cursor position to the end of the line (EL 0).
    /// </summary>
    public static string EraseToEndOfLine => "\x1b[0K";

    /// <summary>
    /// Erases the entire current line (EL 2).
    /// </summary>
    public static string EraseEntireLine => "\x1b[2K";

    /// <summary>
    /// Erases the entire screen.
    /// </summary>
    public static string EraseEntireScreen => "\x1b[2J";

    /// <summary>
    /// Erases the scrollback buffer (ESC[3J). Use alongside <see cref="EraseEntireScreen"/>
    /// to fully clear both the visible screen and the scroll history.
    /// </summary>
    public static string EraseScrollbackBuffer => "\x1b[3J";

    /// <summary>
    /// Saves the current cursor position (DECSC / SCP).
    /// Note: most terminals have a single save slot — nested saves are not supported.
    /// </summary>
    public static string SaveCursor => "\x1b[s";

    /// <summary>
    /// Restores the previously saved cursor position (DECRC / RCP).
    /// </summary>
    public static string RestoreCursor => "\x1b[u";

    /// <summary>
    /// Moves the cursor to the specified 1-based <paramref name="row"/> at column 1, then erases the entire line.
    /// Convenience combination of <see cref="MoveCursor"/> and <see cref="EraseEntireLine"/>.
    /// </summary>
    public static string MoveAndEraseLine(int row) => $"\x1b[{row};1H\x1b[2K";

    /// <summary>
    /// Sets the foreground text color using a <see cref="ConsoleColor"/> value.
    /// </summary>
    public static string SetForegroundColor(ConsoleColor color) => $"\x1b[{ConsoleColorToAnsi(color)}m";

    /// <summary>
    /// Resets all text attributes (color, bold, etc.) to their defaults.
    /// </summary>
    public static string ResetAttributes => "\x1b[0m";

    /// <summary>
    /// Returns the visible (printed) length of a string after stripping ANSI escape sequences.
    /// Escape sequences are zero-width on screen but occupy characters in the raw string.
    /// </summary>
    /// <remarks>
    /// This counts UTF-16 code units (chars) rather than terminal display cells. Emoji,
    /// combining characters, variation selectors, and East Asian wide characters may be
    /// measured incorrectly. For the console harness this is acceptable since content is
    /// predominantly ASCII, and emoji are padded with surrounding spaces.
    /// </remarks>
    public static int VisibleLength(string text)
    {
        if (string.IsNullOrEmpty(text))
        {
            return 0;
        }

        int length = 0;
        for (int i = 0; i < text.Length; i++)
        {
            if (text[i] == '\x1b' && i + 1 < text.Length && text[i + 1] == '[')
            {
                // Skip the ESC[ and all characters up to and including the final byte (0x40–0x7E).
                i += 2;
                while (i < text.Length && text[i] < 0x40)
                {
                    i++;
                }

                // i now points to the final byte of the escape sequence; the for-loop will advance past it.
            }
            else if (text[i] != '\n' && text[i] != '\r')
            {
                length++;
            }
        }

        return length;
    }

    /// <summary>
    /// Counts the number of physical terminal rows a text item will occupy,
    /// accounting for both explicit newlines and terminal line wrapping.
    /// </summary>
    /// <param name="text">The text to measure.</param>
    /// <param name="terminalWidth">The terminal width in columns. If &lt;= 0, wrapping is ignored (1 row per logical line).</param>
    /// <returns>The number of physical rows the text occupies.</returns>
    public static int CountPhysicalLines(string text, int terminalWidth)
    {
        if (string.IsNullOrEmpty(text))
        {
            return 0;
        }

        int physicalLines = 0;
        int lineStart = 0;

        for (int i = 0; i <= text.Length; i++)
        {
            if (i == text.Length || text[i] == '\n')
            {
                if (terminalWidth <= 0)
                {
                    // No wrapping — each logical line is one physical row
                    physicalLines += 1;
                }
                else
                {
                    string logicalLine = text[lineStart..i];
                    int visibleWidth = VisibleLength(logicalLine);

                    physicalLines += visibleWidth == 0
                        ? 1
                        : (visibleWidth - 1) / terminalWidth + 1;
                }

                lineStart = i + 1;
            }
        }

        // If text ends with a newline, don't count the trailing empty line
        if (text[text.Length - 1] == '\n')
        {
            physicalLines--;
        }

        return physicalLines;
    }

    private static int ConsoleColorToAnsi(ConsoleColor color) => color switch
    {
        ConsoleColor.Black => 30,
        ConsoleColor.DarkRed => 31,
        ConsoleColor.DarkGreen => 32,
        ConsoleColor.DarkYellow => 33,
        ConsoleColor.DarkBlue => 34,
        ConsoleColor.DarkMagenta => 35,
        ConsoleColor.DarkCyan => 36,
        ConsoleColor.Gray => 37,
        ConsoleColor.DarkGray => 90,
        ConsoleColor.Red => 91,
        ConsoleColor.Green => 92,
        ConsoleColor.Yellow => 93,
        ConsoleColor.Blue => 94,
        ConsoleColor.Magenta => 95,
        ConsoleColor.Cyan => 96,
        ConsoleColor.White => 97,
        _ => 37
    };
}
