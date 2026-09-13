"""
Engine nhập/xuất dữ liệu bằng file cho khu quản trị SC07.

Ý tưởng: KHÔNG viết tay 18 bộ form/parse. Cột của mỗi bảng được suy ra từ
`Model._meta` nên thêm/bớt field trong models.py là file mẫu, file xuất và
trình nhập tự đổi theo — không có nơi thứ hai phải sửa.

Quy ước cột:
- Bỏ hết khoá chính và 4 cột audit (created_by/created_at/updated_by/updated_at).
  Audit do `AuditableModel.save()` + `CurrentUserMiddleware` tự điền.
- Field thường  -> 1 cột trùng tên field.
- Khoá ngoại    -> dò theo KHOÁ TỰ NHIÊN của bảng đích (`NATURAL_KEYS`), cột đặt
  tên `<field>__<khoá>` (vd `vocabulary__word`, `vocabulary__reading`). Bảng đích
  không khai khoá tự nhiên thì lùi về `<field>_id` (id thô).
- ManyToMany KHÔNG có cột. Cả 3 quan hệ M2M của repo đều đi qua through model
  (VocabularyTopic / UserWordlistWord / PracticeSheetWord) và 3 bảng nối đó tự
  nằm trong danh sách nhập được — nhập bảng nối là cách duy nhất giữ đủ audit.

Chế độ ghi: CHỈ THÊM MỚI. Dòng đã có trong DB (so theo khoá trùng lặp) bị bỏ
qua, không cập nhật, không xoá gì. Xem `duplicate_fields()`.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field as dataclass_field

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import models

# 6 app nội bộ = 18 bảng. django.contrib.auth KHÔNG đụng vào (quyết định của Dat,
# xem claude/db-schema-django.md).
LOCAL_APP_LABELS = (
    "core",
    "accounts",
    "vocabulary",
    "learning",
    "practice_sheets",
    "gamification",
)

AUDIT_FIELDS = ("created_by", "created_at", "updated_by", "updated_at")

# Tên sheet hướng dẫn trong file mẫu .xlsx — trùng với chuỗi đã dùng ở
# message.properties (practice_sheets.upload.error.missing_required_column).
GUIDE_SHEET_NAME = "Huong_dan"

# Chặn trên số dòng mỗi lần nhập. Mỗi dòng chạy full_clean() (có validate_unique)
# nên file quá to sẽ treo request; chia nhỏ file thay vì nâng số này.
MAX_IMPORT_ROWS = 2000

CSV_ENCODINGS = ("utf-8-sig", "cp932", "utf-8")

BOOL_TRUE = {"1", "true", "t", "yes", "y", "x", "co", "có", "dung", "đúng"}
BOOL_FALSE = {"0", "false", "f", "no", "n", "", "khong", "không", "sai"}

# Khoá tự nhiên: dùng cho (1) cột tham chiếu FK và (2) phát hiện trùng.
# Chỉ khai bảng nào có khoá nghiệp vụ thật; bảng còn lại tự suy từ
# UniqueConstraint / unique_together / unique=True, xem duplicate_fields().
NATURAL_KEYS = {
    "accounts.user": ("username",),
    "core.mastercode": ("code_type", "code"),
    "vocabulary.topic": ("slug",),
    "vocabulary.vocabulary": ("word", "reading"),
    "gamification.pointrule": ("action_code",),
    # Khoá của BadgeCategory là code_type (1 nhóm danh hiệu = 1 code_type bên
    # MasterCode), KHÔNG phải "code" — model này không có field tên code.
    "gamification.badgecategory": ("code_type",),
}


class DataFileError(Exception):
    """Lỗi ở tầng file (sai định dạng, thiếu cột, quá số dòng)."""

    def __init__(self, message_key, **params):
        super().__init__(message_key)
        self.message_key = message_key
        self.params = params


# ---------------------------------------------------------------------------
# Danh sách bảng
# ---------------------------------------------------------------------------

def model_label(model):
    return f"{model._meta.app_label}.{model._meta.model_name}"


def _all_local_models():
    found = []
    for app_label in LOCAL_APP_LABELS:
        try:
            config = django_apps.get_app_config(app_label)
        except LookupError:  # pragma: no cover - app bị gỡ khỏi INSTALLED_APPS
            continue
        for model in config.get_models():
            if model._meta.auto_created or model._meta.proxy:
                continue
            found.append(model)
    return found


def importable_models():
    """18 bảng, xếp theo thứ tự phụ thuộc: bảng bị tham chiếu đứng trước.

    Nhập theo đúng thứ tự này thì khoá ngoại luôn dò ra. Vòng lặp tự tham chiếu
    (User.created_by trỏ về chính User) không tính là phụ thuộc.
    """
    models_list = _all_local_models()
    by_label = {model_label(m): m for m in models_list}
    remaining = dict(by_label)
    ordered = []
    while remaining:
        ready = []
        for label, model in remaining.items():
            deps = set()
            for f in model._meta.fields:
                if f.is_relation and f.related_model is not None:
                    dep = model_label(f.related_model)
                    if dep != label and dep in remaining:
                        deps.add(dep)
            if not deps:
                ready.append(label)
        if not ready:  # còn phụ thuộc vòng -> xả phần còn lại theo tên
            ready = sorted(remaining)
        for label in sorted(ready):
            ordered.append(remaining.pop(label))
    return ordered


def get_importable_model(label):
    """Tra model theo nhãn 'app_label.modelname'. None nếu không nằm trong 18 bảng."""
    label = (label or "").strip().lower()
    for model in _all_local_models():
        if model_label(model) == label:
            return model
    return None


def verbose_name(model):
    return str(model._meta.verbose_name).strip() or model._meta.model_name


# ---------------------------------------------------------------------------
# Cột
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Column:
    header: str          # tên cột trong file
    field_name: str      # tên field trên model
    lookup: str | None   # FK: field dò trên bảng đích; None = id thô / field thường
    is_fk: bool
    required: bool
    hint: str            # mô tả ngắn để in vào sheet Huong_dan

    @property
    def label(self):
        return self.header


def _plain_natural_key(model):
    """Khoá tự nhiên chỉ gồm field thường (không FK) — mới dùng làm cột được."""
    keys = NATURAL_KEYS.get(model_label(model), ())
    if not keys or not _fields_exist(model, keys):
        return ()
    for name in keys:
        if model._meta.get_field(name).is_relation:
            return ()
    return tuple(keys)


def _field_hint(f):
    parts = [f.get_internal_type()]
    if getattr(f, "max_length", None):
        parts.append(f"tối đa {f.max_length}")
    if f.choices:
        parts.append("giá trị nằm trong MasterCode")
    if f.has_default():
        parts.append("bỏ trống = mặc định")
    elif f.null or f.blank:
        parts.append("được để trống")
    else:
        parts.append("bắt buộc")
    if f.help_text:
        parts.append(str(f.help_text))
    return " · ".join(parts)


def columns_for(model):
    """Danh sách cột của 1 bảng, đúng thứ tự khai trong models.py."""
    columns = []
    for f in model._meta.fields:
        if f.primary_key or not f.editable or f.auto_created:
            continue
        if f.name in AUDIT_FIELDS:
            continue
        required = not (f.blank or f.null or f.has_default())
        if isinstance(f, models.ForeignKey):
            target_keys = _plain_natural_key(f.related_model)
            if target_keys:
                for key in target_keys:
                    columns.append(
                        Column(
                            header=f"{f.name}__{key}",
                            field_name=f.name,
                            lookup=key,
                            is_fk=True,
                            required=required,
                            hint=f"tham chiếu {verbose_name(f.related_model)} theo {key}",
                        )
                    )
            else:
                columns.append(
                    Column(
                        header=f"{f.name}_id",
                        field_name=f.name,
                        lookup=None,
                        is_fk=True,
                        required=required,
                        hint=f"id của {verbose_name(f.related_model)}",
                    )
                )
        else:
            columns.append(
                Column(
                    header=f.name,
                    field_name=f.name,
                    lookup=None,
                    is_fk=False,
                    required=required,
                    hint=_field_hint(f),
                )
            )
    return columns


def headers_for(model):
    return [c.header for c in columns_for(model)]


def skipped_m2m_names(model):
    """M2M bị bỏ khỏi file — UI in ra để admin biết phải nhập bảng nối nào."""
    out = []
    for f in model._meta.many_to_many:
        through = getattr(f.remote_field, "through", None)
        if through is not None and not through._meta.auto_created:
            out.append((f.name, model_label(through)))
        else:  # pragma: no cover - repo không còn M2M ẩn nào
            out.append((f.name, ""))
    return out


def _fields_exist(model, names):
    for name in names:
        try:
            model._meta.get_field(name)
        except Exception:
            return False
    return True


def duplicate_fields(model):
    """Bộ field dùng để nhận ra 'dòng này đã có trong DB'.

    Ưu tiên khoá tự nhiên đã khai; sau đó tới UniqueConstraint, unique_together,
    rồi field unique=True đơn lẻ. Rỗng = bảng không có khoá nào -> mọi dòng đều
    tính là mới (UI cảnh báo, nhập 2 lần sẽ ra dữ liệu đôi).

    NATURAL_KEYS gõ sai tên field thì BỎ QUA chứ không dùng: nếu tin nó, câu
    filter() lúc dò trùng sẽ nổ FieldError giữa lúc admin đang nhập.
    """
    keys = NATURAL_KEYS.get(model_label(model))
    if keys and _fields_exist(model, keys):
        return tuple(keys)
    for constraint in model._meta.constraints:
        fields = getattr(constraint, "fields", None)
        if fields:
            return tuple(fields)
    for together in model._meta.unique_together:
        return tuple(together)
    for f in model._meta.fields:
        if f.unique and not f.primary_key and f.editable:
            return (f.name,)
    return ()


# ---------------------------------------------------------------------------
# Đọc file
# ---------------------------------------------------------------------------

def _decode_csv(raw):
    for encoding in CSV_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DataFileError("admin.data.error.encoding")


def _read_csv(raw):
    text = _decode_csv(raw)
    reader = csv.reader(io.StringIO(text, newline=""))
    rows = [list(r) for r in reader]
    if not rows:
        raise DataFileError("admin.data.error.empty_file")
    headers = [str(h).strip() for h in rows[0]]
    return headers, rows[1:]


def _read_xlsx(raw):
    try:
        from openpyxl import load_workbook
    except ImportError:  # pragma: no cover - openpyxl nằm trong requirements
        raise DataFileError("admin.data.error.xlsx_unavailable")
    workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    sheet = None
    for candidate in workbook.worksheets:
        if candidate.title != GUIDE_SHEET_NAME:
            sheet = candidate
            break
    if sheet is None:
        raise DataFileError("admin.data.error.empty_file")
    rows = []
    for row in sheet.iter_rows(values_only=True):
        rows.append(["" if v is None else v for v in row])
    workbook.close()
    if not rows:
        raise DataFileError("admin.data.error.empty_file")
    headers = [str(h).strip() for h in rows[0]]
    return headers, rows[1:]


def read_table(raw, filename):
    """(headers, rows) từ nội dung file. Chấp nhận .csv / .xlsx / .xlsm."""
    name = (filename or "").lower()
    if name.endswith(".csv"):
        headers, rows = _read_csv(raw)
    elif name.endswith(".xlsx") or name.endswith(".xlsm"):
        headers, rows = _read_xlsx(raw)
    else:
        raise DataFileError("admin.data.error.unsupported_format")
    # Bỏ dòng trống hoàn toàn ở cuối file (Excel hay để lại)
    while rows and all(str(v).strip() == "" for v in rows[-1]):
        rows.pop()
    if not rows:
        raise DataFileError("admin.data.error.empty_file")
    if len(rows) > MAX_IMPORT_ROWS:
        raise DataFileError("admin.data.error.too_many_rows", max_rows=MAX_IMPORT_ROWS, row_count=len(rows))
    return headers, rows


# ---------------------------------------------------------------------------
# Ghi file
# ---------------------------------------------------------------------------

def write_csv(headers, rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    # BOM để Excel bản tiếng Nhật mở UTF-8 không ra mojibake.
    return buffer.getvalue().encode("utf-8-sig")


def write_xlsx(headers, rows, guide_rows=None, sheet_title="Data"):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = (sheet_title or "Data")[:31]
    sheet.append(list(headers))
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.freeze_panes = "A2"
    for row in rows:
        sheet.append(["" if v is None else v for v in row])
    for index, header in enumerate(headers, start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = max(
            12, min(40, len(str(header)) + 6)
        )
    if guide_rows:
        guide = workbook.create_sheet(GUIDE_SHEET_NAME)
        for row in guide_rows:
            guide.append(list(row))
        for cell in guide[1]:
            cell.font = Font(bold=True)
        guide.column_dimensions["A"].width = 32
        guide.column_dimensions["B"].width = 14
        guide.column_dimensions["C"].width = 70
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def export_rows(model, queryset=None):
    """Dữ liệu hiện có của 1 bảng, đúng bộ cột của file mẫu."""
    columns = columns_for(model)
    queryset = model._default_manager.all() if queryset is None else queryset
    fk_names = {c.field_name for c in columns if c.is_fk}
    if fk_names:
        queryset = queryset.select_related(*sorted(fk_names))
    rows = []
    for obj in queryset.iterator():
        row = []
        for column in columns:
            if column.is_fk:
                related = getattr(obj, column.field_name, None)
                if related is None:
                    row.append("")
                elif column.lookup:
                    row.append(getattr(related, column.lookup, ""))
                else:
                    row.append(related.pk)
            else:
                value = getattr(obj, column.field_name, "")
                row.append("" if value is None else value)
        rows.append(row)
    return rows


def guide_rows(model):
    out = [["Cột", "Bắt buộc", "Ghi chú"]]
    for column in columns_for(model):
        out.append([column.header, "x" if column.required else "", column.hint])
    for name, through in skipped_m2m_names(model):
        out.append([name, "", f"KHÔNG nhập ở đây — nhập bảng nối {through}"])
    return out


# ---------------------------------------------------------------------------
# Phân tích file trước khi ghi
# ---------------------------------------------------------------------------

STATUS_NEW = "new"
STATUS_DUPLICATE = "duplicate"
STATUS_ERROR = "error"


@dataclass
class RowResult:
    number: int                      # số dòng thật trong file (header là dòng 1)
    status: str
    display: str = ""
    errors: list = dataclass_field(default_factory=list)
    data: dict = dataclass_field(default_factory=dict)


@dataclass
class ImportReport:
    model_label: str
    model_name: str
    headers: list = dataclass_field(default_factory=list)
    missing_columns: list = dataclass_field(default_factory=list)
    unknown_columns: list = dataclass_field(default_factory=list)
    rows: list = dataclass_field(default_factory=list)
    duplicate_key: tuple = ()

    @property
    def new_rows(self):
        return [r for r in self.rows if r.status == STATUS_NEW]

    @property
    def new_count(self):
        return len(self.new_rows)

    @property
    def duplicate_count(self):
        return sum(1 for r in self.rows if r.status == STATUS_DUPLICATE)

    @property
    def error_count(self):
        return sum(1 for r in self.rows if r.status == STATUS_ERROR)

    @property
    def problem_rows(self):
        return [r for r in self.rows if r.status == STATUS_ERROR]

    @property
    def can_apply(self):
        """Có lỗi thì KHÔNG cho ghi — sửa file rồi tải lại.

        Nửa vời (ghi dòng đúng, bỏ dòng sai) khiến lần nhập lại sau đó vừa trùng
        vừa thiếu, rất khó dò. Thà bắt sửa file một lần.
        """
        return not self.missing_columns and self.error_count == 0 and self.new_count > 0


def _clean_value(field, raw):
    value = raw
    if isinstance(value, str):
        value = value.strip()
    if isinstance(field, models.BooleanField):
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in BOOL_TRUE:
            return True
        if text in BOOL_FALSE:
            return False if not field.null else (None if text == "" else False)
        raise ValidationError(f"'{raw}' không phải giá trị đúng/sai")
    if value in ("", None):
        if field.null:
            return None
        if field.has_default():
            return field.get_default()
        return "" if isinstance(field, (models.CharField, models.TextField)) else None
    return field.to_python(value)


def analyze(model, headers, rows):
    """Đối chiếu từng dòng với DB + validate, KHÔNG ghi gì."""
    columns = columns_for(model)
    report = ImportReport(
        model_label=model_label(model),
        model_name=verbose_name(model),
        headers=list(headers),
        duplicate_key=duplicate_fields(model),
    )
    index_of = {}
    for position, header in enumerate(headers):
        index_of.setdefault(str(header).strip(), position)

    known_headers = {c.header for c in columns}
    report.unknown_columns = [h for h in headers if h and h not in known_headers]
    report.missing_columns = [c.header for c in columns if c.required and c.header not in index_of]
    if report.missing_columns:
        return report

    dup_key = report.duplicate_key
    seen_in_file = set()
    fk_cache = {}

    for offset, raw_row in enumerate(rows):
        number = offset + 2  # dòng 1 là header
        errors = []
        data = {}

        # 1. đổi từng ô sang giá trị Python / đối tượng FK
        for column in columns:
            position = index_of.get(column.header)
            raw = raw_row[position] if position is not None and position < len(raw_row) else ""
            if isinstance(raw, str):
                raw = raw.strip()
            field = model._meta.get_field(column.field_name)
            if column.is_fk:
                data.setdefault(f"__fk__{column.field_name}", {})[column.lookup or "pk"] = raw
                continue
            try:
                data[column.field_name] = _clean_value(field, raw)
            except (ValidationError, ValueError, TypeError) as exc:
                errors.append(f"{column.header}: {_first_message(exc)}")

        # 2. dò khoá ngoại
        for key in [k for k in list(data) if k.startswith("__fk__")]:
            field_name = key[len("__fk__"):]
            lookups = data.pop(key)
            field = model._meta.get_field(field_name)
            filters = {k: v for k, v in lookups.items() if str(v).strip() != ""}
            if not filters:
                if field.null or field.blank:
                    data[field_name] = None
                else:
                    errors.append(f"{field_name}: thiếu tham chiếu bắt buộc")
                continue
            cache_key = (field.related_model, tuple(sorted(filters.items())))
            if cache_key in fk_cache:
                related = fk_cache[cache_key]
            else:
                try:
                    related = field.related_model._default_manager.get(**filters)
                except field.related_model.DoesNotExist:
                    related = None
                except Exception as exc:  # nhiều bản ghi khớp / lookup sai kiểu
                    related = None
                    errors.append(f"{field_name}: {_first_message(exc)}")
                fk_cache[cache_key] = related
            if related is None:
                shown = ", ".join(f"{k}={v}" for k, v in filters.items())
                errors.append(f"{field_name}: không tìm thấy bản ghi khớp ({shown})")
            else:
                data[field_name] = related

        if errors:
            report.rows.append(RowResult(number=number, status=STATUS_ERROR, errors=errors))
            continue

        # 3. trùng trong file / trùng trong DB
        if dup_key:
            try:
                signature = tuple(_signature_value(data.get(name)) for name in dup_key)
            except Exception:  # pragma: no cover
                signature = None
            if signature is not None:
                if signature in seen_in_file:
                    report.rows.append(
                        RowResult(
                            number=number,
                            status=STATUS_DUPLICATE,
                            display=_display(dup_key, data),
                            errors=["trùng với một dòng phía trên trong cùng file"],
                        )
                    )
                    continue
                seen_in_file.add(signature)
                filters = {name: data.get(name) for name in dup_key}
                if model._default_manager.filter(**filters).exists():
                    report.rows.append(
                        RowResult(
                            number=number,
                            status=STATUS_DUPLICATE,
                            display=_display(dup_key, data),
                            errors=["đã có trong hệ thống"],
                        )
                    )
                    continue

        # 4. validate bằng chính model
        instance = model(**data)
        hook = PRE_SAVE_HOOKS.get(report.model_label)
        if hook:
            hook(instance, data)
        exclude = [f.name for f in model._meta.fields if f.name in AUDIT_FIELDS or f.primary_key]
        exclude += EXTRA_VALIDATION_EXCLUDES.get(report.model_label, [])
        try:
            instance.full_clean(exclude=exclude)
        except ValidationError as exc:
            report.rows.append(
                RowResult(number=number, status=STATUS_ERROR, errors=_flatten(exc))
            )
            continue

        report.rows.append(
            RowResult(
                number=number,
                status=STATUS_NEW,
                display=_display(dup_key, data) or str(instance),
                data=data,
            )
        )
    return report


def _signature_value(value):
    if isinstance(value, models.Model):
        return value.pk
    if isinstance(value, str):
        return value.strip()
    return value


def _display(dup_key, data):
    if not dup_key:
        return ""
    parts = []
    for name in dup_key:
        value = data.get(name)
        parts.append(str(getattr(value, "pk", value)))
    return " / ".join(parts)


def _first_message(exc):
    if isinstance(exc, ValidationError):
        messages = _flatten(exc)
        return messages[0] if messages else str(exc)
    return str(exc)


def _flatten(exc):
    out = []
    if hasattr(exc, "message_dict"):
        for field_name, messages in exc.message_dict.items():
            for m in messages:
                out.append(m if field_name == "__all__" else f"{field_name}: {m}")
    else:
        out.extend(exc.messages if hasattr(exc, "messages") else [str(exc)])
    return out


def apply_report(report, model):
    """Ghi các dòng 'mới'. GỌI TRONG transaction.atomic() ở tầng view.

    Dùng create() từng dòng chứ không bulk_create: AuditableModel.save() mới điền
    created_by/updated_by từ CurrentUserMiddleware, bulk_create bỏ qua save().
    """
    hook = PRE_SAVE_HOOKS.get(model_label(model))
    created = 0
    for row in report.new_rows:
        instance = model(**row.data)
        if hook:
            hook(instance, row.data)
        instance.save()
        created += 1
    return created


# ---------------------------------------------------------------------------
# Hook riêng theo bảng
# ---------------------------------------------------------------------------

def _prepare_user(instance, data):
    """Không bao giờ ghi mật khẩu thô xuống DB.

    Ô password trong file: để trống -> tài khoản không đăng nhập được bằng mật
    khẩu (đúng ý khi nhập danh sách người học rồi bắt họ đặt lại). Có giá trị và
    chưa băm -> băm ngay tại đây. Đã là chuỗi băm (copy từ bảng khác) -> giữ nguyên.
    """
    from django.contrib.auth.hashers import identify_hasher, make_password

    raw = (data.get("password") or "").strip()
    if not raw:
        instance.set_unusable_password()
        return
    try:
        identify_hasher(raw)
    except Exception:
        instance.password = make_password(raw)


PRE_SAVE_HOOKS = {
    "accounts.user": _prepare_user,
}

# password của User được hook xử lý riêng nên bỏ khỏi full_clean (nếu không,
# ô trống sẽ báo "không được để trống" dù ta cố ý đặt mật khẩu không dùng được).
EXTRA_VALIDATION_EXCLUDES = {
    "accounts.user": ["password"],
}
