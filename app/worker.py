"""
OSINT-Hub Celery Worker — Dynamic Module Dispatcher
====================================================
Routes tasks to the correct OSINT module class dynamically.
All modules return a ScanResult. Errors are isolated per module.
"""

import asyncio
import os
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from celery import Celery
import structlog

from app.schemas import ScanResult, StatusEnum, TargetTypeEnum

logger = structlog.get_logger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
DEFAULT_CLI_TIMEOUT_SECONDS = int(os.getenv("CLI_TIMEOUT_SECONDS", "180"))

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
    task_time_limit=210,
    task_soft_time_limit=190,
    result_expires=86400,  # Keep results 24h in Redis
)


async def execute_cli_command(
    cmd: List[str],
    timeout_seconds: int = DEFAULT_CLI_TIMEOUT_SECONDS,
    env: Optional[Dict[str, str]] = None,
    socks_proxy: Optional[str] = None,
) -> tuple[int, str, str]:
    """Execute CLI command safely without shell=True."""
    exec_env = os.environ.copy()
    if env:
        exec_env.update(env)
    if socks_proxy:
        exec_env["ALL_PROXY"] = socks_proxy
        exec_env["HTTP_PROXY"] = socks_proxy
        exec_env["HTTPS_PROXY"] = socks_proxy

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
        return (
            process.returncode or 0,
            stdout_bytes.decode("utf-8", errors="replace").strip(),
            stderr_bytes.decode("utf-8", errors="replace").strip(),
        )
    except asyncio.TimeoutError:
        try:
            process.kill()
            await process.wait()
        except Exception:
            pass
        raise TimeoutError(f"CLI timed out after {timeout_seconds}s")


def _load_module(module_name: str):
    """Dynamically load the module class for a given module name."""
    MODULE_REGISTRY = {
        "email_holehe": ("app.modules.email_holehe", "HoleheModule"),
        "email_mosint": ("app.modules.email_mosint", "MOSINTModule"),
        "email_ghunt": ("app.modules.email_ghunt", "GHuntModule"),
        "email_epieos": ("app.modules.email_epieos", "EpieosModule"),
        "username_maigret": ("app.modules.username_maigret", "MaigretModule"),
        "username_sherlock": ("app.modules.username_sherlock", "SherlockModule"),
        "username_tookie": ("app.modules.username_tookie", "TookieModule"),
        "username_whatsmyname": ("app.modules.username_whatsmyname", "WhatsMyNameModule"),
        "phone_phoneinfoga": ("app.modules.phone_phoneinfoga", "PhoneInfogaModule"),
        "phone_toutatis": ("app.modules.phone_toutatis", "ToutatisModule"),
        "darkweb_onionsearch": ("app.modules.darkweb_onionsearch", "OnionSearchModule"),
        "geoint_shodan": ("app.modules.geoint_shodan", "ShodanModule"),
        "geoint_censys": ("app.modules.geoint_censys", "CensysModule"),
        "domain_builtwith": ("app.modules.domain_builtwith", "BuiltWithModule"),
        "domain_osintsh": ("app.modules.domain_osintsh", "OsintShModule"),
        "leak_daprofiler": ("app.modules.leak_daprofiler", "DaProfilerModule"),
    }
    if module_name not in MODULE_REGISTRY:
        return None
    module_path, class_name = MODULE_REGISTRY[module_name]
    import importlib
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name)()
    except Exception as e:
        logger.warning("Module import failed", module=module_name, error=str(e))
        return None


async def run_module_async(
    scan_id_str: str,
    target: str,
    target_type_str: str,
    module_name: str,
) -> Dict[str, Any]:
    start_time = time.time()
    scan_id = UUID(scan_id_str)
    target_type = TargetTypeEnum(target_type_str)
    log = logger.bind(scan_id=scan_id_str, module=module_name, target=target)
    log.info("Starting module")

    def _failed(msg: str, status: StatusEnum = StatusEnum.FAILED) -> Dict[str, Any]:
        return ScanResult(
            scan_id=scan_id,
            target=target,
            target_type=target_type,
            module_name=module_name,
            status=status,
            execution_time_ms=int((time.time() - start_time) * 1000),
            error=msg,
        ).model_dump(mode="json")

    module_instance = _load_module(module_name)
    if module_instance is None:
        return _failed(f"Module '{module_name}' not yet implemented — skipping.")

    try:
        result = await asyncio.wait_for(
            module_instance.run(scan_id=scan_id, target=target, target_type=target_type),
            timeout=float(DEFAULT_CLI_TIMEOUT_SECONDS),
        )
        result.execution_time_ms = int((time.time() - start_time) * 1000)
        log.info("Module done", status=result.status)
        return result.model_dump(mode="json")

    except asyncio.TimeoutError:
        log.warning("Module timed out")
        return _failed(f"Timed out after {DEFAULT_CLI_TIMEOUT_SECONDS}s", StatusEnum.TIMEOUT)

    except Exception as exc:
        log.error("Module crashed", error=str(exc))
        return _failed(f"Execution error: {exc}")


@celery_app.task(bind=True, name="osint.run_module_task")
def run_module_task(
    self,
    scan_id_str: str,
    target: str,
    target_type_str: str,
    module_name: str,
) -> Dict[str, Any]:
    """Celery task: bridges sync Celery loop to async module execution."""
    return asyncio.run(
        run_module_async(
            scan_id_str=scan_id_str,
            target=target,
            target_type_str=target_type_str,
            module_name=module_name,
        )
    )
