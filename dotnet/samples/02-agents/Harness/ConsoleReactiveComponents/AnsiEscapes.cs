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
