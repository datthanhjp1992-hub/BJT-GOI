"""
Tạo tài khoản khởi tạo cho BJT-GOI — chạy: python manage.py seed_users

Idempotent: chạy lại nhiều lần không tạo trùng. Tài khoản đã có thì chỉ cập
nhật email / cờ quyền, KHÔNG đụng tới mật khẩu (trừ khi truyền
--reset-passwords), để không vô tình ghi đè mật khẩu người dùng đã tự đổi.

    python manage.py seed_users
    python manage.py seed_users --reset-passwords
    python manage.py seed_users --admin-password 'MatKhauMoi' --reset-passwords

Mật khẩu mặc định lấy từ biến môi trường nếu có (BJT_ADMIN_PASSWORD /
BJT_USER_PASSWORD), nếu không thì dùng giá trị truyền qua tham số dòng lệnh.
Lệnh KHÔNG ghi mật khẩu ra file nào.
"""
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.db import transaction

DEFAULT_ADMIN_PASSWORD = "admin123"
DEFAULT_USER_PASSWORD = "user123"


class Command(BaseCommand):
    help = "Tạo 1 tài khoản admin + 2 tài khoản người dùng (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--admin-username", default="dat")
        parser.add_argument("--admin-email", default="dat.thanhjp1992@gmail.com")
        parser.add_argument(
            "--admin-password",
            default=os.environ.get("BJT_ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD),
        )
        parser.add_argument(
            "--user-password",
            default=os.environ.get("BJT_USER_PASSWORD", DEFAULT_USER_PASSWORD),
        )
        parser.add_argument(
            "--reset-passwords", action="store_true",
            help="Đặt lại mật khẩu cho cả tài khoản đã tồn tại.",
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **opts):
        User = get_user_model()
        admin_pw = opts["admin_password"]
        user_pw = opts["user_password"]
        reset = opts["reset_passwords"]

        rows = []

        with transaction.atomic():
            # --- admin ---
            admin, created = User.objects.get_or_create(
                username=opts["admin_username"],
                defaults={"email": opts["admin_email"]},
            )
            admin.email = opts["admin_email"]
            admin.is_staff = True
            admin.is_superuser = True
            if created or reset:
                admin.set_password(admin_pw)
            admin.save()
            rows.append((admin, "tạo mới" if created else "đã có", admin_pw, created or reset))

            # --- 2 tài khoản người dùng, cùng thiết lập, chỉ khác username ---
            for i in (1, 2):
                username = f"hocvien{i}"
                u, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        "email": f"{username}@bjt-goi.local",
                        # created_by/updated_by không tự điền được ở management
                        # command (CurrentUserMiddleware chỉ chạy trong HTTP
                        # request), nên gán tay actor là admin cho đúng audit.
                        "created_by": admin,
                    },
                )
                u.email = f"{username}@bjt-goi.local"
                u.is_staff = False
                u.is_superuser = False
                u.updated_by = admin
                if created or reset:
                    u.set_password(user_pw)
                u.save()
                rows.append((u, "tạo mới" if created else "đã có", user_pw, created or reset))

        self._report(rows, reset)

    # ------------------------------------------------------------------
    def _report(self, rows, reset):
        w = max(len(u.username) for u, *_ in rows) + 2
        self.stdout.write("")
        self.stdout.write(
            f"  {'USERNAME'.ljust(w)}{'VAI TRÒ'.ljust(12)}{'TRẠNG THÁI'.ljust(12)}"
            f"{'MÚI GIỜ'.ljust(20)}MẬT KHẨU"
        )
        self.stdout.write("  " + "-" * (w + 62))
        for u, state, pw, pw_set in rows:
            role = "admin" if u.is_superuser else "người dùng"
            shown = pw if pw_set else "(giữ nguyên)"
            self.stdout.write(f"  {u.username.ljust(w)}{role.ljust(12)}{state.ljust(12)}"
                              f"{u.timezone.ljust(20)}{shown}")
        self.stdout.write("")

        # Cảnh báo độ mạnh — KHÔNG chặn, chỉ nói cho biết.
        weak = []
        for u, _state, pw, pw_set in rows:
            if not pw_set:
                continue
            try:
                validate_password(pw, u)
            except ValidationError as e:
                weak.append((u.username, e.messages[0]))
        if weak:
            self.stdout.write(self.style.WARNING(
                "  Mật khẩu không đạt chuẩn của Django (chỉ cảnh báo, tài khoản vẫn tạo được):"
            ))
            for name, msg in weak:
                self.stdout.write(self.style.WARNING(f"    - {name}: {msg}"))
            self.stdout.write(self.style.WARNING(
                "  Đổi sau bằng: python manage.py seed_users --admin-password '...' "
                "--user-password '...' --reset-passwords"
            ))

        if not reset:
            self.stdout.write(
                "  Tài khoản đã tồn tại thì mật khẩu giữ nguyên. "
                "Thêm --reset-passwords nếu muốn đặt lại."
            )
        self.stdout.write(self.style.SUCCESS(f"  Xong — {len(rows)} tài khoản."))
