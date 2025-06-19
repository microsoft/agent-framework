# Python SDK Design Guidelines: Best Practices for Design, Implementation, and Documentation

This guide outlines general best practices for designing, implementing, and documenting Python libraries, emphasizing readability, idiomatic usage, consistency, extensibility, and clarity.

---

## ✅ Design Principles

SDKs and libraries should be designed to directly enhance the productivity of developers. While other qualities such as completeness, extensibility, and performance are important, developer productivity should remain the primary objective. This is achieved by strictly adhering to the following principles:

### **Idiomatic**

- The SDK must follow Python’s design guidelines, best practices, and conventions.  
- APIs should feel natural and intuitive to Python developers.  
- Embrace the Python ecosystem with both its strengths and flaws—actively contributing to its improvement for all developers.

### **Consistent**

- Client libraries must be consistent internally (within Python), consistent with underlying services, and ideally aligned across multiple programming languages.  
- Priority of consistency:
  1. Within Python libraries.
  2. With the underlying services or domain.
  3. Across multiple languages (lowest priority).
- Common concepts such as logging, HTTP interactions, and error handling should be uniform throughout the library. Developers should not have learn these repeatedly when switching libraries.
- Vocabulary and terminology consistency with underlying services facilitate diagnosability and clarity.
- Every deviation or difference from a service or existing convention must have a clearly articulated, justified reasoning based on idiomatic design—not simply preference.
- Libraries should feel coherent, as though designed and built by a single team or individual, rather than a disparate collection of modules.  
- Aim for feature parity across related Python libraries before across languages or underlying services.

### **Approachable**

- SDK authors should be experts in the complexity of the underlying technologies—abstracting complexity so their users don’t have to learn unnecessary details.
- Provide clear, comprehensive, helpful documentation (e.g., tutorials, how-tos, detailed API docs, and robust samples), empowering developers to succeed quickly.
- The design should make it easy to get started through intelligent defaults representing current best practices, enabling progressive learning of advanced concepts.
- SDK installation and usage should leverage standard and common Python ecosystem tools (e.g., pip, PyPI, etc.).
- The most common use-cases should be easily discoverable to avoid overwhelming developers with complexity or unnecessary details early in their learning curve.

### **Diagnosable**

- It should always be easy for developers to understand internal behavior (e.g., when exactly network requests occur).
- Default values and behaviors must be strongly discoverable, intuitive, and clearly justified.
- Consistently thoughtful logging, tracing, and exception handling are a mandatory practice.
- Errors should always be concise, actionable, correlated directly with underlying causes (service or local), and clearly human-readable. Good error messages guide the developer toward a productive next step or solution.
- Integration with standard Python debugging tools should be seamless and effortless.

### **Dependable**

- Prioritize stability. Breaking changes significantly reduce developer trust, often more than new features or improvements increase it.
- Deliberately introducing backward incompatibilities is strictly prohibited without exceptionally strong justification, rigorous analysis, and thorough communication.
- Carefully manage third-party dependencies to ensure they never constrain a library’s stability and backward compatibility guarantees.

---

## ✅ General API Design Principles

Design APIs to be:

- **Idiomatic**: Natural and intuitive for Python developers.
- **Consistent**: Predictable behavior and similar structure across library functionalities.
- **Approachable**: Quick and easy for developers to learn and use effectively.
- **Diagnosable**: Enable effective debugging and easy troubleshooting.
- **Dependable**: Ensure stability and backward compatibility.

---

## ✅ Return Types and Exceptions

- **Always raise exceptions instead of returning special error indicators** (e.g., avoid returning `None` or boolean for errors).
- Clearly document types of exceptions that a method can raise.
- Use built-in Python exceptions or define clear custom exceptions, explicitly documented.

✅ Recommended Exception Chaining:



try:
    perform_action()
except ServiceError as ex:
    raise ClientSpecificError("Friendly error description.") from ex



