# Concurrent Workflow with Visualization Sample

This sample demonstrates how to create a concurrent workflow using the fan-out/fan-in pattern with built-in workflow visualization capabilities.

## What it does

The sample creates a business analysis workflow that:

1. **Fan-out**: Dispatches the same business prompt to multiple domain expert agents (Research, Marketing, Legal) simultaneously
2. **Concurrent Processing**: Each expert agent analyzes the prompt independently and in parallel
3. **Fan-in**: Aggregates all expert responses into a single consolidated report
4. **Visualization**: Generates visual representations of the workflow structure using `WorkflowViz`

## Workflow Structure

```
Input Prompt
     ↓
DispatchToExperts
   ↙   ↓   ↘
Research Marketing Legal (concurrent processing)
   ↘   ↓   ↙
AggregateInsights
     ↓
Consolidated Report
```

## Key Features

- **Concurrent execution** for better performance when multiple independent analyses are needed
- **Domain expertise** from specialized AI agents (research, marketing, legal perspectives)
- **Workflow visualization** with multiple export formats:
  - DOT format (GraphViz source)
  - SVG (if Graphviz is installed)
  - PNG (if Graphviz is installed)
- **Structured aggregation** of expert insights into a formatted report

## Prerequisites

### Required
- .NET 9.0 or .NET Framework 4.7.2
- Azure OpenAI deployment
- Environment variables:
  - `AZURE_OPENAI_ENDPOINT` - Your Azure OpenAI endpoint URL
  - `AZURE_OPENAI_DEPLOYMENT_NAME` - Deployment name (defaults to "gpt-4o-mini")

### Optional (for visualization export)
- [Graphviz](https://graphviz.org/download/) installed and accessible in PATH
  - Required for SVG and PNG export
  - DOT format export works without Graphviz

## Running the Sample

1. Set your environment variables:
   ```bash
   set AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
   set AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-mini
   ```

2. Run the sample:
   ```bash
   dotnet run
   ```

3. The sample will:
   - Display the workflow structure in DOT format
   - Export visualization files (workflow.dot, workflow.svg, workflow.png)
   - Execute the concurrent analysis
   - Show the consolidated expert report

## Sample Output

The sample analyzes the prompt: *"We are launching a new budget-friendly electric bike for urban commuters."*

Each expert provides their perspective:
- **Research**: Market opportunities, target demographics, competitive analysis
- **Marketing**: Value propositions, messaging, positioning strategies
- **Legal**: Compliance requirements, risk factors, regulatory considerations

## Visualization Files

After running, check for these generated files:
- `workflow.dot` - GraphViz source (always generated)
- `workflow.svg` - Scalable vector graphic (requires Graphviz)
- `workflow.png` - Raster image (requires Graphviz)

## Code Highlights

### WorkflowViz Usage
```csharp
var viz = new WorkflowViz(workflow);
var dotString = viz.ToDotString();           // Get DOT representation
var dotFile = await viz.ExportAsync("dot");  // Export DOT file
var svgFile = await viz.ExportAsync("svg");  // Export SVG (requires Graphviz)
```

### Fan-out/Fan-in Pattern
```csharp
var workflow = new WorkflowBuilder(dispatcher)
    .AddFanOutEdge(dispatcher, targets: [researcher, marketer, legal])
    .AddFanInEdge(aggregator, sources: [researcher, marketer, legal])
    .Build<string>();
```

## Related Samples

- **Concurrent** - Basic concurrent workflow without visualization
- **04_AgentWorkflowPatterns** - Various workflow patterns including concurrent
- **WorkflowAsAnAgent** - Wrapping workflows as reusable agents

## Benefits of This Pattern

- **Parallel processing** reduces total execution time
- **Multiple perspectives** provide comprehensive analysis
- **Visual documentation** helps understand and communicate workflow structure
- **Scalable architecture** for adding more expert domains
- **Reusable pattern** for any multi-expert analysis scenario