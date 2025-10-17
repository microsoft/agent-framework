// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Reflection;
using Microsoft.Shared.Diagnostics;
using OpenAI.Chat;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Utils;

[System.Diagnostics.CodeAnalysis.SuppressMessage("Performance", "CA1810:Initialize reference type static fields inline", Justification = "Specifically for accessing hidden members")]
[System.Diagnostics.CodeAnalysis.SuppressMessage("Design", "CA1065:Do not raise exceptions in unexpected locations", Justification = "Specifically for accessing hidden members")]
internal static class ChatCompletionsOptionsExtensions
{
    private static readonly Func<ChatCompletionOptions, bool?> s_getStreamNullable;
    private static readonly Func<ChatCompletionOptions, IList<ChatMessage>> s_getMessages;

    static ChatCompletionsOptionsExtensions()
    {
        // OpenAI SDK does not have a simple way to get the input as a c# object.
        // However, it does parse most of the interesting fields into internal properties of `ChatCompletionsOptions` object.

        // --- Stream (internal bool? Stream { get; set; }) ---
        const string StreamPropName = "Stream";
        var streamProp = typeof(ChatCompletionOptions).GetProperty(StreamPropName, BindingFlags.Instance | BindingFlags.NonPublic)
            ?? throw new MissingMemberException(typeof(ChatCompletionOptions).FullName!, StreamPropName);
        var streamGetter = streamProp.GetGetMethod(nonPublic: true) ?? throw new MissingMethodException($"{StreamPropName} getter not found.");

        s_getStreamNullable = streamGetter.CreateDelegate<Func<ChatCompletionOptions, bool?>>();

        // --- Messages (internal IList<OpenAI.Chat.ChatMessage> Messages { get; set; }) ---
        const string InputPropName = "Messages";
        var inputProp = typeof(ChatCompletionOptions).GetProperty(InputPropName, BindingFlags.Instance | BindingFlags.NonPublic)
            ?? throw new MissingMemberException(typeof(ChatCompletionOptions).FullName!, InputPropName);
        var inputGetter = inputProp.GetGetMethod(nonPublic: true)
            ?? throw new MissingMethodException($"{InputPropName} getter not found.");

        s_getMessages = inputGetter.CreateDelegate<Func<ChatCompletionOptions, IList<ChatMessage>>>();
    }

    public static IList<ChatMessage> GetMessages(this ChatCompletionOptions options)
    {
        Throw.IfNull(options);
        return s_getMessages(options);
    }

    public static bool GetStream(this ChatCompletionOptions options)
    {
        Throw.IfNull(options);
        return s_getStreamNullable(options) ?? false;
    }
}
