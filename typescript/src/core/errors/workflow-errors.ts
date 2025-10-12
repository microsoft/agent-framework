import { AgentFrameworkError } from './base-error';

/**
 * Error thrown during workflow validation.
 *
 * This error indicates that a workflow definition is invalid or cannot be executed.
 * This is a base class for specific workflow validation errors. Common issues include:
 * - Invalid workflow structure
 * - Missing required nodes or edges
 * - Invalid node configurations
 * - Circular dependencies
 * - Type incompatibilities between connected nodes
 *
 * @example
 * ```typescript
 * // Basic usage
 * throw new WorkflowValidationError('Workflow definition is invalid');
 *
 * // With validation details
 * if (!workflow.startNode) {
 *   throw new WorkflowValidationError(
 *     'Workflow must have a start node',
 *     undefined,
 *     'WORKFLOW_VAL_START_001'
 *   );
 * }
 *
 * // During workflow creation
 * class Workflow {
 *   constructor(definition: WorkflowDefinition) {
 *     if (!this.validate(definition)) {
 *       throw new WorkflowValidationError(
 *         'Invalid workflow definition: missing required properties',
 *         undefined,
 *         'WORKFLOW_VAL_DEF_001'
 *       );
 *     }
 *   }
 * }
 *
 * // Catching and handling
 * try {
 *   const workflow = new Workflow(definition);
 * } catch (error) {
 *   if (error instanceof WorkflowValidationError) {
 *     console.error('Workflow validation failed:', error.message);
 *     // Show validation errors to user
 *   }
 * }
 * ```
 */
export class WorkflowValidationError extends AgentFrameworkError {
  /**
   * Creates a new WorkflowValidationError.
   *
   * @param message - Description of the validation error
   * @param cause - Optional underlying error that caused this error
   * @param code - Optional error code for programmatic handling
   */
  constructor(message: string, cause?: Error, code?: string) {
    super(message, cause, code);
  }
}

/**
 * Error thrown when workflow graph connectivity is invalid.
 *
 * This error extends WorkflowValidationError and specifically indicates issues
 * with the graph structure of a workflow. Common issues include:
 * - Disconnected nodes (unreachable from start node)
 * - Missing edges between nodes
 * - Invalid edge definitions
 * - Circular references that prevent execution
 * - Multiple edges with conflicting conditions
 *
 * @example
 * ```typescript
 * // Basic usage
 * throw new GraphConnectivityError('Node "process" is not connected to the workflow');
 *
 * // With specific node information
 * const disconnectedNodes = findDisconnectedNodes(workflow);
 * if (disconnectedNodes.length > 0) {
 *   throw new GraphConnectivityError(
 *     `Disconnected nodes found: ${disconnectedNodes.join(', ')}`,
 *     undefined,
 *     'WORKFLOW_GRAPH_DISCONNECTED_001'
 *   );
 * }
 *
 * // Circular dependency detection
 * const cycle = detectCycle(workflow);
 * if (cycle) {
 *   throw new GraphConnectivityError(
 *     `Circular dependency detected: ${cycle.join(' -> ')}`,
 *     undefined,
 *     'WORKFLOW_GRAPH_CYCLE_001'
 *   );
 * }
 *
 * // Missing required edges
 * if (!workflow.edges.some(e => e.source === startNode.id)) {
 *   throw new GraphConnectivityError(
 *     'Start node must have at least one outgoing edge',
 *     undefined,
 *     'WORKFLOW_GRAPH_START_EDGE_001'
 *   );
 * }
 *
 * // During graph validation
 * function validateGraph(workflow: Workflow): void {
 *   const reachable = new Set<string>();
 *   traverseFrom(workflow.startNode.id, reachable);
 *
 *   const allNodes = workflow.nodes.map(n => n.id);
 *   const unreachable = allNodes.filter(id => !reachable.has(id));
 *
 *   if (unreachable.length > 0) {
 *     throw new GraphConnectivityError(
 *       `Unreachable nodes: ${unreachable.join(', ')}`,
 *       undefined,
 *       'WORKFLOW_GRAPH_UNREACHABLE_001'
 *     );
 *   }
 * }
 *
 * // Catching specific graph errors
 * try {
 *   validateGraph(workflow);
 * } catch (error) {
 *   if (error instanceof GraphConnectivityError) {
 *     console.error('Graph connectivity issue:', error.message);
 *     // Visualize problematic nodes/edges
 *   }
 * }
 * ```
 */
