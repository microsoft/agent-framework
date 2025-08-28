// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.PowerFx;

public class RecalcEngineFactoryTests(ITestOutputHelper output) : RecalcEngineTest(output)
{
    [Fact]
    public void VariableUpdateTest()
    {
        RecalcEngine engine = this.CreateEngine();

        FormulaValue evalResult;

        engine.UpdateVariable("single", FormulaValue.New(1));
        evalResult = engine.Eval("single");
        Console.WriteLine($"# {evalResult.Format()}");

        RecordValue recordSub =
            FormulaValue.NewRecordFromFields(
                new NamedValue("sub", FormulaValue.New(3.14)));
        RecordValue recordRoot =
            FormulaValue.NewRecordFromFields(
                new NamedValue("another", FormulaValue.NewBlank()),
                new NamedValue("val", FormulaValue.New(2.82)),
                new NamedValue("root", recordSub));
        engine.DeleteFormula("Topic");
        engine.UpdateVariable("Topic", recordRoot);
        evalResult = engine.Eval("Topic");
        Console.WriteLine($"# {evalResult.Format()}");
        evalResult = engine.Eval("Topic.val");
        Console.WriteLine($"# {evalResult.Format()}");
        evalResult = engine.Eval("Topic.root");
        Console.WriteLine($"# {evalResult.Format()}");
        evalResult = engine.Eval("Topic.root.sub");
        Console.WriteLine($"# {evalResult.Format()}");
        //recordRoot.UpdateField("another", FormulaValue.New("abc"));
        RecordValue recordRoot2 =
            FormulaValue.NewRecordFromFields(
                new NamedValue("another", FormulaValue.New("abc")),
                new NamedValue("val", FormulaValue.New(2.82)),
                new NamedValue("root", recordSub));
        engine.DeleteFormula("Topic");
        engine.UpdateVariable("Topic", recordRoot2);
        evalResult = engine.Eval("Topic.another");
        Console.WriteLine($"# {evalResult.Format()}");
        engine.UpdateVariable("Topic.another", FormulaValue.New(-1));
        evalResult = engine.Eval("Topic.another");
        Console.WriteLine($"# {evalResult.Format()}");
    }

    [Fact]
    public void DefaultNotNull()
    {
        // Act
        RecalcEngine engine = this.CreateEngine();

        // Assert
        Assert.NotNull(engine);
    }

    [Fact]
    public void NewInstanceEachTime()
    {
        // Act
        RecalcEngine engine1 = this.CreateEngine();
        RecalcEngine engine2 = this.CreateEngine();

        // Assert
        Assert.NotNull(engine1);
        Assert.NotNull(engine2);
        Assert.NotSame(engine1, engine2);
    }

    [Fact]
    public void HasSetFunctionEnabled()
    {
        // Arrange
        RecalcEngine engine = this.CreateEngine();

        // Act
        CheckResult result = engine.Check("1+1");

        // Assert
        Assert.True(result.IsSuccess);
    }

    [Fact]
    public void HasCorrectMaximumExpressionLength()
    {
        // Arrange
        RecalcEngine engine = RecalcEngineFactory.Create(2000, 3);

        // Assert
        Assert.Equal(2000, engine.Config.MaximumExpressionLength);
        Assert.Equal(3, engine.Config.MaxCallDepth);

        // Act: Create a long expression that is within the limit
        string goodExpression = string.Concat(GenerateExpression(999));
        CheckResult goodResult = engine.Check(goodExpression);

        // Assert
        Assert.True(goodResult.IsSuccess);

        // Act: Create a long expression that exceeds the limit
        string longExpression = string.Concat(GenerateExpression(1001));
        CheckResult longResult = engine.Check(longExpression);

        // Assert
        Assert.False(longResult.IsSuccess);

        static IEnumerable<string> GenerateExpression(int elements)
        {
            yield return "1";
            for (int i = 0; i < elements - 1; i++)
            {
                yield return "+1";
            }
        }
    }
}
