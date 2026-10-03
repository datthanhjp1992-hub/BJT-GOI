# Spec — Cải thiện UI/UX và cách hoạt động của BJT-GOI

> Ngày lập: 02/10/2026 · Trạng thái: **Đã duyệt (02/10/2026)** · Người duyệt: Dat
>
> Tài liệu này liệt kê các task cải thiện giao diện và trải nghiệm, kèm cách làm
> cụ thể. Mỗi task ghi rõ **mục tiêu → file đụng tới → cách làm → điều kiện
> hoàn thành → test**. Duyệt xong phase nào thì code phase đó.

---

## 0. Nguyên tắc chung (áp dụng cho MỌI task)

Giữ đúng các quy ước đang có trong dự án:

1. **Không hardcode chuỗi hiển thị.** Mọi nhãn/thông báo mới thêm vào
   `label.properties` / `message.properties`, tra qua `{% label %}` / `{% message %}`.
   Đặt key theo đúng scope (`learning.*`, `common.*`...).
2. **Không hardcode choices.** Danh sách lựa chọn mới đi qua `MasterCode` + `seed_mastercode.py`.
3. **Model mới kế thừa `AuditableModel`.**
4. **Cải tiến dần (progressive enhancement):** mọi tính năng JavaScript mới phải có
   đường lùi khi tắt JS — form POST + redirect vẫn chạy như hiện tại.
   Không thêm framework front-end, không thêm build step.
5. **Đủ 3 theme A/B/C.** Sửa giao diện phải kiểm tra cả 3 theme.
6. **Logic nằm ở `services.py` / `selectors.py`,** view chỉ lắp context.
7. **Mỗi task có test** trong `apps/<app>/tests.py`. Chạy `python manage.py test` xanh trước khi commit.
8. **Cập nhật `flowChart/js/flows.js`** khi luồng xử lý thay đổi.

---

## Tổng quan lộ trình

| Phase | Nội dung | Ưu tiên | Ước lượng |
|---|---|---|---|
| 1 | Màn học flashcard: chấm thẻ không tải lại trang, phím tắt, hiện thẻ 2 bước, chế độ tập trung, mobile | ⭐ Cao nhất | 3–4 ngày |
| 2 | Hệ thống thiết kế: gom 3 file CSS theme, bỏ inline style, dark mode | ⭐ Cao | 2–3 ngày |
| 3 | Luồng sử dụng: nút "Học hôm nay", hướng dẫn lần đầu, trạng thái trống/đang tải | ⭐ Cao (cần duyệt nghiệp vụ) | 3–4 ngày |
| 4 | Hiệu năng & hạ tầng: cold start Render, đo và giảm số query | Trung bình | 1–2 ngày |
| 5 | Mở rộng: nhắc học (email/PWA), đưa kính ngữ vào SRS | Thấp (làm sau) | Tách spec riêng |

**Thứ tự đề xuất:** Phase 1 → Phase 2 → Phase 3 → Phase 4. Phase 2 có thể làm
song song với Phase 1, nhưng nên merge Phase 2 **trước** khi làm các màn mới ở
Phase 3 để không phải viết CSS 3 lần.

---

## Phase 1 — Màn học flashcard (SC04 / phiên học theo hàng đợi)

Màn được dùng nhiều nhất: `templates/learning/flashcard.html`, dùng chung cho
`flashcard_view` (theo chủ đề) và `study_view` (theo bộ lọc SC05 / SC15).

### T1.1 ⭐ Tách template thẻ thành partial

**Mục tiêu:** chuẩn bị cho T1.2 — phần thẻ phải render được riêng, không kèm layout.

**File:** `templates/learning/flashcard.html`, tạo mới `templates/learning/_card_panel.html`.

**Cách làm:**
- Chuyển toàn bộ nội dung trong `{% block content %}` sang `_card_panel.html`.
- `flashcard.html` chỉ còn:
  ```django
  {% block content %}
    <div id="card-panel" data-card-panel>{% include "learning/_card_panel.html" %}</div>
  {% endblock %}
  ```
- Không đổi context, không đổi hành vi.

**Hoàn thành khi:** mọi test hiện có của `apps/learning/tests.py` vẫn xanh, giao diện không đổi.

---

### T1.2 ⭐ Chấm thẻ không tải lại trang (AJAX + đường lùi khi tắt JS)

**Mục tiêu:** bấm Quên/Khó/Nhớ/Dễ thì thẻ kế tiếp hiện ngay, không tải lại cả
trang. Hiện mỗi lần chấm = POST → 302 → GET cả trang (sidebar, CSS, JS), mất
khoảng 0,5–1,5 giây do Render (Singapore) gọi Supabase (Tokyo).

