# Spec — Luyện tập theo bài (Quyển 1)

> Ngày lập: 17/10/2026 · Trạng thái: **mục 0.2 đã chốt (Dat, 17/10/2026) — T1, T2 xong — chờ T3 mockup** · Người duyệt: Dat
>
> Nguồn: `bjt.db` của BJT-WEB — giáo trình hội thoại công sở "Quyển 1" (anh Smith,
> công ty ABC商事; 12 chương, 45 bài). Đây là "phần 2" trong bản rà `bjt.db` ngày 16/10/2026;
> "phần 1" (hội thoại + audio + câu then chốt từng bài) làm sau, cùng app.
> Mỗi task ghi **mục tiêu → file → cách làm → điều kiện hoàn thành → test**, theo mẫu `spec.md`.

---

## 0. Phạm vi và các điểm cần chốt

### 0.1 Ba dạng luyện tập — dữ liệu có sẵn

| Dạng | Bảng `bjt.db` | Số lượng | Hình dạng | Chấm tự động được? |
|---|---|---|---|---|
| **Luyện thay thế** (ドリル) | `drills` + `drill_items` | 34 bài × 3 câu = 102 câu | 1 câu mẫu `山川物産、佐藤課長 → こちら、山川物産の佐藤課長です。` + 3 gợi ý → câu đáp án | Không chắc — đáp án là câu tự do |
| **Hội thoại đóng vai** (復習) | `reviews` + `review_lines` + `review_answers` | 12 chương × 2 = 24 đoạn, 117 lời thoại, 65 chỗ trống | Tình huống tiếng Việt + hội thoại có chỗ trống `{1}` `{2}` | Không chắc — chỗ trống là cụm tự do |
| **Mức độ lịch sự** | `formal_informal` | 82 câu ở 41 bài, mỗi bài 2 câu | `ヤンと申します` (1) / `ヤンといいます` (2) / `よろしく！` (3) | **Có** — chọn 1 trong 3 mức |

Dữ liệu sạch: không câu nào thiếu đáp án, số `{n}` trong lời thoại khớp đúng 65 đáp án,
24 tình huống đều có tiếng Việt. Không có audio riêng cho phần luyện tập.

Mức `formality` suy từ dữ liệu (chưa có chú thích trong `bjt.db`):
1 = rất trang trọng (尊敬・謙譲, 申します / いたします), 2 = lịch sự (です・ます),
3 = thân mật (よろしく！, ねえ, あのう). **Cần đối chiếu sách trước T2.**

### 0.2 Quyết định đã chốt (Dat, 17/10/2026 — cả 5 điểm theo đề xuất)

| # | Câu hỏi | Chốt |
|---|---|---|
| ◆1 | Phần 2 cần tên bài / chương / tình huống, mà phần 1 chưa làm | Tạo app mới **`lessons`** ngay bây giờ với `Unit` + `Lesson` *tối thiểu* (tên, tình huống). Phần 1 sau này thêm hội thoại/audio vào **cùng app**, không đổi bảng. |
| ◆2 | Chấm luyện thay thế và hội thoại thế nào | **Tự nói → lật đáp án → tự chấm** "Đúng / Chưa" (giống lật thẻ flashcard). Không bắt gõ: so khớp chuỗi tiếng Nhật tự do (kanji/kana, dấu câu, 〜ます/〜ました) sẽ chấm sai nhiều hơn chấm đúng. |
| ◆3 | Có lưu kết quả không | Lưu **kết quả gần nhất của từng câu** (`Đúng / Chưa`, số lần) — đủ để hiện "đã luyện x/y" mỗi bài và nút "Luyện lại câu chưa thuộc". Không lưu lịch sử từng lượt. |
| ◆4 | Mức độ lịch sự — dạng câu hỏi | **Đổi 17/10/2026 (Dat):** mỗi câu là **một cặp trong cùng bài — "câu nào trang trọng hơn?"**, chấm ngay, hiện cả hai mức. 10 cặp ngẫu nhiên / lượt, hoặc theo chương. (Bản đầu "chọn 1 trong 3 mức" bị bỏ — xem phát hiện ở T2.) |
| ◆5 | Có đưa vào khu Kiểm tra (`apps.exam`) không | **Không** ở bản đầu — ◆2 tự chấm không hợp với bộ máy chấm điểm của exam. Xét lại cho ◆4 sau khi dùng thử. |

### 0.3 Không làm trong bản này

- Hội thoại đầy đủ, audio, câu then chốt, từ vựng từng bài (= phần 1).
- Nhận dạng giọng nói, chấm câu gõ tự do.
- Đưa câu luyện tập vào SRS / Sổ câu sai.
- Soạn/sửa bài trên web — dùng Django admin + nhập CSV (SC07b) như keigo.

