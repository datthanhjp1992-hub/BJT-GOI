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
| 4 | Hiệu năng & hạ tầng: cold start Render, đo và giảm số query, **học liền mạch (T4.3)** | ⭐ Cao (T4.3) / Trung bình | 1–2 ngày + T4.3: 4–5 ngày |
| 5 | Mở rộng: nhắc học (email/PWA), đưa kính ngữ vào SRS | Thấp (làm sau) | Tách spec riêng |
| 6 | Kiểm soát khối lượng ôn tập: hạn mức từ mới cho mọi lối vào, từ dở bước học, vuốt "Dễ", báo kết quả chấm, tự giảm từ mới khi nợ ôn | ⭐ Cao nhất (09/10/2026) | 4–5 ngày |

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

### T4.3 ⭐ Học liền mạch — tải trước bộ thẻ, chấm điểm gửi ngầm

> Dat chốt hướng này ngày 06/10/2026 (phương án C), duyệt spec cùng ngày.
> **Code xong 06/10/2026 — chờ Dat chạy trên server thật.** Khi code có vài chỗ đổi so với
> bản duyệt (API gộp thành một endpoint theo lô...), xem "Ghi chú T4.3" dưới checklist.

**Vấn đề:** mỗi lần vuốt/chấm, trình duyệt phải chờ **2 lượt đi-về server** rồi mới
hiện thẻ kế: `POST study/review/<id>/` (chấm, ghi DB) → 302 → `GET study/` (tìm từ kế,
dựng HTML). Mỗi lượt khoảng 10–15 query, mà Render (Singapore) gọi Supabase (Tokyo)
mất ~70ms mỗi query → ước tính 1,5–3 giây/thẻ.

**Số đo mốc (Dat đo 06/10/2026, Chrome DevTools, server thật trên Render):**
- POST chấm (`study/review/1660/`): chờ server **1,26 s**. Tải về chỉ 1,6 ms (0,4 kB).
- GET thẻ kế (`study/`): theo biểu đồ thời gian khoảng **~1 s** (ước theo thước đo, chưa có số chính xác).
- Tổng mỗi lần chấm/vuốt: **khoảng 2,3–2,5 s** người học phải chờ. Gần như toàn bộ là
  thời gian server xử lý, dung lượng tải không đáng kể (POST 0,4 kB, GET ~2,5 kB).
- Mục tiêu sau T4.3: thẻ kế hiện < 100 ms. Thời gian POST chạy ngầm không còn ảnh hưởng tới người học.

**Mục tiêu:** chấm/vuốt xong là thẻ kế hiện **ngay** (< 100ms, không chờ mạng).
Server vẫn là nơi giữ dữ liệu chính (SM-2, lịch, streak, tổng kết); trình duyệt chỉ
lo hiển thị và gửi kết quả chấm ở phía sau.

**Phạm vi:** phiên theo hàng đợi `study_*` (Học hôm nay ở SC03, SC05, SC15, "Ôn thêm").
**Chưa** làm: SC04 theo chủ đề (`flashcard_view` tính lại hàng đợi mỗi lần, cần thiết kế
riêng — T4.3.8), trắc nghiệm (`study_quiz`).

#### Luồng mới

```
Bắt đầu phiên (POST daily/start, study/start, review/start, study/retry) — như cũ
 → GET study/   (tải trang đầy đủ, 1 lần)
     trang nhúng sẵn <script type="application/json" id="study-deck">:
     danh sách thẻ + trạng thái phiên
 → trình duyệt hiện thẻ đầu
Chấm / vuốt
 → hiện thẻ kế NGAY từ deck trong bộ nhớ
 → đẩy {seq, vocab, quality} vào hàng chờ gửi
     hàng chờ gửi LẦN LƯỢT từng cái (1 request đang bay tại một thời điểm):
     POST study/api/grade/  →  JSON nhỏ: thẻ đã thuộc chưa, khi nào gặp lại
Hết thẻ
 → chờ hàng chờ gửi xong → GET study/ (partial, như hiện tại) → màn tổng kết
```

Gửi **lần lượt**, không gửi song song: session Django lưu trong DB, 2 request ghi
session cùng lúc sẽ đè mất của nhau (mất từ trong hàng đợi / mục hoàn tác).

#### Dữ liệu deck (nhúng trong trang)

```json
{
  "session": 123,                 // StudySession.pk — lệch thì trang đã cũ
  "seq": 0,                       // số thứ tự lần chấm cuối server đã nhận
  "total": 30, "scope": "Học hôm nay", "extra_review": false,
  "queue":    [11, 12, 13],       // thứ tự y như STUDY_QUEUE_KEY
  "learning": [{"id": 9, "due": "2026-10-06T10:05:00+09:00"}],
  "seen":     [9],                // đã chấm lần đầu trong phiên (nhãn "Gặp lại", tiến độ)
  "undo": {"vocab": 9, "word": "見積"},   // mục hoàn tác trên cùng (hoặc null)
  "cards": {
    "11": {"state": "new", "previews": {"quen": "1 phút", ...}, "html": "<...mặt thẻ...>"}
  },
  "more": "/learning/study/deck/?offset=50"   // còn thẻ chưa tải (null nếu hết)
}
```

- `html` là **mặt thẻ** do server render bằng partial mới `learning/_card_face.html`
  (từ, cách đọc, nghĩa, chủ đề, ví dụ). Template vẫn dùng `{% label %}`, nên JS **không
  chứa chuỗi hiển thị nào** (nguyên tắc 1). Phần thay đổi theo lần chấm (tag trạng thái,
  "Gặp lại", thanh tiến độ, nút hoàn tác, "học trước N phút", khoảng cách dưới nút)
  là khung cố định trong `_card_panel.html`, JS chỉ đổi số và bật/tắt. Nhãn trạng thái
  để sẵn trong DOM (`data-state-label="new"`...).
- `previews` chỉ có khi user bật "hiện khoảng cách ôn lại" (SC08). Không bật thì bỏ hẳn.
- Nhúng tối đa **50 thẻ**. Phiên dài hơn (vd. "Ôn thêm" 200 từ) thì JS tải tiếp
  `GET study/deck/?offset=` ở phía sau khi còn ≤ 10 thẻ chưa hiện.
- **Bình luận không nằm trong deck.** Khối thảo luận tải khi mở:
  `GET study/card/<id>/comments/` → HTML fragment. Gửi bình luận giữ như cũ (tải lại trang).

#### API mới (`apps/learning/views.py` + `urls.py`)

| URL | Vào | Ra |
|---|---|---|
| `POST study/sync/` | field `payload` = `{"session", "ops": [{"seq","op":"grade"\|"undo","vocab","quality"}]}` | `{"seq", "now", "cards": {id: {"state","learning","due","previews"}}, "missing", "undo", "resync"}` |
| `GET study/cards/?ids=1,2,3` | tối đa 50 id | `{"cards": {...}}` (id đã bị xoá thì không có) |
| `GET study/card/<id>/discussion/` | — | HTML thân khu thảo luận |

*(Bản duyệt ban đầu tách `study/api/grade/` + `undo/` có header + `study/deck/?offset=`;
khi code đã gộp lại — lý do ở "Ghi chú T4.3".)*

- `grade` gọi lại đúng `_grade_word()` hiện có. Không viết logic chấm thứ hai.
  View chỉ thêm phần đọc/trả JSON (nguyên tắc 6).
- **Chống chấm trùng:** server lưu `study_seq` (lần chấm cuối) và kết quả của nó trong
  session. Request tới với `seq` ≤ `study_seq` thì trả lại kết quả cũ, không chấm lại
  (gửi lại khi mạng chập chờn hoặc `sendBeacon` lúc đóng tab).
- `session` khác `STUDY_SESSION_ID_KEY` hiện tại (đã bắt đầu phiên khác ở tab khác)
  → `409`. JS tải lại trang.
