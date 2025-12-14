"""
Airflow Plugin: Fix for SerializedDagModel race condition bug
This patches the write_dag method to handle None values and concurrent writes properly.

Author: System Fix
Version: 1.1 - Fixed for Airflow 2.10.4+ with bundle_name parameter
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from airflow.plugins_manager import AirflowPlugin
from airflow.models.serialized_dag import SerializedDagModel
from airflow.serialization.serialized_objects import SerializedDAG
from airflow.utils.session import provide_session
from airflow.utils import timezone

if TYPE_CHECKING:
    from airflow.models.dag import DAG
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# Store original method reference
_original_write_dag = SerializedDagModel.write_dag


@provide_session
def patched_write_dag(
    dag: DAG,
    min_update_interval: int | None = None,
    bundle_name: str | None = None,  # Added for Airflow 2.10.4+
    session: Session = None,
) -> bool:
    """
    Patched version of SerializedDagModel.write_dag that properly handles:
    1. None values when DAG doesn't exist yet
    2. Race conditions between scheduler and dag-processor
    3. Database row locking to prevent concurrent writes
    4. bundle_name parameter for Airflow 2.10.4+
    
    This fixes: AttributeError: 'NoneType' object has no attribute '_data'
    """
    try:
        # Serialize the DAG
        serialized_dag = SerializedDAG.from_dict(SerializedDAG.to_dict(dag))
        
        # Query with row-level locking to prevent race conditions
        # with_for_update() ensures only one process can modify this row at a time
        latest_ser_dag = (
            session.query(SerializedDagModel)
            .filter(SerializedDagModel.dag_id == dag.dag_id)
            .with_for_update(nowait=False)  # Wait for lock instead of failing
            .one_or_none()
        )
        
        # Check if we should skip update based on min_update_interval
        if latest_ser_dag and min_update_interval is not None:
            if (
                latest_ser_dag.last_updated
                and timezone.utcnow() - latest_ser_dag.last_updated
                < timedelta(seconds=min_update_interval)
            ):
                log.debug(
                    "Skipping serialization for DAG %s - updated recently (within %s seconds)",
                    dag.dag_id,
                    min_update_interval,
                )
                return False
        
        # CRITICAL FIX: Create new SerializedDagModel if it doesn't exist
        # This is what Airflow's original code is missing!
        if latest_ser_dag is None:
            log.info("Creating new serialized DAG entry for: %s", dag.dag_id)
            latest_ser_dag = SerializedDagModel(dag_id=dag.dag_id)
            session.add(latest_ser_dag)
            # Flush to ensure the object is persisted before we try to update it
            session.flush()
        
        # Now it's safe to update the data
        latest_ser_dag._data = serialized_dag._data
        latest_ser_dag.last_updated = timezone.utcnow()
        latest_ser_dag.dag_hash = SerializedDagModel._hash_dag(dag)
        latest_ser_dag.fileloc = dag.fileloc
        
        # Set bundle_name if provided (Airflow 2.10.4+)
        if hasattr(latest_ser_dag, 'bundle_name') and bundle_name is not None:
            latest_ser_dag.bundle_name = bundle_name
        
        # Commit the changes
        session.flush()
        
        log.debug("Successfully serialized DAG: %s (bundle: %s)", dag.dag_id, bundle_name or "default")
        return True
        
    except Exception as e:
        log.error(
            "Error serializing DAG %s: %s - %s",
            dag.dag_id,
            type(e).__name__,
            str(e),
            exc_info=True,
        )
        # Rollback on any error to maintain database consistency
        session.rollback()
        return False


# Apply the patch at module load time
log.info("=" * 80)
log.info("🔧 Applying SerializedDagModel.write_dag patch v1.1 (Airflow 2.10.4+)")
log.info("   This fixes: AttributeError: 'NoneType' object has no attribute '_data'")
log.info("   Support for bundle_name parameter added")
log.info("=" * 80)

SerializedDagModel.write_dag = staticmethod(patched_write_dag)


class SerializedDagFixPlugin(AirflowPlugin):
    """
    Plugin to register the serialized DAG fix.
    This ensures the patch is loaded when Airflow starts.
    """
    name = "serialized_dag_fix_plugin"