**File:** `apps/learning/views.py`, `static/js/main.js`, `_card_panel.html`.

**Cách làm:**
1. **Server — trả fragment khi được yêu cầu:**
   - Thêm helper trong `views.py`:
     ```python
     PARTIAL_HEADER = "HTTP_X_CARD_PARTIAL"

     def _wants_partial(request):
         return request.META.get(PARTIAL_HEADER) == "1"

     def _render_card(request, context):
         template = "learning/_card_panel.html" if _wants_partial(request) else "learning/flashcard.html"
         return render(request, template, context)
     ```
   - `flashcard_view` và `study_view` dùng `_render_card(...)` thay cho `render(...)`
     (cả nhánh "hết thẻ" lẫn nhánh có thẻ).
   - Các view POST (`flashcard_review`, `study_review_view`, `undo_view`) **giữ nguyên
     redirect**. `fetch()` tự đi theo redirect cùng origin và giữ header tự đặt, nên GET
     sau redirect vẫn nhận `X-Card-Partial: 1` → trả fragment. Không phải sửa logic chấm.
   - Thêm `Vary: X-Card-Partial` vào response (`django.utils.cache.patch_vary_headers`)
     để trình duyệt/proxy không cache lẫn hai dạng.
2. **Client — `initCardPanel()` trong `main.js`:**
   - Bắt sự kiện `submit` (event delegation trên `[data-card-panel]`) cho các form có
     `data-ajax` (form chấm điểm, form hoàn tác).
   - `fetch(form.action, {method: "POST", body: new FormData(form), headers: {"X-Card-Partial": "1"}, credentials: "same-origin"})`.
     Nhớ gửi kèm giá trị của nút đã bấm (`event.submitter.name/value`) vào FormData.
   - Nhận HTML → thay `innerHTML` của `#card-panel` → gọi lại `initFlashcards()` → focus vào thẻ.
   - Khoá các nút trong lúc chờ (chống bấm 2 lần); lỗi mạng / response không OK →
     `form.submit()` bình thường (lùi về cách cũ).
   - Cập nhật `document.title` nếu cần; flash message (`partials/messages.html`) cũng
     include trong fragment để thông báo "Đã hoàn tác…" vẫn hiện.
3. Form bình luận, góp ý, báo lỗi **không** chuyển sang AJAX ở task này (giữ submit thường).

**Hoàn thành khi:**
- Chấm 1 thẻ không tải lại trang; nút Back của trình duyệt không bị kẹt.
- Tắt JS: mọi thứ chạy như hiện tại.
- Hoàn tác hoạt động trong cả hai chế độ.

**Test:**
- GET `learning:flashcard` có header `HTTP_X_CARD_PARTIAL="1"` → dùng template `_card_panel.html`, không có `<html>`.
- POST chấm điểm với `follow=True` + header → response cuối là fragment.
- Không có header → full page như cũ.

---

### T1.3 ⭐ Phím tắt

**Mục tiêu:** học nhanh bằng bàn phím như Anki.

| Phím | Hành động |
|---|---|
| `Space` / `Enter` | Lật thẻ (hiện đáp án) |
| `1` `2` `3` `4` | Quên / Khó / Nhớ / Dễ (chỉ khi thẻ đã lật — xem T1.4) |
| `Z` | Hoàn tác |
| `E` | Mở/đóng ví dụ |
| `?` | Hiện bảng phím tắt |

**File:** `static/js/main.js`, `_card_panel.html`, `label.properties`.

**Cách làm:**
- Gắn `data-grade="quen|kho|nho|de"` cho 4 nút, `data-undo` cho nút hoàn tác.
- Một listener `keydown` trên `document`, **bỏ qua** khi focus đang ở `input`,
  `textarea`, `select` hoặc `[contenteditable]` (để gõ bình luận không bị bắt phím),
  và bỏ qua khi có phím Ctrl/Alt/Meta.
- Phím số → `button.click()` (đi qua đúng luồng submit của T1.2).
- Hiện số phím nhỏ trên mỗi nút (`<kbd>1</kbd>`), ẩn trên thiết bị cảm ứng
  (`@media (hover: none)`).
- Bảng phím tắt: `<dialog>` đơn giản, nội dung lấy từ label (`learning.flashcard.shortcut.*`).

**Hoàn thành khi:** học trọn một phiên chỉ bằng bàn phím; gõ bình luận không kích hoạt phím tắt.

---

### T1.4 ⭐ Hiện thẻ theo 2 bước (nhớ trước, xem sau)

