# Style Guide — Ứng dụng học từ vựng Nhật-Việt

Tài liệu này mô tả 3 bộ style (theme) đang được thiết kế. Người dùng có thể chọn 1 trong 3 style trong màn hình **SC08_CaiDat** (Cài đặt). Khi phát triển màn hình mới, hãy dựa vào token màu/kiểu chữ/khoảng cách tương ứng bên dưới để đảm bảo đồng bộ với style hiện có, **thay vì tự sáng tạo màu/kiểu mới**.

Style được lưu theo user (ví dụ cột `ui_theme` trong bảng `users`, giá trị: `A` | `B` | `C`), áp dụng bằng cách load đúng file CSS theme tương ứng (`style_A.css` / `style_B.css` / `style_C.css` trong bản mẫu — khi lên Django sẽ là 1 file CSS biến `--theme` hoặc load class `theme-a/theme-b/theme-c` trên `<body>`).

---

## Style A — "Washi & Vermillion"
Phong cách truyền thống Nhật Bản, giấy washi ấm áp, điểm nhấn đỏ son. Dùng cho cảm giác trang trọng, học thuật.

| Token | Giá trị | Ý nghĩa |
|---|---|---|
| `--bg` | `#FAF6EE` | Nền trang (giấy washi) |
| `--surface` | `#FFFFFF` | Nền card/panel |
| `--ink` | `#24211D` | Màu chữ chính |
| `--ink-soft` | `#6b6455` | Chữ phụ / muted |
| `--accent` | `#B5432E` | Màu nhấn chính (đỏ son) |
| `--accent-dark` | `#8f3323` | Hover của accent |
| `--accent-soft` | `#f0d9cf` | Nền nhẹ cho tag/badge |
| `--gold` | `#B8912B` | Điểm nhấn phụ |
| `--teal` | `#3F6B63` | Điểm nhấn phụ (trạng thái tích cực) |
| `--border` | `#DCD3C0` | Viền, đường phân cách |
| Font tiêu đề | `Georgia, "Hiragino Mincho ProN", "Yu Mincho", serif` | Serif — trang trọng |
| Font nội dung | `-apple-system, "Hiragino Kaku Gothic ProN", "Yu Gothic", system-ui, sans-serif` | Sans hệ thống |
| Bo góc | 3–6px (gần vuông) | |
| Card | viền 1px `--border`, không đổ bóng | |

## Style B — "Studio Mono"
Hiện đại, tối giản, dạng lưới phẳng, một màu nhấn indigo. Cảm giác chuyên nghiệp kiểu SaaS.

| Token | Giá trị | Ý nghĩa |
|---|---|---|
| `--bg` | `#F2F3EF` | Nền trang |
| `--surface` | `#FFFFFF` | Nền card |
| `--ink` | `#14141A` | Chữ chính |
| `--ink-soft` | `#6b6c72` | Chữ phụ |
| `--accent` | `#3B4FC7` | Màu nhấn (indigo) |
| `--accent-soft` | `#e4e7fb` | Nền nhẹ cho tag/badge |
| `--sage` | `#5C7A6A` | Điểm nhấn phụ |
| `--border` | `#DCDDD7` | Viền |
| Font | `-apple-system, "Segoe UI", system-ui, sans-serif` | Sans, letter-spacing -0.01em |
| Font số liệu | `ui-monospace, "SF Mono", Menlo, monospace` | Dùng cho số liệu thống kê, nhãn UPPERCASE |
| Bo góc | 0px (vuông hoàn toàn) | |
| Card | viền 1px `--border`, grid dùng đường viền 1px làm gap thay vì khoảng trắng | |

## Style C — "Genki Playful"
Tươi sáng, bo tròn, gamified — phù hợp học nhẹ nhàng, vui vẻ mỗi ngày, dùng nhiều emoji.

| Token | Giá trị | Ý nghĩa |
|---|---|---|
| `--bg` | `#F6F1FF` | Nền trang (tím pastel) |
| `--surface` | `#FFFFFF` | Nền card |
| `--ink` | `#2E1F3D` | Chữ chính |
| `--ink-soft` | `#7a6f8c` | Chữ phụ |
| `--coral` | `#FF6F61` | Màu nhấn chính |
| `--coral-dark` | `#e5564a` | Hover của coral |
| `--yellow` | `#FFC93C` | Điểm nhấn phụ / thành tích |
| `--sky` | `#4FB6E8` | Điểm nhấn phụ |
| `--mint` | `#3FC1A2` | Trạng thái tích cực |
| `--border` | `#E8DFFB` | Viền |
| Font | `-apple-system, "Segoe UI", system-ui, sans-serif` | Sans, đậm (font-weight 700–800 cho tiêu đề) |
| Bo góc | 14–28px (bo tròn nhiều) | |
| Card | viền 2px màu `--border`, đôi khi có `box-shadow` kiểu "nút bấm" (offset shadow) | |

