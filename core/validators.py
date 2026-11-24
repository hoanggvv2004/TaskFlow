import os

from django.conf import settings
from django.core.exceptions import ValidationError


def validate_upload_file(uploaded_file):
    name = uploaded_file.name or ""
    _, ext = os.path.splitext(name.lower())
    blocked = getattr(settings, "BLOCKED_UPLOAD_EXTENSIONS", set())
    allowed = getattr(settings, "ALLOWED_UPLOAD_EXTENSIONS", set())
    max_size = getattr(settings, "MAX_UPLOAD_SIZE", 10 * 1024 * 1024)

    if not ext:
        raise ValidationError("Tên tệp không hợp lệ.")
    if ext in blocked:
        raise ValidationError("Không cho phép tải lên tệp thực thi.")
    if ext not in allowed:
        raise ValidationError("Định dạng tệp không được hỗ trợ.")
    if uploaded_file.size > max_size:
        raise ValidationError("Dung lượng tệp vượt quá 10MB.")
    if ".." in name or "/" in name.replace("\\", "/").lstrip("."):
        raise ValidationError("Tên tệp không hợp lệ.")
    return True
