import ipaddress
import json

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save

from apps.accounts.models import User
from apps.farms.models import Farm, UserFarm
from apps.farms.modules import MODULES

from .middleware import get_current_request
from .models import AuditLog


FIELD_LABELS = {
    "name": "Nombre",
    "lastname": "Apellido",
    "email": "Correo electrónico",
    "user": "Usuario",
    "farm": "Finca",
    "farm_role": "Rol",
    "role": "Rol",
    "module": "Módulo",
    "can_view": "Consultar",
    "can_create": "Crear",
    "can_update": "Actualizar",
    "can_delete": "Eliminar",
    "status": "Estado",
    "is_owner": "Propietario",
    "address": "Dirección",
    "description": "Descripción",
    "code": "Código",
    "quantity": "Cantidad",
    "created_at": "Fecha de creación",
    "updated_at": "Fecha de actualización",
}

ENTITY_LABELS = {
    "User": "el usuario",
    "UserFarm": "la membresía de finca",
    "Farm": "la finca",
    "FarmRole": "el rol de finca",
    "FarmRoleAppPermission": "los permisos del rol",
    "Pond": "el estanque",
    "UserFarmPond": "la asignación de usuario al estanque",
    "TypeProduct": "el tipo de producto",
    "Product": "el producto",
    "PurchaseDetail": "el detalle de compra",
    "Supplier": "el proveedor",
    "Specie": "la especie",
    "SpecieParameter": "el parámetro de especie",
    "SpecieFeedingReference": "la referencia de alimentación de especie",
    "SpecieProductionReference": "la referencia de producción de especie",
    "Batch": "el lote",
    "ProductionPlan": "el plan de producción",
    "Cycle": "el ciclo",
    "FeedingSchedule": "la programación de alimentación",
    "FeedingPlan": "el plan de alimentación",
    "FeedingEvent": "el evento de alimentación",
    "DailyStat": "la estadística diaria",
    "ProductUsageLog": "el registro de uso de producto",
    "ControlStat": "el registro de control",
    "FishEvaluated": "el pez evaluado",
    "HealthStat": "el registro sanitario",
    "TreatmentPlan": "el plan de tratamiento",
    "TreatmentEvent": "el evento de tratamiento",
    "AmbientalMeasurement": "la medición ambiental",
    "Alert": "la alerta",
    "Sale": "la venta",
    "InventoryMovement": "el movimiento de inventario",
    "Harvest": "la cosecha",
    "HarvestClassification": "la clasificación de cosecha",
    "Client": "el cliente",
    "Buy": "la compra",
    "Invitation": "la invitación",
    "BatchTransfer": "el traslado de lote",
    "GradingEvent": "el evento de clasificación",
    "SaleDetail": "el detalle de venta",
    "CyclePondBatch": "la asignación de lote al ciclo y estanque",
    "PondBatch": "el lote del estanque",
    "SpeciePondType": "el tipo de estanque de la especie",
    "ProductionReport": "el reporte de producción",
}

OPERATION_LABELS = {
    "can_view": "Consultar",
    "can_create": "Crear",
    "can_update": "Actualizar",
    "can_delete": "Eliminar",
}


def _full_name(user):
    name = f"{getattr(user, 'name', '') or ''} {getattr(user, 'lastname', '') or ''}".strip()
    return name or getattr(user, "email", None) or "Usuario sin nombre"


def _related_display(field, instance):
    related = getattr(instance, field.name, None)
    if related is None:
        return None
    if isinstance(related, User):
        name = _full_name(related)
    else:
        name = None
        for attribute in ("name", "code", "title", "number", "description"):
            candidate = getattr(related, attribute, None)
            if candidate:
                name = str(candidate)
                break
        if name is None:
            name = str(related)
            if name == f"{related.__class__.__name__} object ({related.pk})":
                name = f"{related._meta.verbose_name} #{related.pk}"
    return {"id": related.pk, "nombre": name}


def _field_display_value(instance, field):
    if field.is_relation:
        return _related_display(field, instance)

    value = getattr(instance, field.attname)
    if value is None:
        return None
    if hasattr(instance, f"get_{field.name}_display"):
        return getattr(instance, f"get_{field.name}_display")()
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if field.name == "module":
        return _module_label(value)
    return value