export class GraphConnectivityError extends WorkflowValidationError {
  /**
   * Creates a new GraphConnectivityError.
   *
   * @param message - Description of the connectivity error
   * @param cause - Optional underlying error that caused this error
   * @param code - Optional error code for programmatic handling
   */
  constructor(message: string, cause?: Error, code?: string) {
    super(message, cause, code);
  }
}

/**
 * Error thrown when types between connected workflow nodes are incompatible.
 *
 * This error extends WorkflowValidationError and specifically indicates type
 * mismatches in workflow data flow. Common issues include:
 * - Output type of source node doesn't match input type of target node
 * - Missing type annotations on edges
 * - Incompatible data transformations
 * - Type coercion failures
 *
 * @example
 * ```typescript
 * // Basic usage
 * throw new TypeCompatibilityError('Output type string is incompatible with input type number');
 *
 * // With node and edge information
 * function validateEdgeTypes(edge: Edge, sourceNode: Node, targetNode: Node): void {
 *   const sourceType = sourceNode.outputType;
 *   const targetType = targetNode.inputType;
 *
 *   if (!isCompatible(sourceType, targetType)) {
 *     throw new TypeCompatibilityError(
 *       `Type mismatch on edge from ${sourceNode.id} to ${targetNode.id}: ` +
 *       `cannot connect ${sourceType} to ${targetType}`,
 *       undefined,
 *       'WORKFLOW_TYPE_EDGE_001'
 *     );
 *   }
 * }
 *
 * // Array type mismatch
 * if (sourceNode.outputType === 'string' && targetNode.inputType === 'string[]') {
 *   throw new TypeCompatibilityError(
 *     `Cannot connect scalar output to array input: ${sourceNode.id} -> ${targetNode.id}`,
 *     undefined,
 *     'WORKFLOW_TYPE_ARRAY_001'
 *   );
 * }
 *
 * // Complex object type validation
 * function validateObjectTypes(source: ObjectType, target: ObjectType): void {
 *   for (const [key, targetType] of Object.entries(target.properties)) {
 *     const sourceType = source.properties[key];
 *     if (!sourceType) {
 *       throw new TypeCompatibilityError(
 *         `Missing required property "${key}" in source type`,
 *         undefined,
 *         'WORKFLOW_TYPE_PROP_MISSING_001'
 *       );
 *     }
 *     if (sourceType !== targetType) {
 *       throw new TypeCompatibilityError(
 *         `Property "${key}" type mismatch: ${sourceType} vs ${targetType}`,
 *         undefined,
 *         'WORKFLOW_TYPE_PROP_MISMATCH_001'
 *       );
 *     }
 *   }
 * }
 *
 * // During workflow compilation
 * function compileWorkflow(workflow: Workflow): CompiledWorkflow {
 *   for (const edge of workflow.edges) {
 *     const source = workflow.nodes.find(n => n.id === edge.source);
 *     const target = workflow.nodes.find(n => n.id === edge.target);
 *
 *     if (source && target) {
 *       validateEdgeTypes(edge, source, target);
 *     }
 *   }
 *   return compile(workflow);
 * }
 *
 * // Catching type errors
 * try {
 *   const compiled = compileWorkflow(workflow);
 * } catch (error) {
 *   if (error instanceof TypeCompatibilityError) {
 *     console.error('Type compatibility issue:', error.message);
 *     // Show type error with helpful suggestions
 *   }
 * }
 * ```
 */
export class TypeCompatibilityError extends WorkflowValidationError {
  /**
   * Creates a new TypeCompatibilityError.
   *
   * @param message - Description of the type compatibility error
   * @param cause - Optional underlying error that caused this error
   * @param code - Optional error code for programmatic handling
   */
  constructor(message: string, cause?: Error, code?: string) {
    super(message, cause, code);
  }
}