---

## ✅ Parameter Validation

- ✅ Validate parameters used locally (e.g., URLs, local logical constraints).
- ⛔️ Avoid validating parameters meant for external services—let external service perform their validation.
- ⛔️ Prefer structural validation to using `isinstance` checks, ensuring parameters conform to expected interfaces rather than explicit types.

---

## ✅ Supporting Models and Types

- ✅ Allow dictionaries (`dict`) interchangeable with model classes.
- ✅ Provide informative yet concise implementations of `__repr__` (max ~1024 chars):



class Example:
    def __repr__(self):
        data = {"name": self.name, "value": self.value}
        return f"Example({str(data)[:1024]})"



---

## ✅ Extensible Enumerations

- ✅ Use enumeration types that seamlessly handle string values easily.
- ✅ Consider case-insensitive comparisons for improved usability.



from enum import Enum

class MyEnum(str, Enum):
    OPTION_ONE = 'option_one'
    OPTION_TWO = 'option_two'



---

## ✅ Logging and Tracing

- ✅ Utilize Python’s standard `logging` module.
- ✅ Match logger names closely to module/package name structure:



# module: package.submodule 
logger = logging.getLogger('package.submodule')



- ✅ Define clear logging levels:
  - `ERROR`: For unrecoverable library-level errors.
  - `WARNING`: For significant, recoverable issues or handled exceptions.
  - `INFO`: For successful operations or significant events.
  - `DEBUG`: For detailed diagnostic and development tracing.

- ✅ Redact sensitive information in logs unless explicitly in DEBUG mode.
- ✅ Include exception details at WARNING level; append stack traces only at DEBUG log level.

---

## ✅ Sync and Async APIs

- Clearly separate synchronous and asynchronous APIs:
  - Sync: `my_library.Client`
  - Async: `my_library.aio.AsyncClient`

Example of clear async namespace:



from my_library.aio import AsyncClient



---

## ✅ Testing Practices

- ✅ Use `pytest` and `pytest-asyncio` consistently for testing.
- ✅ Write unit, integration, and functional tests executable independently and concurrently.
- ✅ Maintain test suites to ensure regular quality control through continuous integration.

---

## ✅ Python Coding Style (PEP8)

- ✅ Follow `PEP8` guidelines consistently:
  - snake_case for module names, functions, variable names, and instance methods.
  - PascalCase for class names.
  - CAPITALIZED_SNAKE_CASE for constant naming.
- ✅ Use explicit type annotations (`PEP484`).
- ✅ Clearly document public API elements and behaviors through comprehensive docstrings.

---

## ✅ Exception Handling

- ✅ Explicit exception chaining clearly communicates context:



try:
    do_something()
except Exception as e:
    raise LibraryError("Meaningful error message here.") from e



---

## ✅ Distributed Tracing

- Favor decorator-based tracing solutions if suitable:



from tracing_library import distributed_trace

@distributed_trace
def perform_task():
    pass



---

## ✅ Documentation and Docstrings

Provide essential documentation deliverables:

- **`README.md`**: Quick installation, concise setup instructions, and basic usage examples.
- **Quickstarts and conceptual documentation**: Tutorials, how-to guides, and detailed conceptual explanations.
- **Complete API reference documentation** auto-generated from comprehensive docstrings.

Example docstring format:



def get_resource(name, **kwargs):
    """
    Gets the resource identified by name.

    :param name: The name identifying the resource.
    :type name: str

    :keyword int retries: The number of retries attempted in case of failure. Defaults to 3.
    :raises ValueError: If the provided `name` is invalid.
    """



✅ Clearly document expected exceptions, parameter types, keywords, defaults, and side-effects.

---

## ✅ Documentation Style

- ✅ Adhere strictly to established Python documentation style guidelines (e.g., Google Python style guide).
- ✅ Use direct, concise, and clear language. Avoid jargon and passive voice wherever possible.