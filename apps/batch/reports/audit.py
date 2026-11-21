from apps.core.models import AuditLog

from .constants import MODULE_LABELS


def get_client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_production_report_generation(
    *,
    user,
    farm_id: int,
    batch_id: int,
    batch_code: str,
    modules: list[str],
    export_format: str,
    cycle_id: int | None,
    empty_modules: list[str],
    ip: str | None,
) -> AuditLog:
    module_labels = [MODULE_LABELS.get(m, m) for m in modules]
    empty_labels = [MODULE_LABELS.get(m, m) for m in empty_modules]
    description = (
        f"Reporte histórico generado para lote {batch_code} "
        f"(formato: {export_format.upper()})"
    )
    return AuditLog.objects.create(
        user=user,
        farm_id=farm_id,
        description=description,
        type_source=AuditLog.TypeSource.PRODUCTION_REPORT,
        source_id=batch_id,
        ip=ip,
        new_values={
            "batch_id": batch_id,
            "batch_code": batch_code,
            "modules": modules,
            "module_labels": module_labels,
            "format": export_format,
            "cycle_id": cycle_id,
            "modules_without_data": empty_modules,
            "modules_without_data_labels": empty_labels,
        },
    )
