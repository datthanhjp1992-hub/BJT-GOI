# Spec — Từ đồng nghĩa trên thẻ flashcard

> Ngày lập: 17/10/2026 · Trạng thái: **mục 0.3 đã chốt (Dat, 17/10/2026 — cả 5 điểm theo đề xuất) — T1 + T2 xong, còn T3 (dữ liệu)** · Người duyệt: Dat
>
> Nguồn: bản vẽ thẻ của Dat (17/10/2026), 6 ô: đồng nghĩa · loại từ · từ học · nghĩa ·
> nút xem ví dụ · ví dụ. Mỗi task ghi **mục tiêu → file → cách làm → điều kiện hoàn thành → test**,
> theo mẫu `spec.md`.

---

## 0. Phạm vi và các điểm đã chốt

### 0.1 Đối chiếu bản vẽ với màn SC04 hiện tại

| Ô trong bản vẽ | Hiện trạng (`templates/learning/_card_panel.html`, `_card_extra.html`) | Việc phải làm |
|---|---|---|
| Loại từ (adj-na) | **Có** — `word.part_of_speech`, tag góc phải (MasterCode 24) | — |
| Từ học | **Có** — `.jp` + cách đọc (ẩn/hiện mặt trước theo SC08 `show_reading_on_front`) + Hán Việt | — |
| Nghĩa | **Có** — hiện sau khi lật (T1.4 "nhớ trước, xem sau") | — |
| Nút xem ví dụ | **Có** — `<details data-examples>`, phím `E`; **ẩn hẳn** khi từ không có ví dụ | Xem ◆4 |
| Ví dụ | **Có** — `ExampleSentence`, tối đa 3 câu | — |
| **Từ đồng nghĩa** | **Chưa có** — không model, không cột CSV, không dữ liệu | **Toàn bộ spec này** |

→ Spec này chỉ thêm **từ đồng nghĩa**; bố cục thẻ giữ như cũ.

### 0.2 Dữ liệu nguồn

- `bjt.db` (BJT-WEB): bảng `vocab` có 884 từ, 332 từ có `note`. Nhưng `note` chủ yếu là định
  nghĩa hoặc câu ví dụ; chỉ **2 dòng** có dạng đồng nghĩa (`きんきん ＝わずかに`,
  `自腹 = 自分で払うこと`). **Không có nguồn đồng nghĩa nào dùng được.**
- → Dữ liệu phải soạn mới: Claude đề xuất các cặp đồng nghĩa giữa các từ **đã có** trong
  hệ thống, xuất ra CSV, **Dat duyệt** trước khi nạp (T3).

### 0.3 Quyết định đã chốt (Dat, 17/10/2026 — cả 5 điểm theo đề xuất)

| # | Câu hỏi | Chốt |
|---|---|---|
| ◆1 | Quan hệ đồng nghĩa có tự động hai chiều không (gắn 静か→穏やか thì 穏やか cũng hiện 静か)? | **Có** — một dòng dữ liệu là đủ cho cả hai thẻ, khỏi lệch nhau. |
| ◆2 | Từ đồng nghĩa **không có** trong hệ thống thì lưu ra sao? | **Một ô chữ tự do** `synonyms_note` trên `Vocabulary` (vd `静寂、閑静`), hiện thành chip không bấm được. Không tạo `Vocabulary` mới, vì từ mới sẽ chui vào danh sách SC05 và hàng đợi học. |
| ◆3 | Vị trí trên thẻ | **Mặt sau, ngay dưới nghĩa** (khác bản vẽ: bản vẽ đặt trên cùng). Đặt ở mặt trước thì từ đồng nghĩa gợi ra nghĩa trước khi người học kịp tự nhớ, phá bước T1.4. |
| ◆4 | Từ không có ví dụ: nút "Xem ví dụ" mờ (bản vẽ) hay ẩn (hiện tại)? | **Giữ ẩn nút**, thêm một dòng chữ nhỏ "Chưa có ví dụ". Nút bị vô hiệu thì tương phản thấp và trên điện thoại không có tooltip giải thích. |
| ◆5 | Bấm chip đồng nghĩa đi đâu? | Mở SC05 (danh sách từ vựng) đã tìm sẵn từ đó (`?q=<word>`), **ở tab mới**, để không cắt ngang phiên học. Hiện chưa có trang chi tiết riêng cho một từ. |

