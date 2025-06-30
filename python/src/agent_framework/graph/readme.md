Some thoughts on flows and how they can be combined:

A node is:
  an action operating on some input (+context), producing some output
  an identifier
  the pair of types (input, output)
  outgoing edges

  when executing:
    input coming into the node must be of the input type
    entering the node causes the action to execute on the input
    output produced by the action must be of the output type


    when the node is entered, the action executes, producing output of the
    output type, and subsequently chasing all valid edges out of the node

A condition is:
  an action that operates on some input (+context), producing bool output

An edge is:
  the pair of nodes it connects (source, target)
  an optional conditional

  when executing,
    the source node's output type must match the target node's input type


A graph part (node, edge) is "materializable" when the object at hand is able to construct it
A graph is "materializable" when all the associated nodes and edges are materializable


A flow input is:
  an input type
  an identifier to a materializable node accepting that type of input
  an optional conditional

A flow output is:
  an output type
  an identifier to a materializable node producing that type of output
  an optional conditional


A flow is:
  a pair of types (input, output)
  some inner graph of materializable nodes,
  a well-defined set of "flow inputs"
  a well-defined set of "flow outputs"


A pair of flows can be joined using the multiplication operation if and only if the LHS
flow's output type matches the RHS flow's input type


join(lhs: Flow[TIn, TInOut], rhs: Flow[TInOut, TOut]) -> Flow[TIn, TOut]:
   """pseudocode"""
   for output in lhs:
      for input in rhs:
         condition: Action[TInOut, bool] | None = combine(output.condition, input.condition)
         create_edge(from=output.id, to=input.id, condition=condition)

   new_inputs = lhs.inputs
   new_outputs = rhs.outputs


A ConditionIsh is either a Flow[TIn, bool] or an Action[TIn, bool]


We can define higher-order concepts:

Loops:
   While(conditionish, Flow[TIn, TIn])
   Do(Flow[TIn, TIn], while=ConditionIsh[TIn, bool])

Sequences are supported out of the box via Join (but could use nice syntactic sugar, e.g. *)

Control Flow:
   If(ConditionIsh) * Flow[TIn, TOut] (or use << to indicate binding, since it is not really joining flows)
   Match({
      ConditionIsh: Flow[TIn, TOut]
   })


Lowering a flow/materialized graph to a target execution environment is a two-step compilation process:

1. Materialize the graph
2. Lower it to the execution environment

This lets us decouple the Workflow frontend from the execution environment, and gives us a "medium intermediate language" that lets us build the higher-level APIs more easily, without having to commit to a choice of runtime from the get-go.

Gaps from AutoGen's pub/sub:

The only thing we are missing from having 1:1 equality between pub/sub and this model is whether we allow edges to join multiple incoming and outgoing nodes, rather than point-to-point, but we can leverage optimization during the lowering operation to make use of pub/subs multiplexing capabilities when appropriate.

From the point of view of the consumer of the API this should not affect the expressiveness.