**Mục tiêu:** buộc người học tự nhớ trước khi thấy nghĩa. Hiện 4 nút chấm hiện
sẵn nên có thể bấm mà không cần lật thẻ.

**File:** `_card_panel.html`, `main.js`, 3 file CSS (hoặc `base.css` nếu Phase 2 xong trước).

**Cách làm:**
- Trạng thái 1: thẻ chỉ hiện mặt chữ (+ cách đọc tuỳ chọn, xem dưới) và một nút lớn
  **"Hiện đáp án"** (`Space`). Khối 4 nút chấm có class `.grade-row` và bị ẩn.
- Trạng thái 2: thẻ lật (`.is-flipped`) → hiện nghĩa + ví dụ + 4 nút chấm.
- Thực hiện bằng CSS: `.flashcard-wrap:not(.is-revealed) .grade-row{display:none}`;
  JS thêm `.is-revealed` khi lật.
- `<noscript>`: hiện thẳng nghĩa + 4 nút (giữ đúng hành vi hiện tại khi tắt JS).
- **Tuỳ chọn trong SC08** (mới): "Hiện cách đọc ở mặt trước" — field
  `User.show_reading_on_front` (BooleanField, mặc định True), migration mới,
  thêm vào `accounts/forms.py` + `templates/accounts/settings.html`
  (cùng cách đã làm với `show_review_interval`).

**Hoàn thành khi:** không thể chấm khi chưa lật (khi bật JS); tắt JS vẫn chấm được.

---

### T1.5 Chế độ tập trung khi học

**Mục tiêu:** bớt rối mắt — sidebar, khối góp ý/báo lỗi/bình luận chiếm chỗ ngay dưới thẻ.

**File:** `templates/base.html`, `_card_panel.html`, CSS.

**Cách làm:**
- `base.html`: thêm `{% block shell_class %}{% endblock %}` vào `<div class="app-shell ...">`.
  `flashcard.html` đặt `is-focus`.
- CSS: `.app-shell.is-focus .site-sidebar{display:none}` trên màn ≥ 720px, kèm nút
  "☰" nhỏ ở topbar để mở lại sidebar (trạng thái nhớ bằng `localStorage`, có try/catch).
- Gom "Góp ý sửa nghĩa / Báo lỗi / Bình luận" vào một `<details>` **"💬 Thảo luận về từ này (N)"**,
  mặc định đóng; N = số bình luận. Chỉ hiện sau khi lật thẻ.
- Thanh trên cùng của màn học gọn lại: thanh tiến độ + "x/N" + nút "Kết thúc".

**Hoàn thành khi:** khi đang học, màn hình chỉ còn thẻ, tiến độ và 4 nút chấm ở vùng nhìn đầu tiên.

---

### T1.6 Tối ưu cho điện thoại

**Mục tiêu:** học thoải mái bằng một tay.

**File:** CSS, `main.js`.

**Cách làm:**
- Màn ≤ 560px: 4 nút chấm cố định ở đáy màn hình (`position: sticky; bottom: 0`),
  đủ cao để ngón cái bấm (≥ 48px), tôn trọng `env(safe-area-inset-bottom)`.
- Chạm vào thẻ để lật (đã có).
- **Vuốt** (tuỳ chọn, làm sau cùng): `touchstart`/`touchend` trên `.flashcard`,
  vuốt trái = Quên, vuốt phải = Nhớ, ngưỡng ≥ 80px và chỉ khi thẻ đã lật.
  Có hiệu ứng nghiêng thẻ + màu báo trước khi thả tay.
- Kiểm tra ở 375×812 cho cả 3 theme.

**Hoàn thành khi:** học trọn một phiên trên điện thoại không phải cuộn lên xuống để bấm nút.

---

### T1.7 Màn tổng kết cuối phiên

**Mục tiêu:** cảm giác "xong việc" rõ ràng, có hướng đi tiếp.

**File:** `_card_panel.html` (nhánh `word is None`), `views._session_summary`.

**Cách làm:**
- Giữ 3 ô số liệu hiện có; thêm **thời gian học** (`ended_at - started_at` của StudySession)
  và **streak hiện tại** (`services.get_streak_days`).
- Một nút chính duy nhất theo ngữ cảnh: còn từ cần ôn thêm → "Ôn thêm N từ";
  không còn → "Về trang chủ". Các lựa chọn khác là link phụ.
- Hiệu ứng nhẹ khi hoàn thành (CSS animation, tôn trọng `prefers-reduced-motion`).

---

## Phase 2 — Hệ thống thiết kế (CSS)

### T2.1 ⭐ Gom 3 file theme về 1 file chung + biến CSS

