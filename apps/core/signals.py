import ipaddress
import json

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save

from apps.farms.models import Farm, UserFarm

from .middleware import get_current_request
from .models import AuditLog


def _snapshot(instance):
    values = {}
    for field in instance._meta.concrete_fields:
        if field.name in {"password", "last_login"}:
            continue
        values[field.attname] = getattr(instance, field.attname)
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


def _record_change(instance, using, operation, old_values=None, old_farm_ids=None):
    source_type = _source_type(instance)
    farm_ids = _farm_ids(instance, using)
    if old_farm_ids:
        farm_ids.update(old_farm_ids)
    if not farm_ids:
        return

    actor, ip = _actor_and_ip()
    source_id = instance.pk
    for farm_id in farm_ids:
        AuditLog.objects.using(using).create(
            user=actor,
            farm_id=farm_id,
            description=f"{source_type} {source_id} {operation}",
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
