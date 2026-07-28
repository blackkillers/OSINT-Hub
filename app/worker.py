"""
OSINT-Hub Celery Async Task Worker & CLI Subprocess Orchestrator
=================================================================
Handles non-blocking, isolated execution of OSINT CLI tools with strict 3-minute hard timeouts,
sandboxed subprocess management (no shell=True), and structured logging via Structlog.
"""

import asyncio
import os
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from celery import Celery
import structlog

from app.schemas import (
    EdgeModel,
    NodeModel,
    NodeTypeEnum,
    ScanResult,
    StatusEnum,
    TargetTypeEnum,
)

# Initialize Structlog logger
logger = structlog.get_logger(__name__)

# Environment configurations
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
DEFAULT_CLI_TIMEOUT_SECONDS = int(os.getenv("CLI_TIMEOUT_SECONDS", "180")) # 3 minutes hard timeout

# Instantiate Celery Application
celery_app = Celery(
    "osint_hub_workers",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=210,  # 3m30s Celery hard limit
    task_soft_time_limit=190,
)


async def execute_cli_command(
    cmd: List[str],
    timeout_seconds: int = DEFAULT_CLI_TIMEOUT_SECONDS,
    env: Optional[Dict[str, str]] = None,
    socks_proxy: Optional[str] = None,
) -> tuple[int, str, str]:
    """
    Executes a CLI command in a sandboxed asyncio subprocess.
    NEVER uses shell=True. Pass arguments strictly as a list of strings.

    Returns:
        tuple (exit_code, stdout_str, stderr_str)
    """
    exec_env = os.environ.copy()
    if env:
        exec_env.update(env)

    if socks_proxy:
        exec_env["ALL_PROXY"] = socks_proxy
        exec_env["HTTP_PROXY"] = socks_proxy
        exec_env["HTTPS_PROXY"] = socks_proxy

    # Create subprocess strictly without shell=True
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=exec_env,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=float(timeout_seconds)
        )
        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
        return process.returncode or 0, stdout, stderr

    except asyncio.TimeoutError:
        try:
            process.kill()
            await process.wait()
        except Exception:
            pass
        raise TimeoutError(f"Command execution timed out after {timeout_seconds} seconds")


async def run_module_async(
    scan_id_str: str,
    target: str,
    target_type_str: str,
    module_name: str,
) -> Dict[str, Any]:
    """
    Asynchronous executor wrapper for OSINT modules.
    Dynamically loads module class, runs execution with safety handling,
    and returns a guaranteed valid ScanResult dictionary.
    """
    start_time = time.time()
    scan_id = UUID(scan_id_str)
    target_type = TargetTypeEnum(target_type_str)

    log = logger.bind(scan_id=scan_id_str, module=module_name, target=target)
    log.info("Starting module execution")

    try:
        # Dynamic module loading from app.modules
        if module_name == "email_holehe":
            from app.modules.email_holehe import HoleheModule
            module_instance = HoleheModule()
            result = await asyncio.wait_for(
                module_instance.run(scan_id=scan_id, target=target, target_type=target_type),
                timeout=float(DEFAULT_CLI_TIMEOUT_SECONDS),
            )
        else:
            # Fallback mock/generic handler for undefined module names during setup
            result = ScanResult(
                scan_id=scan_id,
                target=target,
                target_type=target_type,
                module_name=module_name,
                status=StatusEnum.FAILED,
                error=f"Module '{module_name}' is not registered or implemented yet.",
                execution_time_ms=int((time.time() - start_time) * 1000),
            )

        execution_ms = int((time.time() - start_time) * 1000)
        result.execution_time_ms = execution_ms
        log.info("Module execution finished", status=result.status, time_ms=execution_ms)
        return result.model_dump(mode="json")

    except asyncio.TimeoutError:
        execution_ms = int((time.time() - start_time) * 1000)
        log.warning("Module execution timed out", time_ms=execution_ms)
        fallback = ScanResult(
            scan_id=scan_id,
            target=target,
            target_type=target_type,
            module_name=module_name,
            status=StatusEnum.TIMEOUT,
            execution_time_ms=execution_ms,
            error=f"Module execution timed out after {DEFAULT_CLI_TIMEOUT_SECONDS}s",
        )
        return fallback.model_dump(mode="json")

    except Exception as exc:
        execution_ms = int((time.time() - start_time) * 1000)
        log.error("Module execution failed with unexpected exception", error=str(exc), exc_info=True)
        fallback = ScanResult(
            scan_id=scan_id,
            target=target,
            target_type=target_type,
            module_name=module_name,
            status=StatusEnum.FAILED,
            execution_time_ms=execution_ms,
            error=f"Execution error: {str(exc)}",
        )
        return fallback.model_dump(mode="json")


@celery_app.task(bind=True, name="osint.run_module_task")
def run_module_task(
    self,
    scan_id_str: str,
    target: str,
    target_type_str: str,
    module_name: str,
) -> Dict[str, Any]:
    """
    Celery task entrypoint. Bridges Celery synchronous execution loop
    with Python's async/await asyncio event loop.
    """
    return asyncio.run(
        run_module_async(
            scan_id_str=scan_id_str,
            target=target,
            target_type_str=target_type_str,
            module_name=module_name,
        )
    )
