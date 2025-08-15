# Workflow-as-Executor Design Options

## Executive Summary

This document presents comprehensive design options for implementing workflows as executors within other workflows in the Agent Framework workflow engine. Based on deep analysis of the existing codebase, we present six viable implementation strategies, each with distinct trade-offs regarding user experience, implementation complexity, and architectural impact.

## Current Architecture Overview

### Core Components
- **Workflow Engine**: Graph-based execution model using Pregel-style supersteps
- **Executors**: Base units of computation with typed message handlers
- **Message Passing**: Strongly-typed, async message routing between executors
- **State Management**: SharedState with isolated WorkflowContext per executor
- **Event System**: Comprehensive lifecycle and custom event support

### Key Strengths for Composition
- Clean abstraction boundaries between components
- Type-safe message passing with automatic routing
- Event-driven architecture supporting monitoring and coordination
- Async execution model naturally supporting nested operations
- Extensible executor model with simple base class

### Current Limitations
- No built-in support for workflow nesting
- No sub-workflow invocation mechanisms
- No dynamic workflow composition capabilities

## Option 1: Native WorkflowExecutor Class

### User Experience
Define sub-workflows using the existing WorkflowBuilder API and wrap them in a WorkflowExecutor to use as regular executors within parent workflows.

```python
# User code example
sub_workflow = (
    WorkflowBuilder()
    .set_start_executor(data_validator)
    .add_edge(data_validator, transformer)
    .add_edge(transformer, aggregator)
    .build()
)

main_workflow = (
    WorkflowBuilder()
    .set_start_executor(input_processor)
    .add_edge(input_processor, WorkflowExecutor(sub_workflow, id="sub_flow"))
    .add_edge(WorkflowExecutor(sub_workflow), output_handler)
    .build()
)
```

### How It Works
- WorkflowExecutor inherits from base Executor class
- Maintains internal workflow instance as private member
- Handler method executes sub-workflow and collects results
- Events from sub-workflow optionally propagated to parent
- State isolation through separate SharedState instances

### Implementation Requirements
- **New Components**:
  - WorkflowExecutor class (~200 lines)
  - State isolation wrapper
  - Event filtering/propagation logic
- **Modifications**:
  - Minor Runner changes for nested execution contexts
  - Context factory for isolated instances

### Advantages
- Minimal changes to existing codebase
- Natural extension of current patterns
- Maintains type safety and validation
- Clear encapsulation boundaries

### Disadvantages
- Static composition only (compile-time)
- No runtime workflow selection
- Limited flexibility for dynamic scenarios

## Option 2: Dynamic Workflow Invocation via CallWorkflowExecutor

### User Experience
Reference workflows by name or ID with dynamic selection at runtime through a registry-based system.

```python
# User code example
workflow_registry.register("data_pipeline", data_pipeline_workflow)
workflow_registry.register("ml_pipeline", ml_pipeline_workflow)

main_workflow = (
    WorkflowBuilder()
    .set_start_executor(router)
    .add_edge(router, CallWorkflowExecutor("data_pipeline"), 
              condition=lambda x: x.type == "data")
    .add_edge(router, CallWorkflowExecutor("ml_pipeline"), 
              condition=lambda x: x.type == "ml")
    .build()
)
```

### How It Works
- Central workflow registry maintains available sub-workflows
- CallWorkflowExecutor performs runtime lookup by identifier
- Late binding enables dynamic workflow selection
- Supports versioning and hot-swapping of workflows
- Registry can be populated from configuration or code

### Implementation Requirements
- **New Components**:
  - WorkflowRegistry singleton (~150 lines)
  - CallWorkflowExecutor class (~100 lines)
  - Workflow versioning support
  - Registry persistence mechanisms
- **Modifications**:
  - None to existing components

### Advantages
- Runtime flexibility
- Workflow reusability across projects
- Dynamic composition based on data/config
- Supports A/B testing of workflows

### Disadvantages
- Loses some compile-time type safety
- Additional registry management overhead
- Potential runtime lookup failures

## Option 3: Compiler-Based Workflow Flattening

### User Experience
Define hierarchical workflows with nesting syntax that automatically flattens to single-level graph during compilation.

```python
# User code example
@workflow_component
def data_processing_workflow():
    return (
        WorkflowBuilder()
        .set_start_executor(cleaner)
        .add_edge(cleaner, validator)
        .build()
    )

main_workflow = (
    WorkflowBuilder()
    .set_start_executor(ingester)
    .embed_workflow(data_processing_workflow(), id="processing")
    .add_edge("processing", reporter)
    .build()  # Automatically flattened during build
)
```

