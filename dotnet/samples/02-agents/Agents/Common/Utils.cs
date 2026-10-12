// Copyright (c) Microsoft. All rights reserved.

namespace Common;

public static class ConsoleUtils
{
    public static void Red(string text)
    {
        WriteLine(text, ConsoleColor.Red);
    }

    public static void Yellow(string text)
    {
        WriteLine(text, ConsoleColor.Yellow);
    }

    public static void Gray(string text)
    {
        WriteLine(text, ConsoleColor.DarkGray);
    }

    public static void Green(string text)
    {
        WriteLine(text, ConsoleColor.Green);
    }

    public static void WriteLine(string text, ConsoleColor color)
    {
        ConsoleColor orgColor = Console.ForegroundColor;
        try
        {
            Console.ForegroundColor = color;
            Console.WriteLine(text);
        }
        finally
        {
            Console.ForegroundColor = orgColor;
        }
    }

    public static void LineSeparator()
    {
        int width = GetConsoleWidth();
        WriteLine("".PadLeft(width > 0 ? width : 80, '-'), ConsoleColor.Gray);
    }

    public static void Separator()
    {
        Console.WriteLine();
        int width = GetConsoleWidth();
        WriteLine("".PadLeft(width > 0 ? width : 80, '-'), ConsoleColor.Gray);
        Console.WriteLine();
    }

    private static int GetConsoleWidth()
    {
        try
        {
            return Console.WindowWidth;
        }
        catch
        {
            return 80;
        }
    }

    public static void Init(string? title = null)
    {
        Console.Clear();
        Console.OutputEncoding = System.Text.Encoding.UTF8;
        if (!string.IsNullOrWhiteSpace(title))
        {
            Gray($"--- {title} ---");
        }
    }
}
