"""
Xoá cache MasterCode ngay khi có thay đổi, để trang quản trị MasterCode sửa
xong là hiển thị đúng ngay (không phải đợi CACHE_TTL_SECONDS hết hạn).
Kết nối trong apps/core/apps.py -> CoreConfig.ready().
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from apps.core.mastercode import invalidate_cache


def _handle_mastercode_change(sender, instance, **kwargs):
    invalidate_cache(instance.code_type, instance.code)


def connect():
    from apps.core.models import MasterCode

    post_save.connect(_handle_mastercode_change, sender=MasterCode, dispatch_uid="mastercode_cache_on_save")
    post_delete.connect(_handle_mastercode_change, sender=MasterCode, dispatch_uid="mastercode_cache_on_delete")
