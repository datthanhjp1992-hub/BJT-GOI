# Nghe dịch bản tin — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mục mới `/nghe-ban-tin/`: 20 bản tin × 3 đoạn, nghe audio → tự dịch → mở chữ Nhật/bản dịch, gạch chân từ có trong kho, đánh dấu bài đã luyện.

**Architecture:** App Django mới `apps/news` (2 model có khoá tự nhiên → SC07b tự nhập). Tiến độ dùng lại `lessons.UserPracticeMark` với kind `news`. Gạch chân từ là hàm thuần trong `apps/news/services.py`, tính lúc render. Audio VOICEVOX như từ vựng, upload qua `scripts/upload_vocab_audio.py` thêm tiền tố `n`.

**Tech Stack:** Django 5.2 (`.venv`), PostgreSQL (Supabase), template Django + JS thuần, VOICEVOX speaker 30.

**Spec:** `docs/SPEC_NGHE_BAN_TIN.md`

## Global Constraints

- Chạy mọi lệnh bằng `.venv\Scripts\python.exe`; test cần Postgres (PG portable trong scratchpad — máy Dat không có).
- Chữ UI qua `{% label %}` (`label.properties`), màu/khoảng cách theo token `docs/STYLE_GUIDE.md`, theme A/B/C.
- Chữ Nhật và bản dịch **ẩn mặc định**; trang không dài (đo 1280×860 và 375px).
- Audio: VOICEVOX speaker 30, bỏ mọi khoảng trắng trước khi đọc, mp3 48 kbps, credit 「VOICEVOX:No.7」.
- Popover từ vựng không phát audio nghĩa.
- Đăng nhập bắt buộc mọi view.

## Review Focus

- Đoạn chưa có `audio_url` → không hiện trình phát hỏng, hiện chữ "Chưa có audio". (test ở Task 4)
- Bấm "Đã luyện" hai lần / F5 sau POST không được lật trạng thái: POST mang `done=1|0` tường minh, không phải toggle, rồi redirect (PRG). (Task 4)
- `text_jp` có ký tự `<`/`&` vẫn hiển thị đúng — template không dùng `|safe` với nội dung. (Task 3/4)
- Số bài không tồn tại (`/nghe-ban-tin/99/`) → 404. (Task 4)
- localStorage bị chặn → tốc độ về 1×, không lỗi JS (bọc try/catch). (Task 4, kiểm tay)

---

### Task 1: Nội dung — 2 file CSV

**Files:**
- Create: `docs/data/news/01_news_lesson.csv` — cột `number,title_jp,title_vi`
- Create: `docs/data/news/02_news_segment.csv` — cột `lesson__number,number,text_jp,translation_vi,audio_url`

- [ ] **Step 1:** Tách 20 bài × 3 đoạn từ PDF (pdftotext), bỏ số trang/đầu trang, nối dòng, bỏ khoảng trắng chen giữa chữ Nhật. Kiểm tra: đúng 20 dòng bài, 60 dòng đoạn, không đoạn rỗng.
- [ ] **Step 2:** Viết `title_vi` + `translation_vi` cho 60 đoạn.
- [ ] **Step 3:** Gửi Dat duyệt bản dịch (không chặn Task 2–4).
- [ ] **Step 4:** Commit `docs/data/news/`.

### Task 2: Model, migration, MasterCode, dataio

**Files:**
- Create: `apps/news/{__init__,apps,models,admin}.py`, `apps/news/migrations/0001_initial.py`, `apps/news/tests.py`
- Modify: `config/settings/base.py` (INSTALLED_APPS thêm `"apps.news"`), `apps/core/dataio.py` (`LOCAL_APP_LABELS` thêm `"news"`), `apps/core/constants.py` (`PRACTICE_KIND_NEWS = "news"`), `apps/core/management/commands/seed_mastercode.py` (thêm `("news", "Nghe bản tin", None, "NewsLesson", 4)` vào PRACTICE_KIND)

**Interfaces:**
- Produces: `NewsLesson(number: PositiveSmallInteger unique, title_jp: Char(200), title_vi: Char(255, blank))`, ordering `number`; `NewsSegment(lesson FK related_name="segments" CASCADE, number: PositiveSmallInteger, text_jp: Text, translation_vi: Text(blank), audio_url: URL(blank))`, UniqueConstraint(lesson, number) name `uniq_news_segment`, ordering `lesson, number`. Cả hai `AuditableModel`. `PRACTICE_KIND_NEWS`.

- [ ] **Step 1: Test** `NewsModelTests`:
  - `test_natural_keys_reject_duplicates`: tạo trùng `NewsLesson.number` và trùng (`lesson`,`number`) của segment → `IntegrityError`.
  - `test_mastercode_has_news`: sau `seed_mastercode`, `[c for c,_ in practice_kind_choices()] == ["drill","blank","polite","news"]`.
  - `test_dataio_headers`: `dataio.headers_for(NewsSegment)[:2] == ["lesson__number", "number"]`.
  - Sửa `apps/lessons/tests.py::test_mastercode_seeded` thành danh sách 4 mã.
- [ ] **Step 2:** Chạy `python manage.py test apps.news apps.lessons` → FAIL.
- [ ] **Step 3:** Viết model/admin/app, `makemigrations news`, sửa 4 file Modify.
- [ ] **Step 4:** Chạy lại → PASS.
- [ ] **Step 5:** Commit.

### Task 3: Gạch chân từ trong kho