def _module_label(module):
    labels = {
        "production_batches": "Lotes de producción",
        "production_cycles": "Ciclos de producción",
        "farm_events": "Eventos de finca",
        "feeding_management": "Alimentación",
        "harvest_management": "Cosechas",
        "fish_health": "Salud de peces",
        "water_quality_monitoring": "Calidad del agua",
        "pond_management": "Estanques",
        "inventory_products": "Inventario de productos",
        "inventory_purchases": "Compras",
        "inventory_sales": "Ventas",
        "species_catalog": "Catálogo de especies",
        "farm_management": "Administración de fincas",
        "alerts": "Alertas",
        "audit_logs": "Auditoría",
        "user_administration": "Administración de usuarios",
    }
    return labels.get(module, MODULES.get(module, module))


def _display_value_text(value):
    if isinstance(value, dict):
        return value.get("nombre", "")
    return str(value) if value is not None else "Sin asignar"


def _user_farm_summary(display_fields):
    fields = display_fields["fields"]
    user = _display_value_text(fields.get("user_id", {}).get("value"))
    farm = _display_value_text(fields.get("farm_id", {}).get("value"))
    role = _display_value_text(fields.get("farm_role_id", {}).get("value"))
    if role == "Sin asignar":
        assignment = "no tiene un rol asignado"
    else:
        assignment = f"tiene asignado el rol «{role}»"
    return f"{user} {assignment} en la finca «{farm}»."


def _role_permission_summary(display_fields):
    fields = display_fields["fields"]
    role = _display_value_text(fields.get("role_id", {}).get("value"))
    module = _display_value_text(fields.get("module", {}).get("value"))
    granted = [
        label
        for field_name, label in OPERATION_LABELS.items()
        if fields.get(field_name, {}).get("value") == "Sí"
    ]
    operations = ", ".join(granted) if granted else "sin operaciones habilitadas"
    return f"Rol «{role}», módulo «{module}»: {operations}."


def _generic_summary(instance, display_fields):
    fields = display_fields["fields"]
    preferred = (
        "name",
        "code",
        "title",
        "batch_code",
        "module",
        "status",
        "type",
        "severity",
        "quantity",
        "message",
        "description",
    )
    field_names = {field.attname: field.name for field in instance._meta.concrete_fields}
    selected = [
        fields[name]
        for name in preferred
        if name in fields and fields[name]["value"] is not None
    ]
    if not selected:
        selected = [
            item
            for name, item in fields.items()
            if field_names.get(name) not in {"id", "created_at", "updated_at"}
            and item["value"] is not None
        ][:3]
    return "; ".join(
        f"{item['label']}: {_display_value_text(item['value'])}"
        for item in selected
    )


def _display_snapshot(instance):
    fields = {}
    for field in instance._meta.concrete_fields:
        if field.name in {"password", "last_login"}:
            continue
        fields[field.attname] = {
            "label": FIELD_LABELS.get(field.name, str(field.verbose_name).capitalize()),
            "value": _field_display_value(instance, field),
        }

    display = {"fields": fields}
    if instance.__class__.__name__ == "UserFarm":
        display["summary"] = _user_farm_summary(display)
    elif instance.__class__.__name__ == "FarmRoleAppPermission":
        display["summary"] = _role_permission_summary(display)
    else:
        display["summary"] = _generic_summary(instance, display)
    return display


def _snapshot(instance):
    values = {}
    for field in instance._meta.concrete_fields:
        if field.name in {"password", "last_login"}:
            continue
        values[field.attname] = getattr(instance, field.attname)
    values["display"] = _display_snapshot(instance)
    return json.loads(json.dumps(values, cls=DjangoJSONEncoder))


