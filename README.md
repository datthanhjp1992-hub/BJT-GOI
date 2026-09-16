# BJT-GOI

Ứng dụng web học từ vựng tiếng Nhật (tập trung nội dung theo BJT — Business Japanese
Proficiency Test) dành cho người Việt. Backend: Django + PostgreSQL.

## Cây thư mục

```
BJT-GOI/
├── manage.py
├── requirements.txt
├── .env.example              # copy thành .env rồi điền giá trị thật
├── .gitignore
├── README.md
├── label.properties           # TOÀN BỘ nhãn hiển thị (nút, field, nav, tiêu đề...)
├── message.properties         # TOÀN BỘ thông báo (lỗi, thành công, xác nhận, hint...)
│
├── config/                   # Django project settings/urls (không chứa business logic)
│   ├── settings/
│   │   ├── base.py           # settings dùng chung
│   │   ├── dev.py            # settings khi chạy local
│   │   └── prod.py           # settings khi deploy
│   ├── urls.py                # root URL router, include từng app
│   ├── wsgi.py
│   └── asgi.py
│
├── apps/                      # toàn bộ business logic nằm ở đây, chia theo domain
│   ├── core/                  # dùng chung cho mọi app khác
│   │   ├── models.py          # AuditableModel: created_by/created_at/updated_by/updated_at
│   │   ├── middleware.py      # lấy request.user hiện tại để tự điền audit fields
│   │   └── constants.py       # BJT_LEVEL_CHOICES, UI_THEME_CHOICES
│   │
│   ├── accounts/               # User, đăng nhập/đăng ký, hồ sơ, cài đặt (theme, mục tiêu)
│   │   ├── models.py           # User (kế thừa AbstractUser) + ui_theme, target_bjt_level
│   │   ├── views.py             # SC01, SC02, SC08, SC09
│   │   └── context_processors.py  # bơm ui_theme vào mọi template
│   │
│   ├── vocabulary/              # Topic, Vocabulary, ExampleSentence (nội dung học)
│   │   └── views.py              # SC05_DanhSachTuVung
│   │
│   ├── learning/                 # tiến độ học (SRS), flashcard, quiz, dashboard
│   │   ├── services.py            # thuật toán SM-2 (spaced repetition)
│   │   └── views.py                # SC03, SC04, SC06
│   │
│   ├── practice_sheets/           # tính năng tạo PDF luyện viết tay (SC10)
│   │   ├── pdf_generator.py        # port từ script mockup make_practice_pdf.py
│   │   └── views.py
│   │
│   ├── error_reports/             # Báo cáo lỗi nội dung (SC14): người học báo lỗi,
│   │   │                            #   admin xử lý ở khu quản trị
│   │   ├── models.py                # ErrorReport
│   │   └── services.py              # mark_fixed / dismiss / reopen (luồng trạng thái)
│   │
│   └── gamification/               # Góp ý (Contribution), Điểm, Danh hiệu nhiều nhóm (SC11-SC13)
│       ├── models.py                # Contribution, PointRule, UserPointTransaction,
│       │                            # BadgeCategory, BadgeTier, UserPinnedBadge
│       ├── services.py              # duyệt/từ chối góp ý, tính bậc danh hiệu, ghim danh hiệu
│       └── management/commands/seed_gamification.py
│
├── templates/                  # HTML templates, tổ chức theo app (khớp tên app ở trên)
│   ├── base.html                # layout gốc, load đúng theme_x.css theo user
│   ├── accounts/
│   ├── vocabulary/
│   ├── learning/
│   ├── practice_sheets/
│   └── error_reports/
│
├── static/
│   ├── css/theme_a.css          # 3 theme lấy từ bản mockup đã duyệt (Washi & Vermillion)
│   ├── css/theme_b.css          # (Studio Mono)
│   ├── css/theme_c.css          # (Genki Playful)
│   └── js/main.js
│
├── media/practice_sheets/       # nơi lưu file PDF luyện viết đã tạo cho từng user
│
└── docs/
    ├── STYLE_GUIDE.md            # token thiết kế của 3 theme — tham chiếu khi code UI mới
    ├── CHANGELOG_YEU_CAU.md      # lịch sử các thay đổi nghiệp vụ đã chốt
    └── mockup_reference/         # toàn bộ 30 file HTML mockup gốc (SC01-SC10 x 3 style)
                                   # + mau_luyen_viet.pdf, giữ lại để đối chiếu khi code UI
```

