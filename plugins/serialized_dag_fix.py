"""
Airflow Plugin to fix the SerializedDagModel.write_dag race condition bug
This patches the issue where latest_ser_dag is None causing AttributeError
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from airflow.plugins_manager import AirflowPlugin
from airflow.models.serialized_dag import SerializedDagModel
from airflow.serialization.serialized_objects import SerializedDAG
from airflow.utils.session import provide_session

if TYPE_CHECKING:
    from airflow.models.dag import DAG
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# Store the original method
_original_write_dag = SerializedDagModel.write_dag


@provide_session
def patched_write_dag(
    dag: DAG,
    min_update_interval: int | None = None,
    session: Session = None,
) -> bool:
    """
    Patched version of write_dag that handles None latest_ser_dag gracefully.
    
    This fixes the race condition where multiple processes try to serialize
    the same DAG simultaneously, causing one to get None when querying.
    """
    from datetime import timedelta
    from airflow.utils import timezone
    from sqlalchemy.orm.exc import NoResultFound
    
    # Serialize the DAG
    serialized_dag = SerializedDAG.from_dict(SerializedDAG.to_dict(dag))
    
    try:
        # Use with_for_update() to lock the row and prevent race conditions
        latest_ser_dag = (
            session.query(SerializedDagModel)
            .filter(SerializedDagModel.dag_id == dag.dag_id)
            .with_for_update()
            .one_or_none()
        )
        
        # Check if we need to update based on min_update_interval
        if latest_ser_dag and min_update_interval is not None:
            if (
                latest_ser_dag.last_updated
                and timezone.utcnow() - latest_ser_dag.last_updated
                < timedelta(seconds=min_update_interval)
            ):
                log.debug(
                    "Skipping DAG serialization for %s - updated recently",
                    dag.dag_id
                )
                return False
        
        # Create new serialized DAG object if it doesn't exist
        if latest_ser_dag is None:
            log.info("Creating new serialized DAG entry for %s", dag.dag_id)
            latest_ser_dag = SerializedDagModel(dag_id=dag.dag_id)
            session.add(latest_ser_dag)
        
        # Update the data - this is where the original code fails
        # because it doesn't check if latest_ser_dag is None
        latest_ser_dag._data = serialized_dag._data
        latest_ser_dag.last_updated = timezone.utcnow()
        latest_ser_dag.dag_hash = SerializedDagModel._hash_dag(dag)
        latest_ser_dag.fileloc = dag.fileloc
        
        session.flush()
        log.info("Successfully serialized DAG: %s", dag.dag_id)
        return True
        
    except Exception as e:
        log.error(
            "Error serializing DAG %s: %s",
            dag.dag_id,
            str(e),
            exc_info=True
        )
        # Rollback the transaction on error
        session.rollback()
        return False


# Apply the patch
log.info("Applying SerializedDagModel.write_dag patch to fix race condition")
SerializedDagModel.write_dag = staticmethod(patched_write_dag)


class SerializedDagFixPlugin(AirflowPlugin):
    """Plugin to register the serialized DAG fix"""
    name = "serialized_dag_fix"