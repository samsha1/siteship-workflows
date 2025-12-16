"""
Airflow Plugin: Fix for SerializedDagModel race condition bug
This patches the write_dag method to handle None values and concurrent writes properly.
Author: Siteship System Fix
Version: 1.6 - Optimized for Airflow 3.1.1+ (robust bundle support)
"""
from __future__ import annotations
import json
import logging
from datetime import timedelta
from hashlib import md5
from typing import TYPE_CHECKING
import zlib
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
    processor_subdir: str | None = None,
    bundle_name: str | None = None,
    bundle_version: str | None = None,
    session: Session = None,
) -> bool:
    """
    Patched version of SerializedDagModel.write_dag that properly handles:
    1. None values when DAG doesn't exist yet
    2. Race conditions between scheduler and dag-processor
    3. Database row locking to prevent concurrent writes
    4. bundle_name and bundle_version parameters for Airflow 3.1+
    """
    try:
        # Query with row-level locking to prevent race conditions
        latest_ser_dag = (
            session.query(SerializedDagModel)
            .filter(SerializedDagModel.dag_id == dag.dag_id)
            .with_for_update(nowait=False)
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
       
        # Prepare data and hash
        dag_data = SerializedDAG.to_dict(dag)
        dag_data_json = json.dumps(dag_data, sort_keys=True).encode("utf-8")
        new_dag_hash = md5(dag_data_json).hexdigest()
       
        # Additional check: If exists and hash/subdir/bundle match, skip
        if (
            latest_ser_dag
            and latest_ser_dag.dag_hash == new_dag_hash
            and latest_ser_dag.processor_subdir == processor_subdir
            and latest_ser_dag.bundle_name == bundle_name
            and getattr(latest_ser_dag, 'bundle_version', None) == bundle_version
        ):
            log.debug("Serialized DAG (%s) is unchanged. Skipping writing to DB", dag.dag_id)
            return False
       
        # CRITICAL FIX: Create new SerializedDagModel if it doesn't exist
        if latest_ser_dag is None:
            log.info("Creating new serialized DAG entry for: %s", dag.dag_id)
            latest_ser_dag = SerializedDagModel(
                dag=dag,
                processor_subdir=processor_subdir,
                bundle_name=bundle_name,
                bundle_version=bundle_version
            )
            session.add(latest_ser_dag)
            session.flush()
            log.debug("Successfully serialized new DAG: %s (bundle: %s@%s)", dag.dag_id, bundle_name or "default", bundle_version or "latest")
            return True
       
        # Update existing entry
        latest_ser_dag.fileloc = dag.fileloc
        latest_ser_dag.fileloc_hash = SerializedDagModel.dag_fileloc_hash(dag.fileloc)
        # Assuming compression is enabled (default in Airflow 3.x)
        latest_ser_dag.data_compressed = zlib.compress(dag_data_json, level=6)
        latest_ser_dag.last_updated = timezone.utcnow()
        latest_ser_dag.dag_hash = new_dag_hash
        latest_ser_dag.processor_subdir = processor_subdir
        
        # Safety check for Airflow 3.x+ fields
        if hasattr(latest_ser_dag, 'bundle_name'):
            latest_ser_dag.bundle_name = bundle_name
        if hasattr(latest_ser_dag, 'bundle_version'):
            latest_ser_dag.bundle_version = bundle_version
       
        # Flush changes
        session.flush()
       
        log.debug("Successfully serialized DAG: %s (bundle: %s@%s)", dag.dag_id, bundle_name or "default", bundle_version or "latest")
        return True
       
    except Exception as e:
        log.error(
            "Error serializing DAG %s: %s - %s",
            dag.dag_id,
            type(e).__name__,
            str(e),
            exc_info=True,
        )
        session.rollback()
        return False
# Apply the patch at module load time
log.info("=" * 80)
log.info("🔧 Applying SerializedDagModel.write_dag patch v1.5 (Airflow 3.1.5)")
log.info(" This fixes: AttributeError: 'NoneType' object has no attribute '_data'")
log.info(" Full support for bundle_name and bundle_version")
log.info("=" * 80)
SerializedDagModel.write_dag = staticmethod(patched_write_dag)
class SerializedDagFixPlugin(AirflowPlugin):
    """
    Plugin to register the serialized DAG fix.
    This ensures the patch is loaded when Airflow starts.
    """
    name = "serialized_dag_fix_plugin"