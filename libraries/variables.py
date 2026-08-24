"""Robot variable file. Exposes settings as ${UPPERCASE} variables.

Robot calls get_variables() automatically. Nothing to configure.
"""

from __future__ import annotations

from libraries.config import get_settings


def get_variables() -> dict[str, object]:
    settings = get_settings()
    return {
        "ENV": settings.env,
        "DB_HOST": settings.db_host,
        "DB_NAME": settings.db_name,
        "DB_CONFIGURED": settings.db_configured,
        "CLIENT_ENTITY": settings.client_entity,
        "TRIGGER_STATUS": settings.trigger_status,
        "CRED_ACTIONS": settings.cred_actions,
        "SERVICE_ADDRESS_TYPE": settings.service_address_type,
        "CAQH_ID_TYPE": settings.caqh_id_type,
        "AWS_REGION": settings.aws_region,
        "GLUE_STATUS_JOB": settings.glue_status_job,
        "GLUE_RETRY_JOB": settings.glue_retry_job,
        "RETRY_TABLE": settings.retry_table,
        "FALLOUT_TABLE": settings.fallout_table,
        "S3_BUCKET": settings.s3_bucket,
        "BOOKMARK_KEY": settings.bookmark_key,
        "MAX_RETRY_ATTEMPTS": settings.max_retry_attempts,
    }