**Hiện trạng:** `static/css/theme_a.css`, `theme_b.css`, `theme_c.css` mỗi file ~830
dòng. `diff` giữa A và B chỉ ~270 dòng khác nhau → phần lớn là chép lại. Mỗi lần
sửa giao diện phải sửa 3 chỗ (commit `fix sc05` gần nhất sửa cả 3 file).

**File:** tạo `static/css/base.css`; rút gọn 3 file theme; `templates/base.html`.

**Cách làm:**
1. Viết script nhỏ (để trong `scripts/`, không deploy) so sánh từng rule của 3 file:
   rule giống hệt nhau → chuyển sang `base.css`; rule khác chỉ ở giá trị
   màu/font/bo góc/đổ bóng → thay giá trị bằng biến (`var(--radius)`, `var(--shadow)`,
   `var(--btn-weight)`...) rồi chuyển sang `base.css`; rule khác cấu trúc thật sự →
   giữ lại trong file theme.
2. Mỗi file theme chỉ còn: khối `:root{...}` khai báo token + phần ghi đè riêng.
   Mục tiêu: mỗi file theme ≤ 150 dòng.
3. `base.html` nạp `base.css` trước, rồi `theme_x.css`.
4. Cập nhật `htmlTemplate/STYLE_GUIDE.md` / `docs/STYLE_GUIDE.md`: bảng token mới.

**Hoàn thành khi:**
- Chụp màn hình trước/sau của các màn chính (SC03, SC04, SC05, SC10, SC13, SC15, SC16,
  SC07) × 3 theme không có khác biệt đáng kể.
- Thêm một rule mới chỉ cần sửa `base.css`.

**Kiểm tra:** dùng trình duyệt chụp ảnh từng màn ở 1280px và 375px trước khi sửa, sau khi sửa so lại.

---

### T2.2 Bỏ inline style trong template

**Hiện trạng:** nhiều `style="..."` trong template (vd `flashcard.html` có hàng chục chỗ),
và màu 4 nút chấm nằm trong Python (`GRADE_BUTTONS` ở `apps/learning/views.py`).

**Cách làm:**
- `GRADE_BUTTONS` bỏ cột style, thay bằng class: `.btn-grade.is-forgot / .is-hard / .is-good / .is-easy`
  → màu khai báo bằng token trong từng theme.
- Thay các inline style lặp lại bằng class tiện ích nhỏ trong `base.css`
  (`.text-center`, `.mt-2`, `.text-sm`, `.stack`...) — giới hạn ở khoảng 15 class, không biến thành Tailwind.
- Làm theo từng màn, ưu tiên màn đã đụng ở Phase 1.

**Hoàn thành khi:** `grep -c 'style="' templates/learning/*.html` giảm ≥ 80%.

---

### T2.3 Chế độ tối (dark mode)

**Cách làm:**
- Sau T2.1, mỗi theme thêm khối `@media (prefers-color-scheme: dark){ :root{...} }`
  chỉ đổi token màu.
- SC08 thêm lựa chọn "Giao diện sáng/tối": Theo hệ thống / Sáng / Tối.
  Lưu ở `User.color_scheme` — danh sách lựa chọn đi qua **MasterCode code_type mới "18"**
  (seed trong `seed_mastercode.py`, khai hằng số trong `apps/core/constants.py`).
- `base.html`: `<html data-scheme="{{ user.color_scheme }}">`; CSS dùng
  `:root[data-scheme="dark"]` ghi đè, `:root[data-scheme="auto"]` theo media query.

**Hoàn thành khi:** 3 theme × 2 chế độ đều đọc được rõ (độ tương phản chữ ≥ 4.5:1).

---

### T2.4 Kiểm tra giao diện trên điện thoại toàn site

**Cách làm:** duyệt từng màn ở 375px × 3 theme, ghi lại chỗ vỡ vào bảng ở cuối file này
(mục "Nhật ký kiểm tra mobile"), sửa theo thứ tự màn dùng nhiều nhất.
Chú ý: sidebar trên mobile nên thành menu trượt (nút ☰), bảng dữ liệu (SC05, SC07)
cho cuộn ngang trong khung riêng chứ không làm tràn cả trang.

---

## Phase 3 — Luồng sử dụng

> ⚠️ Phase này **đổi luồng nghiệp vụ** — các điểm cần chốt đã được Dat duyệt ngày 02/10/2026.

### T3.1 ⭐ Nút "Học hôm nay" trên trang chủ (SC03)