- Hết phiên đăng nhập → `401` JSON (không redirect sang trang login). JS chuyển sang trang login.
- Lỗi khác → `4xx/5xx`, JS thử lại (xem dưới).
- Endpoint cũ (`study/review/<id>/`, `undo/` không header) **giữ nguyên** cho trường hợp
  tắt JS (nguyên tắc 4).

#### Logic phía trình duyệt (`static/js/study_deck.js`, chỉ nạp ở màn học)

Tách file riêng vì `main.js` đã ~680 dòng. Vẫn là JS thuần, không build step.

1. **Chọn thẻ kế**, cùng luật với `_next_queue_word`: thẻ vừa hoàn tác → đầu `queue`
   → (hết queue) thẻ trong `learning` có `due` sớm nhất. Chưa tới giờ thì hiện
   "học trước N phút".
2. **Sau khi chấm:** bỏ thẻ khỏi `queue`, thêm vào `seen`.
   - Phiên chính thức: tạm coi thẻ là "đang học", đặt ở cuối `learning`. Khi server trả
     `in_session=false` thì bỏ ra, `true` thì cập nhật `due`. Thứ tự luôn là
     "học hết lượt rồi mới ôn lại", nên tới lúc gặp lại thẻ này thì kết quả server đã về.
   - Phiên ôn thêm: bấm Quên thì đẩy xuống cuối `queue` (giống `_grade_word`).
   - Ngoại lệ: thẻ kế duy nhất còn lại là thẻ vừa chấm mà server chưa trả lời → hiện
     trạng thái "Đang tải..." cho tới khi có kết quả. Chỉ xảy ra ở cuối phiên.
3. **Tiến độ** tính bằng đúng công thức `_progress_numbers` (total, remaining = queue ∪
   learning, seen).
4. **Hoàn tác (Z):** đưa thẻ về đầu ngay trên màn hình, rồi xếp lệnh undo vào **cùng
   hàng chờ** (sau các lần chấm chưa gửi). Server đã có sẵn ngăn xếp hoàn tác.
5. **Hàng chờ gửi:**
   - Gửi lần lượt. Lỗi mạng hoặc 5xx thì thử lại sau 1s → 3s → 10s.
   - Thất bại 3 lần: hiện thanh báo "Mất kết nối — kết quả đang lưu tạm". Người học
     vẫn học tiếp; hàng chờ lưu vào `localStorage` (khoá theo `session`, bọc try/catch).
     Có mạng lại hoặc tải lại trang thì gửi tiếp.
   - Đóng tab hoặc chuyển trang khi còn lệnh chưa gửi: `navigator.sendBeacon` từng lệnh
     (kèm `csrfmiddlewaretoken`). Nhờ `seq`, gửi trùng cũng không sao.
6. **Hết thẻ:** đợi hàng chờ trống → `GET study/` với header `X-Card-Partial` (đường cũ)
   → server render màn tổng kết như hiện tại.
7. **Phím tắt, vuốt, lật 2 bước, chế độ tập trung:** giữ nguyên. Chỉ đổi chỗ "bấm nút chấm
   → submit form" thành "bấm nút chấm → `deck.grade()`". Form vẫn ở đó cho trường hợp tắt JS.
8. **Đường lùi:** không có `#study-deck` (trang cũ đang mở, trình duyệt thiếu `fetch`) thì
   chạy y như hiện tại (T1.2).

#### Rủi ro đã tính

| Tình huống | Cách xử lý |
|---|---|
| Đóng tab ngay sau khi chấm | `sendBeacon` + `localStorage`; nặng nhất là mất 1–2 lần chấm cuối, từ đó vẫn còn trong hàng đợi phía server và sẽ gặp lại |
| Mở 2 tab cùng một phiên | `seq` chống chấm trùng; tab nào lệch `session` thì nhận 409 và tải lại |
| Dữ liệu từ bị admin sửa giữa phiên | Thẻ hiện bản cũ trong phiên đó; chấp nhận được |
| Từ bị xoá giữa phiên | `grade` trả 404 cho từ đó → JS bỏ qua thẻ, không báo lỗi |
| Trang nặng hơn | 50 thẻ × ~1KB ≈ 50KB HTML, nhẹ hơn một ảnh |

#### Các bước thực hiện

| Bước | Nội dung | File chính |
|---|---|---|
| T4.3.0 | **Đo mốc:** thêm header `Server-Timing` (middleware nhỏ: tổng ms + số query) để xem ngay trong tab Network. Ghi số đo trước/sau vào spec | `apps/core/middleware.py`, `config/settings/base.py` |
| T4.3.1 | Tách `_card_extra.html` (chủ đề + ví dụ) và `_card_discussion_body.html` khỏi `_card_panel.html`. Giao diện không đổi | `templates/learning/` |
| T4.3.2 | `services.get_study_cards(user, ids)`: lấy thẻ hàng loạt (`prefetch_related` topics/examples, progress bằng 1 query, số bình luận bằng 1 query) | `apps/learning/services.py` |
| T4.3.3 | `study_view` nhúng `#study-deck`; thêm `study/cards/`, `study/card/<id>/discussion/` | `views.py`, `urls.py`, `_card_panel.html` |
| T4.3.4 | `POST study/sync/` (lô grade/undo) + `seq` chống trùng + 409/401 | `views.py` |
| T4.3.5 | `study_deck.js`: chọn thẻ kế, tiến độ, hàng chờ gửi, thử lại, `localStorage`, `sendBeacon`, hoàn tác. Nối phím tắt/vuốt ở `main.js` | `static/js/` |
| T4.3.6 | Label/message mới ("Mất kết nối...", "Đang lưu..."), CSS thanh báo (3 theme + tối) | `*.properties`, `base.css` |
| T4.3.7 | Test + cập nhật `flowChart/js/flows.js` | `apps/learning/tests.py` |
| T4.3.8 | *(Sau khi T4.3.0–7 chạy ổn trên server thật)* Áp cho SC04 theo chủ đề | spec riêng |

**Test (T4.3.7):**
- `grade` API: chấm đúng như `study_review_view` (cùng tiến độ SM-2, cùng `StudySession`,
  cùng hàng đợi trong session); gửi lại cùng `seq` không chấm 2 lần; sai `session` → 409;
  chưa đăng nhập → 401; từ bị xoá → 404.
- `undo` JSON khớp `undo` thường. Chấm → hoàn tác → chấm lại cho kết quả như chưa từng chấm.
- Deck: đủ thẻ, đúng thứ tự `queue`, phân trang `offset`, không có bình luận,
  `assertNumQueries` cố định (không tăng theo số thẻ).
- Đi trọn một phiên chỉ bằng API → màn tổng kết đúng số liệu như khi đi bằng form.
- Tắt JS (test client gửi form thường) vẫn chạy y như cũ.
- Thủ công trên trình duyệt: vuốt liên tục 20 thẻ không chờ; tắt mạng giữa phiên rồi bật
  lại; đóng tab rồi mở lại; điện thoại 375px; 3 theme.

**Hoàn thành khi:** trên server thật, chấm/vuốt → thẻ kế hiện < 100ms; số liệu SM-2 và
tổng kết khớp với cách cũ; tắt JS vẫn học được.

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

## Phase 6 — Kiểm soát khối lượng ôn tập

> Lập 09/10/2026 · Trạng thái: **Đã duyệt (09/10/2026)** — Dat đồng ý toàn bộ đề xuất ở mục
> "Cần chốt" cuối phase.
> Làm **trước** T4.2 / T4.3.8 — đây là vấn đề người học đang gặp thật.

### Bối cảnh — số liệu thật (Dat, 09/10/2026)

Trang chủ báo **254 từ cần ôn · 20 từ mới · khoảng 92 phút**, người học không còn
thời gian cho từ mới. Truy vấn trên Supabase cho thấy:

