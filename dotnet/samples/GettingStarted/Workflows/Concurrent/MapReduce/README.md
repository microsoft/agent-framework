# Workflow Visualization Sample

This sample demonstrates how to visualize workflows using the `WorkflowViz` class to generate graphical representations of workflow structures.

## Prerequisites

### For Visualization Export (SVG/PNG)
- **[Graphviz](https://graphviz.org/download/)** must be installed and accessible in PATH
  - Windows: `winget install graphviz` or download from the website
  - macOS: `brew install graphviz`
  - Linux: `apt-get install graphviz` or equivalent

**Note**: DOT format export works without Graphviz installed.

## WorkflowViz Usage

```csharp
// Create a visualization instance
var viz = new WorkflowViz(workflow);

// Export to different formats
var dotString = viz.ToDotString();              // Get DOT string representation
var dotFile = await viz.ExportAsync("dot");     // Export to DOT file (always works)
var svgFile = await viz.ExportAsync("svg");     // Export to SVG (requires Graphviz)
var pngFile = await viz.ExportAsync("png");     // Export to PNG (requires Graphviz)

// Convenience methods
await viz.SaveSvgAsync("workflow.svg");
await viz.SavePngAsync("workflow.png");
await viz.SavePdfAsync("workflow.pdf");
```

## Supported Export Formats

- **DOT** - GraphViz source format (no Graphviz required)
- **SVG** - Scalable vector graphics (requires Graphviz)
- **PNG** - Raster image (requires Graphviz)
- **PDF** - Portable document format (requires Graphviz)

## Related Samples

For workflow construction patterns, see:
- **[Concurrent](../Concurrent/)** - Fan-out/fan-in pattern
- **[04_AgentWorkflowPatterns](../../04_AgentWorkflowPatterns/)** - Various workflow patterns
- **[WorkflowAsAnAgent](../WorkflowAsAnAgent/)** - Wrapping workflows as agents