**Hiện trạng:** có 3 lối vào học khác nhau, mỗi lối một logic hàng đợi:
- Trang chủ → "Học tiếp" → `flashcard_view` (1 chủ đề, `get_topic_queue`).
- SC05 → "Bắt đầu học" → `study_*` (bộ lọc, `build_study_queue`).
- SC15 → các thẻ ôn → `study_*` (theo phạm vi).

Người mới không biết nên bấm đâu, và từ đến hạn ở chủ đề khác không được nhắc.

**Đề xuất:** trang chủ có **một nút chính**:

> **Học hôm nay** — 23 từ cần ôn · 10 từ mới · khoảng 11 phút

Hàng đợi gom **mọi chủ đề**: (1) từ đến hạn ôn, quá hạn lâu nhất trước → (2) từ mới,
tối đa `daily_review_goal − số từ mới đã học hôm nay`.

**Đã chốt (02/10/2026):**
- (a) Từ mới ưu tiên **chủ đề đang học dở** (`get_topic_in_progress`), hết thì sang
  chủ đề gợi ý tiếp theo (`get_suggested_topics`) — không trộn ngẫu nhiên.
- (b) Cho chọn "chủ đề ưu tiên" trong SC08: **để sau**, không làm trong task này.
- (c) **Bỏ** link "Học tiếp chủ đề X" — trang chủ chỉ còn một nút chính "Học hôm nay".
  Khối "đang học dở" hiện tại trên `dashboard.html` (dựa trên `get_topic_in_progress`)
  được gỡ khỏi giao diện; hàm service vẫn giữ vì `build_daily_queue` dùng nó ở mục (a).
  Muốn học riêng một chủ đề thì vào SC05.

**File:** `apps/learning/services.py`, `apps/learning/views.py`, `apps/learning/urls.py`,
`templates/learning/dashboard.html`, properties.

**Cách làm:**
1. `services.build_daily_queue(user) -> list[int]` — **tái dùng luồng `study_*`**, không viết luồng học thứ tư:
   - Từ đến hạn: `UserVocabularyProgress` của user có `card_state=REVIEW` và
     `next_review_date <= today`, sắp theo `next_review_date`, rồi đến từ đang ở bước học.
   - Từ mới: `Vocabulary` chưa có progress của user, lấy theo thứ tự ở mục (a),
     cắt theo hạn mức còn lại (dùng `count_new_words_today`).
2. `services.get_daily_overview(user)` trả `{due, new, minutes}` cho nút trang chủ
   (dùng chung `SECONDS_PER_WORD`).
3. View mới `daily_start_view` (POST): gọi `build_daily_queue`, rồi khởi tạo phiên
   giống hệt `study_start_view` (tách phần "khởi tạo phiên" thành helper
   `_start_study_session(request, queue, scope_label, topic=None, touch=True)` và cho
   `study_start_view`, `study_retry_view`, `review_start_view` dùng chung — giảm lặp code).
4. `dashboard.html`: khối nút chính ở đầu trang; khi `due == new == 0` → trạng thái
   "Hôm nay xong rồi 🎉" + số từ đến hạn ngày mai + link "Học thêm từ mới".

**Hoàn thành khi:** người dùng có từ đến hạn ở 3 chủ đề khác nhau bấm một nút là ôn hết.

**Test:** hàng đợi gồm đúng từ đến hạn của nhiều chủ đề; từ mới không vượt hạn mức;
hoàn tác từ mới làm hạn mức lùi lại; trạng thái "xong" khi không còn gì.

---

### T3.2 Hướng dẫn lần đầu (onboarding)

**Mục tiêu:** đăng ký xong là vào học được ngay trong 1 phút.

**Cách làm:**
- Sau `register_view` → redirect sang `accounts:onboarding` (màn mới, 2 bước, 1 form):
  1. Mục tiêu mỗi ngày: 5 / 10 / 20 / 30 từ mới (ghi vào `daily_review_goal`) —
     danh sách lấy từ **MasterCode code_type mới "19"**.
  2. Chọn 1 chủ đề để bắt đầu (lưới thẻ chủ đề có emoji + số từ).
- Bấm "Bắt đầu" → vào thẳng `flashcard_view` của chủ đề đã chọn.
- Có link "Bỏ qua". Không cần cờ trong DB: user chưa có `UserVocabularyProgress` và
  chưa có `StudySession` thì trang chủ hiện khối gợi ý mở lại onboarding.

---

### T3.3 Trạng thái trống và trạng thái đang tải

**Cách làm:**
- Partial dùng chung `templates/partials/empty_state.html` (icon, tiêu đề, mô tả, nút hành động) —
  áp dụng cho: chưa có từ nào (SC05), chưa học gì (SC15, SC13), chưa có phiếu (SC10),
  hòm thư rỗng (SC07).