## Ghi chú thiết kế quan trọng

- **Audit columns**: mọi model nghiệp vụ (Topic, Vocabulary, UserVocabularyProgress,
  PracticeSheet, ...) kế thừa `apps.core.models.AuditableModel` để tự có sẵn 4 cột
  `created_by / created_at / updated_by / updated_at`. Không tự thêm 4 cột này thủ công
  vào model mới — chỉ cần kế thừa class này.
- **label.properties / message.properties — không hardcode chuỗi hiển thị**: mọi
  nhãn (label) và thông báo (message) tiếng Việt trong view/model/template đều tra
  qua `apps.core.properties.label(key)` / `.message(key, **kwargs)` (hoặc template
  tag `{% label %}` / `{% message %}`, xem `apps/core/templatetags/properties_tags.py`),
  KHÔNG viết chuỗi trực tiếp trong code. Quy ước đặt key (common vs riêng theo
  từng feature) ghi ngay trong 2 file — đọc phần đầu file trước khi thêm key mới.
  Sửa xong 2 file trên server đang chạy thì chạy `python manage.py reload_properties`
  để xoá cache (không cần restart).
- **MasterCode — không hardcode choices**: mọi danh sách lựa chọn hiển thị (cấp độ BJT,
  theme, loại/trạng thái góp ý, tên từng bậc danh hiệu...) nằm trong bảng
  `apps.core.models.MasterCode`, đọc/ghi qua `apps.core.mastercode` (có cache, tự
  invalidate). KHÔNG thêm `choices=[...]` cứng ở model mới — xem
  `apps/core/constants.py` (danh sách `code_type` đang dùng) và
  `docs/SPEC_GOP_Y_THANH_TICH.md` mục 2.
- **Theme (giao diện)**: lưu ở `User.ui_theme` (A/B/C), set trong màn Cài đặt
  (`apps.accounts.views.settings_view`). `base.html` tự chọn đúng file CSS theo
  `ui_theme` nhờ context processor `apps.accounts.context_processors.ui_theme`.
  Xem `docs/STYLE_GUIDE.md` để biết token màu/font của từng theme trước khi style
  thêm màn hình mới.
- **Cấp độ BJT**: lưu dạng chuỗi `J5..J1, J1+` (xem `apps.core.constants.BJT_LEVEL_CHOICES`).
  Đây là nhãn phân loại nội dung nội bộ, chưa phải thang điểm BJT chính thức (0-800) —
  xem lưu ý trong `docs/CHANGELOG_YEU_CAU.md` mục 5.
- **PDF luyện viết**: `apps/practice_sheets/pdf_generator.py` sinh PDF server-side bằng
  reportlab. Do font Noto Sans CJK trên server là dạng CFF/OpenType (reportlab không đọc
  trực tiếp được), chữ Nhật được render qua Pillow (ảnh) rồi chèn vào PDF; chữ Việt dùng
  font DejaVu Sans (TrueType, hỗ trợ đầy đủ dấu) đăng ký thẳng với reportlab.
- Các template trong `templates/*/` hiện mới là khung với TODO — cần copy phần HTML
  tương ứng từ `docs/mockup_reference/SCxx_..._<theme đã chọn>.html` vào, thay dữ liệu
  cứng bằng biến Django (`{{ ... }}` / `{% for %}`).

## Cài đặt & chạy thử

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # rồi sửa DB_* cho khớp PostgreSQL local của bạn

