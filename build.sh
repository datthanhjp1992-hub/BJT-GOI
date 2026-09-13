#!/usr/bin/env bash
#
# Build command của Render:  bash ./build.sh
#
# Gọi qua `bash ./build.sh` chứ không phải `./build.sh` để không phụ thuộc bit
# thực thi của file — repo này được commit từ Windows, bit đó thường mất.
set -o errexit   # lỗi một bước là dừng, không deploy bản nửa vời
set -o pipefail
set -o nounset

pip install --upgrade pip
pip install -r requirements.txt

# Gom static cho WhiteNoise. BẮT BUỘC chạy ở bước build vì
# CompressedManifestStaticFilesStorage cần file staticfiles.json lúc runtime —
# thiếu nó là mọi trang 500 ngay ở thẻ {% static %} đầu tiên.
python manage.py collectstatic --no-input

# Supabase là DB dùng chung; migration của repo chỉ thêm bảng/cột nên chạy
# trước khi instance mới lên là an toàn.
python manage.py migrate --no-input

# Cả hai đều idempotent (update_or_create) — deploy lại bao nhiêu lần cũng
# không tạo bản ghi trùng. Thiếu seed_mastercode thì MỌI <select> trên UI rỗng
# (cấp độ BJT, theme...), xem apps/core/mastercode.py.
python manage.py seed_mastercode
python manage.py seed_gamification
