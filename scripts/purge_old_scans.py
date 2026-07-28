#!/usr/bin/env python3
"""
OSINT-Hub Data Privacy & Retention Purge Script
================================================
Automated Cron task purging raw scan results and logs older than 7 days (configurable).
Guarantees compliance with strict data privacy guidelines.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
import asyncpg
import structlog

# Initialize logger
logger = structlog.get_logger("osint_purge_cron")

# Retention period configuration
RETENTION_DAYS = int(os.getenv("DATA_RETENTION_DAYS", "7"))
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://osint_admin:osint_pass@postgres:5432/osint_hub_db")

# Convert SQLAlchemy asyncpg URL if necessary
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def purge_expired_scans():
    """Purges scans, raw results, graph nodes, and edges older than RETENTION_DAYS."""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    logger.info("Starting automated data retention purge", cutoff_date=cutoff_date.isoformat(), retention_days=RETENTION_DAYS)

    try:
        conn = await asyncpg.connect(DATABASE_URL)
        
        # Delete scans older than cutoff date (Cascades to scan_module_results, graph_nodes, graph_edges)
        deleted_scans = await conn.execute(
            """
            DELETE FROM scans
            WHERE created_at < $1;
            """,
            cutoff_date
        )

        logger.info("Purge completed successfully", result=deleted_scans)
        await conn.close()

    except Exception as exc:
        logger.error("Failed to execute data retention purge", error=str(exc))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(purge_expired_scans())