**Files:** Create `apps/news/services.py`; Test `apps/news/tests.py`

**Interfaces:**
- Produces: `vocab_terms() -> list[tuple[str, Vocabulary]]` (đọc DB: từ đang hoạt động; term = `word` bỏ đuôi `する`; bỏ term < 2 ký tự; bỏ term thuần kana < 4 ký tự; sắp xếp dài trước). `highlight(text: str, terms: list[tuple[str, object]]) -> list[tuple[str, object | None]]` — hàm thuần, nối các phần lại phải bằng đúng `text`.
- Thuật toán: quét trái→phải, tại mỗi vị trí thử term theo thứ tự dài trước, khớp thì cắt ra và nhảy qua (không chồng lấn).

- [ ] **Step 1: Test** `HighlightTests`:
  - `highlight("原料コストが高騰", [("原料",1),("高騰",2)]) == [("原料",1),("コストが",None),("高騰",2)]`
  - dài trước: terms `[("生産拠点",1),("生産",2)]` trên `"生産拠点を"` → `[("生産拠点",1),("を",None)]`
  - `"".join(p for p,_ in highlight(t, terms)) == t` với `t` chứa `<b>&`
  - `vocab_terms()` với Vocabulary `高騰する`, `うち`, `うちうち`, `株`: term `高騰` có, `うち` không, `うちうち` có, `株` không.
- [ ] **Step 2:** Chạy → FAIL. **Step 3:** Viết. **Step 4:** Chạy → PASS. **Step 5:** Commit.

### Task 4: Trang danh sách + trang bài + đánh dấu

**Files:**
- Create: `apps/news/urls.py`, `apps/news/views.py`, `templates/news/index.html`, `templates/news/lesson.html`
- Modify: `config/urls.py` (`path("nghe-ban-tin/", include("apps.news.urls"))`), `templates/partials/sidebar.html` (link `news:index`, `active_nav == "news"`), `label.properties` (khoá `news.*`)

**Interfaces:**
- Consumes: Task 2 models, `PRACTICE_KIND_NEWS`, `UserPracticeMark`; Task 3 `vocab_terms`, `highlight`.
- Produces: url names `news:index` (`""`), `news:lesson` (`<int:number>/`), `news:mark` (`<int:number>/danh-dau/`, POST only).
- Context: index → `lessons` (mỗi bài có `.done`), `done_count`, `total`; lesson → `lesson`, `segments` (mỗi đoạn có `.parts` = kết quả `highlight`), `done`, `prev_number`, `next_number`. `active_nav="news"`.
- Mark: POST `done=1` → `update_or_create` mark `is_known=True`, `times+=1`, `last_at=now`; `done=0` → `is_known=False`. Redirect về `news:lesson`.

- [ ] **Step 1: Test** `NewsViewTests`:
  - chưa đăng nhập → redirect login cho cả 3 url.
  - index: 200, chứa `title_jp` bài 1, `done_count` đúng.
  - lesson 99 → 404; lesson 1 → 200, chứa chữ của đoạn 1; đoạn không có audio → có label `news.no_audio`.
  - POST mark `done=1` hai lần → 1 mark `is_known=True`; POST `done=0` → `is_known=False`; GET mark → 405.
  - `text_jp="A<b>B"` → response chứa `A&lt;b&gt;B`.
- [ ] **Step 2:** Chạy → FAIL.
- [ ] **Step 3:** Viết view/url/template/sidebar/label. Chữ Nhật + bản dịch trong `<details>` (ẩn mặc định, không cần JS). Audio `<audio controls preload="none">`; nút 0.75×/1× đặt `playbackRate` cho mọi `<audio>`, nhớ bằng localStorage trong try/catch. Từ gạch chân là `<button>` mở popover (từ, cách đọc, nghĩa).
- [ ] **Step 4:** Chạy `apps.news` + `apps.core` (TemplateLeakTests) → PASS.
- [ ] **Step 5:** Xem trang bằng preview ở 1280×860 và 375px, cả 3 theme; chụp màn hình.
- [ ] **Step 6:** Commit.

### Task 5: Audio

**Files:**
- Create: `scripts/generate_news_audio.py` (dùng lại `audio_query`, `to_mp3`, `SPEAKER` từ `scripts/generate_vocab_audio.py`; ra `media/news_audio/n<segment_id>.mp3` + manifest bỏ qua file không đổi)
- Modify: `scripts/upload_vocab_audio.py` — tiền tố `n` → `NewsSegment.audio_url`

- [ ] **Step 1:** Chạy thử script tạo trên 1 đoạn (`--limit 1`), nghe file.
- [ ] **Step 2:** Chạy thử upload (không `--apply`) → kế hoạch chỉ "Ghi audio_url … đoạn tin".
- [ ] **Step 3:** Commit.

### Task 6: Lên Supabase + kiểm tra

- [ ] **Step 1:** `python manage.py migrate --settings=config.settings.supabase`; `seed_mastercode` trên Supabase.
- [ ] **Step 2:** Nhập 2 CSV (dataio, chế độ upsert) — kiểm 20 bài, 60 đoạn.
- [ ] **Step 3:** Tạo + upload audio (`--apply --as-user dat`); kiểm 60/60 đoạn có `audio_url`, mở thử 1 link 200 `audio/mpeg`.
- [ ] **Step 4:** Báo Dat: trang nào, đã kiểm gì, chưa kiểm gì.
