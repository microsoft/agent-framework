# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import pytest

from agent_framework_local_codeact import LocalExecuteCodeTool
from agent_framework_local_codeact._validator import CodeValidationError, validate_code


def test_validate_allows_basic_arithmetic() -> None:
    """Basic arithmetic should be allowed."""
    code = "x = 1 + 2\ny = x * 3"
    validate_code(code)  # Should not raise


def test_validate_allows_tool_calls() -> None:
    """Tool calls with await should be allowed."""
    code = "result = await my_tool(param='value')"
    validate_code(code)  # Should not raise


def test_validate_allows_call_tool_fallback() -> None:
    """The call_tool fallback should be allowed."""
    code = "result = await call_tool('my_tool', param='value')"
    validate_code(code)  # Should not raise


def test_validate_allows_asyncio_gather() -> None:
    """asyncio.gather for fan-out should be allowed."""
    code = """import asyncio
results = await asyncio.gather(tool_a(), tool_b())"""
    validate_code(code)  # Should not raise


def test_validate_allows_pathlib_file_operations() -> None:
    """Pathlib for file operations should be allowed."""
    code = """from pathlib import Path
content = Path('/input/file.txt').read_text(encoding='utf-8')"""
    validate_code(code)  # Should not raise


def test_validate_allows_print() -> None:
    """Print for output should be allowed."""
    code = "print('hello', 'world')"
    validate_code(code)  # Should not raise


def test_validate_allows_json_operations() -> None:
    """JSON operations should be allowed."""
    code = """import json
data = json.dumps({'key': 'value'})"""
    validate_code(code)  # Should not raise


def test_validate_allows_comprehensions() -> None:
    """List/dict/set comprehensions should be allowed."""
    code = """squares = [x**2 for x in range(10)]
evens = {x for x in range(10) if x % 2 == 0}
mapping = {x: x**2 for x in range(5)}"""
    validate_code(code)  # Should not raise


def test_validate_allows_control_flow() -> None:
    """Control flow (if/for/while) should be allowed."""
    code = """for i in range(10):
    if i % 2 == 0:
        print(i)
    else:
        continue

x = 0
while x < 5:
    x += 1"""
    validate_code(code)  # Should not raise


def test_validate_allows_os_environ() -> None:
    """Safe os.environ operations should be allowed."""
    code = """import os
value = os.environ.get('KEY', 'default')"""
    validate_code(code)  # Should not raise


def test_validate_allows_os_path() -> None:
    """os.path operations should be allowed."""
    code = """import os
joined = os.path.join('/base', 'file.txt')"""
    validate_code(code)  # Should not raise


def test_validate_blocks_eval() -> None:
    """eval() should be blocked."""
    code = "result = eval('1 + 1')"
    with pytest.raises(CodeValidationError) as exc_info:
        validate_code(code)
    assert "eval" in str(exc_info.value)


def test_validate_blocks_exec() -> None:
    """exec() should be blocked."""
    code = "exec('print(1)')"
    with pytest.raises(CodeValidationError) as exc_info:
        validate_code(code)
    assert "exec" in str(exc_info.value)


def test_validate_blocks_compile() -> None:
    """compile() should be blocked."""
    code = "code_obj = compile('1 + 1', '<string>', 'eval')"
    with pytest.raises(CodeValidationError) as exc_info:
        validate_code(code)
    assert "compile" in str(exc_info.value)


def test_validate_blocks_import_subprocess() -> None:
    """Subprocess imports should be blocked."""
    code = "import subprocess"
    with pytest.raises(CodeValidationError) as exc_info:
        validate_code(code)
    assert "subprocess" in str(exc_info.value)


def test_validate_blocks_import_sys() -> None:
    """sys imports should be blocked."""
    code = "import sys"
    with pytest.raises(CodeValidationError) as exc_info:
        validate_code(code)
    assert "sys" in str(exc_info.value)


def test_validate_blocks_import_socket() -> None:
    """socket imports should be blocked."""
    code = "import socket"
    with pytest.raises(CodeValidationError) as exc_info:
        validate_code(code)
    assert "socket" in str(exc_info.value)