def _farm_ids(instance, using, seen=None):
    if instance.pk is None:
        return set()
    model = type(instance)
    if model is Farm:
        return {instance.pk}
    if model._meta.label_lower == "accounts.user":
        return set(
            UserFarm.objects.using(using)
            .filter(user_id=instance.pk)
            .values_list("farm_id", flat=True)
        )

    direct_farm_ids = {
        getattr(instance, field.attname)
        for field in model._meta.concrete_fields
        if field.is_relation
        and field.remote_field.model is Farm
        and getattr(instance, field.attname) is not None
    }
    if direct_farm_ids:
        return direct_farm_ids

    seen = seen or set()
    key = (model._meta.label_lower, instance.pk)
    if key in seen or len(seen) >= 20:
        return set()
    seen.add(key)

    farm_ids = set()
    for field in model._meta.concrete_fields:
        if not field.is_relation or not field.many_to_one:
            continue
        related_id = getattr(instance, field.attname)
        if related_id is None:
            continue
        related_model = field.remote_field.model
        if related_model is Farm:
            farm_ids.add(related_id)
            continue
        related = (
            related_model._base_manager.using(using)
            .filter(pk=related_id)
            .first()
        )
        if related is not None:
            farm_ids.update(_farm_ids(related, using, seen))
    return farm_ids


def _actor_and_ip():
    request = get_current_request()
    if request is None:
        return None, None
    user = getattr(request, "user", None)
    actor = user if getattr(user, "is_authenticated", False) else None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    ip = (
        forwarded.split(",", 1)[0].strip()
        if forwarded
        else request.META.get("REMOTE_ADDR")
    )
    try:
        ip = str(ipaddress.ip_address(ip)) if ip else None
    except ValueError:
        ip = None
    return actor, ip


def _source_type(instance):
    return instance.__class__.__name__


def _actor_name(actor):
    return _full_name(actor) if actor is not None else "Un usuario del sistema"


def _instance_name(instance):
    if isinstance(instance, User):
        return _full_name(instance)
    for attribute in ("name", "code", "title", "number"):
        value = getattr(instance, attribute, None)
        if value:
            return str(value)
    return f"{instance._meta.verbose_name} #{instance.pk}"


def _farm_name(instance):
    if isinstance(instance, Farm):
        return _instance_name(instance)
    farm_id = next(
        (
            getattr(instance, field.attname)
            for field in instance._meta.concrete_fields
            if field.is_relation and field.remote_field.model is Farm
        ),
        None,
    )
    if farm_id is None:
        return None
    farm = Farm._base_manager.filter(pk=farm_id).first()
    return _instance_name(farm) if farm else f"Finca #{farm_id}"


def _describe_user_farm(instance, operation, old_values, actor_name):
    user_name = _full_name(instance.user)
    farm_name = _instance_name(instance.farm)
    old_role = (
        old_values.get("display", {}).get("fields", {}).get("farm_role_id", {}).get("value")
        if old_values
        else None
    )
    new_role = (
        _related_display(instance._meta.get_field("farm_role"), instance)
    )
    old_role_name = _display_value_text(old_role)
    new_role_name = _display_value_text(new_role)
    if operation == "updated" and old_role_name != new_role_name:
        if old_role_name == "Sin asignar":
            change = f"asignó el rol «{new_role_name}»"
        elif new_role_name == "Sin asignar":
            change = f"retiró el rol «{old_role_name}»"
        else:
            change = f"cambió el rol «{old_role_name}» por «{new_role_name}»"
    elif operation == "created":
        change = (
            f"agregó a {user_name} con el rol «{new_role_name}»"
            if new_role_name != "Sin asignar"
            else f"agregó a {user_name} sin un rol asignado"
        )
    elif operation == "deleted":
        change = f"eliminó la membresía de {user_name}"
    else:
        change = f"actualizó la membresía de {user_name}"
    return f"{actor_name} {change} en la finca «{farm_name}»."


def _description(instance, operation, old_values, actor):
    actor_name = _actor_name(actor)
    if instance.__class__.__name__ == "UserFarm":
        return _describe_user_farm(instance, operation, old_values, actor_name)

    entity = ENTITY_LABELS.get(
        instance.__class__.__name__,
        f"el registro de {instance._meta.verbose_name}",
    )
    action = {
        "created": "creó",
        "updated": "actualizó",
        "deleted": "eliminó",
    }[operation]
    farm_name = _farm_name(instance)
    context = (
        f" de la finca «{farm_name}»"
        if farm_name and not isinstance(instance, Farm)
        else ""
    )
    if instance.__class__.__name__ == "FarmRoleAppPermission":
        role = getattr(instance, "role", None)
        role_name = _instance_name(role) if role else "Rol sin asignar"
        module = _module_label(instance.module)
        return (
            f"{actor_name} {action} los permisos del rol «{role_name}» "
            f"para «{module}»{context}."
        )
    return f"{actor_name} {action} {entity} «{_instance_name(instance)}»{context}."


