# SPEC — Luyện nghe dịch qua bản tin

Ngày: 18/11/2026 · Nguồn: `inputDocument/Thaolejp_BJT_Luyen nghe dich qua ban tin.pdf` (20 bài, web cá nhân — không bận tâm bản quyền).

## 1. Mục đích

Dat có 20 bản tin kinh tế tiếng Nhật (mỗi bài 3 đoạn 問題1–3), chỉ có chữ — không audio, không bản dịch, không câu hỏi.
Muốn biến thành một mục luyện mới trên web: **nghe một đoạn → tự dịch trong đầu/nói ra → mở chữ Nhật và bản dịch mẫu để so**.
Đúng tinh thần "luyện nghe dịch" của tài liệu.

**Thành công** = mở bài bất kỳ trên điện thoại, nghe được từng đoạn, ẩn/hiện chữ và bản dịch, thấy từ nào đã học trong kho từ vựng, đánh dấu bài đã luyện.

- **Ngoài phạm vi:** chép chính tả, chấm điểm, câu hỏi trắc nghiệm, tiến độ theo từng đoạn, ghi chú cá nhân.
- **Không được:** hiện sẵn bản dịch/chữ Nhật (mất tác dụng luyện), trang dài lê thê (quy tắc "no long pages": đo ở 1280×860 và 375px).

## 2. Các cách đã cân nhắc

| | Cách | Được | Mất |
|---|---|---|---|
| **A ✔** | Nghe → tự dịch → mở đáp án; gạch chân từ có trong kho | Đúng mục đích tài liệu, ít code, tái dùng nhiều | Không chấm điểm |
| B | Chép chính tả, máy so với bản gốc | Đo được tiến bộ | Gõ tiếng Nhật trên điện thoại mệt; so kanji/kana dễ chấm sai |
| C | Trắc nghiệm nghe hiểu trong mục Kiểm tra | Dùng lại cả hệ thống thi + sổ câu sai | Thành bài thi, phải soạn ~60 câu hỏi, lệch mục đích "dịch" |

Dat chọn **A** (18/11/2026).

## 3. Dữ liệu

App mới `apps/news` (URL `/nghe-ban-tin/`), 2 bảng, đều `AuditableModel`:

- **NewsLesson** — `number` (unique, 1–20), `title_jp`, `title_vi`.
- **NewsSegment** — `lesson` FK, `number` (1–3), `text_jp` (Text), `translation_vi` (Text), `audio_url` (URL, blank). UniqueConstraint (`lesson`, `number`).

Có khoá tự nhiên nên màn nhập SC07b (`apps/core/dataio.py`) tự nhận — không viết importer riêng.
File dữ liệu: `docs/data/news/01_news_lesson.csv`, `docs/data/news/02_news_segment.csv`.

**Nội dung** — Claude soạn, Dat duyệt:
- `text_jp`: chép từ PDF, bỏ số trang, nối dòng bị ngắt (bỏ khoảng trắng chen giữa chữ Nhật).
- `translation_vi` + `title_vi`: Claude dịch, văn phong tự nhiên, sát nghĩa.

**Tiến độ:** dùng lại `UserPracticeMark` (apps/lessons) với `kind="news"`, `object_id = NewsLesson.id`, mức **bài** (không theo đoạn). Thêm mã `news` vào MasterCode PRACTICE_KIND (`seed_mastercode.py`).

## 4. Audio

- VOICEVOX giọng No.7 アナウンス (speaker 30) như từ vựng; bỏ hết khoảng trắng trước khi đọc (bài học từ pilot: 「50 人」 bị đọc sai).
- Mỗi đoạn một file `media/news_audio/n<segment_id>.mp3`, mp3 48 kbps.
- Upload vào bucket `vocab-audio` qua `scripts/upload_vocab_audio.py` — thêm tiền tố `n` → `NewsSegment.audio_url` cạnh `w/e/m` đang có (URL kèm `?v=<md5>` như cũ).
- Tạo audio: script mới nhỏ hoặc mở rộng `generate_vocab_audio.py` — người làm chọn, miễn dùng chung hàm `audio_query`/`to_mp3`.
- Credit 「VOICEVOX:No.7」 hiện dưới trình phát.

