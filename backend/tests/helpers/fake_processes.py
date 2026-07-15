# test-only fake subprocess helpers for SimulatorClient isolation
# launched via injected _spawn only; never via production CLI
from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

# write marker then sleep forever (timeout tests)
_HANG_SCRIPT = """
import sys, time
from pathlib import Path
Path(sys.argv[1]).write_text("started", encoding="utf-8")
time.sleep(3600)
"""

# write provided result bytes then exit with code
_WRITE_RESULT_SCRIPT = """
import sys
from pathlib import Path
# argv: marker_path, result_path, exit_code, result_bytes_hex
marker = Path(sys.argv[1])
result_path = Path(sys.argv[2])
exit_code = int(sys.argv[3])
payload = bytes.fromhex(sys.argv[4]) if sys.argv[4] else b""
if payload:
    result_path.write_bytes(payload)
marker.write_text("done", encoding="utf-8")
sys.stdout.buffer.write(b"fake-stdout")
sys.stderr.buffer.write(b"fake-stderr")
raise SystemExit(exit_code)
"""

# exit nonzero without writing result
_FAIL_SCRIPT = """
import sys
sys.stdout.buffer.write(b"fail-out")
sys.stderr.buffer.write(b"fail-err")
raise SystemExit(int(sys.argv[1]))
"""


def helpers_dir() -> Path:
    return Path(__file__).resolve().parent


def write_helper_scripts(dest: Path) -> dict[str, Path]:
    dest.mkdir(parents=True, exist_ok=True)
    hang = dest / "hang.py"
    write_result = dest / "write_result.py"
    fail = dest / "fail.py"
    hang.write_text(_HANG_SCRIPT, encoding="utf-8")
    write_result.write_text(_WRITE_RESULT_SCRIPT, encoding="utf-8")
    fail.write_text(_FAIL_SCRIPT, encoding="utf-8")
    return {"hang": hang, "write_result": write_result, "fail": fail}


# spawn that ignores simulator argv and runs a Python helper instead
def make_script_spawn(
    script: Path,
    *extra_args: str,
) -> Callable[..., Awaitable[asyncio.subprocess.Process]]:
    async def _spawn(
        *_cmd: str,
        stdout: Any = None,
        stderr: Any = None,
        **_kwargs: Any,
    ) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            sys.executable,
            str(script),
            *extra_args,
            stdout=stdout,
            stderr=stderr,
        )

    return _spawn


# spawn that writes result.json from fixture JSON then exits 0
def make_fixture_result_spawn(
    result_payload: dict[str, Any] | bytes,
) -> Callable[..., Awaitable[asyncio.subprocess.Process]]:
    if isinstance(result_payload, bytes):
        raw = result_payload
    else:
        raw = json.dumps(result_payload).encode("utf-8")

    async def _spawn(
        *cmd: str,
        stdout: Any = None,
        stderr: Any = None,
        **_kwargs: Any,
    ) -> asyncio.subprocess.Process:
        # locate --output path in the produced command vector
        output_path: Path | None = None
        for i, part in enumerate(cmd):
            if part == "--output" and i + 1 < len(cmd):
                output_path = Path(cmd[i + 1])
                break
        if output_path is None:
            raise RuntimeError("fake spawn missing --output")

        async def _run() -> asyncio.subprocess.Process:
            output_path.write_bytes(raw)
            return await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(b'out'); "
                "sys.stderr.buffer.write(b'err'); raise SystemExit(0)",
                stdout=stdout,
                stderr=stderr,
            )

        return await _run()

    return _spawn


# spawn that exits with a fixed code and optional result write
def make_exit_spawn(
    exit_code: int,
    *,
    write_result: bytes | None = None,
    stdout_data: bytes = b"",
    stderr_data: bytes = b"",
) -> Callable[..., Awaitable[asyncio.subprocess.Process]]:
    async def _spawn(
        *cmd: str,
        stdout: Any = None,
        stderr: Any = None,
        **_kwargs: Any,
    ) -> asyncio.subprocess.Process:
        if write_result is not None:
            for i, part in enumerate(cmd):
                if part == "--output" and i + 1 < len(cmd):
                    Path(cmd[i + 1]).write_bytes(write_result)
                    break
        stdout_hex = stdout_data.hex()
        stderr_hex = stderr_data.hex()
        code = (
            "import sys\n"
            f"sys.stdout.buffer.write(bytes.fromhex({stdout_hex!r}))\n"
            f"sys.stderr.buffer.write(bytes.fromhex({stderr_hex!r}))\n"
            f"raise SystemExit({exit_code})\n"
        )
        return await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            stdout=stdout,
            stderr=stderr,
        )

    return _spawn
