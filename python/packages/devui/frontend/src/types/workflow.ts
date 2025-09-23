// TypeScript types that mirror the agent_framework_workflow structure
// for better type safety and consistency with the backend

/**
 * Base executor interface that mirrors agent_framework_workflow._executor.Executor
 */
export interface Executor {
  id: string;
  type: string; // The executor class name (AgentExecutor, FunctionExecutor, etc.)
  [key: string]: unknown; // Additional executor-specific properties
}

/**
 * Specific executor types that extend the base Executor
 */
export interface AgentExecutor extends Executor {
  type: "AgentExecutor";
  agent_protocol?: unknown; // The wrapped agent
  streaming: boolean;
}

export interface FunctionExecutor extends Executor {
  type: "FunctionExecutor";
  function_name?: string;
}

export interface RequestInfoExecutor extends Executor {
  type: "RequestInfoExecutor";
}

export interface WorkflowExecutor extends Executor {
  type: "WorkflowExecutor";
  workflow: Workflow; // Nested workflow
}

/**
 * Edge interface that mirrors agent_framework_workflow._edge.Edge
 */
export interface Edge {
  source_id: string;
  target_id: string;
  condition_name?: string; // Name of condition function for serialization
}

/**
 * Base edge group interface that mirrors agent_framework_workflow._edge.EdgeGroup
 */
export interface EdgeGroup {
  id: string;
  type: string; // The edge group class name
  edges: Edge[];
}

/**
 * Specific edge group types
 */
export interface SingleEdgeGroup extends EdgeGroup {
  type: "SingleEdgeGroup";
}

export interface FanOutEdgeGroup extends EdgeGroup {
  type: "FanOutEdgeGroup";
  selection_func_name?: string; // Name of selection function
}

export interface FanInEdgeGroup extends EdgeGroup {
  type: "FanInEdgeGroup";
}

export interface SwitchCaseEdgeGroup extends EdgeGroup {
  type: "SwitchCaseEdgeGroup";
  cases: Array<{
    condition_name?: string;
    target_id: string;
  }>;
}

/**
 * Main Workflow interface that mirrors agent_framework_workflow._workflow.Workflow
 * This provides strong typing for the workflow_dump field
 */
export interface Workflow {
  id: string;
  edge_groups: EdgeGroup[];
  executors: Record<string, Executor>;
  start_executor_id: string;
  max_iterations: number;
}

/**
 * Type guards for runtime type checking
 */
export function isWorkflow(obj: unknown): obj is Workflow {
  return (
    typeof obj === "object" &&
    obj !== null &&
    "id" in obj &&
    "edge_groups" in obj &&
    "executors" in obj &&
    "start_executor_id" in obj &&
    "max_iterations" in obj &&
    typeof (obj as any).id === "string" &&
    Array.isArray((obj as any).edge_groups) &&
    typeof (obj as any).executors === "object" &&
    typeof (obj as any).start_executor_id === "string" &&
    typeof (obj as any).max_iterations === "number"
  );
}

export function isExecutor(obj: unknown): obj is Executor {
  return (
    typeof obj === "object" &&
    obj !== null &&
    "id" in obj &&
    "type" in obj &&
    typeof (obj as any).id === "string" &&
    typeof (obj as any).type === "string"
  );
}

export function isEdge(obj: unknown): obj is Edge {
  return (
    typeof obj === "object" &&
    obj !== null &&
    "source_id" in obj &&
    "target_id" in obj &&
    typeof (obj as any).source_id === "string" &&
    typeof (obj as any).target_id === "string"
  );
}

export function isEdgeGroup(obj: unknown): obj is EdgeGroup {
  return (
    typeof obj === "object" &&
    obj !== null &&
    "id" in obj &&
    "type" in obj &&
    "edges" in obj &&
    typeof (obj as any).id === "string" &&
    typeof (obj as any).type === "string" &&
    Array.isArray((obj as any).edges)
  );
}

/**
 * Utility type for workflow dump that can be either a properly typed Workflow
 * or a generic object (for backwards compatibility during transition)
 */
export type WorkflowDump = Workflow | Record<string, unknown>;

/**
 * Helper function to safely access workflow dump as a typed Workflow
 */
export function getTypedWorkflow(workflowDump: WorkflowDump): Workflow | null {
  if (isWorkflow(workflowDump)) {
    return workflowDump;
  }
  return null;
}