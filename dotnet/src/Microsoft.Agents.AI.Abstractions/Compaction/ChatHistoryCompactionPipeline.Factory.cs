// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Compaction;

public partial class ChatHistoryCompactionPipeline
{
    /// <summary>
    /// %%% COMMENT
    /// </summary>
    public enum Size
    {
        /// <summary>
        /// %%% COMMENT
        /// </summary>
        Compact,
        /// <summary>
        /// %%% COMMENT
        /// </summary>
        Adequate,
        /// <summary>
        /// %%% COMMENT
        /// </summary>
        Accomodating,
    }

    /// <summary>
    /// %%% COMMENT
    /// </summary>
    public enum Approach
    {
        /// <summary>
        /// %%% COMMENT
        /// </summary>
        Aggressive,
        /// <summary>
        /// %%% COMMENT
        /// </summary>
        Balanced,
        /// <summary>
        /// %%% COMMENT
        /// </summary>
        Gentle,
    }

    /// <summary>
    /// %%% COMMENT
    /// </summary>
    /// <param name="approach"></param>
    /// <param name="size"></param>
    /// <param name="chatClient"></param>
    /// <returns></returns>
    /// <exception cref="NotImplementedException"></exception>
    public static ChatHistoryCompactionPipeline Create(Approach approach, Size size, IChatClient chatClient) =>
        approach switch
        {
            Approach.Aggressive => CreateAgressive(size, chatClient),
            Approach.Balanced => CreateBalanced(size),
            Approach.Gentle => CreateGentle(size),
            _ => throw new NotImplementedException(), // %%% EXCEPTION
        };

    private static ChatHistoryCompactionPipeline CreateAgressive(Size size, IChatClient chatClient) =>
        new(// 1. Gentle: collapse old tool-call groups into short summaries like "[Tool calls: LookupPrice]"
            new ToolResultCompactionStrategy(MaxTokens(size), preserveRecentGroups: 2),
            // 2. Moderate: use an LLM to summarize older conversation spans into a concise message
            new SummarizationCompactionStrategy(chatClient, MaxTokens(size), preserveRecentGroups: 2),
            // 3. Aggressive: keep only the last N user turns and their responses
            new SlidingWindowCompactionStrategy(MaxTurns(size)),
            // 4. Emergency: drop oldest groups until under the token budget
            new TruncationCompactionStrategy(MaxTokens(size), preserveRecentGroups: 1));

    private static ChatHistoryCompactionPipeline CreateBalanced(Size size) =>
        new(// 1. Gentle: collapse old tool-call groups into short summaries like "[Tool calls: LookupPrice]"
            new ToolResultCompactionStrategy(MaxTokens(size), preserveRecentGroups: 2),
            // 2. Aggressive: keep only the last N user turns and their responses
            new SlidingWindowCompactionStrategy(MaxTurns(size)));

    private static ChatHistoryCompactionPipeline CreateGentle(Size size) =>
        new(// 1. Gentle: collapse old tool-call groups into short summaries like "[Tool calls: LookupPrice]"
            new ToolResultCompactionStrategy(MaxTokens(size), preserveRecentGroups: 2));

    private static int MaxTokens(Size size) =>
        size switch
        {
            Size.Compact => 500,
            Size.Adequate => 1000,
            Size.Accomodating => 2000,
            _ => throw new NotImplementedException(), // %%% EXCEPTION
        };

    private static int MaxTurns(Size size) =>
        size switch
        {
            Size.Compact => 10,
            Size.Adequate => 50,
            Size.Accomodating => 100,
            _ => throw new NotImplementedException(), // %%% EXCEPTION
        };
}
