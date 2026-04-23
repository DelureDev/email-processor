"""Structured one-line RUN_SUMMARY emitted at the end of every pipeline run.

Format: '[RUN_SUMMARY] key=value key=value ...'
Designed for VM-side triage via `grep RUN_SUMMARY logs/processor.log | tail -N`.
"""
def compute_status(stats: dict) -> str:
    """Return 'OK' if no surface-able issues, 'FAIL' otherwise.

    FAIL is returned when any of: stats['errors'], stats['unknown_files'],
    stats['unmatched_clinics'], stats['missing_comments'] is non-empty.
    CRASH is set explicitly by the caller on an uncaught exception.
    """
    if stats.get('errors') or stats.get('unknown_files') \
            or stats.get('unmatched_clinics') or stats.get('missing_comments'):
        return 'FAIL'
    return 'OK'


def build_run_summary(
    stats: dict,
    *,
    status: str,
    duration_s: int,
    mode: str,
    exception_class: str | None = None,
) -> str:
    """Build the RUN_SUMMARY log line.

    Never raises — missing stats keys default to safe values.
    """
    parts = [
        '[RUN_SUMMARY]',
        f'status={status}',
        f'mode={mode}',
        f'files={stats.get("files_processed", 0)}',
        f'records={stats.get("total_records", 0)}',
        f'errors={len(stats.get("errors", []))}',
        f'unknown={len(stats.get("unknown_files", []))}',
        f'skip_rule={len(stats.get("skipped_files", []))}',
        f'clinic_miss={len(stats.get("unmatched_clinics", []))}',
        f'smtp={stats.get("smtp_status", "SKIP")}',
        f'network={stats.get("network_status", "SKIP")}',
        f'duration={int(duration_s)}s',
    ]
    if exception_class:
        parts.append(f'exception={exception_class}')
    return ' '.join(parts)