### 0.4 Không làm

- Trái nghĩa, từ liên quan, nhóm từ (cùng một bảng nối nhưng thêm `kind` thì sau này mở rộng được — **không** thêm bây giờ).
- Sửa/thêm đồng nghĩa từ giao diện người học. Chỉ sửa qua Django admin + nhập CSV (SC07b).
- Hiện đồng nghĩa ở màn kiểm tra (`apps/exam`) — tránh lộ đáp án.

---

## 1. Kiến trúc

### 1.1 Model (`apps/vocabulary/models.py`)

| Thay đổi | Trường | Ghi chú |
|---|---|---|
| Model mới `VocabularySynonym(AuditableModel)` | `vocabulary` FK, `synonym` FK (cùng tới `Vocabulary`, `CASCADE`) | Bảng nối khai tường minh, có đủ 4 cột audit, như `VocabularyTopic`. Ràng buộc: `unique (vocabulary, synonym)` + `CheckConstraint vocabulary ≠ synonym`. |
| `Vocabulary.synonyms` | `ManyToManyField("self", through=VocabularySynonym, symmetrical=True, blank=True)` | ◆1. Django ≥ 3 hỗ trợ `symmetrical` với `through`: `add()` tự tạo dòng chiều ngược. |
| `Vocabulary.synonyms_note` | `CharField(max_length=255, blank=True)` | ◆2 — từ ngoài hệ thống, ngăn bằng `、`. |

**Lưu ý nhập CSV:** đường `dataio` tạo từng dòng bằng `save()` nên **không** tự sinh chiều
ngược. `VocabularySynonym.save()` tự tạo dòng ngược nếu chưa có (`get_or_create`), và
`check_vocab_data` (T3) báo những cặp lệch một chiều.

### 1.2 Hiển thị (`templates/learning/_card_extra.html`)

Đặt khối đồng nghĩa **trong `_card_extra.html`**, phía trên khối ví dụ. File này đã được
render sẵn cho từng thẻ của `#study-deck` (`views._study_card_payload`), nên `study_deck.js`
**không phải sửa** — chuyển thẻ là khối đồng nghĩa đổi theo.

```
静か  しずか                       [adj-na]
          Yên tĩnh, im lặng
Đồng nghĩa: [穏やか ↗] [静寂]          ← chip bấm được / chip chữ (synonyms_note)
[ 📖 Xem ví dụ  E ]                    ← ẩn khi không có; thay bằng "Chưa có ví dụ" (◆4)
```

- Không có đồng nghĩa nào (cả M2M lẫn `synonyms_note` đều trống) → **không render** khối, không chừa chỗ trống.
- Tối đa 5 chip; hơn thì hiện "+N". Đo chiều cao thẻ ở 1280×860 và 375px (`spec.md` §0 quy tắc 9).
- Nhãn mới qua `properties` (`learning.flashcard.label.synonyms`, `learning.flashcard.hint.no_example`), không viết cứng.

### 1.3 Query

Ba chỗ đang lấy `word.examples.all()[:3]` (`apps/learning/views.py` dòng ~502, ~1019,
`_study_card_payload` ~1086) thêm `prefetch_related("synonyms")`. Bộ thẻ `#study-deck` phải
prefetch theo lô — **không được** sinh N+1 (kiểm bằng `assertNumQueries` như T4.2).

---

## 2. Danh sách task