---

## Quy tắc dùng chung cho cả 3 style
- Component dùng chung 1 bộ class: `.topbar`, `.mainnav`, `.card`, `.btn`, `.btn-primary`, `.btn-outline`, `.stat`, `.tag`, `.tag.level`, `.flashcard`, `.progressbar`, `.sidebar`, `.admin-layout` — chỉ khác nhau về giá trị token màu/bo góc/font khai báo trong file CSS riêng của từng style.
- Khi thêm màn hình mới: dùng lại đúng các class trên, không tạo class mới trùng chức năng.
- Mọi màn hình phải có 3 bản tương ứng 3 style (đặt tên file theo quy tắc bên dưới) để người dùng luôn xem được đúng giao diện họ đã chọn trong Cài đặt.
- Quy tắc đặt tên file mockup: `SCxx_TenManHinh_X.html` với `X` ∈ {A, B, C}. CSS riêng theo style: `style_X.css`.

## Ghi chú cho bản Django thật

### Cấu trúc CSS (từ 02/10/2026 — spec.md Phase 2)
`templates/base.html` nạp **hai** file, theo đúng thứ tự:

1. `static/css/theme_x.css` (x = a/b/c theo `User.ui_theme`) — token (`:root`) + những rule
   mà theme này THẬT SỰ khác hai theme kia (bo góc, cỡ chữ, độ đậm, viền...).
2. `static/css/base.css` — mọi rule giống nhau ở cả 3 theme. Nạp SAU nên khi trùng
   thuộc tính với theme thì base thắng.

Quy tắc khi sửa:
- Rule mới dùng chung → viết ở `base.css`, chỉ dùng biến (`var(--surface)`...). Không chép vào 3 file theme.
- Theme cần giá trị khác → đè trong `theme_x.css`, và KHÔNG khai báo cùng thuộc tính cho cùng selector ở `base.css` (base nạp sau sẽ thắng).
- Không viết `style="..."` cố định trong template — dùng class ở mục "T2.2" cuối `base.css`
  (`.m-0`, `.mb-18`, `.text-sm`...). Chỉ style phụ thuộc dữ liệu (`width:{{ percent }}%`) mới để inline.
- `apps/accounts/tests.py` kiểm tra mọi `var(--token)` đều được khai ở cả 3 theme.

### Token bổ sung (T2.2 / T2.3)
Ngoài bảng token gốc ở trên, mỗi theme khai thêm (giá trị ở chế độ sáng giữ nguyên màu cũ):

| Token | Dùng cho |
|---|---|
| `--accent-text`, `--accent-text-strong` | CHỮ màu nhấn (link, nhãn, mục đang chọn). Chế độ tối sáng hơn `--accent` để đủ tương phản. `--accent` vẫn là màu TÔ NỀN nút (chữ trắng). |
| `--surface-alt`, `--row-hover`, `--line-soft`, `--chip-bg` | Nền phụ nhạt, hàng bảng khi rê chuột, đường kẻ mảnh, chip đếm |
| `--good-bg`, `--good-line`, `--bad-bg` | Nền đúng/sai (kính ngữ, bài tập) |
| `--error`, `--error-bg` | Thông báo lỗi (`.flash.error`) |
| `--grade-{forgot,hard,good}-{bg,fg}` | 4 nút chấm SC04 |
| `--ink-fill` (theme B) | Nền nút màu mực — tối thì đổi sang xám đậm để chữ trắng còn đọc được |
| `--study-radius` | Bo góc riêng các khối của màn học SC04 |

### Chế độ sáng / tối (T2.3)
- `User.color_scheme` = `auto` | `light` | `dark` (MasterCode `code_type` 18), chọn ở SC08.
- `base.html` đặt `<html data-scheme="...">`. Mỗi theme có bảng màu tối ở
  `:root[data-scheme="dark"]` và (giống hệt) trong `@media (prefers-color-scheme:dark){:root[data-scheme="auto"]}`.
- Bảng màu tối chỉ ĐỔI GIÁ TRỊ TOKEN — muốn một màu mới đổi theo chế độ tối thì phải dùng token, không viết mã màu cứng.
- Mọi cặp chữ/nền ở chế độ tối đạt tương phản ≥ 4.5:1 (đo lúc làm T2.3).

### Điện thoại (T2.4)
- ≤ 900px: sidebar ẩn, nút ☰ ở top panel mở thành danh sách dọc.
- ≤ 720px: `<table>` không class tự cuộn ngang trong chính nó. Bảng có bố cục mobile riêng (kính ngữ) thì đặt class và tự lo.
