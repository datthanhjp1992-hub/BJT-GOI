"""
Shared abstract base models.

AuditableModel adds the 4 standard audit columns requested for every table:
created_by, created_at, updated_by, updated_at.
Every model in vocabulary/learning/practice_sheets apps should inherit from it.
"""
from django.conf import settings
from django.db import models

from apps.core.middleware import get_current_user


class AuditableModel(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="+",
        on_delete=models.SET_NULL,
        editable=False,
        help_text="User who created this record (null = created by system).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="+",
        on_delete=models.SET_NULL,
        editable=False,
        help_text="User who last updated this record.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # Auto-fill created_by / updated_by from the current request's user,
        # if available (set by CurrentUserMiddleware).
        user = get_current_user()
        if user is not None and getattr(user, "is_authenticated", False):
            if self._state.adding and not self.created_by_id:
                self.created_by = user
            self.updated_by = user
        super().save(*args, **kwargs)


class MasterCode(AuditableModel):
    """
    Bảng mã dùng chung cho TOÀN BỘ hệ thống — thay cho việc mỗi model tự khai
    `choices=[...]` cứng. Đọc/ghi qua apps.core.mastercode (KHÔNG query thẳng
    MasterCode ở nơi khác trừ trang quản trị MasterCode và chính module đó),
    để mọi chỗ đều đi qua lớp cache thống nhất.

    Xem docs/SPEC_GOP_Y_THANH_TICH.md mục 2 để biết danh sách code_type đang
    dùng và seed data — seed thật nằm ở
    apps/core/management/commands/seed_mastercode.py.
    """
    code_type = models.CharField(
        max_length=10,
        help_text="Nhóm code, vd '01' = danh hiệu đóng góp, '05' = cấp độ BJT.",
    )
    code = models.CharField(max_length=10, help_text="Mã trong nhóm, vd '001'.")
    code_name = models.CharField(max_length=150, help_text="Tên hiển thị, vd 'Tân Binh'.")
    mother_code = models.CharField(
        max_length=10, null=True, blank=True,
        help_text="Mã cha TRONG CÙNG code_type — null = cấp cao nhất.",
    )
    description = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("code_type", "code")
        ordering = ["code_type", "sort_order", "code"]
        verbose_name = "Master code"
        verbose_name_plural = "Master codes"

    def __str__(self):
        return f"[{self.code_type}.{self.code}] {self.code_name}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.mother_code:
            exists = (
                MasterCode.objects.filter(code_type=self.code_type, code=self.mother_code)
                .exclude(pk=self.pk)
                .exists()
            )
            if not exists:
                raise ValidationError(
                    {"mother_code": f"Không tìm thấy code cha '{self.mother_code}' trong code_type '{self.code_type}'."}
                )
            if self.mother_code == self.code:
                raise ValidationError({"mother_code": "mother_code không được trùng chính code này."})
