"""Xoá cache label/message.properties mà không cần restart server — dùng sau
khi sửa tay 2 file .properties trên môi trường đang chạy (vd prod)."""
from django.core.management.base import BaseCommand

from apps.core.properties import reload_cache


class Command(BaseCommand):
    help = "Xoá cache của label.properties / message.properties."

    def handle(self, *args, **options):
        reload_cache()
        self.stdout.write(self.style.SUCCESS("Đã xoá cache label/message.properties."))