- Nút submit dài (tạo PDF SC10, xuất PDF kính ngữ, nhập dữ liệu SC07b): thêm
  `data-loading-text`; `main.js` đổi chữ + khoá nút khi submit, tránh bấm 2 lần.

---

### T3.4 Nhất quán điều hướng

- Sidebar: thêm số **badge** cạnh mục "Ôn tập" = số từ đến hạn hôm nay
  (context processor mới `learning_badges`, có cache 60 giây theo user để không tốn query mỗi trang).
- Mọi màn có tiêu đề + breadcrumb ngắn ở cùng một vị trí (partial `page_header.html`).

---

## Phase 4 — Hiệu năng & hạ tầng

### T4.1 Cold start của Render free

**Hiện trạng:** server ngủ sau 15 phút, lần vào đầu chậm ~1 phút. Keep-alive dạng
luồng nền đã phải tắt (25/09/2026) vì làm nghẽn server.

**Trạng thái (02/10/2026):** Dat sẽ tự nghiên cứu phần cron sau — ghi chú lại ở đây
để làm tiếp, chưa triển khai.

**Ghi chú để nghiên cứu (không đụng code app):**
- Tạo cron bên ngoài gọi `GET /healthz/` mỗi 10 phút — **GitHub Actions**
  (`.github/workflows/keepalive.yml`, `schedule: cron: "*/10 * * * *"`) hoặc cron-job.org.
- Lưu ý: GitHub Actions có thể trễ vài phút và tốn phút chạy của gói free — cron-job.org ổn định hơn.
- Đồng thời giải quyết luôn chuyện Supabase free tự pause sau 7 ngày (nếu `/healthz/`
  có chạm DB — hiện **không** chạm; cân nhắc thêm `/healthz/?db=1` chạy `SELECT 1`, gọi 1 lần/ngày).
- `/healthz/` **giữ nguyên** — Render dùng nó làm `healthCheckPath` và cron ngoài sẽ gọi vào đây.

**T4.1b — Gỡ keep-alive dạng luồng nền: ✅ ĐÃ LÀM (02/10/2026)**
- Xoá `apps/core/keepalive.py`, lời gọi `keepalive.start()` trong `config/wsgi.py`,
  các biến `KEEPALIVE_*` trong `config/settings/render.py`.
- Xoá model `SiteSetting` (chỉ chứa cấu hình keep-alive) + migration xoá bảng,
  màn "Cài đặt hệ thống" (`admin_panel:system_settings`, `system_ping_now`),
  form, template, link sidebar, label/message liên quan, test `KeepAliveTests`.
- MasterCode code_type "17" bỏ khỏi seed + migration dữ liệu xoá các dòng cũ;
  không tái sử dụng mã "17" cho việc khác.

### T4.2 Đo và giảm số query của màn học

**Cách làm:**
1. Viết test đo bằng `assertNumQueries` cho `flashcard_view`, `study_view`,
   `dashboard_view`, `review_view` — chốt con số hiện tại làm mốc.
2. Điểm nghi vấn:
   - `get_topic_queue` chạy lại toàn bộ sau mỗi lần chấm (đọc mọi progress của chủ đề +
     `unseen.count()` + `in_bulk`).
   - `_card_context` đọc lại progress của từ đang hiện (đã có trong queue).
   - `word.topics.all`, `word.examples.all`, `get_vocabulary_comments` → gộp bằng
     `prefetch_related` khi lấy từ hiện tại.
   - `get_topic_in_progress` / `get_recent_topics`: `count()` trong vòng lặp.
3. Mục tiêu: màn học ≤ 12 query/request; trang chủ ≤ 10.

---

## Phase 5 — Mở rộng (làm sau, tách spec riêng khi bắt đầu)

- **T5.1 Nhắc học:** dùng 2 field đã có (`daily_reminder_enabled`,
  `weekly_email_summary_enabled`). Cần: cấu hình gửi email (SMTP/Resend), lệnh
  `manage.py send_reminders` chạy bằng cron ngoài (cùng chỗ với T4.1), gửi theo
  múi giờ của từng user.
- **T5.2 PWA:** `manifest.json` + service worker tối thiểu (cache CSS/JS/font) → cài lên
  màn hình chính điện thoại; sau đó mới tính đến thông báo đẩy.
- **T5.3 Kính ngữ vào ôn tập:** cho phép thêm `KeigoForm` vào hàng đợi SRS như một loại
  thẻ riêng (mặt trước: động từ thường + loại kính ngữ; mặt sau: dạng kính ngữ).
  Cần model tiến độ riêng hoặc tổng quát hoá `UserVocabularyProgress` — **phải thiết kế kỹ**,
  vì app `keigo` được tách riêng có chủ đích để không lẫn vào SRS của từ vựng.