python manage.py migrate
python manage.py seed_mastercode      # nạp dữ liệu MasterCode (bắt buộc trước khi chạy app)
python manage.py seed_gamification    # nạp PointRule + BadgeCategory/BadgeTier
python manage.py createsuperuser
python manage.py runserver
```

Yêu cầu: PostgreSQL đã tạo sẵn database/user khớp với `.env`; máy chủ có sẵn font
`Noto Sans CJK` và `DejaVu Sans` (thường có sẵn trên Ubuntu/Debian qua gói
`fonts-noto-cjk` và `fonts-dejavu`) để tính năng tạo PDF luyện viết hoạt động đúng.

## Deploy lên Render

Render chạy web service (Django + gunicorn); database vẫn là PostgreSQL của
Supabase. Ba file phục vụ việc này: `render.yaml` (blueprint), `build.sh`
(các bước build) và `config/settings/render.py` (settings).

### Các bước

1. **Lấy connection string Supabase**: Dashboard > nút **Connect** > tab
   **Session pooler**, **cổng 5432**. Thay `[YOUR-PASSWORD]` bằng mật khẩu
   thật (ký tự đặc biệt phải URL-encode: `@` → `%40`, `#` → `%23`, `/` → `%2F`).

   > Đừng dùng **Direct connection** (`db.<ref>.supabase.co`) — nó chỉ có IPv6,
   > Render gọi không tới. Transaction pooler (6543) cũng chạy được nhưng
   > không có prepared statement, để dành cho môi trường serverless.

2. **Render Dashboard > New > Blueprint**, trỏ vào repo này. Render đọc
   `render.yaml`, hỏi đúng một biến là `DATABASE_URL` — dán chuỗi ở bước 1.

3. Bấm deploy. `build.sh` sẽ tự chạy `collectstatic`, `migrate`,
   `seed_mastercode`, `seed_gamification` (tất cả đều idempotent).

4. **Tạo tài khoản quản trị.** Gói free của Render không có shell, nên chạy từ
   máy mình, trỏ thẳng vào Supabase:

   ```bash
   # .env ở local đã có DATABASE_URL giống hệt
   python manage.py createsuperuser --settings=config.settings.supabase
   ```

### Những chỗ dễ vướng

- **403 CSRF khi bấm Đăng nhập** — thiếu `CSRF_TRUSTED_ORIGINS`.
  `config/settings/render.py` đã tự dựng từ `RENDER_EXTERNAL_HOSTNAME`, nên
  lỗi này chỉ xuất hiện nếu dùng tên miền riêng; lúc đó thêm tên miền vào biến
  môi trường `CSRF_TRUSTED_ORIGINS` (dạng `https://ten-mien.com`).
- **Trang trắng / 500 ngay ở CSS** — `collectstatic` chưa chạy.
  `CompressedManifestStaticFilesStorage` cần file `staticfiles.json`; đó là lý
  do `build.sh` gọi `collectstatic` TRƯỚC `migrate`.
- **Lần vào đầu tiên chậm ~1 phút** — gói free ngủ sau 15 phút không có
  request. Bình thường.
- **Supabase free tự pause sau 7 ngày không hoạt động** → app sẽ không nối
  được DB. Cần một cron ping định kỳ (GitHub Actions) nếu để lâu không dùng.
- **File PDF luyện viết (SC10) sẽ mất sau mỗi lần deploy** — đĩa của instance
  Render là tạm. Khi làm tới màn đó phải chuyển `MEDIA_ROOT` sang Supabase
  Storage hoặc S3, và cài font Noto Sans CJK + DejaVu cho reportlab.

### GitHub Pages vẫn giữ nguyên
`index.html` + `.nojekyll` ở gốc repo là **site tài liệu tĩnh** (sơ đồ CSDL,
bản mẫu giao diện), không liên quan tới ứng dụng chạy trên Render. Hai thứ
sống song song, không xung đột.