| Nhóm | Số từ | Giải thích |
|---|---|---|
| `learning`, ngày ôn 08/10 (đã quá hạn) | 121 | Từ mới học 08/10, mới chấm "Nhớ" **một** lần (còn bước 10 phút) thì phiên dừng |
| `review`, đến hạn 09/10 | 133 | Từ đã tốt nghiệp, phần lớn là từ học 08/10 được hẹn sau 1 ngày |

| Ngày | Từ mới | So với hạn mức 20 |
|---|---|---|
| 08/10 | 143 | ×7 |
| 06/10 | 147 | ×7 (9 phiên; Lesson18/19/20 học theo một chủ đề: 29 + 50 + 81 lượt chấm) |
| 01/10 | 100 | ×5 |
| 30/09 | 50 | ×2,5 |

Tỉ lệ "đúng" của các phiên: 93–100%. Dat học chủ yếu trên điện thoại và **vuốt thẻ để
sang từ kế** — vuốt phải luôn là "Nhớ", không có cách vuốt ra "Dễ".

**Kết luận:** thuật toán SM-2 (`srs.py`) chạy đúng. Khối lượng phình vì:
1. Có **lối vào học từ mới không bị giới hạn**: SC05 "Bắt đầu học" (mặc định "Tất cả",
   `build_study_queue` không cắt từ mới) và nút "Học thêm N từ mới" ở SC04.
2. **Hạn mức từ mới không phụ thuộc lượng nợ ôn** — nợ 254 từ vẫn mời thêm 20 từ mới.
3. Từ mới cần **hai** lần "Nhớ" (bước 1 phút → 10 phút) mới tốt nghiệp. Với luật "hết lượt
   rồi mới ôn lại" (01/10/2026), lượt lặp dồn về cuối phiên; phiên dài bỏ dở là hàng trăm từ
   kẹt ở `learning`.
4. Trên điện thoại chỉ có Quên/Nhớ: từ đã biết chắc vẫn đi lịch 1 → 6 → 15 ngày thay vì
   tốt nghiệp ngay với "Dễ" (4 ngày). Người học cũng không thấy rõ vuốt = chấm điểm.

Mô phỏng bằng chính `srs.schedule()` (học đều mỗi ngày, quên 10%): 20 từ mới/ngày → sau
30 ngày ~73 từ ôn/ngày, sau 120 ngày ~125. 10 từ mới/ngày → ~35 / ~55. Tức số ôn mỗi
ngày ổn định ở khoảng **5–8 × số từ mới mỗi ngày** — giữ được hạn mức từ mới là giữ được
khối lượng ôn.

### Không làm
- **V4 — rút bước học của từ mới xuống 1 bước:** Dat chốt **không làm** (09/10/2026). T6.2
  đã xử lý phần "kẹt bước học", còn bước 10 phút vẫn có ích cho việc nhớ trong ngày đầu.
- Giới hạn cứng số từ ÔN mỗi ngày: để sau, xem lại khi T6.1 + T6.5 chạy ổn một thời gian.
- Không đổi thuật toán SM-2 cho từ đang ở `review`. (Ngưỡng "đã thuộc" ban đầu không đổi; sau đó Dat
  duyệt đổi sang tính theo khoảng cách ôn — xem "Ghi chú: đã thuộc theo khoảng cách" ngày 10/10/2026.)

---

### T6.1 ⭐ Một hạn mức từ mới cho MỌI lối vào (mục F)

**Mục tiêu:** mỗi ngày chỉ có tối đa `daily_review_goal` từ mới vào hệ thống ôn, dù học
từ trang chủ, SC04, SC05 hay SC06. Muốn học vượt thì phải chủ động xác nhận và được báo
trước cái giá phải trả.

**Hiện trạng:**

| Lối vào | Hàm dựng hàng đợi | Giới hạn từ mới |
|---|---|---|
| SC03 "Học hôm nay" | `build_daily_queue` → `_daily_parts` | ✅ `goal − count_new_words_today` |
| SC04 / SC06 theo chủ đề | `get_topic_queue` | ✅ như trên, **nhưng** nút "Học thêm N từ mới" (`flashcard_more_new_view`) mở thêm không giới hạn số lần |
| SC05 "Bắt đầu học" | `build_study_queue` | ❌ không giới hạn, mặc định "Tất cả" (`LIBRARY_DEFAULT_SESSION_LIMIT`) |
| SC15 Ôn tập | `studied_vocabulary` | — chỉ từ đã học, không có từ mới |
| "Ôn thêm" (màn tổng kết) | `study_retry_view` | — chỉ từ vừa học, không đẩy lịch |

**File:** `apps/learning/services.py`, `apps/learning/views.py`, `apps/vocabulary/views.py`,
`templates/vocabulary/list.html`, `templates/learning/_card_panel.html`, properties.

**Cách làm:**
1. **Hàm dùng chung** trong `services.py`:
   ```python
   @dataclass
   class NewWordAllowance:
       goal: int            # user.daily_review_goal
       learned_today: int   # count_new_words_today(user)
       left: int            # số từ mới còn được học hôm nay (>= 0)
       backlog: int         # số từ đang nợ ôn (T6.5 dùng)
       paused: bool         # True = T6.5 tạm dừng/giảm từ mới vì nợ ôn

   def new_word_allowance(user) -> NewWordAllowance
   ```
   T6.1 chỉ tính `left = max(0, goal − learned_today)`, `paused=False`; T6.5 bổ sung luật nợ ôn
   **bên trong** hàm này — các lối vào không phải sửa lại.
2. **Mọi lối vào dùng hàm trên**, không tự tính `goal − count_new_words_today` nữa:
   - `_daily_parts` (SC03).
   - `get_topic_queue` (SC04/SC06): `new_left = allowance.left`.
   - `build_study_queue` (SC05): thêm tham số `new_limit: int | None`. Nhóm `_BUCKET_NEW` chỉ
     giữ `new_limit` từ đầu (theo thứ tự hiện có), phần còn lại **bỏ khỏi hàng đợi** (không
     dời xuống cuối). Hàm trả thêm số từ mới bị giữ lại (`held_new`) cho view báo. SC15 gọi
     với `new_limit=None` (không đổi hành vi).
3. **SC05 — khi có từ mới bị giữ lại:**
   - Hàng đợi vẫn chạy với phần đã cắt (từ đến hạn + từ mới trong hạn mức). Nếu hàng đợi
     rỗng vì toàn bộ là từ mới đã hết hạn mức → không vào màn học, quay lại SC05.
   - Quay lại / flash: "Hôm nay bạn đã học {learned}/{goal} từ mới — giữ lại {held} từ mới."
   - SC05 hiện khối cảnh báo (partial dùng chung, xem bước 5) với nút **"Vẫn học thêm {n} từ
     mới"** — form POST tới `study_start` với **đúng bộ lọc hiện tại** (SC05 lọc bằng GET nên
     tham số có sẵn trên URL) + field ẩn `over_limit=1`. Khi có `over_limit=1`,
     `new_limit = allowance.left + goal` (mỗi lần xác nhận mở thêm tối đa **một hạn mức**,
     không mở "tất cả").
4. **SC04 — nút "Học thêm N từ mới":** giữ nút, nhưng thay bằng cùng khối cảnh báo ở bước 5
   (nút bấm vẫn POST `flashcard_more_new`, mỗi lần tối đa `goal` từ như hiện nay).
5. **Partial mới `templates/learning/_over_limit_notice.html`** (dùng cho SC04 + SC05):
   > Hôm nay bạn đã học **{learned}/{goal}** từ mới.
   > Học thêm {n} từ nữa thì **ngày mai có thêm khoảng {n} từ cần ôn** (tổng ~{tomorrow} từ).
   > [Vẫn học thêm {n} từ mới]
   - `{tomorrow}` = `count_due_tomorrow(user) + n`. Ước lượng "+n" là chính xác với luật hiện
     tại: từ mới tốt nghiệp bằng "Nhớ" luôn hẹn sau `GRADUATE_INTERVAL` = 1 ngày.
   - Nút có `data-loading-text` (T3.3).

