// Copyright (c) Microsoft. All rights reserved.

using System;
using FluentAssertions;
using FluentAssertions.Execution;
using FluentAssertions.Primitives;
using Microsoft.CodeAnalysis;

namespace Microsoft.Agents.AI.Workflows.Generators.UnitTests;

internal sealed class SyntaxTreeAssertions : ObjectAssertions<SyntaxTree, SyntaxTreeAssertions>
{
    private readonly string _syntaxString;

    public SyntaxTreeAssertions(SyntaxTree instance, AssertionChain assertionChain) : base(instance, assertionChain)
    {
        this._syntaxString = instance.ToString();
    }

    public AndConstraint<SyntaxTreeAssertions> AddHandler(string handlerName)
    {
        string expectedRegistration = $".AddHandler({handlerName})";

        this.CurrentAssertionChain
            .ForCondition(this._syntaxString.Contains(expectedRegistration))
            .BecauseOf($"expected handler {handlerName} to be registered")
            .FailWith("Expected {context} to contain handler registration {0}{reason}, but it was not found. Actual syntax: {1}",
                expectedRegistration, this._syntaxString);

        return new(this);
    }

    public AndConstraint<SyntaxTreeAssertions> AddHandler(string handlerName, string inTypeParam)
    {
        string expectedRegistration = $".AddHandler<{inTypeParam}>({handlerName})";

        this.CurrentAssertionChain
            .ForCondition(this._syntaxString.Contains(expectedRegistration))
            .BecauseOf($"expected handler {handlerName} to be registered")
            .FailWith("Expected {context} to contain handler registration {0}{reason}, but it was not found. Actual syntax: {1}",
                expectedRegistration, this._syntaxString);

        return new(this);
    }

    public AndConstraint<SyntaxTreeAssertions> AddHandler(string handlerName, string inTypeParam, string outTypeParam)
    {
        string expectedRegistration = $".AddHandler<{inTypeParam},{outTypeParam}>({handlerName})";

        this.CurrentAssertionChain
            .ForCondition(this._syntaxString.Contains(expectedRegistration))
            .BecauseOf($"expected handler {handlerName} to be registered")
            .FailWith("Expected {context} to contain handler registration {0}{reason}, but it was not found. Actual syntax: {1}",
                expectedRegistration, this._syntaxString);

        return new(this);
    }

    public AndConstraint<SyntaxTreeAssertions> AddHandler<TIn>(string handlerName, bool globalQualified = false)
    {
        Type inType = typeof(TIn);
        string inTypeParam = globalQualified ? $"global::{inType.FullName}" : inType.Name;
        return this.AddHandler(handlerName, inTypeParam);
    }

    public AndConstraint<SyntaxTreeAssertions> AddHandler<TIn, TOut>(string handlerName, bool globalQualified = false)
    {
        Type inType = typeof(TIn), outType = typeof(TOut);
        string inTypeParam = globalQualified ? $"global::{inType.FullName}" : inType.Name;
        string outTypeParam = globalQualified ? $"global::{outType.FullName}" : outType.Name;
        return this.AddHandler(handlerName, inTypeParam, outTypeParam);
    }

    public AndConstraint<SyntaxTreeAssertions> HaveNoHandlers()
    {
        this.CurrentAssertionChain
            .ForCondition(!this._syntaxString.Contains(".AddHandler("))
            .BecauseOf("expected no handlers to be registered")
            .FailWith("Expected {context} to have no handler registrations{reason}, but found at least one. Actual syntax: {1}",
                this._syntaxString);

        return new(this);
    }

    public AndConstraint<SyntaxTreeAssertions> RegisterSentMessageType(string messageTypeParam)
    {
        string expectedRegistration = $".SendsMessage<{messageTypeParam}>()";

        this.CurrentAssertionChain
            .ForCondition(this._syntaxString.Contains(expectedRegistration))
            .BecauseOf($"expected message type {messageTypeParam} to be registered")
            .FailWith("Expected {context} to contain message type registration {0}{reason}, but it was not found. Actual syntax: {1}",
                expectedRegistration, this._syntaxString);

        return new(this);
    }

    public AndConstraint<SyntaxTreeAssertions> RegisterSentMessageType<TMessage>(bool globalQualified = true)
    {
        Type messageType = typeof(TMessage);
        string messageTypeParam = globalQualified ? $"global::{messageType.FullName}" : messageType.Name;
        return this.RegisterSentMessageType(messageTypeParam);
    }

    public AndConstraint<SyntaxTreeAssertions> NotRegisterSentMessageTypes()
    {
        this.CurrentAssertionChain
            .ForCondition(!this._syntaxString.Contains(".SendsMessage<"))
            .BecauseOf("expected no message types to be registered")
            .FailWith("Expected {context} to have no message type registrations{reason}, but found at least one. Actual syntax: {1}",
                this._syntaxString);

        return new(this);
    }