def test_validate_blocks_import_requests() -> None:
    """requests imports should be blocked."""
    code = "import requests"
    with pytest.raises(CodeValidationError) as exc_info:
        validate_code(code)
    assert "requests" in str(exc_info.value)


def test_validate_blocks_unknown_import() -> None:
    """Unknown imports should be blocked."""
    code = "import unknown_module"
    with pytest.raises(CodeValidationError) as exc_info:
        validate_code(code)
    assert "unknown_module" in str(exc_info.value)


def test_validate_blocks_os_system() -> None:
    """os.system() should be blocked."""
    code = """import os
os.system('ls')"""
    with pytest.raises(CodeValidationError) as exc_info:
        validate_code(code)
    assert "os.system" in str(exc_info.value)


def test_validate_blocks_os_exec() -> None:
    """os.exec* operations should be blocked."""
    code = """import os
os.execv('/bin/ls', ['ls'])"""
    with pytest.raises(CodeValidationError) as exc_info:
        validate_code(code)
    assert "os.execv" in str(exc_info.value)


def test_validate_blocks_os_popen() -> None:
    """os.popen() should be blocked."""
    code = """import os
pipe = os.popen('ls')"""
    with pytest.raises(CodeValidationError) as exc_info:
        validate_code(code)
    assert "os.popen" in str(exc_info.value)


def test_validate_blocks_globals() -> None:
    """globals() should be blocked."""
    code = "g = globals()"
    with pytest.raises(CodeValidationError) as exc_info:
        validate_code(code)
    assert "globals" in str(exc_info.value)


def test_validate_blocks_locals() -> None:
    """locals() should be blocked."""
    code = "l = locals()"
    with pytest.raises(CodeValidationError) as exc_info:
        validate_code(code)
    assert "locals" in str(exc_info.value)


def test_validate_blocks_import_magic() -> None:
    """__import__() should be blocked."""
    code = "mod = __import__('os')"
    with pytest.raises(CodeValidationError) as exc_info:
        validate_code(code)
    assert "__import__" in str(exc_info.value)


def test_validate_custom_allowed_imports() -> None:
    """Custom allowed_imports should replace defaults."""
    # csv is not in the default allow-list
    code_with_csv = "import csv"
    with pytest.raises(CodeValidationError):
        validate_code(code_with_csv)

    # But it should work with custom allow-list
    custom_allowed = {"csv", "json"}
    validate_code(code_with_csv, allowed_imports=custom_allowed)


def test_validate_custom_blocked_imports() -> None:
    """Custom blocked_imports should replace defaults."""
    # json is normally allowed
    code_with_json = "import json"
    validate_code(code_with_json)  # Should not raise

    # But block it with custom block-list
    custom_blocked = {"json"}
    with pytest.raises(CodeValidationError) as exc_info:
        validate_code(code_with_json, blocked_imports=custom_blocked)
    assert "json" in str(exc_info.value)


def test_validate_custom_blocked_builtins() -> None:
    """Custom blocked_builtins should replace defaults."""
    # len is normally allowed (not in default blocked list)
    code_with_len = "x = len([1, 2, 3])"
    validate_code(code_with_len)  # Should not raise

    # But block it with custom block-list
    custom_blocked = {"len"}
    with pytest.raises(CodeValidationError) as exc_info:
        validate_code(code_with_len, blocked_builtins=custom_blocked)
    assert "len" in str(exc_info.value)


async def test_tool_with_custom_allowed_imports() -> None:
    """LocalExecuteCodeTool should respect custom allowed_imports."""
    # csv is not in default allow-list
    tool = LocalExecuteCodeTool(allowed_imports={"csv", "json"})
    result = await tool._run_code(code="import csv\n{'ok': True}")
    # Should execute successfully
    assert len(result) > 0
    assert not any(c.type == "error" for c in result)


async def test_tool_with_custom_blocked_imports() -> None:
    """LocalExecuteCodeTool should respect custom blocked_imports."""
    # json is normally allowed
    tool = LocalExecuteCodeTool(blocked_imports={"json"})
    result = await tool._run_code(code="import json")
    # Should be blocked
    assert len(result) == 1
    assert result[0].type == "error"
    assert "json" in (result[0].error_details or "")