---

## Checklist tổng hợp

### Phase 1 — Màn học (code xong 02/10/2026 — chờ Dat chạy test trên DB thật)
- [x] T1.1 Tách `_card_panel.html`
- [x] T1.2 Chấm thẻ không tải lại trang
- [x] T1.3 Phím tắt
- [x] T1.4 Hiện thẻ 2 bước + tuỳ chọn "hiện cách đọc ở mặt trước"
- [x] T1.5 Chế độ tập trung
- [x] T1.6 Tối ưu điện thoại (nút cố định đáy, vuốt)
- [x] T1.7 Màn tổng kết

### Phase 2 — Thiết kế (code xong 02/10/2026 — chờ Dat chạy test trên DB thật)
- [x] T2.1 Gom CSS về `base.css` + token — theme ~190 dòng (gồm cả token tối), base ~880 dòng
- [x] T2.2 Bỏ inline style, màu nút chấm ra CSS — `templates/learning`: 71 → 8 (chỉ còn style theo dữ liệu)
- [x] T2.3 Dark mode (MasterCode "18")
- [~] T2.4 Kiểm tra mobile — xong màn `learning`; các màn khác chờ chạy server (xem nhật ký)

### Phase 3 — Luồng (code xong 03/10/2026 — chờ Dat chạy test trên DB thật)
- [x] Duyệt các điểm cần chốt của T3.1
- [x] T3.1 Nút "Học hôm nay" + helper `_start_study_session` (bỏ link "Học tiếp chủ đề X")
- [x] T3.2 Onboarding (MasterCode "19")
- [x] T3.3 Empty state + loading state
- [x] T3.4 Badge sidebar + page header — header áp cho các màn người học (xem ghi chú)

### Phase 4 — Hiệu năng
- [ ] T4.1 Cron ngoài cho `/healthz/` (⏸ Dat nghiên cứu sau)
- [x] T4.1b Gỡ keep-alive luồng nền (`keepalive.py`, `SiteSetting`, màn Cài đặt hệ thống)
- [ ] T4.2 `assertNumQueries` + giảm query

---

### Ghi chú Phase 3 (03/10/2026) — để đối chiếu khi review
- **T3.1** `services.build_daily_queue()` / `get_daily_overview()`; view `daily_start_view`
  (`POST /learning/daily/start/`). `study_start_view`, `study_retry_view`, `review_start_view`
  giờ cùng gọi `_start_study_session()` (sửa luôn chỗ `review_start_view` trước đây không
  reset `study_learning`). Phiên "Học hôm nay" lưu `StudySession.topic = None`.
  `get_topic_in_progress()` vẫn giữ (tách `_topic_in_progress()` cho hàng đợi dùng).
  Gỡ 11 key label/message của khối "Học tiếp"/"Ôn tập hôm nay" không còn dùng.
- **T3.2** `accounts:onboarding` + `OnboardingForm`; MasterCode "19" = 5/10/20/30 (mã = số từ,
  chỉ seed — build.sh đã chạy `seed_mastercode`). Trang chủ hiện lời mời mở lại khi user
  chưa có tiến độ lẫn phiên học.
- **T3.3** `partials/empty_state.html` áp cho SC05, SC10, SC11 (góp ý của tôi), SC12 (hòm thư),
  SC13, SC15. `data-loading-text` cho: "Học hôm nay", onboarding, tạo PDF SC10, xem trước +
  xác nhận nhập dữ liệu SC07b. PDF kính ngữ (SC17 ôn tập, SC20 bài tập): theo yêu cầu Dat
  03/10/2026, người học chọn **"Xem / in"** (mở tab mới, `inline`) hoặc **"⬇ Tải PDF về máy"**
  (`?download=1` → `attachment`); link tải có trạng thái "Đang tải..." (main.js, khoá 4 giây).
- **T3.4** Context processor `learning_badges` (lười, cache 60 giây/user, xoá cache khi chấm
  / hoàn tác). Badge cùng định nghĩa "đến hạn" với SC15. `partials/page_header.html` áp cho
  SC05, SC08, SC09, SC10, SC11, SC13, SC14 (form + của tôi), SC15, onboarding. **Chưa áp**:
  SC03 (trang gốc, giữ lời chào), các màn học SC04/SC06, khu quản trị (header có nút bên phải)
  và khu kính ngữ (layout riêng `kl-*`) — làm khi có yêu cầu.
