"""
Loader cho label.properties / message.properties ở project root — nguồn duy
nhất cho MỌI chuỗi hiển thị (label) và MỌI thông báo hệ thống (message).
Không hardcode chuỗi tiếng Việt trong view/model/template nữa — luôn gọi
label(key) / message(key) ở đây, hoặc dùng template tag tương ứng
(apps/core/templatetags/properties_tags.py).

Định dạng: chuẩn Java .properties — dòng "key = value", dòng bắt đầu bằng
"#" là comment, dòng trống bị bỏ qua. Không dùng section như .ini vì
.properties vốn phẳng; tính phân nhóm common/riêng thể hiện qua PREFIX của
key (vd "common.button.save" vs "accounts.login.title"), xem quy ước đầy đủ
ở đầu 2 file .properties.

message() hỗ trợ placeholder kiểu str.format: "Đã cộng {points} điểm" ->
message("contribution.approve.success", points=10).
"""
from pathlib import Path

from django.conf import settings
from django.core.cache import cache

LABEL_FILE = Path(settings.BASE_DIR) / "label.properties"
MESSAGE_FILE = Path(settings.BASE_DIR) / "message.properties"

_CACHE_TTL_SECONDS = 300
_CACHE_KEY_LABEL = "properties:label"
_CACHE_KEY_MESSAGE = "properties:message"


def _parse_properties_file(path):
    """Đọc 1 file .properties thành dict {key: value}. Bỏ qua dòng comment
    (#...), dòng trống, và dòng không có dấu '='."""
    data = {}
    if not path.exists():
        return data
    with open(path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            data[key.strip()] = value.strip()
    return data


def _load(cache_key, path):
    data = cache.get(cache_key)
    if data is not None:
        return data
    data = _parse_properties_file(path)
    cache.set(cache_key, data, _CACHE_TTL_SECONDS)
    return data


def label(key, default=None):
    """Tra 1 label theo key, vd label("common.button.save") -> "Lưu".
    Trả `default` (hoặc chính `key` nếu không truyền default) nếu thiếu —
    không raise, để UI không vỡ khi quên thêm key mới vào label.properties."""
    data = _load(_CACHE_KEY_LABEL, LABEL_FILE)
    return data.get(key, default if default is not None else key)


def message(key, default=None, **kwargs):
    """Tra 1 message theo key, hỗ trợ format placeholder qua kwargs, vd:
    message("contribution.approve.success", points=10)
    -> "Đã duyệt góp ý và cộng 10 điểm cho người gửi." """
    data = _load(_CACHE_KEY_MESSAGE, MESSAGE_FILE)
    template = data.get(key, default if default is not None else key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return template
    return template


def reload_cache():
    """Gọi sau khi sửa tay 2 file .properties trên server (không cần restart
    process) — hoặc tự động qua management command `reload_properties`."""
    cache.delete(_CACHE_KEY_LABEL)
    cache.delete(_CACHE_KEY_MESSAGE)