### How It Works
- Build phase analyzes workflow graph for embedded workflows
- Recursively expands embedded workflows into parent graph
- Rewrites edges to maintain logical flow
- Adds wrapper executors for input/output translation
- Debug mode preserves hierarchy for visualization

### Implementation Requirements
- **New Components**:
  - Graph analysis and rewriting logic (~300 lines)
  - Edge rewriting algorithms
  - Wrapper executor generation
  - Debugging/visualization support
- **Modifications**:
  - WorkflowBuilder.embed_workflow() method
  - Build process enhancement

### Advantages
- Zero runtime overhead (compilation happens once)
- Maintains all type safety guarantees
- Optimal performance (single flat graph)
- Compatible with existing tooling

### Disadvantages
- Complex implementation
- Harder to debug nested structures
- No runtime flexibility
- Larger memory footprint for expanded graphs

## Option 4: Async Sub-Workflow Tasks

### User Experience
Launch sub-workflows as background tasks with non-blocking execution and futures/promises for results.

```python
# User code example
class ParallelWorkflowExecutor(Executor):
    @handler(output_types=[AggregatedResult])
    async def execute(self, data: InputData, ctx: WorkflowContext):
        # Launch multiple sub-workflows in parallel
        tasks = [
            ctx.launch_workflow(workflow_a, data.subset_a),
            ctx.launch_workflow(workflow_b, data.subset_b),
            ctx.launch_workflow(workflow_c, data.subset_c)
        ]
        
        # Wait for all to complete
        results = await asyncio.gather(*tasks)
        
        # Send aggregated result
        await ctx.send_message(AggregatedResult(results))
```

### How It Works
- Context extended with workflow launching capabilities
- Sub-workflows run in separate async tasks
- Parent can await results or fire-and-forget
- Results returned via futures
- Resource pooling for concurrent execution

### Implementation Requirements
- **New Components**:
  - WorkflowContext.launch_workflow() method (~100 lines)
  - Async task management infrastructure
  - Resource pooling system
  - Cancellation support
- **Modifications**:
  - WorkflowContext enhancement
  - Runner support for concurrent workflows

### Advantages
- Excellent for parallel processing scenarios
- Natural async/await integration
- Flexible execution patterns
- Good resource utilization

### Disadvantages
- Complex error handling
- Resource management challenges
- Potential for deadlocks
- Harder to debug concurrent execution

## Option 5: Workflow Templates with Parameterization

### User Experience
Define reusable workflow templates that can be instantiated with different parameters.

```python
# User code example
@workflow_template
def processing_template(config: ProcessingConfig):
    return (
        WorkflowBuilder()
        .set_start_executor(Preprocessor(config.preprocess_params))
        .add_edge(Preprocessor(), Processor(config.process_params))
        .add_edge(Processor(), Postprocessor(config.postprocess_params))
        .build()
    )

main_workflow = (
    WorkflowBuilder()
    .set_start_executor(configurator)
    .add_edge(configurator, 
              WorkflowTemplate(processing_template, 
                             config=ProductionConfig()))
    .build()
)
```

### How It Works
- Templates are workflow factories
- Parameters injected at instantiation time
- Supports dependency injection patterns
- Configuration-driven workflow generation
- Type-safe parameter validation

### Implementation Requirements
- **New Components**:
  - Template decorator and registry (~150 lines)
  - WorkflowTemplate executor class (~100 lines)
  - Parameter validation framework
  - Configuration management system
- **Modifications**:
  - None to existing components

### Advantages
- High reusability
- Configuration-driven workflows
- Type-safe parameterization
- Clean separation of concerns

### Disadvantages
- Additional abstraction layer
- Template management complexity
- Limited to predefined parameters
- Potential configuration sprawl

## Option 6: State Machine-Based Composition

### User Experience
Define workflows as state machines where states can be executors or sub-workflows.

```python
# User code example
sub_workflow = StateMachine()
    .add_state("validate", ValidationWorkflow())
    .add_state("process", ProcessingWorkflow())
    .add_state("complete", CompletionExecutor())
    .add_transition("validate", "process", condition=valid_data)
    .add_transition("process", "complete")
    .build()

main_workflow = (
    WorkflowBuilder()
    .set_start_executor(input_handler)
    .add_edge(input_handler, StateMachineExecutor(sub_workflow))
    .build()
)
```

### How It Works
- StateMachine abstraction over workflow graphs
- Each state can be executor or entire workflow
- Explicit state transitions with conditions
- Supports hierarchical state machines
- State persistence for recovery

### Implementation Requirements
- **New Components**:
  - StateMachine abstraction layer (~400 lines)
  - StateMachineExecutor implementation
  - State persistence system
  - Transition evaluation engine
- **Modifications**:
  - None to existing components

### Advantages
- Natural for state-based problems
- Clear transition logic
- Good for complex control flow
- Supports state persistence/recovery