- Kiểm thử: 24 test mới (`DailyQueueTests`, `DailyStartViewTests`, `OnboardingNudgeTests`,
  `EmptyAndLoadingStateTests`, `NavigationTests`, `OnboardingViewTests`). Máy dev không có
  PostgreSQL nên đã chạy toàn bộ test trên SQLite tạm: 526 test, chỉ còn 8 lỗi CÓ SẴN từ
  trước do SQLite thiếu `SIMILARITY`/`pg_extension` — cần Dat chạy lại trên DB thật.
  Đã xem giao diện thật ở theme A, B (sáng) và C (tối), desktop + 375px: không tràn ngang.

## Các quyết định đã chốt (02/10/2026)

| # | Câu hỏi | Quyết định |
|---|---|---|
| 1 | T1.4 — mặc định hiện cách đọc ở mặt trước? | ✅ Có, tắt được ở SC08 (theo đề xuất) |
| 2 | T1.6 — làm thao tác vuốt để chấm không? | ✅ Có, làm cuối Phase 1 (theo đề xuất) |
| 3 | T3.1 (a) — từ mới của "Học hôm nay" lấy từ đâu? | ✅ Chủ đề đang học dở trước, rồi chủ đề gợi ý (theo đề xuất) |
| 4 | T3.1 (c) — giữ "Học tiếp chủ đề X" làm link phụ? | ❌ **Bỏ** — không cần thiết |
| 5 | T4.1 — cron bằng GitHub Actions hay cron-job.org? | ⏸ Dat nghiên cứu sau, giữ ghi chú trong spec |
| 6 | T4.1 — gỡ `keepalive.py`? | ✅ Gỡ ngay (T4.1b, đã làm) |

---

## Nhật ký kiểm tra mobile (T2.4)

Cách kiểm: render template bằng dữ liệu giả rồi đo trong trình duyệt ở 375px — trang có
tràn ngang không (`scrollWidth`), phần tử nào vượt mép phải — cho cả 3 theme, menu mở/đóng.

| Màn | Theme | Vấn đề | Trạng thái |
|---|---|---|---|
| Mọi trang có sidebar | A, B, C | Sidebar ≤900px thành hàng link ngang, ở 375px rộng ~600px → cả trang tràn ngang | ✅ Sửa: sidebar ẩn, nút ☰ mở danh sách dọc |
| Bảng dữ liệu (`<table>` không class) | A, B, C | Không có khung cuộn — bảng rộng sẽ đẩy trang tràn | ✅ Sửa: ≤720px bảng tự cuộn ngang |
| SC03 Trang chủ, SC04, SC06, SC15 (4 góc nhìn + trống) | A, B, C | Sau 2 sửa trên: không còn tràn | ✅ Đã đo |
| SC01-02, SC05, SC07, SC08-14, SC16-22 | A, B, C | Chưa đo được — cần server chạy (dữ liệu thật) | ⏳ Chờ |

### Ghi chú T2.1–T2.3 (để đối chiếu khi review)
- **Không đổi giao diện ở chế độ sáng**: so computed style của MỌI phần tử (cả `::before/::after`)
  giữa CSS cũ và mới trên 53 trang mockup + 6 trang SC04 render × 3 theme × 2 bề rộng
  (1280/375): 0 khác biệt — làm lại sau T2.1, T2.2 (so template trước/sau) và T2.3.
- **T2.1 thứ tự nạp đổi**: `theme_x.css` trước, `base.css` sau. Một số rule giống nhau vẫn
  nằm trong theme vì tách ra sẽ đổi thứ tự cascade (script tách tự kiểm từng cặp khai báo có
  thể đè nhau). Mục tiêu ≤150 dòng/theme chưa đạt hẳn (~165 dòng trước khi thêm token tối).
- **T2.2 utility dùng `!important`** (như Bootstrap) để giữ đúng độ ưu tiên của style inline cũ.
  Số utility nhiều hơn dự kiến (~30) vì giữ nguyên từng con số khoảng cách cũ thay vì làm tròn.
- **T2.3 tương phản**: chế độ tối mọi cặp chữ/nền ≥ 5.0:1. Chế độ SÁNG có sẵn vài chỗ < 4.5:1
  từ thiết kế gốc, CHƯA sửa vì đổi giao diện đã duyệt — cần Dat quyết:
  - Theme C: chữ trắng trên nút coral 2.7:1; link coral trên nền trắng 2.7:1; chữ phụ trên nền 4.2:1;
    thông báo lỗi 4.0:1; `tag.level` 3.1:1.
  - Cả 3 theme: chữ nút "Khó" 3.9:1.
