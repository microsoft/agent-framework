// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.PowerFx;

public class FoundryExpressionEngineTests(ITestOutputHelper output) : RecalcEngineTest(output)
{
    [Fact]
    public void DefaultNotNull()
    {
        // Act
        RecalcEngine engine = this.CreateEngine();
        FoundryExpressionEngine expressionEngine = new(engine);
        this.Scopes.Set("test", FormulaValue.New("value"));
        engine.SetScopedVariable(this.Scopes, PropertyPath.TopicVariable("test"), FormulaValue.New("value"));

        EvaluationResult<string> valueResult = expressionEngine.GetValue(StringExpression.Variable(PropertyPath.TopicVariable("test")), this.Scopes.BuildState());

        // Assert
        Assert.Equal("value", valueResult.Value);
        Assert.Equal(SensitivityLevel.None, valueResult.Sensitivity);
    }
}
