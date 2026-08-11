import logging

log = logging.getLogger("alerts")


def send_failure_alert(job_id: str, error: str, attempts: int) -> None:
    log.critical(
        f"[ALERT] Batch job {job_id} permanently failed after {attempts} attempts. "
        f"Last error: {error}. This requires human attention."
    )
