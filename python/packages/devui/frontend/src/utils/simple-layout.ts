import type { Node, Edge } from "@xyflow/react";
import type { ExecutorNodeData } from "@/components/workflow/executor-node";

/**
 * Lightweight auto-layout algorithm to replace dagre
 * Handles fan-out nodes properly by spacing siblings
 */
export function applySimpleLayout(
  nodes: Node<ExecutorNodeData>[],
  edges: Edge[],
  direction: "TB" | "LR" = "LR"
): Node<ExecutorNodeData>[] {
  if (nodes.length === 0) return nodes;
  if (nodes.length === 1) {
    return nodes.map((node) => ({
      ...node,
      position: { x: 0, y: 0 },
    }));
  }

  // Create adjacency maps
  const outgoingEdges = new Map<string, string[]>();
  const incomingEdges = new Map<string, string[]>();

  nodes.forEach((node) => {
    outgoingEdges.set(node.id, []);
    incomingEdges.set(node.id, []);
  });

  edges.forEach((edge) => {
    outgoingEdges.get(edge.source)?.push(edge.target);
    incomingEdges.get(edge.target)?.push(edge.source);
  });

  // Find root nodes (nodes with no incoming edges)
  const rootNodes = nodes.filter(
    (node) => (incomingEdges.get(node.id) || []).length === 0
  );

  if (rootNodes.length === 0) {
    // Fallback: use first node as root if no clear root
    rootNodes.push(nodes[0]);
  }

  // Constants for spacing
  const NODE_WIDTH = 220;
  const NODE_HEIGHT = 120;
  const HORIZONTAL_SPACING = direction === "LR" ? 350 : 200;
  const VERTICAL_SPACING = direction === "TB" ? 250 : 180;

  // Track positioned nodes and level information
  const positioned = new Map<string, { x: number; y: number; level: number }>();
  const levelGroups = new Map<number, string[]>();

  // Build level groups using BFS
  const queue: Array<{ nodeId: string; level: number }> = [];
  const visited = new Set<string>();

  // Start with root nodes at level 0
  rootNodes.forEach((node) => {
    queue.push({ nodeId: node.id, level: 0 });
  });

  // BFS to assign levels
  while (queue.length > 0) {
    const { nodeId, level } = queue.shift()!;

    if (visited.has(nodeId)) continue;
    visited.add(nodeId);

    // Add to level group
    if (!levelGroups.has(level)) {
      levelGroups.set(level, []);
    }
    levelGroups.get(level)!.push(nodeId);

    // Add children to next level
    const children = outgoingEdges.get(nodeId) || [];
    children.forEach((childId) => {
      if (!visited.has(childId)) {
        queue.push({ nodeId: childId, level: level + 1 });
      }
    });
  }

  // Handle orphaned nodes (not connected to root)
  nodes.forEach((node) => {
    if (!visited.has(node.id)) {
      const maxLevel = Math.max(...Array.from(levelGroups.keys()), -1);
      const orphanLevel = maxLevel + 1;

      if (!levelGroups.has(orphanLevel)) {
        levelGroups.set(orphanLevel, []);
      }
      levelGroups.get(orphanLevel)!.push(node.id);
    }
  });

  // Position nodes level by level
  levelGroups.forEach((nodeIds, level) => {
    const nodeCount = nodeIds.length;

    nodeIds.forEach((nodeId, index) => {
      let x: number, y: number;

      if (direction === "LR") {
        // Horizontal layout: X increases with level, Y centers siblings
        x = level * HORIZONTAL_SPACING;

        // Center siblings vertically
        const totalHeight = (nodeCount - 1) * VERTICAL_SPACING;
        const startY = -totalHeight / 2;
        y = startY + index * VERTICAL_SPACING;
      } else {
        // Vertical layout: Y increases with level, X centers siblings
        y = level * VERTICAL_SPACING;

        // Center siblings horizontally
        const totalWidth = (nodeCount - 1) * HORIZONTAL_SPACING;
        const startX = -totalWidth / 2;
        x = startX + index * HORIZONTAL_SPACING;
      }

      positioned.set(nodeId, { x, y, level });
    });
  });

  // Apply positions to nodes (centering them on their calculated positions)
  return nodes.map((node) => {
    const pos = positioned.get(node.id) || { x: 0, y: 0 };
    return {
      ...node,
      position: {
        x: pos.x - NODE_WIDTH / 2, // Center the node
        y: pos.y - NODE_HEIGHT / 2,
      },
    };
  });
}