### T1 ⭐ Model + migration + admin + dataio (0,5 ngày)
- **File:** `apps/vocabulary/models.py`, migration `0007_…`, `apps/vocabulary/admin.py`
  (inline đồng nghĩa trong trang sửa từ, dùng `autocomplete_fields`), `apps/core/dataio.py`
  (khoá tự nhiên `vocabulary.vocabularysynonym: ("vocabulary", "synonym")`; thêm bảng vào
  `FullVocabularyDataset` nếu hợp).
- **Hoàn thành:** `migrate` sạch; thêm 1 cặp trong admin → cả 2 từ đều thấy nhau.
- **Test:** symmetrical (`a.synonyms.add(b)` → `b in` `a.synonyms` và `a in` `b.synonyms`); cấm tự
  đồng nghĩa với chính mình; cấm trùng; `save()` lẻ tạo chiều ngược; đủ 4 cột audit; xoá mềm một
  từ → từ đó không hiện ở thẻ kia (lọc `is_deleted=False`).

- **Đã xong 17/10/2026.** Migration `0008_synonyms`. `dataio`: cột mới `synonyms_note` có trong
  mẫu gộp "Từ vựng đầy đủ" (đã cập nhật `htmlTemplate/mau_danh_sach_tu_vung.{csv,xlsx}`); bảng
  `vocabularysynonym` nhập riêng theo khoá `(vocabulary, synonym)`. Sửa `synonym` của một dòng có sẵn
  thì dòng ngược cũ còn lại — để `check_vocab_data` (T3) báo.

### T2 ⭐ Hiện trên thẻ (0,5 ngày)
- **File:** `templates/learning/_card_extra.html`, `apps/learning/views.py` (prefetch),
  CSS chip trong file theme chung, `properties` (2 nhãn mới).
- **Hoàn thành:** đúng sơ đồ 1.2; chuyển thẻ trong `#study-deck` thì đồng nghĩa đổi theo; chế
  độ tối đọc được; tắt JS thì vẫn hiện (nằm trong `.after-reveal` như ví dụ).
- **Test:** từ có / không có đồng nghĩa; chỉ có `synonyms_note`; từ đã xoá mềm không hiện;
  số query của màn học không tăng theo số thẻ; dòng "Chưa có ví dụ" khi 0 ví dụ.

- **Đã xong 17/10/2026.** Khối đồng nghĩa đặt **đầu** `_card_extra.html` (ngay dưới thẻ, trên
  chủ đề); `services.get_study_cards` prefetch `synonyms` — test khẳng định số query không tăng
  theo số thẻ. ◆4: từ không có ví dụ hiện "Chưa có ví dụ cho từ này".

### T3 Soạn dữ liệu + kiểm (1 ngày, phần lớn là Dat duyệt)
- **File:** `docs/data/vocab_bjt/synonyms.csv` (`word,reading,synonym_word,synonym_reading,ghi_chu`),
  `apps/vocabulary/management/commands/check_vocab_data.py` (thêm mục kiểm, hoặc tạo mới).
- **Cách làm:** Claude đề xuất cặp **chỉ giữa các từ đã có** trong `vocab_topics.csv`
  (~1.000 từ), kèm cột lý do ngắn; Dat gạch các cặp sai; nạp qua SC07b.
- **`check_vocab_data`:** mọi `word/reading` trong CSV phải tồn tại; không tự trỏ chính mình;
  không cặp lệch một chiều.
- **Hoàn thành:** nạp 2 lần → lần 2 báo 0 dòng mới; check không lỗi.

---

## 3. Thứ tự và ước lượng

| Bước | Task | Ước lượng | Bàn giao |
|---|---|---|---|
| 1 | Chốt mục 0.3 | — | ✅ 17/10/2026 |
| 2 | T1 | 0,5 ngày | bảng có trên Supabase, sửa được trong admin |
| 3 | T2 | 0,5 ngày | ✅ thẻ hiện đồng nghĩa (dữ liệu nhập tay vài từ để thử) |
| 4 | T3 | 1 ngày | ✅ dữ liệu thật, Dat đã duyệt |