---

## 1. Kiến trúc

### 1.1 App mới `apps/lessons`

URL namespace `lessons`, mục sidebar "Học theo bài" (phần 1 dùng chung). Mọi model kế thừa
`AuditableModel`; mã mức lịch sự qua MasterCode.

### 1.2 Model

| Model | Trường chính | Khoá tự nhiên (dataio) | Nguồn |
|---|---|---|---|
| `Unit` | `number` (1–12), `name_jp`, `name_vi` | `number` | `units` |
| `Lesson` | `unit`, `scene_no` (1–45), `title_jp`, `title_vi`, `situation_vi` | `scene_no` | `lessons` + `lesson_situations` |
| `Drill` | `lesson`, `example_prompt_jp`, `example_answer_jp` | `lesson` | `drills` — tách `example_jp` ở dấu ` → ` |
| `DrillItem` | `drill`, `number`, `prompt_jp`, `answer_jp` | `(drill, number)` | `drill_items` |
| `Roleplay` | `unit`, `number` (1–2), `situation_vi`, `book_page` | `(unit, number)` | `reviews` |
| `RoleplayLine` | `roleplay`, `number`, `speaker`, `text_jp` (giữ `{n}`) | `(roleplay, number)` | `review_lines` |
| `RoleplayBlank` | `roleplay`, `number`, `answer_jp` | `(roleplay, number)` | `review_answers` |
| `PolitenessPhrase` | `lesson`, `phrase_jp`, `level_code` | `(lesson, phrase_jp)` | `formal_informal` |
| `UserPracticeMark` | `user`, `kind` (drill/blank/polite), `object_id`, `is_known`, `times`, `last_at` | `(user, kind, object_id)` | — (◆3) |

`UserPracticeMark` dùng `kind + object_id` thay vì 3 bảng riêng — ba dạng có cùng một
nhu cầu (đúng/chưa gần nhất), và màn tổng quan đếm cả ba trong một truy vấn.

### 1.3 MasterCode

Code type mới: **mức lịch sự** — `1` Rất trang trọng · `2` Lịch sự · `3` Thân mật
(tên hiển thị chốt sau khi đối chiếu sách, mục 0.1).

### 1.4 Màn hình (namespace `lessons`)

| Màn | URL | Nội dung |
|---|---|---|
| L1 Tổng quan | `/bai/` | 12 chương dạng `<details>` (đóng sẵn trừ chương đang học); mỗi bài 1 dòng: tên + chip "Thay thế 2/3", "Lịch sự" và tiến độ |
| L2 Luyện thay thế | `/bai/<scene_no>/thay-the/` | Câu mẫu → lần lượt 3 gợi ý; "Hiện đáp án" → "Đúng / Chưa". Không JS bắt buộc (GET/POST như SC19–SC21) |
| L3 Hội thoại đóng vai | `/bai/chuong/<n>/dong-vai/<k>/` | Tình huống tiếng Việt, lời thoại có ô trống đánh số; mở từng ô hoặc "Hiện tất cả"; tự chấm từng ô |
| L4 Mức độ lịch sự | `/bai/lich-su/` (`?chuong=`) | 10 cặp / lượt, chọn câu trang trọng hơn, chấm ngay |

Cả 4 màn theo quy tắc trang không quá dài (spec.md §0 quy tắc 9): đo ở 1280×860 và 375px.

---

## 2. Danh sách task

### T1 ⭐ App `lessons`: model, MasterCode, admin (1 ngày)
- **File:** `apps/lessons/{models,admin,apps}.py`, migration `0001_initial`, `config/settings/base.py`,
  `config/urls.py`, `apps/core/constants.py` + `seed_mastercode.py`, `apps/core/dataio.py`
  (khoá tự nhiên mục 1.2), `scripts/deploy_supabase.py` (`LOCAL_APPS`).
- **Hoàn thành:** `migrate` sạch; `seed_mastercode` idempotent; 9 bảng hiện trên màn Nhập/xuất dữ liệu.
- **Test:** ràng buộc duy nhất; mọi model đủ 4 cột audit.
- **Đã xong 17/10/2026.** MasterCode `25` (mức lịch sự) + `26` (dạng câu luyện tập).
  Khoá tự nhiên lấy thẳng từ UniqueConstraint/unique của model (không khai thêm ở
  `dataio.NATURAL_KEYS`). Chưa thêm `config/urls.py` — chưa có view, để T4.

### T2 ⭐ Xuất CSV + kiểm dữ liệu (1 ngày)
- **File:** `scripts/export_bjt_lessons.py` (đọc `bjt.db` một lần, như `export_bjt_exam.py`),
  `docs/data/lessons/01_unit.csv` … `08_politeness_phrase.csv`,
  `apps/lessons/management/commands/check_lesson_data.py`.
