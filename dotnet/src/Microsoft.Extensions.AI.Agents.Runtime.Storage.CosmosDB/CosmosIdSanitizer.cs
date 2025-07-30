// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB;

internal static class CosmosIdSanitizer
{
    private const char EscapeChar = '~';
    public const char SeparatorChar = '_';

    private static ReadOnlySpan<char> SanitizedCharacters => new[] { '/', '\\', '?', '#', SeparatorChar, EscapeChar };
    private static ReadOnlySpan<char> ReplacementCharacters => new[] { '0', '1', '2', '3', '4', '5' };

    public static string Sanitize(string input)
    {
        int extraChars = CountSanitizedCharacters(input.AsSpan());

        if (extraChars == 0)
        {
            return input;
        }

#if NET8_0_OR_GREATER
        return string.Create(input.Length + extraChars, input, (output, state) =>
        {
            Encode(state.AsSpan(), output);
        });
#else
        var result = new char[input.Length + extraChars];
        Encode(input.AsSpan(), result);
        return new string(result, 0, input.Length + extraChars);
#endif
    }

    public static string Unsanitize(string input)
    {
        int escapeCount = CountEscapeCharacters(input.AsSpan());

        if (escapeCount == 0)
        {
            return input;
        }

#if NET8_0_OR_GREATER
        return string.Create(input.Length - escapeCount, input, (output, state) =>
        {
            Decode(state.AsSpan(), output);
        });
#else
        var result = new char[input.Length - escapeCount];
        Decode(input.AsSpan(), result);
        return new string(result, 0, input.Length - escapeCount);
#endif
    }

    private static int CountSanitizedCharacters(ReadOnlySpan<char> input)
    {
        int count = 0;
        foreach (var c in input)
        {
            if (SanitizedCharacters.IndexOf(c) >= 0)
            {
                count++;
            }
        }
        return count;
    }

    private static int CountEscapeCharacters(ReadOnlySpan<char> input)
    {
        int count = 0;
        foreach (var c in input)
        {
            if (c == EscapeChar)
            {
                count++;
            }
        }
        return count;
    }

    private static void Encode(ReadOnlySpan<char> input, Span<char> output)
    {
        int j = 0;
        foreach (var c in input)
        {
            int idx = SanitizedCharacters.IndexOf(c);
            if (idx < 0)
            {
                output[j++] = c;
            }
            else
            {
                output[j++] = EscapeChar;
                output[j++] = ReplacementCharacters[idx];
            }
        }
    }

    private static void Decode(ReadOnlySpan<char> input, Span<char> output)
    {
        int j = 0;
        bool isEscaped = false;

        foreach (var c in input)
        {
            if (isEscaped)
            {
                int idx = ReplacementCharacters.IndexOf(c);
                if (idx < 0)
                {
                    throw new ArgumentException("Input is not in a valid format: Encountered unsupported escape sequence");
                }

                output[j++] = SanitizedCharacters[idx];
                isEscaped = false;
            }
            else if (c == EscapeChar)
            {
                isEscaped = true;
            }
            else
            {
                output[j++] = c;
            }
        }
    }
}

//// Sanitizes Cosmos DB IDs by replacing characters that are not allowed.
//// This implementation was copied from dotnet/orleans and slightly modified
//// to enable targeting net472.
//// https://github.com/dotnet/orleans/blob/dd821c52d0a1123df7391461341592bd33fafbbf/src/Azure/Shared/Cosmos/CosmosIdSanitizer.cs
//internal static class CosmosIdSanitizer
//{
//    private const char EscapeChar = '~';
//    private static ReadOnlySpan<char> SanitizedCharacters => new[] { '/', '\\', '?', '#', SeparatorChar, EscapeChar };
//    private static ReadOnlySpan<char> ReplacementCharacters => new[] { '0', '1', '2', '3', '4', '5' };

//    public const char SeparatorChar = '_';

//    public static string Sanitize(string input)
//    {
//        var count = 0;
//        foreach (var c in input)
//        {
//            var charId = SanitizedCharacters.IndexOf(c);
//            if (charId >= 0)
//            {
//                ++count;
//            }
//        }

//        if (count == 0)
//        {
//            return input;
//        }

//#if NET8_0_OR_GREATER
//        return string.Create(input.Length + count, input, static (output, input) =>
//        {
//            var i = 0;
//            foreach (var c in input)
//            {
//                var charId = SanitizedCharacters.IndexOf(c);
//                if (charId < 0)
//                {
//                    output[i++] = c;
//                    continue;
//                }

//                output[i++] = EscapeChar;
//                output[i++] = ReplacementCharacters[charId];
//            }
//        });
//#else
//        var result = new char[input.Length + count];
//        var j = 0;
//        foreach (var c in input)
//        {
//            var charId = SanitizedCharacters.IndexOf(c);
//            if (charId < 0)
//            {
//                result[j++] = c;
//                continue;
//            }
//            result[j++] = EscapeChar;
//            result[j++] = ReplacementCharacters[charId];
//        }
//        return new string(result, 0, j);
//#endif
//    }

//    public static string Unsanitize(string input)
//    {
//        var count = 0;
//        foreach (var c in input)
//        {
//            if (c == EscapeChar)
//            {
//                ++count;
//            }
//        }

//        if (count == 0)
//        {
//            return input;
//        }

//#if NET8_0_OR_GREATER
//        return string.Create(input.Length - count, input, static (output, input) =>
//        {
//            var i = 0;
//            var isEscaped = false;
//            foreach (var c in input)
//            {
//                if (isEscaped)
//                {
//                    var charId = ReplacementCharacters.IndexOf(c);
//                    if (charId < 0)
//                    {
//                        throw new ArgumentException("Input is not in a valid format: Encountered unsupported escape sequence");
//                    }

//                    output[i++] = SanitizedCharacters[charId];
//                    isEscaped = false;
//                }
//                else if (c == EscapeChar)
//                {
//                    isEscaped = true;
//                }
//                else
//                {
//                    output[i++] = c;
//                }
//            }
//        });
//#else
//        var result = new char[input.Length - count];
//        var j = 0;
//        var isEscaped = false;
//        foreach (var c in input)
//        {
//            if (isEscaped)
//            {
//                var charId = ReplacementCharacters.IndexOf(c);
//                if (charId < 0)
//                {
//                    throw new ArgumentException("Input is not in a valid format: Encountered unsupported escape sequence");
//                }
//                result[j++] = SanitizedCharacters[charId];
//                isEscaped = false;
//            }
//            else if (c == EscapeChar)
//            {
//                isEscaped = true;
//            }
//            else
//            {
//                result[j++] = c;
//            }
//        }
//        return new string(result, 0, j);
//#endif
//    }
//}
