// Copyright (c) Microsoft. All rights reserved.

using Harness.ConsoleReactiveFramework;

namespace Harness.ConsoleReactiveComponents;

/// <summary>
/// Props for <see cref="TopBottomRule"/>.
/// </summary>
public record TopBottomRuleProps : ConsoleReactiveProps
{
    /// <summary>Gets the width of the horizontal rules in characters.</summary>
    public int Width { get; init; }

    /// <summary>Gets the foreground color of the horizontal rules. If <c>null</c>, the default terminal color is used.</summary>
    public ConsoleColor? Color { get; init; }
}

/// <summary>
/// A component that renders a top and bottom horizontal rule (─) with children
/// stacked vertically between them.
/// </summary>
public class TopBottomRule : ConsoleReactiveComponent<TopBottomRuleProps, ConsoleReactiveState>
{
    /// <summary>
    /// Calculates the total height including the top rule, children, and bottom rule.
    /// </summary>
    /// <param name="props">The component props containing children.</param>
    /// <returns>2 (for the rules) plus the sum of all children heights.</returns>
    public static int CalculateHeight(TopBottomRuleProps props)
    {
        int childrenHeight = 0;
        foreach (var child in props.Children)
        {
            childrenHeight += child.Height;
        }

        // Top rule + children + bottom rule
        return 2 + childrenHeight;
    }

    /// <inheritdoc />
    public override void RenderCore(TopBottomRuleProps props, ConsoleReactiveState state)
    {
        int ruleWidth = props.Width;
        string rule = new('─', ruleWidth);

        if (props.Color.HasValue)
        {
            Console.Write(AnsiEscapes.SetForegroundColor(props.Color.Value));
        }

        // Top rule
        Console.Write(AnsiEscapes.MoveCursor(this.Y, this.X));
        Console.Write(rule);

        // Render children stacked below the top rule
        int currentY = this.Y + 1;

        if (props.Color.HasValue)
        {
            Console.Write(AnsiEscapes.ResetAttributes);
        }

        foreach (var child in props.Children)
        {
            child.X = this.X;
            child.Y = currentY;
            child.Render();
            currentY += child.Height;
        }

        if (props.Color.HasValue)
        {
            Console.Write(AnsiEscapes.SetForegroundColor(props.Color.Value));
        }

        // Bottom rule
        Console.Write(AnsiEscapes.MoveCursor(currentY, this.X));
        Console.Write(rule);

        if (props.Color.HasValue)
        {
            Console.Write(AnsiEscapes.ResetAttributes);
        }
    }
}