- **Cách làm:** tách câu mẫu ở ` → `; giữ `{n}` trong lời thoại; đối chiếu nhãn mức lịch sự với sách.
- **`check_lesson_data`:** đủ 12 chương / 45 bài; mỗi `Drill` đúng 3 câu; trong mỗi đoạn đóng
  vai, tập `{n}` trong lời thoại == tập `RoleplayBlank.number`; mỗi bài có câu lịch sự đủ 2 câu.
- **Hoàn thành:** nạp qua SC07b (upsert) lần 2 báo 0 dòng mới; check không lỗi.
- **Đã xong 17/10/2026.** `scripts/export_bjt_lessons.py` → 8 file (12 / 45 / 34 / 102 / 24 /
  117 / 65 / 82 dòng). Nạp thử 2 lần qua `dataio` (upsert) trên Postgres local: lần 2 toàn bộ
  là cập nhật, 0 dòng mới, 0 lỗi; `check_lesson_data` đạt.
- **Phát hiện khi đối chiếu mức lịch sự (ảnh hưởng ◆4 / T7):** trong CÙNG một bài, số nhỏ luôn
  trang trọng hơn (41/41 bài đúng). Nhưng mức **không tuyệt đối giữa các bài**: bài 42 xếp
  「いつもお世話になっています」(です・ます) vào mức 3, bài 43–44 xếp 「今日はありがとうございました」
  /「これからもよろしくお願いします」 vào mức 1. Câu hỏi "chọn 1 trong 3 mức" sẽ chấm sai
  những câu này → đề xuất T7 đổi sang **"câu nào trang trọng hơn?"** theo cặp trong bài
  (chấm đúng cho cả 41 bài). Giữ nguyên `level_code` trong dữ liệu; nhãn MasterCode 25 hiểu là
  thứ tự tương đối. **Dat đã chốt 17/10/2026: hỏi theo cặp** (◆4).

### T3 Mockup L1–L4 (0,5–1 ngày) — **Dat duyệt trước khi code UI**
- **File:** `htmlTemplate/SC24_LuyenTapBai_A.html` (theme A, dữ liệu thật của bài 1–3).

### T4 L1 Tổng quan + sidebar (0,5 ngày)
### T5 L2 Luyện thay thế (1 ngày)
- **Test:** chưa đăng nhập → login; POST "Đúng/Chưa" tạo/cập nhật `UserPracticeMark`;
  bài không có drill → 404.

### T6 L3 Hội thoại đóng vai (1,5 ngày)
- **Cách làm:** `{n}` → ô đánh số, dựng trong selector (escape trước rồi mới chèn thẻ, như `|ruby`).
- **Test:** đoạn có 3 ô hiện đúng 3 ô; chữ trong lời thoại được escape.

### T7 L4 Mức độ lịch sự (1 ngày)
- **Test:** câu trang trọng hơn = `level_code` nhỏ hơn trong cặp; thứ tự hai câu hiển thị ngẫu nhiên; lọc `?chuong=`.

### T8 Tiến độ + "luyện lại câu chưa thuộc" + điện thoại, theme B/C (1 ngày)

---

## 3. Thứ tự và ước lượng

| Bước | Task | Ước lượng | Bàn giao |
|---|---|---|---|
| 1 | Chốt mục 0.2 | — | |
| 2 | T1 → T2 | 2 ngày | dữ liệu lên Supabase, chưa có UI |
| 3 | T3 mockup | 0,5–1 ngày | ✅ Dat duyệt giao diện |
| 4 | T4 + T7 | 1,5 ngày | ✅ **Mốc 1:** quiz lịch sự dùng được (chấm tự động, ít rủi ro nhất) |
| 5 | T5 + T6 | 2,5 ngày | ✅ **Mốc 2:** đủ 3 dạng |
| 6 | T8 | 1 ngày | ✅ **Mốc 3:** hoàn tất |

**Tổng: khoảng 8 ngày công.**

---

## 4. Rủi ro

| Rủi ro | Cách xử lý |
|---|---|
| Mức lịch sự 1/2/3 chỉ là thứ tự tương đối trong một bài (xem T2) | T7 hỏi theo cặp "câu nào trang trọng hơn?", không hỏi mức tuyệt đối |
| Tự chấm dễ "tự cho đúng" | Chấp nhận — mục đích là luyện nói; L1 chỉ hiện tiến độ, không xếp hạng |
| Phần 1 sau này cần thêm trường cho `Lesson` | Thêm cột nullable, không đổi khoá `scene_no`; CSV phần 2 vẫn nạp được |
| Lời thoại có `{n}` lệch số đáp án khi sửa tay | `check_lesson_data` kiểm khớp tập `{n}` ↔ `RoleplayBlank` |