*Ghi chú:* field tên `daily_review_goal` nhưng nghĩa thật là hạn mức **từ mới**/ngày (nhãn
SC08 đã ghi đúng "Số từ mới mỗi ngày"). Không đổi tên field ở phase này.

**Hoàn thành khi:** không có cách nào học quá `goal` từ mới trong ngày mà không bấm qua
khối cảnh báo; SC15 và "Ôn thêm" không đổi.

**Test:**
- `new_word_allowance`: chưa học → `left = goal`; học đủ → 0; hoàn tác từ mới → `left` tăng lại.
- SC05 lọc chủ đề 120 từ chưa học, `goal=20` → hàng đợi 20 từ, `held_new = 100`, flash đúng.
- SC05 khi đã đủ hạn mức, chỉ toàn từ mới → không tạo `StudySession`, quay lại SC05 có cảnh báo.
- SC05 `over_limit=1` → thêm đúng `goal` từ mới, không hơn.
- SC05 lọc có cả từ đến hạn lẫn từ mới → từ đến hạn giữ nguyên toàn bộ.
- SC04 `get_topic_queue` dùng `allowance.left`; SC15 `review_start` không bị cắt.

---

### T6.2 ⭐ Từ dở bước học khi rời phiên (mục V3)

**Mục tiêu:** dừng phiên giữa chừng không để lại hàng loạt từ "quá hạn"; từ dở dang được hẹn
lại ngày mai như từ bình thường và được ưu tiên ôn trước.

**Hiện trạng:** `review_word()` đặt `next_review_date = hôm nay` cho từ còn ở bước học
(`LEARNING`/`RELEARNING`). Rời phiên thì:
- Ngay **hôm nay** chúng vẫn nằm trong "Học hôm nay" (`_daily_due_ids` lấy mọi từ
  `IN_SESSION_STATES` không xét ngày) và trong badge/ô "Từ cần ôn hôm nay".
- **Từ hôm sau** chúng thành "quá hạn" ở SC15, và ở "Học hôm nay" bị xếp **sau toàn bộ**
  từ ôn — dù đây là những từ mới nhất, dễ quên nhất.
- Hôm sau bấm "Nhớ" ở bước 0 vẫn phải đi tiếp bước 10 phút, thêm một lượt lặp.

**File:** `apps/learning/srs.py`, `apps/learning/services.py`, `apps/learning/views.py`,
`static/js/study_deck.js` (chỉ nếu cần đồng bộ thứ tự), properties.