## 5. Màn hình

**Danh sách** `/nghe-ban-tin/` — 20 dòng: số bài, tiêu đề Nhật + Việt, dấu ✓ nếu đã luyện, đếm "đã luyện x/20" ở đầu.

```
Nghe dịch bản tin                      Đã luyện 3/20
─────────────────────────────────────────────────
 ✓ 第1課  ペット同伴可能な会員制シェアオフィス開業
          Khai trương văn phòng chia sẻ cho phép mang thú cưng
   第2課  …
```

**Bài** `/nghe-ban-tin/<number>/` — 3 thẻ đoạn:

```
‹ Danh sách    第1課 ペット同伴可能な…     Bài trước · Bài sau ›
┌ 問題1 ─────────────────────────────────────────┐
│ ▶ Nghe   [0.75×] [1×]                            │
│ [Hiện chữ Nhật]   [Hiện bản dịch]                │
│ (ẩn) 東京不動産が9月6日、… ← từ trong kho gạch chân│
│ (ẩn) Ngày 6/9, Tokyo Fudosan sẽ khai trương…      │
└──────────────────────────────────────────────────┘
┌ 問題2 … ┐ ┌ 問題3 … ┐
            [ Đánh dấu đã luyện ✓ ]
VOICEVOX:No.7
```

- Chữ Nhật và bản dịch **ẩn mặc định**, mỗi đoạn bật riêng; tốc độ áp dụng cho cả trang (nhớ bằng localStorage — nếu lỗi thì về 1×).
- Bấm từ gạch chân → popover nhỏ: từ, cách đọc, nghĩa (không phát audio nghĩa — giữ quy tắc audio nghĩa chỉ ở "Nghe cả chủ đề").
- Nút "Đánh dấu đã luyện" = POST, bấm lại thì bỏ dấu.
- Theme A/B/C dùng token có sẵn trong `docs/STYLE_GUIDE.md`; chữ UI qua `{% label %}` như các trang khác.
- Thêm mục menu trong `templates/partials/sidebar.html`. Yêu cầu đăng nhập như các trang học khác.

## 6. Gạch chân từ trong kho

Hàm thuần `highlight(text, vocab)`:
- Lấy `Vocabulary` đang hoạt động có `word` dài ≥ 2 ký tự; với từ kết thúc bằng `する` thì so phần gốc (高騰する → 高騰).
- Tìm trong `text_jp`, ưu tiên từ **dài nhất**, không chồng lấn; trả về các đoạn [chữ thường | từ + id].
- Tính lúc render (≈3.500 từ × 3 đoạn — nhanh). `shortcut: so chuỗi con, không chia động từ (乗り切った không khớp 乗り切る); nếu cần thì thêm bộ tách từ sau.`
- Từ thuần kana ngắn dễ khớp nhầm (vd うち trong うちうち) → chỉ gạch chân từ kana-only khi dài ≥ 4 ký tự.

## 7. Kiểm thử

- Test hàm `highlight` (dài nhất trước, không chồng lấn, bỏ する, kana ngắn bị bỏ).
- Test view: danh sách, bài (404 khi số bài không có), POST đánh dấu/bỏ dấu, yêu cầu đăng nhập.
- Test dataio nhận 2 bảng mới (theo mẫu `apps/lessons/tests.py`).
- Máy Dat không có Postgres: Claude tự dựng PG portable trong scratchpad để chạy test và xem trang (cần Dat đồng ý tải ~340MB một lần); nếu không được thì nói rõ là chưa kiểm chứng.

## 8. Thứ tự làm

1. Soạn 2 file CSV (chữ Nhật + bản dịch) → Dat duyệt bản dịch.
2. App `news`: model + migration + admin + MasterCode `news`.
3. View/template + sidebar + label + highlight + test.
4. Deploy migration lên Supabase, nhập CSV, tạo + upload audio.
5. Kiểm tra trang trên 1280×860 và 375px.

## 9. Để người làm tự quyết

Tên class CSS, cách vẽ popover, tách script audio riêng hay mở rộng script cũ, câu chữ của label.