    public AndConstraint<SyntaxTreeAssertions> RegisterYieldedOutputType(string outputTypeParam)
    {
        string expectedRegistration = $".YieldsOutput<{outputTypeParam}>()";

        this.CurrentAssertionChain
            .ForCondition(this._syntaxString.Contains(expectedRegistration))
            .BecauseOf($"expected output type {outputTypeParam} to be registered")
            .FailWith("Expected {context} to contain output type registration {0}{reason}, but it was not found. Actual syntax: {1}",
                expectedRegistration, this._syntaxString);

        return new(this);
    }

    public AndConstraint<SyntaxTreeAssertions> RegisterYieldedOutputType<TOutput>(bool globalQualified = true)
    {
        Type outputType = typeof(TOutput);
        string outputTypeParam = globalQualified ? $"global::{outputType.FullName}" : outputType.Name;
        return this.RegisterYieldedOutputType(outputTypeParam);
    }

    public AndConstraint<SyntaxTreeAssertions> NotRegisterYieldedOutputTypes()
    {
        this.CurrentAssertionChain
            .ForCondition(!this._syntaxString.Contains(".YieldsOutput<"))
            .BecauseOf("expected no output types to be registered")
            .FailWith("Expected {context} to have no output type registrations{reason}, but found at least one. Actual syntax: {1}",
                this._syntaxString);

        return new(this);
    }

    private AndConstraint<SyntaxTreeAssertions> ContainPartialDeclaration(int level, int index, string className)
    {
        this.CurrentAssertionChain
            .ForCondition(index > 0)
            .BecauseOf($"expected \"partial class {className}\" at nesting level {level}")
            .FailWith("Expected {context} to contain \"partial class {0}\" at nesting level {1}{reason}, but it was not found. Actual syntax: {2}",
                className, level, this._syntaxString);

        return new(this);
    }

    private AndConstraint<SyntaxTreeAssertions> DeclarePartialsInCorrectOrder(int prevIndex, int currIndex, string prevClass, string currClass)
    {
        this.CurrentAssertionChain
            .ForCondition(prevIndex < currIndex)
            .BecauseOf($"expected \"partial class {prevClass}\" before \"partial class {currClass}\"")
            .FailWith("Expected {context} to have \"partial class {0}\" before \"partial class {1}\"{reason}, but the order was incorrect. Actual syntax: {2}",
                prevClass, currClass, this._syntaxString);

        return new(this);
    }

    public AndConstraint<SyntaxTreeAssertions> HaveHierarchy(params string[] expectedNesting)
    {
        if (expectedNesting.Length == 0)
        {
            return new AndConstraint<SyntaxTreeAssertions>(this);
        }

        int[] indicies = new int[expectedNesting.Length];

        for (int i = 0; i < expectedNesting.Length; i++)
        {
            indicies[i] = this._syntaxString.IndexOf($"partial class {expectedNesting[i]}", StringComparison.Ordinal);
        }

        // Verify partial declarations are present
        AndConstraint<SyntaxTreeAssertions> runningResult = this.ContainPartialDeclaration(0, indicies[0], expectedNesting[0]);
        for (int i = 1; i < expectedNesting.Length; i++)
        {
            runningResult = runningResult.And.ContainPartialDeclaration(i, indicies[i], expectedNesting[i])
                                         .And.DeclarePartialsInCorrectOrder(indicies[i - 1], indicies[i], expectedNesting[i - 1], expectedNesting[i]);
        }

        return runningResult;
    }

    public AndConstraint<SyntaxTreeAssertions> HaveNamespace()
    {
        this.CurrentAssertionChain
            .ForCondition(this._syntaxString.Contains("namespace "))
            .BecauseOf("expected namespace declaration")
            .FailWith("Expected {context} to contain a namespace declaration{reason}, but it was found. Actual syntax: {0}",
                this._syntaxString);

        return new(this);
    }

    public AndConstraint<SyntaxTreeAssertions> NotHaveNamespace()
    {
        this.CurrentAssertionChain
            .ForCondition(!this._syntaxString.Contains("namespace "))
            .BecauseOf("expected no namespace declaration")
            .FailWith("Expected {context} to not contain a namespace declaration{reason}, but it was found. Actual syntax: {0}",
                this._syntaxString);

        return new(this);
    }
}

internal static class SyntaxTreeFluentExtensions
{
    public static SyntaxTreeAssertions Should(this SyntaxTree syntaxTree) => new(syntaxTree, AssertionChain.GetOrCreate());
}
