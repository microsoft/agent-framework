// Copyright (c) Microsoft. All rights reserved.

#if NET
using System;
#endif
using System.Collections.Generic;
using System.Linq;
#if NET
using System.Runtime.CompilerServices;
#else
using System.Text;
#endif

namespace Microsoft.Extensions.AI;

/// <summary>Internal extensions for working with <see cref="AIContent"/>.</summary>
internal static class AIContentExtensions
{
    /// <summary>Concatenates the text of all <see cref="TextContent"/> instances in the list.</summary>
    public static string ConcatText(this IEnumerable<AIContent> contents)
    {
        if (contents is IList<AIContent> list)
        {
            int count = list.Count;
            switch (count)
            {
                case 0:
                    return string.Empty;

                case 1:
                    return (list[0] as TextContent)?.Text ?? string.Empty;

                default:
#if NET
                    DefaultInterpolatedStringHandler builder = new(count, 0, null, stackalloc char[512]);
                    for (int i = 0; i < count; i++)
                    {
                        if (list[i] is TextContent text)
                        {
                            builder.AppendLiteral(text.Text);
                        }
                    }

                    return builder.ToStringAndClear();
#else
                    StringBuilder builder = new();
                    for (int i = 0; i < count; i++)
                    {
                        if (list[i] is TextContent text)
                        {
                            builder.Append(text.Text);
                        }
                    }

                    return builder.ToString();
#endif
            }
        }

        return string.Concat(contents.OfType<TextContent>());
    }

    /// <summary>Concatenates the <see cref="ChatMessage.Text"/> of all <see cref="ChatMessage"/> instances in the list.</summary>
    /// <remarks>A newline separator is added between each non-empty piece of text.</remarks>
    public static string ConcatText(this IList<ChatMessage> messages)
    {
        int count = messages.Count;
        switch (count)
        {
            case 0:
                return string.Empty;

            case 1:
                return messages[0].Text;

            default:
#if NET
                DefaultInterpolatedStringHandler builder = new(count, 0, null, stackalloc char[512]);
                bool needsSeparator = false;
                for (int i = 0; i < count; i++)
                {
                    string text = messages[i].Text;
                    if (text.Length > 0)
                    {
                        if (needsSeparator)
                        {
                            builder.AppendLiteral(Environment.NewLine);
                        }

                        builder.AppendLiteral(text);

                        needsSeparator = true;
                    }
                }

                return builder.ToStringAndClear();
#else
                StringBuilder builder = new();
                for (int i = 0; i < count; i++)
                {
                    string text = messages[i].Text;
                    if (text.Length > 0)
                    {
                        if (builder.Length > 0)
                        {
                            builder.AppendLine();
                        }

                        builder.Append(text);
                    }
                }

                return builder.ToString();
#endif
        }
    }
}
