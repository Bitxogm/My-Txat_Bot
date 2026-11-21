"""Run a parser on untrusted input in a child process that can be killed.

Threads can't be stopped, and a hostile PDF or image can spin a core or eat memory for as long
as it likes; a child process gets an address-space cap and is killed on timeout.
"""

import asyncio
import logging
import multiprocessing
from collections.abc import Callable
from multiprocessing.connection import Connection
from typing import Any

logger = logging.getLogger(__name__)

# Address space of the child: a decompression bomb fails there instead of taking the backend.
CHILD_MEMORY_BYTES = 1024 * 1024 * 1024

TIMEOUT = "timeout"
CRASHED = "crashed"
NO_LIMIT = "no_limit"

# One parse at a time: each one is a whole process, and a hostile file can use a full core.
_slot = asyncio.Semaphore(1)


def _child(conn: Connection, target: Callable[..., Any], args: tuple[Any, ...]) -> None:
    import os

    # Same user and files as the backend, but no secrets (SESSION_SECRET, cloud API key) in the
    # memory of the process that parses untrusted bytes.
    os.environ.clear()
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (CHILD_MEMORY_BYTES, CHILD_MEMORY_BYTES))
    except (ImportError, ValueError, OSError):
        # Without the memory cap a bomb could take the whole container: refuse to parse.
        conn.send(NO_LIMIT)
        conn.close()
        return
    try:
        conn.send(target(*args))
    except MemoryError:
        conn.send(CRASHED)
    finally:
        conn.close()


def _run(target: Callable[..., Any], args: tuple[Any, ...], time_limit: float) -> Any:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_child, args=(sender, target, args), daemon=True)
    process.start()
    sender.close()
    try:
        if not receiver.poll(time_limit):
            return TIMEOUT
        try:
            return receiver.recv()
        except EOFError:  # the child died (memory cap, crash in C code)
            return CRASHED
    finally:
        receiver.close()
        if process.is_alive():
            process.kill()
        process.join(timeout=5)


async def run_isolated(target: Callable[..., Any], *args: Any, time_limit: float) -> Any:
    """`target(*args)` in a child process. `target` must be a module-level function that never
    raises (it returns its own error codes). Returns its result, TIMEOUT, CRASHED or NO_LIMIT
    (the memory cap couldn't be set, so nothing was parsed)."""
    async with _slot:
        result = await asyncio.to_thread(_run, target, args, time_limit)
    if result in (CRASHED, NO_LIMIT):
        logger.warning("Isolated parser failed: %s", result)
    return result