**Cách làm:**
1. **Hoãn sang mai khi phiên đóng.** Trong `_clear_study_session()` (được gọi khi bấm "Kết
   thúc", khi bắt đầu phiên khác, khi hết thẻ): các id trong `STUDY_LEARNING_KEY` mà
   progress vẫn ở `IN_SESSION_STATES` → `services.postpone_learning(user, ids)`:
   `next_review_date = local_today + 1`, `due_at = None`, **giữ** `card_state`/`learning_step`.
   Một query `UPDATE`. Gọi `invalidate_due_badge`.
   - Chỉ áp cho phiên **chính thức** (`touch=True`); phiên ôn thêm không đụng lịch.
   - SC04 (theo chủ đề) không có danh sách learning trong session: áp cùng hàm cho các từ
     `IN_SESSION_STATES` thuộc chủ đề, đã chấm trong phiên SC04 đó (lấy từ
     `_first_grades` của session) khi bấm "Kết thúc" — link "Kết thúc" của SC04 đổi thành
     form POST giống phiên `study_*`.
2. **Phiên bỏ ngang không bấm Kết thúc** (đóng tab): không cần job dọn. Từ có
   `next_review_date = hôm qua` hôm sau tự đến hạn — chỉ cần các luật ở bước 3–4 coi chúng
   là "đến hạn hôm nay", không phải "quá hạn".
3. **Định nghĩa "từ dở bước học từ hôm trước"** (gọi tắt *từ dở*): `card_state ∈
   IN_SESSION_STATES` và `next_review_date < hôm nay`.
   - `_daily_due_ids`: thứ tự mới = **từ dở** → từ `REVIEW` đến hạn (quá hạn lâu nhất trước) →
     từ đang học **hôm nay** (đã tới `due_at`). Từ `IN_SESSION_STATES` có `next_review_date
     > hôm nay` (vừa hoãn) **không** vào hàng đợi hôm nay.
   - `get_topic_queue`: tương tự — từ dở đứng cùng nhóm "đến hạn ôn", trước từ mới.
   - Bộ đếm (`count_due_today`, `get_learning_stats`, `get_review_overview`,
     `get_review_calendar`): từ dở tính vào **"đến hạn hôm nay"**, không vào "quá hạn".
4. **Chấm từ dở: "Nhớ" là tốt nghiệp luôn.** Đã qua ít nhất một đêm thì bước 10 phút không
   còn ý nghĩa. `srs.schedule(card, quality, overnight=False)` thêm tham số; khi
   `overnight=True` và thẻ ở `IN_SESSION_STATES`:
   - `GOOD` → tốt nghiệp như đã qua bước cuối (LEARNING: `GRADUATE_INTERVAL`; RELEARNING:
     như hiện tại).
   - `AGAIN`/`HARD`/`EASY`: giữ nguyên luật hiện có.
   - `review_word()` truyền `overnight = progress.next_review_date < local_today`.
     `grade_previews()` cũng truyền cờ này để khoảng cách hiển thị khớp.
   - `srs.py` vẫn là hàm thuần (không đọc đồng hồ) — cờ do `services` tính.

**Hoàn thành khi:** dừng phiên lúc còn 100 từ đang học → trang chủ không còn tính 100 từ đó
cho hôm nay; hôm sau chúng đứng đầu "Học hôm nay", mỗi từ "Nhớ" một lần là xong.

**Test:**
- Phiên `study_*` còn 5 từ trong `STUDY_LEARNING_KEY` → `study_end` → 5 progress có
  `next_review_date = mai`, `due_at = None`, state không đổi; phiên ôn thêm thì không đổi gì.
- Hôm nay sau khi hoãn: `build_daily_queue` không chứa 5 từ đó; `count_due_today` giảm 5.
- Hôm sau (giả lập ngày): 5 từ đứng **đầu** `build_daily_queue`; `get_review_overview` tính
  chúng vào `due_today`, `overdue = 0`.
- `srs.schedule(learning step 0, GOOD, overnight=True)` → `REVIEW`, 1 ngày;
  `overnight=False` → giữ hành vi cũ (step 1, 10 phút). Thêm test cho RELEARNING.
- Hoàn tác lần chấm của từ dở khôi phục đúng `next_review_date` cũ (snapshot đã có).

---

### T6.3 ⭐ Vuốt lên = "Dễ" (mục V1)

**Mục tiêu:** trên điện thoại chấm được "Dễ" bằng một cử chỉ — từ đã biết chắc tốt nghiệp
ngay (từ mới: 4 ngày; từ đang ôn: khoảng cách xa nhất).

**File:** `static/js/main.js` (`initCardSwipe`), `static/css/base.css`, `label.properties`,
`templates/learning/_card_panel.html`.

**Cách làm:**
- `initCardSwipe` hiện chỉ nhận vuốt ngang, vuốt dọc bỏ qua để cuộn trang. Đổi:
  - Hướng chốt một lần như cũ. Ngang: giữ nguyên (phải = Nhớ `data-grade-key="3"`, trái =
    Quên `"1"`).
  - Dọc **lên** (`dy ≤ −SWIPE_THRESHOLD`, `|dy| > |dx|`) → nút `data-grade-key="4"` (Dễ).
    Vuốt **xuống**: không làm gì (để dành cho cuộn).
  - Hiệu ứng: thẻ dịch lên theo tay (`translateY`), class `swipe-up` (viền màu của nút Dễ,
    token theme như `swipe-left/right`).
- **Cuộn trang:** khi thẻ đã lật trên màn ≤ 560px, `.is-revealed .flashcard{touch-action:none}`
  để trình duyệt không cuộn trang khi kéo **trên thẻ** (iOS Safari không hỗ trợ
  `pan-down`). Ví dụ câu / khu thảo luận nằm ngoài `.flashcard` nên vẫn cuộn được bình
  thường. Trước khi lật: giữ nguyên (không vuốt được).
- Áp cho cả hai đường: phiên có bộ thẻ (`study_deck.js` bắt `submit`/`click` như phím 4) và
  SC04 (fetch T1.2) — vì vuốt chỉ gọi `button.click()`, không phải sửa `study_deck.js`.
- Cập nhật label `learning.flashcard.hint.swipe` = "← Quên rồi · → Nhớ · ↑ Dễ" và bảng phím
  tắt (`learning.flashcard.shortcut.*`) có dòng cử chỉ.

**Hoàn thành khi:** trên điện thoại 375px vuốt lên chấm "Dễ"; vuốt dọc ngoài thẻ vẫn cuộn;
3 theme × sáng/tối có màu viền rõ.

**Test:** JS không có test tự động trong repo — kiểm thủ công (Chrome DevTools giả lập cảm
ứng + điện thoại thật): lên / trái / phải / xuống / vuốt ngắn dưới ngưỡng / chưa lật thẻ.
Test Python: label mới tồn tại (`learning.flashcard.hint.swipe` chứa "↑").

---

### T6.4 Báo kết quả sau mỗi lần chấm (mục V2)

**Mục tiêu:** người học luôn biết vuốt/bấm là **đang chấm điểm**, và từ đó sẽ quay lại khi nào.

**File:** `apps/learning/views.py` (`_card_context`, `_study_cards_json`/`_card_previews`),
`_card_panel.html`, `static/js/main.js`, `static/js/study_deck.js`, `base.css`, properties.

**Cách làm:**
1. **Server luôn gửi khoảng cách** cho từng nút, kể cả khi user tắt "hiện khoảng cách ôn lại"
   (SC08 chỉ quyết định **hiện dưới nút** hay không):
   - `_card_context`: luôn tính `grade_previews` (hàm thuần, không thêm query vì progress đã
     đọc) → mỗi nút có `data-toast="{text}"`; `<small class="btn-grade-delay">` vẫn chỉ hiện
     khi bật tuỳ chọn.
   - Bộ thẻ T4.3: `previews` luôn có trong `cards` (JS đặt lại `data-toast` khi đổi thẻ).
2. **Nội dung** (dựng sẵn ở server bằng properties, JS không chứa chữ):
   - Từ quay lại **trong phiên** (đơn vị phút/giờ — luật "hết lượt rồi mới ôn lại" khiến số
     phút không khớp thực tế): "✓ {Nhớ} · gặp lại trong phiên này" — key
     `learning.flashcard.toast.in_session`.
   - Từ tốt nghiệp / đang ôn: "✓ {Dễ} · gặp lại sau {4 ngày}" — key
     `learning.flashcard.toast.scheduled`.
   - "Quên rồi": "✗ Quên rồi · gặp lại trong phiên này".
   - Phiên ôn thêm (không đẩy lịch): "{Nhớ} · lịch ôn không đổi" — key
     `learning.flashcard.toast.extra`.
3. **Hiển thị:** một `<div class="grade-toast" role="status" aria-live="polite" hidden>` cố
   định trong `_card_panel.html` (ngoài khu được thay khi đổi thẻ). Khi nút chấm bị bấm
   (click, phím 1–4 hay vuốt — đều đi qua `button.click()`), JS lấy `data-toast` của nút →
   hiện 1,5 giây, mờ dần; chấm tiếp thì thay nội dung ngay. Trên điện thoại đặt ngay trên
   hàng nút dính đáy; không che thẻ. `prefers-reduced-motion`: không animation.
4. Tắt JS: không có toast (form submit thường, giữ như cũ).

**Hoàn thành khi:** mỗi lần chấm đều thấy một dòng ngắn đúng nút đã chọn và đúng lịch.

**Test:** `_card_context` có `toast` cho đủ 4 nút ở cả hai trạng thái của tuỳ chọn SC08; từ
mới: "Nhớ" → in_session, "Dễ" → scheduled 4 ngày; phiên `touch=False` → extra; bộ thẻ JSON
có `previews` khi tuỳ chọn tắt.

---

### T6.5 Tự giảm từ mới khi nợ ôn cao (mục B)

**Mục tiêu:** khi đang nợ nhiều từ ôn, app tự ngừng mời thêm từ mới (không đào hố sâu hơn),
và mở lại khi nợ giảm.

**File:** `apps/learning/services.py` (`new_word_allowance` của T6.1), `dashboard.html`,
`_over_limit_notice.html`, properties.

**Cách làm:**
1. `backlog` = số từ **đến hạn hôm nay** theo định nghĩa sau T6.2 (REVIEW đến hạn/quá hạn +
   từ dở; **không** tính từ đang học trong ngày và từ vừa hoãn).
2. Luật trong `new_word_allowance` (hằng số trong `services.py`, chưa đưa vào SC08):
   | Nợ ôn | Từ mới hôm nay |
   |---|---|
   | `backlog < BACKLOG_SLOW × goal` (3 × 20 = 60) | đủ hạn mức như T6.1 |
   | `BACKLOG_SLOW × goal ≤ backlog < BACKLOG_STOP × goal` (60–99) | **một nửa** hạn mức (làm tròn lên) |
   | `backlog ≥ BACKLOG_STOP × goal` (≥ 100) | **0** — tạm dừng từ mới |
   `left = max(0, mức trên − learned_today)`; `paused = True` khi bị giảm/dừng.
3. Vì `backlog` tính lại mỗi lần gọi, ôn bớt nợ trong ngày thì từ mới tự mở lại (trang chủ
   cập nhật số trên nút "Học hôm nay"; badge cache 60 giây như T3.4).
4. **Trang chủ** khi `paused`: dưới nút "Học hôm nay" một dòng giải thích —
   "Đang nợ {backlog} từ ôn — tạm dừng từ mới cho tới khi còn dưới {threshold} từ." (hoặc
   "…giảm còn {n} từ mới hôm nay."). Khối cảnh báo vượt hạn mức (T6.1 bước 5) cũng nêu lý do
   này. Người học vẫn có thể bấm "Vẫn học thêm" — app khuyên, không cấm.
5. "Học hôm nay" không đổi thứ tự (ôn trước, từ mới sau): khi `paused` thì phần từ mới đã nhỏ
   hoặc bằng 0 nên không cần xen kẽ.

**Hoàn thành khi:** với số liệu 09/10/2026 (254 nợ, goal 20) trang chủ hiện 0 từ mới + lý
do; ôn xuống dưới 100 → 10 từ mới; dưới 60 → 20.

**Test:** ba ngưỡng (59/60/99/100 với goal 20), `learned_today` trừ đúng, `paused` đúng; từ
đang học trong ngày và từ vừa hoãn không tính vào `backlog`; SC04/SC05 nhận `left` đã giảm.

---

### T6.6 Hướng dẫn cử chỉ lần đầu (mục V5)

**Mục tiêu:** người dùng điện thoại biết ngay vuốt = chấm điểm, có ba hướng.

**File:** `_card_panel.html`, `main.js`, `base.css`, `label.properties`.

**Cách làm:**
- Lớp phủ nhỏ trên thẻ **sau lần lật đầu tiên** của phiên, chỉ trên thiết bị cảm ứng
  (`matchMedia("(hover: none)")`): ba mũi tên ← Quên rồi · → Nhớ · ↑ Dễ, chạm để đóng.
- Chỉ hiện ở **3 phiên đầu**: đếm bằng `localStorage` (`bjt.swipeCoach.count`, bọc try/catch;
  không đọc được thì hiện mỗi phiên một lần — chấp nhận được). Không cần lưu DB.
- Dòng gợi ý cố định `swipe-hint` (đã có) giữ lại, nội dung theo T6.3.
- Chữ lấy từ label (`learning.flashcard.coach.*`), JS chỉ bật/tắt.

**Hoàn thành khi:** lần đầu học trên điện thoại thấy hướng dẫn; từ phiên thứ 4 không thấy nữa.

---

### Thứ tự làm & phụ thuộc

| Bước | Task | Phụ thuộc |
|---|---|---|
| 1 | T6.1 hạn mức chung (F) | — |
| 2 | T6.2 từ dở bước học (V3) | — (định nghĩa "đến hạn" mới dùng ở T6.5) |
| 3 | T6.3 vuốt lên = Dễ (V1) | — |
| 4 | T6.4 báo kết quả chấm (V2) | nên sau T6.2 (khoảng cách của từ dở đổi) |
| 5 | T6.5 tự giảm từ mới (B) | T6.1, T6.2 |
| 6 | T6.6 hướng dẫn cử chỉ (V5) | T6.3 |

Mỗi bước: test xanh (`python manage.py test` trên PostgreSQL), kiểm 3 theme × sáng/tối ×
375px cho các bước có giao diện. Nguyên tắc 8 (`flowChart/js/flows.js`): thư mục
`flowChart/` **không có trong repo** — bỏ qua cho tới khi Dat đưa lại file.

### Các điểm đã chốt (Dat duyệt 09/10/2026 — đồng ý toàn bộ đề xuất)

| # | Câu hỏi | Quyết định |
|---|---|---|
| 1 | T6.1 — mỗi lần "Vẫn học thêm" mở bao nhiêu từ? | ✅ Một hạn mức (`goal`), bấm lại được |
| 2 | T6.2 — dừng phiên thì từ đang học hoãn sang **ngày mai** (không ôn lại trong hôm nay)? | ✅ Có |
| 3 | T6.2 — từ dở đứng **đầu** "Học hôm nay" (trước từ ôn)? | ✅ Có — từ mới nhất, dễ quên nhất |
| 4 | T6.2 — từ dở bấm "Nhớ" một lần là tốt nghiệp? | ✅ Có |
| 5 | T6.3 — khoá cuộn trang khi kéo trên thẻ đã lật (màn ≤ 560px)? | ✅ Có — thẻ vừa một màn hình từ T1.6 |
| 6 | T6.4 — hiện toast cả trên máy tính? | ✅ Có (gọn, 1,5 giây) |
| 7 | T6.5 — ngưỡng nợ ôn 3× / 5× hạn mức (60 / 100 với goal 20)? | ✅ Như bảng; sau này có thể đưa vào SC08 |
| 8 | T6.5 — khi tạm dừng vẫn cho "Vẫn học thêm"? | ✅ Có — khuyên, không cấm |

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
- [x] T4.3 Học liền mạch (code xong 06/10/2026 — chờ Dat chạy trên server thật)
  - [x] T4.3.0 Đo mốc (`Server-Timing`)
  - [x] T4.3.1 Tách `_card_extra.html` + `_card_discussion_body.html`
  - [x] T4.3.2 `services.get_study_cards`
  - [x] T4.3.3 Nhúng deck + `study/cards/` + bình luận tải sau
  - [x] T4.3.4 API `study/sync/` (grade + undo theo lô) + chống chấm trùng
  - [x] T4.3.5 `study_deck.js` (hàng chờ gửi, thử lại, `sendBeacon`)
  - [x] T4.3.6 Message + CSS thanh báo
  - [x] T4.3.7 Test + `flows.js`
  - [ ] T4.3.8 Áp cho SC04 (spec riêng, làm sau)

### Phase 6 — Khối lượng ôn tập (duyệt 09/10/2026)
- [x] T6.1 Hạn mức từ mới chung cho mọi lối vào + khối "Vẫn học thêm" (F) — code xong 09/10/2026, chờ Dat chạy trên server thật
- [x] T6.2 Hoãn từ dở bước học sang mai, ưu tiên đầu hàng, "Nhớ" là tốt nghiệp (V3) — code xong 09/10/2026, chờ Dat chạy trên server thật
- [x] T6.3 Vuốt lên = Dễ (V1) — code xong 09/10/2026, chờ Dat thử trên điện thoại thật
- [x] T6.4 Báo kết quả sau mỗi lần chấm (V2) — code xong 09/10/2026. **Tạm tắt 10/10/2026** (Dat: làm chậm nhịp vuốt trên điện thoại) — comment `initGradeToast()` trong `main.js`, server vẫn dựng `data-toast`
- [x] T6.5 Tự giảm / tạm dừng từ mới khi nợ ôn cao (B) — code xong 09/10/2026, chờ Dat chạy trên server thật
- [x] T6.6 Hướng dẫn cử chỉ lần đầu (V5) — code xong 09/10/2026, chờ Dat thử trên điện thoại thật
- [x] ~~V4 Rút bước học từ mới xuống 1 bước~~ — Dat chốt không làm (09/10/2026)

### Ghi chú T6.1 (09/10/2026) — để đối chiếu khi review
- `services.new_word_allowance()` là nguồn hạn mức duy nhất: `_daily_parts` (SC03),
  `get_topic_queue` (SC04/SC06), `get_topic_in_progress` và SC05 đều đi qua đây.
- SC05: `services.plan_study_queue(..., new_limit=)` trả `StudyPlan(queue, held_new)`;
  `build_study_queue()` giữ nguyên API (SC15 gọi, không giới hạn). `held_new` chỉ đếm từ mới
  mà KHÔNG có hạn mức thì đã lọt vào lượt học (sau khi cắt `limit`).
- SC05 tính trước kế hoạch ngay khi lọc (thêm ~3 query: id từ, tiến độ, đếm từ mới hôm nay /
  ngày mai) → trang hiện đúng "Lượt này học N từ", ẩn nút "Bắt đầu học" khi lượt học rỗng, và
  hiện khối "Vẫn học thêm" (POST lại bộ lọc + `over_limit=1`).
- `study_start_view`: lượt học rỗng vì toàn từ mới vượt hạn mức → quay lại SC05 đúng bộ lọc
  (không tạo `StudySession`); có từ bị giữ → flash "giữ lại N từ mới".
- `_filter_params` của SC05 chuyển thành `selectors.filter_params()` (dùng chung với đường quay lại).
- Partial mới `templates/learning/_over_limit_notice.html` (SC04 màn xong + SC05). Bỏ key
  `learning.flashcard.button.more_new`, rút gọn `learning.flashcard.hint.new_limit_reached`.
- Test: `NewWordAllowanceTests` (12 test). `test_missing_limit_means_every_word` nâng
  `daily_review_goal` lên 30 vì 25 từ mới giờ vượt hạn mức mặc định 20 (đúng ý T6.1).
  Toàn bộ test chạy trên PostgreSQL 16 local; 2 lỗi CÓ SẴN từ trước ở `admin_panel`
  (`DataIoEngineTests`/`FullVocabularyDatasetTests` đếm số bảng 19 ≠ 31 sau khi thêm app keigo).
- Đã xem giao diện SC04 (màn xong) + SC05 ở theme A/B/C, 1280px và 375px, sáng + tối (B):
  không tràn ngang.

### Ghi chú T6.2 (09/10/2026) — để đối chiếu khi review
- **Định nghĩa "từ dở" chốt khi code** (chính xác hơn bản spec "next_review_date < hôm nay"):
  `card_state ∈ {learning, relearning}`, `next_review_date <= hôm nay` và lần chấm cuối KHÔNG
  phải hôm nay — `due_at` rỗng (vừa hoãn bằng "Kết thúc") hoặc trước nửa đêm hôm nay (bỏ
  ngang phiên). Lý do: từ hoãn hôm qua có `next_review_date = hôm nay` nên điều kiện "< hôm nay"
  sẽ bỏ sót. Code: `services._is_leftover_learning()` / `leftover_learning_q()`.
- `services.postpone_learning(user, ids)`: một UPDATE, chỉ đụng từ learning/relearning đang đến
  hạn hôm nay; giữ `card_state`/`learning_step`.
- Gọi ở `_clear_study_session()` (Kết thúc, bắt đầu phiên khác, hết thẻ) — chỉ phiên chính
  thức. SC04: "Kết thúc phiên" đổi từ link sang form POST `learning:flashcard_end` (route mới),
  hoãn các từ đã chấm trong phiên (`_first_grades`). Kết thúc có hoãn từ thì flash
  "Đã hẹn N từ đang học dở sang ngày mai…".
- Thứ tự: `_daily_due_ids` = từ dở → REVIEW đến hạn → từ đang học hôm nay; `get_topic_queue`
  đặt từ dở đầu nhóm đến hạn (đếm vào `n_review`, không vào `n_learning`). Từ đã hoãn sang mai
  không xuất hiện hôm nay ở cả hai.
- Bộ đếm: `get_review_overview` / `get_review_calendar` tính từ dở vào "hôm nay" (không vào
  "quá hạn"); `count_due_tomorrow` tính cả từ đang học đã hoãn sang mai.
- `srs.schedule(..., overnight=False)`: `overnight=True` + "Nhớ" với từ learning/relearning →
  tốt nghiệp. `review_word()` và `grade_previews()` tự tính cờ (`services._overnight`).
- Phía JS (`study_deck.js`) không phải sửa: thứ tự hàng đợi do server dựng, kết quả tốt nghiệp
  sớm đi về qua `study/sync/` như mọi lần chấm.
- Test: `OvernightScheduleTests` (4) + `LeftoverLearningTests` (12).
- **Với 121 từ đang kẹt trên server thật:** không cần chạy script dữ liệu — chúng thoả định nghĩa
  "từ dở" (`next_review_date` 08/10, `due_at` hôm 08/10) nên sau khi deploy tự lên đầu "Học hôm
  nay", tính vào "đến hạn hôm nay" và mỗi từ "Nhớ" một lần là tốt nghiệp.

### Ghi chú T6.3 (09/10/2026) — để đối chiếu khi review
- `main.js initCardSwipe`: hướng chốt ở ~10px đầu — ngang (trái Quên / phải Nhớ như cũ), **lên**
  → nút `data-grade-key="4"` (Dễ), xuống → không chấm. Bảng `SWIPE_KEYS`.
- **Khác bản spec:** `touch-action:none` cho thẻ đã lật áp theo media `(hover:none) and
  (pointer:coarse)` (mọi thiết bị cảm ứng, kể cả tablet) thay vì `≤ 560px` — tablet cũng cần
  vuốt lên ăn chắc. Để kéo XUỐNG trên thẻ vẫn cuộn được trang, JS tự `scrollBy` theo ngón tay.
- Màu viền `swipe-up` dùng token `--accent` / `--accent-soft` (màu nút Dễ) → tự đúng 3 theme + tối.
  `study_deck.js` dọn thêm class `swipe-up` khi đổi thẻ.
- Label `learning.flashcard.hint.swipe` = "Vuốt thẻ: ← Quên rồi · → Nhớ · ↑ Dễ"; bảng phím tắt
  thêm dòng cử chỉ (`learning.flashcard.shortcut.swipe`).
- Kiểm trên Chromium (Playwright + CDP `Input.dispatchTouchEvent`, 375×812, cảm ứng) ở cả SC04
  và phiên có bộ thẻ: lên → Dễ (từ mới `review` 4 ngày), phải → Nhớ, trái → Quên; chưa lật thẻ /
  vuốt ngắn < 80px / vuốt xuống → không chấm; kéo xuống trên thẻ cuộn trang (scrollY 120 → 40).
  **Chưa thử trên iPhone/Android thật.**
- Test: `SwipeUpMarkupTests` (2) + 2 rule mới trong `StudyScreenCssTests`.

### Ghi chú T6.4 (09/10/2026) — để đối chiếu khi review
- `views._grade_toasts(progress, touch, previews)` dựng câu báo cho 4 nút từ
  `services.grade_previews()` (hàm thuần, không thêm query) — luôn tính, không phụ thuộc tuỳ
  chọn SC08 "hiện khoảng cách" (tuỳ chọn đó chỉ quyết định hiện số dưới nút như cũ).
- Nội dung (`message.properties`, `learning.flashcard.toast.*`): Quên → "✗ Quên rồi · gặp lại
  trong phiên này"; khoảng cách tính bằng phút/giờ → "✓ {nút} · gặp lại trong phiên này"; tính
  bằng ngày/tháng → "✓ {nút} · gặp lại sau {N ngày}"; phiên ôn thêm → "{nút} · lượt ôn thêm,
  lịch ôn không đổi".
- SC04: mỗi nút có `data-toast`. Phiên có bộ thẻ: mỗi thẻ trong `#study-deck` và mỗi kết quả của
  `study/sync/` có `toasts`; `study_deck.js` gắn lại `data-toast` khi vẽ thẻ.
- `main.js initGradeToast`: bắt `click` ở pha capture (trước khi thẻ bị đổi) trên
  `[data-study-card] [data-grade-key]` — nút, phím 1–4 và vuốt đều đi qua `button.click()`.
  Phần tử `.grade-toast` nằm trong `flashcard.html`, NGOÀI `#card-panel` (không bị thay khi đổi
  thẻ). Hiện 1,6 giây; màu đảo `--ink`/`--bg` nên đọc rõ mọi theme + tối; ≤560px nằm ngay trên
  hàng nút ghim đáy; `prefers-reduced-motion` tắt hiệu ứng.
- Đổi test cũ `test_buttons_hide_the_interval_by_default`: "4 ngày" giờ có trong `data-toast`
  nên kiểm "không có `.btn-grade-delay`" thay cho "không có chữ 4 ngày".
- Kiểm trên Chromium (375px cảm ứng + 1280px, theme C tối) ở SC04 và phiên có bộ thẻ: bấm Dễ,
  phím 3, vuốt trái đều ra đúng câu; tự ẩn sau ~1,6 giây.
- Test: `GradeToastTests` (6).

### Ghi chú T6.5 (09/10/2026) — để đối chiếu khi review
- Luật nằm TRONG `services.new_word_allowance()` nên mọi lối vào của T6.1 (SC03, SC04/SC06, SC05)
  tự áp dụng. Hằng số `BACKLOG_SLOW = 3`, `BACKLOG_STOP = 5` (bội của `daily_review_goal`).
  `NewWordAllowance` có thêm `cap` (hạn mức thật hôm nay) và `threshold` (ôn xuống dưới số này
  thì hạn mức tăng lại).
- `services.count_backlog()` = REVIEW đến hạn/quá hạn/chưa xếp lịch + từ dở bước học (định nghĩa
  T6.2). Không tính từ đang học trong ngày và từ đã hoãn sang mai. Thêm 1 query COUNT mỗi lần
  tính hạn mức.
- Trang chủ: `get_daily_overview()` trả thêm `paused/backlog/cap/goal/threshold`; dưới dòng
  "N từ cần ôn · M từ mới" hiện partial mới `learning/_backlog_hint.html` ("Đang nợ … — tạm dừng
  từ mới cho tới khi còn dưới …" / "… hôm nay chỉ N từ mới; ôn xuống dưới … thì lại đủ …").
- Khối "Vẫn học thêm" (SC04 màn xong, SC05) khi bị giảm/dừng thì dòng đầu nêu lý do nợ ôn thay
  cho "đã học X/Y". Nút "Vẫn học thêm" vẫn mở thêm một hạn mức — khuyên, không cấm (quyết định 8).
- Với số liệu 09/10/2026 (254 nợ, goal 20): ≥ 100 → 0 từ mới; từ 60–99 → 10; dưới 60 → 20.
- Test: `BacklogAllowanceTests` (9). Đã xem trang chủ + SC05 ở 375px (theme A): không tràn ngang.

### Ghi chú T6.6 (09/10/2026) — để đối chiếu khi review
- Lớp phủ `[data-swipe-coach]` trong `flashcard.html`, NGOÀI `#card-panel` (fragment khi đổi thẻ
  không có nó). Hộp 3 ô: ↑ Dễ ở trên, ← Quên rồi / → Nhớ ở dưới; màu lấy đúng màu 3 nút chấm của
  theme (ô ↑ dùng `.btn-primary`, hai ô dưới dùng token `--grade-*`) + dòng "Mỗi lần vuốt là
  một lần chấm — không phải chuyển trang." (đúng chỗ Dat từng hiểu nhầm). Chữ từ label
  `learning.flashcard.coach.*` + nhãn nút sẵn có.
- `main.js`: `revealCard()` gọi `maybeShowSwipeCoach()` — chỉ khi `(hover: none) and (pointer:
  coarse)`, mỗi lần mở trang tối đa một lần, đếm `localStorage["bjt.swipeCoach.count"]` tới 3
  (try/catch; không đọc được thì hiện mỗi lần mở trang). Chạm lớp phủ hoặc Esc để đóng. Khi lớp
  phủ đang mở, vuốt không chấm (ngón tay chạm lớp phủ, không chạm thẻ).
- Kiểm trên Chromium (375px cảm ứng, theme B): lần mở 1–3 hiện sau khi lật, chạm thì đóng, vuốt
  khi đang mở không chấm; lần 4 không hiện; máy tính (1280px, không cảm ứng) không bao giờ hiện.
- Test: `SwipeCoachTests` (3).

### Ghi chú: "đã thuộc" theo khoảng cách ôn (10/10/2026, Dat duyệt)
- **Vấn đề:** luật cũ `srs_level >= 5` đếm số lần ôn thành công. Bấm "Dễ" làm khoảng cách giãn
  nhanh nên ít lần ôn hơn → từ biết rõ lại thành "đã thuộc" MUỘN hơn (luôn Dễ: ngày 134; luôn
  Nhớ: ngày 60).
- **Luật mới:** `srs.is_mastered(card)` = đang ôn (`review`) và `interval_days >= 21`
  (`srs.MASTERED_INTERVAL`, như thẻ "mature" của Anki). Luôn Nhớ → đã thuộc ở lần ôn ngày 22 (hẹn
  38 ngày); luôn Dễ → ngày 12 (hẹn 27 ngày). Quên → relearning → hết "đã thuộc".
- `review_word()` ghi `is_mastered = srs.is_mastered(card)`. Mọi nơi khác (trang chủ, hồ sơ, SC05
  lọc "Đã thuộc", SC15 thẻ "Đã thuộc", danh hiệu học tập) vẫn đọc cột `is_mastered` — không đổi.
- Bảng "Theo độ nhớ" (SC15) chia lại theo khoảng cách: mới nhớ (chưa tốt nghiệp hoặc < 7 ngày) /
  đang nhớ (7–20 ngày) / đã thuộc (≥ 21 ngày). Nhãn `learning.review.band.*` đổi theo.
- Migration dữ liệu `learning/0003_mastered_by_interval` tính lại `is_mastered` cho mọi dòng
  (có hàm quay ngược về luật cũ). **Số "Từ đã thuộc" và danh hiệu học tập của người dùng có thể
  thay đổi sau khi deploy** — tăng hoặc giảm tuỳ dữ liệu.
- Test: `MasteredByIntervalTests` (5) + viết lại `test_memory_bands_split_by_review_interval`.

### Ghi chú T4.3 (06/10/2026) — để đối chiếu khi review
- **Khác bản duyệt:**
  - Gộp chấm + hoàn tác vào MỘT endpoint theo lô `POST study/sync/`. Khi mạng chậm, các lần
    chấm dồn lại gửi một request (đo thử: 4 lần chấm = 2 request), và hoàn tác luôn đi đúng
    thứ tự sau các lần chấm trước nó. Form `undo/` + `study/review/<id>/` cũ giữ nguyên cho
    trường hợp tắt JS.
  - Tải thêm thẻ bằng `study/cards/?ids=` thay vì `?offset=`: hàng đợi phía server đổi sau
    mỗi lần chấm nên `offset` không ổn định, JS tự biết cần id nào.
  - Không có partial `_card_face.html`: mặt trước (từ / cách đọc / nghĩa) là chữ thuần, JS gán
    `textContent` (thẻ `.flashcard` là flex, bọc thêm khung sẽ đổi bố cục). Chỉ mặt sau
    (chủ đề + ví dụ) render sẵn bằng `_card_extra.html`.
  - `sendBeacon` lúc đóng tab chỉ gửi khi KHÔNG có lô nào đang bay: gửi song song sẽ ghi đè
    session của nhau. Lô đang bay mà không tới được thì localStorage giữ lại, lần mở màn học
    sau tự gửi nốt rồi tải lại theo server.
  - Không thêm message "Đang lưu...": lúc phải chờ (thẻ cuối lượt chưa có kết quả, tải thêm
    thẻ) dùng lại trạng thái bận `.card-panel.is-busy` sẵn có.
- **Server:** `_apply_undo()` tách từ `undo_view` để `study_sync_view` dùng chung; khoá session
  mới `study_seq` (dọn trong `_clear_study_session`). Bộ thẻ cũng đi kèm khi render partial,
  nên "Ôn thêm" từ màn tổng kết (đi qua main.js) tự có bộ thẻ mới.
- **Số đo trên máy dev (SQLite, Chrome):** chấm → thẻ kế hiện sau **2–5 ms** (lần đầu ~75 ms
  do trình duyệt vẽ lần đầu). `GET study/` = 14 query. Chưa đo trên Render — Dat đo lại bằng
  header `Server-Timing` (Network → Timing) để ghi số "sau".
- **Đã thử trên trình duyệt:** phím tắt Space/1-4/Z; hoàn tác tại chỗ; đi hết phiên tới màn tổng
  kết (số liệu khớp: 12 từ, 92%, 13 lượt chấm); "Ôn thêm" (bộ thẻ mới, Quên → xuống cuối);
  giả lập mất mạng (thanh báo sau 3 lần lỗi, có mạng lại tự gửi); tải lại trang khi còn lệnh
  chưa gửi (gửi nốt rồi hiện tổng kết); mở khu thảo luận ở thẻ đã chuyển; 375px không tràn ngang.
- **Kiểm thử:** 18 test mới (`StudyDeckTests`). Toàn bộ 548 test trên SQLite tạm: chỉ còn 8 lỗi
  CÓ SẴN từ trước (SQLite thiếu `SIMILARITY` / `pg_extension`) — cần Dat chạy lại trên DB thật.

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
| 7 | Delay khi vuốt thẻ — xử lý thế nào? (06/10/2026) | ✅ Phương án C: tải trước bộ thẻ, chấm gửi ngầm (T4.3) |
| 8 | Số từ ôn quá lớn, không còn thời gian học từ mới (09/10/2026) | ✅ Làm Phase 6 theo thứ tự F → V3 → V1 + V2 → B → V5; **không** làm V4 |

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
