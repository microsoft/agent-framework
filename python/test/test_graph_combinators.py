from __future__ import annotations
from dataclasses import dataclass
import enum
from typing import Generic, Sequence, TypeVar

from agent_framework.graph import While, Switch, FlowCompiler, GraphBuilder, StepT, Flow, runnable, Executor, LogTracer

TIn = TypeVar("TIn", contravariant=True)
TInOut = TypeVar("TInOut", contravariant=False, covariant=False)
TOut = TypeVar("TOut", covariant=True)


@dataclass
class WorkflowContext:
    remaining_retries: int = 3
    result: str | None = None
    error: str | None = None

    def wrap(self, TInOut):
        """Wraps the current context in a StepContext."""
        return StepContext(workflow_context=self, value=TInOut)

    def with_result(self, result: str) -> 'WorkflowContext':
        """Sets the result and returns a new WorkflowContext."""
        return WorkflowContext(remaining_retries=self.remaining_retries, result=result, error=None)

    def with_error(self, error: str) -> 'WorkflowContext':
        """Sets the error and returns a new WorkflowContext."""
        return WorkflowContext(remaining_retries=self.remaining_retries, result=None, error=error)


@dataclass
class StepContext(Generic[TIn]):
    workflow_context: WorkflowContext
    value: TIn

    def map(self, step: StepT[TIn, TInOut]) -> 'StepContext[TInOut]':
        """Returns a new StepContext with the updated value."""
        runnable_step = runnable(step)

        return StepContext(workflow_context=self.workflow_context, value=runnable_step(self.value))

    def unwrap(self, step: StepT[TIn, TOut]) -> WorkflowContext:
        """Unwraps the current context and applies the step to the value."""
        try:
            runnable_step = runnable(step)
            return self.workflow_context.with_result(runnable_step(self.value))
        except Exception as e:
            return self.workflow_context.with_error(str(e))


class InputSimulator:
    def __init__(self, inputs: str | Sequence[str]):
        if isinstance(inputs, str):
            inputs = [inputs]

        if not inputs:
            raise ValueError("InputSimulator must be initialized with at least one input string.")

        self.inputs = inputs
        self.index = 0

    def __call__(self, prompt: str) -> str:
        """Simulates user input by returning the next input string."""
        user_input = self.inputs[self.index]

        if self.index + 1 < len(self.inputs):
            self.index += 1

        self.index += 1
        return user_input


def newtype(name: str, base: type) -> type:
    """Creates a new type with the given name and base class."""
    return type(name, (base,), {"__new__": lambda cls, *args, **kwargs: base.__new__(cls, *args, **kwargs)})


Ok = newtype("Ok", str)
Ok: type[Ok]

Err: type[Err] = newtype("Err", str)
Err: type[Err]

Result = Ok | Err


class Error(str):
    """A class to represent an error result in the workflow."""
    def __new__(cls, *args, **kwargs):
        """Creates a new Error instance."""
        return str.__new__(cls, *args, **kwargs)


def _sample():
    class RequestType(enum.Enum):
        PARENS = "parens"
        QUIT = "quit"
        BAD = "bad"

    @dataclass
    class UserRequest:
        type_: RequestType
        parens_text: str | None = None

    input_ = InputSimulator(["((())", "q"])

    def get_user_request(ctx: WorkflowContext) -> StepContext[UserRequest]:
        user_input = input_("Enter parentheses text (or 'q' to quit): ")
        if user_input.lower() in ["q", "quit"]:
            return ctx.wrap(UserRequest(type_=RequestType.QUIT, parens_text=None))

        if not user_input.strip():
            return ctx.wrap(UserRequest(type_=RequestType.BAD, parens_text=None))

        return ctx.wrap(UserRequest(type_=RequestType.PARENS, parens_text=user_input.strip()))

    def case_(request_type: RequestType) -> StepT[StepContext[UserRequest], bool]:
        """Returns a condition that checks if the request type matches the given type."""
        def condition(request: StepContext[UserRequest]) -> bool:
            return request.value.type_ == request_type

        return condition

    def match_parens(ctx: StepContext[UserRequest]) -> WorkflowContext:
        def match_parens_(parens_text: str) -> str:
            open_count = 0
            for idx, char in enumerate(parens_text):
                if char == "(":
                    open_count += 1
                elif char == ")":
                    open_count -= 1
                    if open_count < 0:
                        return "Unmatched closing parenthesis at position {}".format(idx)

            if open_count > 0:
                return "Unmatched opening parenthesis in string."

            return "Parentheses are balanced."

        return ctx.unwrap(match_parens_)

    def write_quit_response(ctx: StepContext[UserRequest]) -> WorkflowContext:
        """Writes a response for quitting the workflow."""
        return ctx.workflow_context.with_result("Quitting the workflow as requested.")

    # In a sequence, input some data from the user, then process it, and finally, output the result.
    loop = While(
        lambda ctx: ctx.remaining_retries > 0,
        [
            get_user_request,  # since this is StepT, we could just as easily have it b an agent with .run() method
                               # or a "built" ExecutableGraph instance
            Switch({
                case_(RequestType.PARENS):
                    match_parens,
                case_(RequestType.QUIT):
                    write_quit_response,
            })
        ]
    )

    def create_context(self, input: None) -> WorkflowContext:
        """Creates a new WorkflowContext with default values."""
        return WorkflowContext()

    def extract_output(ctx: WorkflowContext) -> Result:
        """Extracts the output from the WorkflowContext."""
        if ctx.error:
            return Err(ctx.error)
        if ctx.result:
            return Ok(ctx.result)

        return Err("No result or error found in the context.")

    flow = create_context + loop + extract_output

    # This should be equivalent to the following via __add__ and __addr__ methods on FlowBase
    # which is implemented by Loop(=LoopFlow), and Sequence(=SequenceFlow):
    # flow = Sequence([
    #   create_context,
    #   loop,
    #   extract_output
    # ])

    executable_graph = FlowCompiler().compile(flow)
    executor = Executor(executable_graph, tracer=LogTracer())

    result = executor.run(None)
    if isinstance(result, Ok):
        print(f"Success: {result}")
    elif isinstance(result, Err):
        print(f"Error: {result}")
