import { memo, type CSSProperties } from "react";
import { BaseEdge, useInternalNode } from "@xyflow/react";

interface SelfLoopEdgeProps {
  id: string;
  source: string;
  markerEnd?: string;
  style?: CSSProperties;
}

/**
 * Custom edge for self-referencing nodes. Renders a bezier loop from output back to input.
 */
export const SelfLoopEdge = memo(function SelfLoopEdge({
  id,
  source,
  markerEnd,
  style,
}: SelfLoopEdgeProps) {
  const sourceNode = useInternalNode(source);
  if (!sourceNode) return null;

  const { width, height } = sourceNode.measured;
  const { x, y } = sourceNode.internals.positionAbsolute;
  if (!width || !height) return null;

  const nodeData = sourceNode.data as Record<string, unknown> | undefined;
  const isVertical = nodeData?.layoutDirection === "TB";

  const loopOffset = 100;
  const riseOffset = 40;

  let edgePath: string;

  if (isVertical) {
    // TB: bottom center → curves right → top center
    const startX = x + width / 2;
    const startY = y + height;
    const endX = x + width / 2;
    const endY = y;
    const cpX = x + width + loopOffset;

    edgePath = `M ${startX} ${startY} C ${startX} ${startY + riseOffset}, ${cpX} ${startY + riseOffset}, ${cpX} ${y + height / 2} C ${cpX} ${endY - riseOffset}, ${endX} ${endY - riseOffset}, ${endX} ${endY}`;
  } else {
    // LR: right center → curves down → left center
    const startX = x + width;
    const startY = y + height / 2;
    const endX = x;
    const endY = y + height / 2;
    const cpY = y + height + loopOffset;

    edgePath = `M ${startX} ${startY} C ${startX + riseOffset} ${startY}, ${startX + riseOffset} ${cpY}, ${x + width / 2} ${cpY} C ${endX - riseOffset} ${cpY}, ${endX - riseOffset} ${endY}, ${endX} ${endY}`;
  }

  return <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} style={style} />;
});