def _record_change(instance, using, operation, old_values=None, old_farm_ids=None):
    if (
        operation in {"updated", "deleted"}
        and instance.__class__.__name__ == "UserFarm"
        and old_values
    ):
        display = old_values.get("display", {})
        summary = display.get("summary", "")
        display["summary"] = summary.replace(
            " tiene asignado ", " tenía asignado "
        ).replace(" no tiene ", " no tenía ")

    source_type = _source_type(instance)
    farm_ids = _farm_ids(instance, using)
    if old_farm_ids:
        farm_ids.update(old_farm_ids)
    if not farm_ids:
        return

    actor, ip = _actor_and_ip()
    source_id = instance.pk
    description = _description(instance, operation, old_values, actor)
    for farm_id in farm_ids:
        AuditLog.objects.using(using).create(
            user=actor,
            farm_id=farm_id,
            description=description,
            type_source=source_type,
            source_id=source_id,
            ip=ip,
            old_values=old_values,
            new_values=(
                _snapshot(instance) if operation != "deleted" else None
            ),
        )


def _capture_existing(instance, using):
    try:
        previous = type(instance)._base_manager.using(using).get(pk=instance.pk)
    except type(instance).DoesNotExist:
        return None, set()
    return _snapshot(previous), _farm_ids(previous, using)


def audit_bulk_create(model, instances, **kwargs):
    using = kwargs.pop("using", model.objects.db)
    created = model._default_manager.db_manager(using).bulk_create(
        instances,
        **kwargs,
    )
    for instance in created:
        _record_change(instance, using, "created")
    return created


def audit_queryset_update(queryset, **kwargs):
    using = queryset.db
    before = {
        instance.pk: (_snapshot(instance), _farm_ids(instance, using))
        for instance in queryset
    }
    updated = queryset.update(**kwargs)
    if not updated:
        return updated

    model = queryset.model
    for instance in model._base_manager.using(using).filter(pk__in=before):
        old_values, old_farm_ids = before[instance.pk]
        _record_change(
            instance,
            using,
            "updated",
            old_values=old_values,
            old_farm_ids=old_farm_ids,
        )
    return updated


def register_audit_signals():
    source_types = {value for value, _label in AuditLog.TypeSource.choices}
    for model in apps.get_models():
        if model is AuditLog or model.__name__ not in source_types:
            continue

        pre_save.connect(
            _audit_pre_save,
            sender=model,
            weak=False,
            dispatch_uid=f"audit-pre-save-{model._meta.label_lower}",
        )
        post_save.connect(
            _audit_post_save,
            sender=model,
            weak=False,
            dispatch_uid=f"audit-post-save-{model._meta.label_lower}",
        )
        pre_delete.connect(
            _audit_pre_delete,
            sender=model,
            weak=False,
            dispatch_uid=f"audit-pre-delete-{model._meta.label_lower}",
        )
        post_delete.connect(
            _audit_post_delete,
            sender=model,
            weak=False,
            dispatch_uid=f"audit-post-delete-{model._meta.label_lower}",
        )


def _audit_pre_save(sender, instance, using, raw=False, **kwargs):
    if raw:
        return
    instance._audit_old_values, instance._audit_old_farm_ids = _capture_existing(
        instance, using
    )


def _audit_post_save(sender, instance, created, using, raw=False, **kwargs):
    if raw:
        return
    _record_change(
        instance,
        using,
        "created" if created else "updated",
        old_values=getattr(instance, "_audit_old_values", None),
        old_farm_ids=getattr(instance, "_audit_old_farm_ids", None),
    )


def _audit_pre_delete(sender, instance, using, **kwargs):
    instance._audit_old_values = _snapshot(instance)
    instance._audit_old_farm_ids = _farm_ids(instance, using)


def _audit_post_delete(sender, instance, using, **kwargs):
    _record_change(
        instance,
        using,
        "deleted",
        old_values=getattr(instance, "_audit_old_values", None),
        old_farm_ids=getattr(instance, "_audit_old_farm_ids", None),
    )
