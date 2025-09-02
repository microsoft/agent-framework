# Workflow Getting Started Samples

The getting started with workflow samples demonstrate the fundamental concepts and functionalities
of workflows in Agent Framework.

## Samples Overview

| Sample | File | Concepts |
|---|---|---|
| Sequential | [Step01a_Sequential.cs](./Step01a_Sequential.cs) | Minimal sequential workflow with two executors |
| Sequential (Streaming) | [Step01b_Sequential_Streaming.cs](./Step01b_Sequential_Streaming.cs) | Stream events from a simple sequential run |
| **Note** | | **All following samples use streaming and include agents** |
| Agents In A Workflow | [Step02_Agents_In_Workflow.cs](./Step02_Agents_In_Workflow.cs) | Introduce `AgentExecutor`; call agents inside a workflow |
| Concurrent (Fan‑out/Fan‑in) | [Step03_Concurrent.cs](./Step03_Concurrent.cs) | Dispatch to multiple agent executors and aggregate results |
| Edge Condition | [Step04_Edge_Condition.cs](./Step04_Edge_Condition.cs) | Conditional routing based on an agent’s classification |
| Shared States | [Step05_Shared_States.cs](./Step05_Shared_States.cs) | Store once in shared state; later read by downstream executors |
| Switch‑Case Edge Group | [Step06a_Switch_Case_Edge_Group.cs](./Step06a_Switch_Case_Edge_Group.cs) | Switch‑case branching and `Case/Default` |
| Multi‑Selection Edge Group | [Step06b_Multi_Selection_Edge_Group.cs](./Step06b_Multi_Selection_Edge_Group.cs) | Select one or many targets dynamically (subset fan‑out) |