### Disadvantages
- Most complex implementation
- Different mental model from current system
- Performance overhead for state management
- Learning curve for users

## Important Clarification: Templates vs. Execution Mechanisms

**Option 5 (Workflow Templates) is orthogonal to the sub-workflow execution problem.** Templates provide parameterization and reusability but do NOT provide a mechanism for one workflow to execute another. To use templates effectively for sub-workflows, you must combine Option 5 with an execution mechanism (Options 1, 2, 3, 4, or 6).

### Options That Enable Sub-Workflow Execution
- **Option 1**: Native WorkflowExecutor - Wraps workflow in Executor ✅
- **Option 2**: Dynamic Invocation - Runtime workflow lookup/execution ✅  
- **Option 3**: Compiler Flattening - Compile-time graph expansion ✅
- **Option 4**: Async Tasks - Concurrent workflow execution ✅
- **Option 6**: State Machine - States as workflows ✅

### Options That Enhance But Don't Enable Sub-Workflows
- **Option 5**: Templates - Parameterization only, needs execution mechanism ⚠️

## Implementation Recommendation

### Primary Recommendation: Implement Options 1, 2, and 5 Together

**Phase 1: Native WorkflowExecutor (Option 1)**
- Provides the core execution mechanism
- Natural extension of existing patterns
- Maintains full type safety
- Clear API for users
- Implementation effort: ~200 lines

**Phase 2: Dynamic Invocation (Option 2)**
- Adds runtime flexibility
- Enables workflow reusability
- Supports dynamic composition
- Registry-based management
- Implementation effort: ~250 lines

**Phase 3: Workflow Templates (Option 5)**
- Adds parameterization capability
- Works with BOTH Option 1 and Option 2
- Enables configuration-driven workflows
- Promotes reusability across projects
- Implementation effort: ~250 lines

### Why This Combination?

1. **Complete Solution**: Options 1+2 provide execution mechanisms, Option 5 adds parameterization
2. **Complementary Capabilities**: Static (Option 1), dynamic (Option 2), and templated (Option 5) composition serve different use cases
3. **Minimal Disruption**: All three options build on existing architecture without fundamental changes
4. **Incremental Adoption**: Users can adopt features progressively as needed
5. **Type Safety**: Preserves type checking where possible while allowing dynamic scenarios
6. **Maximum Flexibility**: Templates can be used with both static and dynamic execution

### Example: Combining Templates with Execution

```python
# Step 1: Define a workflow template
@workflow_template
def ml_pipeline_template(model_config: ModelConfig):
    return (
        WorkflowBuilder()
        .set_start_executor(DataLoader(model_config.data_source))
        .add_edge(DataLoader(), FeatureExtractor(model_config.features))
        .add_edge(FeatureExtractor(), ModelTrainer(model_config.model_type))
        .add_edge(ModelTrainer(), Evaluator(model_config.metrics))
        .build()
    )

# Step 2: Use template with WorkflowExecutor (Option 1 + 5)
experiment_workflow = (
    WorkflowBuilder()
    .set_start_executor(experiment_setup)
    .add_edge(
        experiment_setup,
        WorkflowExecutor(
            ml_pipeline_template(ExperimentConfig()),
            id="ml_sub_workflow"
        )
    )
    .add_edge("ml_sub_workflow", results_aggregator)
    .build()
)

# Step 3: Or use template with Dynamic Invocation (Option 2 + 5)
for env in ["dev", "staging", "prod"]:
    workflow_registry.register(
        f"ml_pipeline_{env}",
        ml_pipeline_template(configs[env])
    )

production_workflow = (
    WorkflowBuilder()
    .set_start_executor(environment_selector)
    .add_edge(
        environment_selector,
        CallWorkflowExecutor("ml_pipeline_prod")
    )
    .build()
)
```

### Future Enhancements

Based on user feedback and adoption patterns, consider:
- **Option 4** for high-performance parallel processing needs
- **Option 3** for performance-critical scenarios where runtime overhead must be minimized

### Implementation Timeline

1. **Week 1-2**: Implement Native WorkflowExecutor
   - Core executor class
   - State isolation
   - Basic event propagation
   - Unit tests

2. **Week 3-4**: Implement Dynamic Invocation
   - Registry implementation
   - CallWorkflowExecutor
   - Registry persistence
   - Integration tests

3. **Week 5**: Documentation and Examples
   - API documentation
   - Usage examples
   - Migration guide
   - Performance benchmarks

## Conclusion

The workflow engine's current architecture provides an excellent foundation for implementing workflow-as-executor patterns. The recommended approach of combining Options 1 and 2 offers the best balance of functionality, implementation complexity, and user experience while maintaining backward compatibility and the framework's core design principles.