// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.CodeAnalysis;

namespace Microsoft.Agents.AI.Workflows.Generators.UnitTests;

internal static class SyntaxTreeAssert
{
    public static void AddHandler(SyntaxTree syntaxTree, string handlerName)
    {
        string syntaxString = syntaxTree.ToString();
        string expectedRegistration = $".AddHandler({handlerName})";

        Assert.Contains(expectedRegistration, syntaxString);
    }

    public static void AddHandler(SyntaxTree syntaxTree, string handlerName, string inTypeParam)
    {
        string syntaxString = syntaxTree.ToString();
        string expectedRegistration = $".AddHandler<{inTypeParam}>({handlerName})";

        Assert.Contains(expectedRegistration, syntaxString);
    }

    public static void AddHandler(SyntaxTree syntaxTree, string handlerName, string inTypeParam, string outTypeParam)
    {
        string syntaxString = syntaxTree.ToString();
        string expectedRegistration = $".AddHandler<{inTypeParam},{outTypeParam}>({handlerName})";

        Assert.Contains(expectedRegistration, syntaxString);
    }

    public static void AddHandler<TIn>(SyntaxTree syntaxTree, string handlerName, bool globalQualified = false)
    {
        Type inType = typeof(TIn);
        string inTypeParam = globalQualified ? $"global::{inType.FullName}" : inType.Name;
        AddHandler(syntaxTree, handlerName, inTypeParam);
    }

    public static void AddHandler<TIn, TOut>(SyntaxTree syntaxTree, string handlerName, bool globalQualified = false)
    {
        Type inType = typeof(TIn), outType = typeof(TOut);
        string inTypeParam = globalQualified ? $"global::{inType.FullName}" : inType.Name;
        string outTypeParam = globalQualified ? $"global::{outType.FullName}" : outType.Name;
        AddHandler(syntaxTree, handlerName, inTypeParam, outTypeParam);
    }

    public static void HaveNoHandlers(SyntaxTree syntaxTree)
    {
        Assert.DoesNotContain(".AddHandler(", syntaxTree.ToString());
    }

    public static void RegisterSentMessageType(SyntaxTree syntaxTree, string messageTypeParam)
    {
        string syntaxString = syntaxTree.ToString();
        string expectedRegistration = $".SendsMessage<{messageTypeParam}>()";

        Assert.Contains(expectedRegistration, syntaxString);
    }

    public static void RegisterSentMessageType<TMessage>(SyntaxTree syntaxTree, bool globalQualified = true)
    {
        Type messageType = typeof(TMessage);
        string messageTypeParam = globalQualified ? $"global::{messageType.FullName}" : messageType.Name;
        RegisterSentMessageType(syntaxTree, messageTypeParam);
    }

    public static void NotRegisterSentMessageTypes(SyntaxTree syntaxTree)
    {
        Assert.DoesNotContain(".SendsMessage<", syntaxTree.ToString());
    }

    public static void RegisterYieldedOutputType(SyntaxTree syntaxTree, string outputTypeParam)
    {
        string syntaxString = syntaxTree.ToString();
        string expectedRegistration = $".YieldsOutput<{outputTypeParam}>()";

        Assert.Contains(expectedRegistration, syntaxString);
    }

    public static void RegisterYieldedOutputType<TOutput>(SyntaxTree syntaxTree, bool globalQualified = true)
    {
        Type outputType = typeof(TOutput);
        string outputTypeParam = globalQualified ? $"global::{outputType.FullName}" : outputType.Name;
        RegisterYieldedOutputType(syntaxTree, outputTypeParam);
    }

    public static void NotRegisterYieldedOutputTypes(SyntaxTree syntaxTree)
    {
        Assert.DoesNotContain(".YieldsOutput<", syntaxTree.ToString());
    }

    private static void ContainPartialDeclaration(int level, int index, string className)
    {
        Assert.True(index > 0, $"Expected to contain \"partial class {className}\" at nesting level {level}.");
    }

    private static void DeclarePartialsInCorrectOrder(int prevIndex, int currIndex, string prevClass, string currClass)
    {
        Assert.True(prevIndex < currIndex, $"Expected \"partial class {prevClass}\" before \"partial class {currClass}\".");
    }

    public static void HaveHierarchy(SyntaxTree syntaxTree, params string[] expectedNesting)
    {
        if (expectedNesting.Length == 0)
        {
            return;
        }

        string syntaxString = syntaxTree.ToString();
        int[] indicies = new int[expectedNesting.Length];

        for (int i = 0; i < expectedNesting.Length; i++)
        {
            indicies[i] = syntaxString.IndexOf($"partial class {expectedNesting[i]}", StringComparison.Ordinal);
        }

        // Verify partial declarations are present
        ContainPartialDeclaration(0, indicies[0], expectedNesting[0]);
        for (int i = 1; i < expectedNesting.Length; i++)
        {
            ContainPartialDeclaration(i, indicies[i], expectedNesting[i]);
            DeclarePartialsInCorrectOrder(indicies[i - 1], indicies[i], expectedNesting[i - 1], expectedNesting[i]);
        }
    }

    public static void HaveNamespace(SyntaxTree syntaxTree)
    {
        Assert.Contains("namespace ", syntaxTree.ToString());
    }

    public static void NotHaveNamespace(SyntaxTree syntaxTree)
    {
        Assert.DoesNotContain("namespace ", syntaxTree.ToString());
    }
}
