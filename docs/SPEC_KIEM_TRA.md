# Spec — Kiểm tra (Phase 7)

> Ngày lập: 11/10/2026 · Trạng thái: **UI đã duyệt (11/10/2026), spec chờ duyệt** · Người duyệt: Dat
>
> Giao diện: `htmlTemplate/SC23_KiemTra_A.html` (8 màn S1–S8, theme A).
> Nguồn đề: `mock_exam_question` trong `bjt.db` của BJT-WEB (5 bộ × 100 câu).
> Mỗi task ghi **mục tiêu → file → cách làm → điều kiện hoàn thành → test**,
> theo đúng mẫu `spec.md`. Nguyên tắc chung ở `spec.md` mục 0 áp dụng cho mọi task.

---

## 0. Phạm vi và các điểm đã chốt

### 0.1 Bốn loại kiểm tra

| Loại | Màn | Nguồn câu hỏi | Lưu câu hỏi |
|---|---|---|---|
| Kiểm tra từ vựng | S2, S3 | Sinh từ `Vocabulary` mỗi lần làm | Ảnh chụp câu hỏi trong `ExamAnswer.payload` |
| Luyện theo dạng đề | S4 → S5/S6 | `ExamQuestion` lọc theo dạng, 10 câu ngẫu nhiên | Tham chiếu `ExamQuestion` |
| Thi thử | S4 → S5/S6 | 1 bộ đề 100 câu | Tham chiếu `ExamQuestion` |
| Sổ câu sai | S8 | Gom từ 3 loại trên | `WrongBookEntry` |

### 0.2 Quyết định đã chốt (Dat duyệt mockup 11/10/2026)

| # | Nội dung | Chốt |
|---|---|---|
| ◆1 | Câu sai ở bài từ vựng → từ về "học lại" | **Có**, bật mặc định, người học tắt được ở S2. Phạm vi "từ đến hạn hôm nay": câu đúng chấm như bấm **Nhớ** (`srs.GOOD`) — bài kiểm tra thay cho lượt ôn flashcard. Phạm vi khác: câu đúng **không** đụng lịch ôn. |
| ◆2 | Chế độ Thi | **Chặt**: bấm giờ từng phần, audio phát 1 lần, phần 1 (Nghe) không quay lại câu đã qua, nộp mới thấy đáp án. Chế độ Luyện thì tự do. |
| ◆3 | Điểm số | Chỉ hiện **%** theo phần/dạng. **Không** quy đổi thang BJT 0–800 (khớp `CHANGELOG_YEU_CAU` mục 5). |
| ◆4 | Ra khỏi Sổ câu sai | Đúng **2 lần liên tiếp**, hai lần cách nhau **≥ 1 ngày** (theo `User.local_today()`). |

### 0.3 Nơi lưu audio đề thi — **chốt B. Supabase Storage** (Dat, 11/10/2026)

250 file, **24 MB** (đo ở `BJT-WEB/media/audio/mock_exam`), mỗi file ~57 KB.

Đã so sánh với A (đặt trong `static/` của repo — WhiteNoise 6.12 trả đúng `206 Partial
Content` nên A cũng chạy được). Chọn B vì **audio sẽ được thay / ghi đè**: upload đè là
xong, không phải commit + deploy, lịch sử git không giữ mãi bản cũ, repo giữ nhẹ khi sau
này thêm audio Quyển 1 (~13 MB) hay bộ đề mới.

Chốt kèm:
- **Bucket `exam-audio`, public.** URL cố định, app ghép thẳng; không dùng link ký tạm thời
  (Dat: không lo bản quyền, app cá nhân).
- **Phiên bản để phá cache khi ghi đè.** `ExamQuestion.audio_version` (số nguyên, mặc định 1);
  URL = `EXAM_AUDIO_BASE_URL` + `audio_path` + `?v=<audio_version>`. Ghi đè file thì tăng
  phiên bản -> CDN Supabase và trình duyệt tải bản mới ngay, không phải chờ hết hạn cache.
- **Chỉ upload qua script** (`scripts/upload_exam_audio.py`), không upload tay trên Dashboard —
  vì chỉ script mới tăng `audio_version`. Upload tay thì người học có thể nghe bản cũ tới khi
  cache hết hạn.
- **Khoá `SUPABASE_SERVICE_ROLE_KEY` chỉ nằm trong `.env` trên máy chạy script** (không
  commit, không đặt lên Render). Render chỉ cần `EXAM_AUDIO_BASE_URL` (URL public, không bí mật).

Model chỉ lưu `audio_path` dạng tương đối (`exam/q031_part1_sec1.mp3`), URL dựng ở đúng
một hàm `exam_audio_url()` -> đổi nơi lưu về sau chỉ sửa hàm đó.

### 0.4 Không làm trong Phase 7

- Quy đổi điểm BJT, xếp hạng giữa người học.
- Câu hỏi có hình (biểu đồ, bảng ảnh) — `bjt.db` chỉ có văn bản.
- Soạn/sửa đề trên giao diện web — dùng Django admin + import CSV (SC07b) như keigo.
- Đưa câu thi (không phải từ vựng) vào SRS — Sổ câu sai đã đảm nhận.

---

## 1. Kiến trúc

### 1.1 App mới `apps/exam`

Tách riêng như `apps/keigo`, URL gốc `kiem-tra/` (`config/urls.py`), namespace `exam`.

```
apps/exam/
  models.py          ExamSet, ExamQuestion, ExamOption, ExamAttempt, ExamAnswer, WrongBookEntry
  selectors.py       truy vấn đọc (danh sách đề, thống kê theo dạng, câu sai)
  services/
    attempts.py      vòng đời lượt làm: start / resume / answer / submit_part / finish / score
    vocab_quiz.py    sinh câu hỏi từ vựng + đáp án nhiễu
    timing.py        hạn giờ từng phần, khoá câu phần Nghe
    wrongbook.py     cập nhật Sổ câu sai
    hooks.py         nối sang SRS (learning) và danh hiệu (gamification)
  views.py, urls.py, admin.py, tests/ (tách file theo service)
  management/commands/check_exam_data.py
templates/exam/      hub, vocab_setup, play_vocab, exam_list, play_exam, result, wrongbook, partials/
static/js/exam_play.js   phím tắt, đồng hồ, audio-1-lần, tự lưu (chỉ nạp ở màn làm bài)
```

Không gộp vào `apps/keigo`: keigo là bài tập theo sách (`ExerciseSet` cố định); exam có
thêm bấm giờ, chia phần, audio, câu sinh động. Logic dùng chung (`percent`,
`score_level`, render chỗ trống `（　）`) chuyển từ `apps/keigo/exercises.py` sang
`apps/core/quiz.py` để cả hai app import — keigo giữ nguyên hành vi (test keigo phải xanh).

### 1.2 Model

Tất cả kế thừa `AuditableModel`. Mọi danh sách lựa chọn đi qua MasterCode (mục 1.3).

```python
class ExamSet(AuditableModel):
    number = PositiveSmallIntegerField(unique=True)          # 1..5
    title = CharField(max_length=80)                          # "Bộ đề 1"
    slug = SlugField(unique=True)                             # "bo-de-1"
    is_active = BooleanField(default=True)
    source_note = CharField(max_length=255, blank=True)

class ExamQuestion(AuditableModel):
    exam_set = ForeignKey(ExamSet, related_name="questions", on_delete=CASCADE)
    part = PositiveSmallIntegerField()                        # 1, 2, 3
    section_code = CharField(max_length=10)                   # MasterCode "20": p1s1..p3s3
    number = PositiveSmallIntegerField()                      # thứ tự trong bộ đề, 1..100
    passage_type = CharField(max_length=40, blank=True)       # 会話 / 社内文書 / スケジュール表 ...
    passage_jp = TextField(blank=True)    # phần Nghe: LỜI THOẠI (ẩn tới khi được xem đáp án)
                                          # 場面設定 + phần Đọc: văn bản hiện cùng câu hỏi
    stem_jp = TextField()
    audio_path = CharField(max_length=120, blank=True)        # tương đối, xem 0.3
    explanation_vi = TextField(blank=True)
    level = CharField(max_length=10, blank=True)              # N1/N2/N3 theo nguồn
    source_ref = CharField(max_length=40, unique=True)        # "bjt.db:mock_exam_question:31"
    is_active = BooleanField(default=True)
    class Meta: unique (exam_set, number); index (section_code, is_active)

class ExamOption(AuditableModel):
    question = ForeignKey(ExamQuestion, related_name="options", on_delete=CASCADE)
    position = PositiveSmallIntegerField()                    # 1..4
    text_jp = CharField(max_length=300)
    is_correct = BooleanField(default=False)
    class Meta: unique (question, position)
    # clean(): mỗi câu đúng 1 phương án is_correct — giống QuestionOption của keigo

class ExamAttempt(AuditableModel):
    user = ForeignKey(User, related_name="exam_attempts", on_delete=CASCADE)
    kind_code = CharField(max_length=10)       # MasterCode "21": vocab / drill / mock / wrongbook
    mode_code = CharField(max_length=10)       # MasterCode "22": exam / practice
    exam_set = ForeignKey(ExamSet, null=True, blank=True, on_delete=SET_NULL)   # mock
    section_code = CharField(max_length=10, blank=True)                         # drill
    scope = JSONField(default=dict)            # vocab: {"scope": "due"|"topics"|"mastered",
                                               #  "topic_ids": [...], "types": [...], "srs_link": true}
    total = PositiveSmallIntegerField(default=0)
    score = PositiveSmallIntegerField(default=0)
    current_part = PositiveSmallIntegerField(null=True, blank=True)
    part_started_at = JSONField(default=dict)  # {"1": iso, "2": iso, "3": iso}
    part_submitted_at = JSONField(default=dict)
    started_at = DateTimeField()
    finished_at = DateTimeField(null=True, blank=True)
    class Meta: index (user, -started_at); index (user, finished_at)

class ExamAnswer(AuditableModel):
    attempt = ForeignKey(ExamAttempt, related_name="answers", on_delete=CASCADE)
    order = PositiveSmallIntegerField()                       # thứ tự hiện trong lượt
    question = ForeignKey(ExamQuestion, null=True, blank=True, on_delete=SET_NULL)   # drill/mock
    vocabulary = ForeignKey(Vocabulary, null=True, blank=True, on_delete=SET_NULL)  # vocab
    question_type_code = CharField(max_length=10, blank=True) # MasterCode "23": meaning/word/reading/cloze
    payload = JSONField(default=dict)    # vocab: {"prompt":..., "options":[...], "correct": 0}
                                         # drill/mock: thứ tự phương án đã xáo (nếu có)
    selected = PositiveSmallIntegerField(null=True, blank=True)   # vị trí đã chọn, null = chưa làm
    is_correct = BooleanField(default=False)
    flagged = BooleanField(default=False)
    answered_at = DateTimeField(null=True, blank=True)
    time_ms = PositiveIntegerField(default=0)
    class Meta: unique (attempt, order); index (attempt, selected)

class WrongBookEntry(AuditableModel):
    user = ForeignKey(User, related_name="wrongbook", on_delete=CASCADE)
    question = ForeignKey(ExamQuestion, null=True, blank=True, on_delete=CASCADE)
    vocabulary = ForeignKey(Vocabulary, null=True, blank=True, on_delete=CASCADE)
    question_type_code = CharField(max_length=10, blank=True) # với từ vựng: sai dạng nào
    wrong_count = PositiveSmallIntegerField(default=1)
    correct_streak = PositiveSmallIntegerField(default=0)
    last_correct_on = DateField(null=True, blank=True)
    last_wrong_at = DateTimeField()
    cleared_at = DateTimeField(null=True, blank=True)         # null = còn trong sổ
    class Meta:
        constraints: unique (user, question) khi question không null;
                     unique (user, vocabulary, question_type_code) khi vocabulary không null;
                     check: đúng một trong question / vocabulary
```

Ghi chú thiết kế:
- **Câu từ vựng sinh sẵn cả lượt lúc bắt đầu** (tạo đủ N dòng `ExamAnswer` với `payload`),
  không sinh từng câu khi hiện → F5, thoát ra vào lại, xem lại ở màn kết quả đều thấy
  đúng câu và đúng thứ tự phương án đã hiện. Kho từ thay đổi sau đó không làm hỏng lượt cũ.
- **Không lưu `part_deadline` cứng**: hạn = `part_started_at[part] + PART_MINUTES[part]`,
  tính khi cần → đổi thời lượng không phải migrate dữ liệu.
- `ExamAnswer.selected` là **vị trí trên màn hình** (1..4); với câu đề thi phương án không xáo
  (giữ đúng đề gốc), nên vị trí = `ExamOption.position`.

### 1.3 MasterCode mới (`seed_mastercode.py`, `apps/core/constants.py`)

| code_type | Tên | Mã |
|---|---|---|
| `20` | Dạng câu BJT | `p1s1` Nắm bắt ngữ cảnh · `p1s2` Kính ngữ ứng dụng (nghe) · `p1s3` Nghe hiểu toàn diện · `p2s1` Tình huống hội thoại · `p2s2` Đọc tài liệu · `p3s1` Ngữ pháp – Từ vựng · `p3s2` Kính ngữ ứng dụng (đọc) · `p3s3` Đọc hiểu văn bản. `mother_code` = `p1`/`p2`/`p3` (3 mã cha: 第1部 Nghe, 第2部 Nghe + Đọc, 第3部 Đọc) |
| `21` | Loại bài kiểm tra | `vocab`, `drill`, `mock`, `wrongbook` |
| `22` | Chế độ | `exam` (Thi), `practice` (Luyện) |
| `23` | Dạng câu từ vựng | `meaning` (日→Việt), `word` (Việt→日), `reading` (cách đọc), `cloze` (điền vào câu) |

Thời lượng phần ở chế độ Thi để trong `apps/exam/constants.py` (không phải lựa chọn hiển thị):
`PART_MINUTES = {1: 50, 2: 35, 3: 40}` (≈ 2 giờ cho 100 câu). Chỉnh sau khi Dat thử thật.

### 1.4 URL (namespace `exam`)

| URL | View | Màn mockup |
|---|---|---|
| `kiem-tra/` | `hub_view` | S1 |
| `kiem-tra/tu-vung/` GET form, POST tạo lượt | `vocab_setup_view` | S2 |
| `kiem-tra/de-thi/` | `exam_list_view` | S4 |
| `kiem-tra/bat-dau/` POST (`kind`, `mode`, `exam_set`/`section`) | `start_view` | — |
| `kiem-tra/luot/<id>/` GET câu hiện tại, POST trả lời | `play_view` | S3 / S5 / S6 |
| `kiem-tra/luot/<id>/cau/<order>/` GET nhảy câu (bị chặn nếu khoá) | `play_view` | S5 / S6 |
| `kiem-tra/luot/<id>/co/<order>/` POST cắm/bỏ cờ | `flag_view` | S5 / S6 |
| `kiem-tra/luot/<id>/nop-phan/` POST | `submit_part_view` | S5 / S6 |
| `kiem-tra/luot/<id>/nop/` POST | `finish_view` | — |
| `kiem-tra/luot/<id>/ket-qua/` | `result_view` | S7 |
| `kiem-tra/luot/<id>/sync/` POST JSON (tự lưu) | `sync_view` | — |
| `kiem-tra/so-cau-sai/` | `wrongbook_view` | S8 |

Mọi view dưới `luot/<id>/` kiểm tra `attempt.user == request.user` (404 nếu không).

---

## 2. Danh sách task

### T7.1 ⭐ App `exam`: model, MasterCode, admin (1 ngày)

- **Mục tiêu:** có đủ bảng và mã để các task sau dựa vào.
- **File:** `apps/exam/{models,admin,apps,constants}.py`, migration `0001_initial`,
  `config/settings/base.py` (INSTALLED_APPS), `config/urls.py`,
  `apps/core/constants.py` + `seed_mastercode.py` (code_type 20–23),
  `scripts/deploy_supabase.py` (thêm `exam` vào `LOCAL_APPS` để hậu kiểm 4 cột audit).
- **Cách làm:** theo mục 1.2–1.3. Admin: `ExamQuestion` có inline `ExamOption`, lọc theo
  `exam_set`, `section_code`, `is_active`; tìm theo `stem_jp`. `ExamAttempt` chỉ đọc.
- **Hoàn thành:** `migrate` sạch trên DB trống và trên bản sao Supabase; `seed_mastercode` idempotent.
- **Test:** `ExamOption.clean()` chặn 0 hoặc 2 phương án đúng; ràng buộc `WrongBookEntry`
  (đúng một trong question/vocabulary); mọi model có 4 cột audit.

### T7.2 ⭐ Nhập 500 câu đề (1 ngày)

- **Mục tiêu:** 5 bộ đề lên Supabase, chạy lại không nhân đôi.
- **File:** `docs/data/exam/{exam_set,exam_question,exam_option}.csv` (xuất từ `bjt.db`,
  giống cách làm `docs/data/keigo/`), `scripts/import_exam.py` (cùng khuôn với
  `scripts/import_bjt_topics.py`: dùng `_vocab_common.setup_django/act_as/DryRun`,
  mặc định chạy thử, `--apply`, một transaction), `apps/exam/management/commands/check_exam_data.py`.
- **Cách làm:**
  - Map: `exam_set` → `ExamSet.number`; `(part, section)` → `section_code`;
    `question_jp` → `stem_jp`; `choice_1..4` + `correct_choice` → 4 `ExamOption`;
    `audio_file` `mock_exam/q031_part1_sec1.mp3` → `audio_path` `exam/q031_part1_sec1.mp3`;
    `source_file` dài → `source_ref` + `ExamSet.source_note`.
  - `number` trong bộ: sắp theo `(part, section, id)` → 1..100.
  - Khoá idempotent: `source_ref`.
  - Phần Đọc dạng `short_reading` có 5 loại văn bản ghi trong `section_name_vi`
    ("— Email nội bộ"...) → đưa phần sau dấu "—" vào `passage_type` nếu `passage_type` trống.
- **`check_exam_data`** báo: câu không đủ 4 phương án / không đúng 1 đáp án; câu phần Nghe
  thiếu `audio_path`; `audio_path` không có file (khi lưu theo phương án A); mỗi bộ đủ 100 câu
  và đúng số câu từng dạng (10/10/15 · 15/15 · 15/10/10).
- **Hoàn thành:** `import_exam.py --apply` → 5 bộ × 100 câu; chạy lần 2 báo 0 thay đổi;
  `check_exam_data` không còn lỗi chặn. 75 câu `p2s2` không audio là **dữ liệu đúng**
  (đọc tài liệu), check không báo lỗi các câu này.
- **Test:** import CSV mẫu 2 câu vào DB test; chạy 2 lần cùng kết quả; câu sai định dạng bị từ chối.

### T7.3 Audio đề thi lên Supabase Storage (0,5–1 ngày)

- **File:** `apps/exam/models.py` (+ migration: `ExamQuestion.audio_version`),
  `apps/exam/audio.py` (`exam_audio_url`), `scripts/upload_exam_audio.py`,
  `config/settings/base.py` (`EXAM_AUDIO_BASE_URL`), `.env.example`, `render.yaml`.
- **Chuẩn bị (Dat làm / duyệt):** tạo bucket public `exam-audio`; điền `SUPABASE_URL` +
  `SUPABASE_SERVICE_ROLE_KEY` vào `.env` máy local; đặt `EXAM_AUDIO_BASE_URL` trên Render
  (`https://<ref>.supabase.co/storage/v1/object/public/exam-audio/`).
- **`upload_exam_audio.py <thư mục mp3>`** — cùng khuôn `scripts/import_bjt_topics.py`:
  mặc định chạy thử, `--apply` mới ghi.
  - So từng file với object đang có theo mã băm nội dung (lưu SHA-256 trong metadata của
    object): **giống -> bỏ qua; khác -> upload đè (`x-upsert: true`) + tăng `audio_version`**
    của mọi `ExamQuestion` dùng file đó; chưa có -> upload mới.
  - `Content-Type: audio/mpeg`, `Cache-Control: public, max-age=31536000` (an toàn vì URL
    đổi theo `?v=` mỗi lần ghi đè).
  - Báo cáo: mới / ghi đè / giữ nguyên / file trên bucket không còn câu nào dùng (chỉ báo,
    không tự xoá).
- **`exam_audio_url(question)`**: `""` nếu câu không có audio hoặc chưa cấu hình base URL;
  còn lại base + path + `?v=`.
- **Hoàn thành:** chạy `--apply` lần 2 báo 0 thay đổi; thay 1 file mp3 rồi chạy lại -> đúng 1
  file ghi đè, `audio_version` tăng, trình duyệt nghe bản mới ngay; phát + tua được trên
  Chrome desktop và Safari iOS từ bản deploy Render.
- **Test:** `exam_audio_url` (có / không base URL, có / không audio, đổi phiên bản -> đổi URL);
  logic so khớp của script tách thành hàm thuần (danh sách file local + danh sách object ->
  kế hoạch upload) để test không cần mạng.

### T7.4 ⭐ Bộ máy lượt làm bài (1,5 ngày)

- **Mục tiêu:** một vòng đời chung cho cả 4 loại, logic nằm ở service, view chỉ lắp context.
- **File:** `apps/exam/services/attempts.py`, `timing.py`, `apps/core/quiz.py` (chuyển từ keigo),
  `apps/keigo/exercises.py` (import lại từ core).
- **Hàm chính:**
  - `start_attempt(user, kind, mode, **opts) -> ExamAttempt` — tạo lượt + đủ dòng `ExamAnswer`
    (mock: 100 câu theo `number`; drill: 10 câu ngẫu nhiên của dạng, ưu tiên câu chưa làm;
    vocab: gọi `vocab_quiz.build`; wrongbook: lấy tối đa 10 mục đến lượt ôn).
    Đang có lượt dở **cùng loại + cùng đề** → trả lượt đó (không tạo lượt thứ hai).
  - `current_answer(attempt)` — câu chưa trả lời đầu tiên trong phần hiện tại.
  - `answer(attempt, order, selected, time_ms)` — chấm, ghi `is_correct`, cộng `score`.
    Câu đã trả lời: chế độ Luyện **không ghi đè**; chế độ Thi **được đổi** đáp án ở phần
    Đọc/Nghe+Đọc trước khi nộp phần, **không** đổi được ở phần Nghe.
  - `submit_part(attempt)` / `finish(attempt)` — đóng phần, tính điểm, gọi `hooks.on_finish`.
  - `timing.part_deadline(attempt, part)`, `timing.is_locked(attempt, order)`:
    chế độ Thi + phần 1 → câu có `order` nhỏ hơn câu hiện tại bị khoá; quá hạn phần → mọi câu
    của phần bị khoá và phần tự nộp ở request kế tiếp.
- **Bảo đảm ở server (không tin trình duyệt):** hạn giờ, khoá câu, không ghi đè đáp án,
  quyền sở hữu lượt. **Riêng "audio phát 1 lần" chỉ chặn được ở trình duyệt** (file audio
  là URL công khai) — chấp nhận, ghi rõ trong code.
- **Hoàn thành:** test service xanh; keigo không đổi hành vi.
- **Test:** tạo lượt 2 lần → 1 lượt; trả lời sau hạn → bị từ chối + phần tự nộp; phần 1
  chế độ Thi không quay lại; chế độ Luyện không ghi đè; điểm = số câu đúng; F5 sau POST
  không chấm 2 lần (PRG + unique).

### T7.5 ⭐ Kiểm tra từ vựng — S2, S3 (2,5 ngày)

- **Mục tiêu:** dùng được ngay với ~3.100 từ hiện có, không cần đề thi hay audio.
- **File:** `apps/exam/services/vocab_quiz.py`, `hooks.py`, `views.py`,
  `templates/exam/vocab_setup.html`, `play_vocab.html`, `static/js/exam_play.js`.
- **Phạm vi (S2):**
  - `due` — từ đến hạn hôm nay (dùng lại `learning.services` để lấy đúng tập SC15 đang dùng);
  - `topics` — từ **đã học** (có `UserVocabularyProgress`) trong các topic chọn;
  - `mastered` — từ `is_mastered=True`.
  Số câu 10/20/30; thiếu từ thì làm với số từ đang có (tối thiểu 4, ít hơn thì báo và không cho bắt đầu).
- **Sinh câu (`build`)** — chia đều các dạng đã chọn, mỗi từ một câu:
  - `meaning`: hiện `word` → chọn `meaning_vi`;
  - `word`: hiện `meaning_vi` → chọn `word`;
  - `reading`: hiện `word` → chọn `reading`. **Bỏ qua** từ có `word` toàn kana (hỏi cách đọc vô nghĩa);
  - `cloze`: lấy `ExampleSentence` có chứa `word`, che bằng `（　）` → chọn `word`.
    Chỉ áp dụng cho từ có câu ví dụ chứa đúng mặt chữ.
- **Đáp án nhiễu** (tối đa 3, theo thứ tự ưu tiên, không trùng nhau, không trùng đáp án đúng):
  1. `reading`: cách đọc của từ **cùng mặt chữ đầu** hoặc biến thể của chính cách đọc đúng
     (thêm/bớt っ, ー, dấu ゛, ん) — đúng kiểu bẫy BJT (けっさい / けつさい / けっざい);
  2. từ cùng topic nghiệp vụ;
  3. từ gần giống mặt chữ / cách đọc (dùng `TrigramSimilarity` sẵn có trên `word`, `reading`);
  4. ngẫu nhiên toàn kho.
  Nhiễu phải khác đáp án đúng **theo nội dung hiển thị** (hai từ khác nhau cùng nghĩa
  `meaning_vi` thì không được làm nhiễu của nhau).
- **Nối SRS (`hooks.on_vocab_answer`, ◆1)** khi `scope.srs_link` bật:
  - sai → `review_word(progress, srs.AGAIN)` (về RELEARNING, quay lại trong phiên học kế);
  - đúng **và** phạm vi `due` **và** từ đang đến hạn → `review_word(progress, srs.GOOD)`;
  - còn lại không đụng lịch ôn.
  Gọi ngay khi trả lời (không đợi nộp bài) để thoát giữa chừng vẫn tính.
  Đếm vào hạn mức ôn hôm nay giống lượt chấm flashcard (Phase 6).
- **Màn S3:** một câu/màn, chọn bằng POST (tắt JS vẫn chạy), JS thêm phím `1–4` + `Enter`,
  chấm không tải lại trang (fetch tới `play_view`, nhận JSON khi `Accept: application/json`).
  Phản hồi: đúng/sai, giải thích sinh tự động (cách đọc + nghĩa của đáp án đúng; với nhiễu
  là từ thật thì liệt kê nghĩa của chúng — như mockup câu 稟議書/資金繰り).
- **Hoàn thành:** làm trọn 20 câu với dữ liệu thật trên Supabase; câu sai xuất hiện lại ở
  lượt học kế tiếp; tắt JS vẫn làm bài được.
- **Test:** đủ số câu và đúng tỷ lệ dạng; không có câu `reading` cho từ toàn kana; nhiễu
  không trùng; kho ít từ → ít phương án hơn chứ không lỗi; `srs_link` tắt → `UserVocabularyProgress`
  không đổi; bật + sai → `card_state == relearning`.

### T7.6 ⭐ Thi thử và luyện dạng đề — S4, S5, S6 (3 ngày)

- **File:** `views.py`, `templates/exam/exam_list.html`, `play_exam.html`,
  `partials/{exam_bar,navgrid,audio,passage}.html`, `static/js/exam_play.js`.
- **S4:** chọn chế độ (Thi/Luyện); bảng 5 bộ đề với trạng thái lượt gần nhất (đang làm dở →
  "Làm tiếp"); lưới 8 dạng đề với tỷ lệ đúng của người học (`selectors.section_accuracy`, 30 ngày).
- **S5/S6 — bố cục theo dữ liệu câu:**
  - Phần Nghe có audio: khối audio + (nếu `passage_type == 場面設定`) hiện `passage_jp` làm
    đề bài; **lời thoại (`passage_jp` của câu hội thoại) ẩn** cho tới khi được xem đáp án.
  - Phần Nghe + Đọc / Đọc: `passage_jp` là tài liệu → bố cục 2 cột (tài liệu ghim trái), dưới
    720px xếp dọc.
  - Lưới số câu của phần hiện tại: đã trả lời / đang làm / cắm cờ / khoá.
- **Chế độ Thi:** đồng hồ đếm ngược theo `timing.part_deadline` (server trả số giây còn lại,
  JS chỉ hiển thị); hết giờ → JS gửi `nop-phan`, server cũng tự nộp nếu JS không chạy.
  Audio: JS ẩn nút tua, khoá nút phát sau lần phát đầu, lưu "đã phát" vào `sessionStorage`
  theo `attempt+order` (F5 không phát lại được).
- **Chế độ Luyện:** trả lời xong hiện ngay đáp án, giải thích, lời thoại; audio nghe lại tự do.
- **Tự lưu:** mỗi câu trả lời là một POST → không cần cơ chế lưu riêng. `sync_view` chỉ dùng
  cho `time_ms` và cờ khi JS bật.
- **Hoàn thành:** làm trọn một bộ đề chế độ Thi trên Render (có cold start), thoát giữa phần 2
  vào lại đúng câu, đồng hồ đúng.
- **Test (view):** người khác mở lượt → 404; GET câu bị khoá → chuyển về câu hiện tại;
  hết giờ → phần tự nộp; ẩn lời thoại ở chế độ Thi trước khi nộp (kiểm tra HTML không chứa
  `passage_jp` của câu hội thoại).

### T7.7 Kết quả — S7 (1,5 ngày)

- **File:** `selectors.py` (`attempt_breakdown`, `previous_attempt`), `templates/exam/result.html`.
- **Nội dung:** vòng % tổng (CSS `conic-gradient`, không thư viện); thanh theo phần; bảng theo
  dạng (đúng/tổng, %, thời gian TB/câu từ `time_ms`); so với lượt trước **cùng loại**;
  "Nên luyện tiếp" = dạng % thấp nhất → nút tạo lượt drill dạng đó; danh sách xem lại có
  tab Tất cả / Sai / Cắm cờ, mỗi câu: lựa chọn của bạn, đáp án, giải thích, lời thoại, audio
  (nghe lại tự do), nút báo lỗi (T7.11).
- **"Thêm từ trong câu sai vào ôn tập":** tìm `Vocabulary` có `word` xuất hiện trong
  `stem_jp`/`passage_jp`/phương án đúng của các câu sai (chỉ từ ≥ 2 ký tự, không phải toàn kana),
  hiện danh sách để người học **chọn** rồi mới thêm (không tự thêm) → tạo
  `UserVocabularyProgress` ở trạng thái `new` qua `learning.services.get_or_start_progress`.
- **Ghi chú ◆3** hiện dưới vòng điểm: không quy đổi thang 0–800.
- **Test:** breakdown đúng với lượt mẫu; lượt chưa nộp → chuyển về màn làm bài; danh sách từ
  gợi ý không chứa từ người học đã có trong SRS.

### T7.8 Sổ câu sai — S8 (1,5 ngày)

- **File:** `services/wrongbook.py`, `templates/exam/wrongbook.html`.
- **Ghi sổ:** mọi câu sai ở lượt `vocab`/`drill`/`mock` → `record_wrong` (tạo hoặc
  `wrong_count += 1`, `correct_streak = 0`, `cleared_at = None`).
  Với câu thi ở chế độ Thi: ghi khi **nộp bài** (lúc đó mới chấm cho người học thấy).
- **Ôn (`kind = wrongbook`):** lấy tối đa 10 mục còn trong sổ, ưu tiên `last_wrong_at` cũ
  nhất; câu từ vựng sinh lại theo đúng `question_type_code`. Đúng → `correct_streak += 1`
  **chỉ khi** `last_correct_on` khác hôm nay (◆4: cách ≥ 1 ngày); `correct_streak >= 2` →
  `cleared_at = now`. Sai → `correct_streak = 0`.
- **S8:** 3 số (chờ ôn / đã đúng 1 lần / đã ra khỏi sổ), tab theo loại, bảng câu, nút "Ôn 10 câu".
  Badge số câu chờ ôn ở sidebar (cache như `get_due_badge_count`).
- **Test:** sai 2 lần → 1 mục `wrong_count=2`; đúng 2 lần cùng ngày → vẫn trong sổ; đúng
  hôm nay + ngày mai → ra khỏi sổ; sai lại sau khi đã ra → quay lại sổ.

### T7.9 Tổng quan S1, điều hướng, danh hiệu (1 ngày)

- **File:** `templates/exam/hub.html`, `templates/partials/sidebar.html`, `selectors.py`,
  `apps/gamification/services.py`, `apps/learning/views.py` (thẻ trên dashboard SC03 — tuỳ chọn).
- **S1:** lượt đang dở mới nhất (chỉ mock/drill), 4 thẻ loại kiểm tra, 5 kết quả gần nhất,
  3 dạng yếu nhất 30 ngày (từ vựng tính theo `question_type_code`, đề thi theo `section_code`).
- **Sidebar:** nhóm "Kiểm tra" với 4 mục con như mockup, badge Sổ câu sai.
- **Danh hiệu (nhóm 08, `QUIZ_HIGH_SCORE_COUNT`):** đếm thêm `ExamAttempt` đã nộp có
  `score/total >= 80%` (giữ nguyên phần đếm `StudySession` quiz cũ). Lượt `wrongbook` không tính.
- **SC06 quiz cũ (`learning:quiz`)**: giữ nguyên trong Phase 7; quyết định gỡ hay chuyển
  hướng sang S2 sau khi Dat dùng thử (ghi vào checklist).
- **Test:** hub không lỗi khi chưa có lượt nào; badge danh hiệu tăng sau lượt đạt 80%.

### T7.10 Theme B/C, điện thoại, kiểm tra cuối (1 ngày)

- Dùng class sẵn có trong `static/css/base.css` + token theme; class mới (`.navgrid`,
  `.exam-bar`, `.ring`, `.doc`, `.opt.right/.wrong`) thêm vào `base.css`, giá trị khác nhau
  theo theme đặt ở `theme_{a,b,c}.css`. Không inline style (spec.md T2.2). Dark mode theo T2.3.
- Kiểm tra 8 màn × 3 theme × (desktop, 375px): không tràn ngang (bảng dài bọc `.table-wrap`
  như mockup S4), vùng bấm ≥ 44px trên điện thoại.
- Cập nhật `flowChart/js/flows.js` (luồng làm bài, nộp phần, sổ câu sai), `docs/db-schema.html`.

### T7.11 Báo lỗi câu thi (0,5 ngày)

- **File:** `apps/error_reports/models.py` (+ migration), `forms.py`, `views.py`, trang admin SC14.
- Thêm `exam_question = ForeignKey(ExamQuestion, null=True, blank=True, SET_NULL)` cạnh
  `vocabulary` (cùng lý do SET_NULL đã ghi trong model). Nút "⚑ Báo lỗi câu này" ở S3/S7
  mở form báo lỗi có sẵn, điền sẵn câu. Với câu từ vựng → điền `vocabulary` như hiện nay.
- Admin lọc được báo lỗi theo loại nội dung (từ vựng / câu thi).
- **Test:** gửi báo lỗi từ S7 → bản ghi có `exam_question`; xoá câu → báo lỗi vẫn còn.

---

## 3. Thứ tự làm và ước lượng

| Bước | Task | Ước lượng | Phụ thuộc | Bàn giao được |
|---|---|---|---|---|
| 1 | T7.1 Model + MasterCode | 1 ngày | — | |
| 2 | T7.4 Bộ máy lượt làm | 1,5 ngày | T7.1 | |
| 3 | T7.5 Kiểm tra từ vựng | 2,5 ngày | T7.4 | ✅ **Mốc 1: dùng được bài từ vựng** |
| 4 | T7.9 (phần S1 + sidebar) | 0,5 ngày | T7.5 | |
| 5 | T7.2 Nhập 500 câu | 1 ngày | T7.1 | |
| 6 | T7.3 Audio (Supabase Storage) | 0,5–1 ngày | bucket + key (mục 0.3) | |
| 7 | T7.6 Thi thử + dạng đề | 3 ngày | T7.2, T7.3, T7.4 | |
| 8 | T7.7 Kết quả | 1,5 ngày | T7.6 | ✅ **Mốc 2: thi thử trọn bộ** |
| 9 | T7.8 Sổ câu sai | 1,5 ngày | T7.5, T7.7 | |
| 10 | T7.9 (phần còn lại) + T7.11 | 1 ngày | T7.8 | |
| 11 | T7.10 Theme B/C + mobile | 1 ngày | tất cả | ✅ **Mốc 3: hoàn tất Phase 7** |

**Tổng: khoảng 15 ngày công.** T7.2 có thể làm song song với T7.4–T7.5.
Mỗi mốc: Dat chạy thử trên DB thật → duyệt → merge.

---

## 4. Rủi ro

| Rủi ro | Cách xử lý |
|---|---|
| ~400 câu đề tự soạn chưa qua người bản xứ | Nút báo lỗi ở S3/S7 (T7.11); `ExamQuestion.is_active` để tắt câu lỗi mà không xoá lịch sử |
| Cách đọc sai còn trên DB (sinh tự động lúc nhập) làm câu `reading` sai đáp án | Chạy `import_bjt_topics.py --fix-existing` đã sửa 123 từ; báo lỗi từ S3 đi thẳng vào luồng báo lỗi từ vựng có sẵn |
| Nối SRS làm tăng khối lượng ôn | Chỉ câu **sai** đẩy về học lại; tắt được ở S2; tính vào hạn mức Phase 6 |
| "Audio 1 lần" lách được (mở thẳng URL file) | Chấp nhận — app cá nhân, mục đích là luyện chứ không phải chống gian lận |
| Render free ngủ / mất kết nối giữa bài | Mỗi câu là một POST lưu ngay; hạn giờ tính ở server nên thoát ra vào lại vẫn đúng |
| Đồng hồ lệch khi máy người học sai giờ | Server trả số **giây còn lại**, JS đếm lùi từ đó, không dùng giờ máy |

---

## 5. Checklist

### Mốc 1 — Kiểm tra từ vựng (code + test xong 11/10/2026 — chờ Dat dùng thử trên DB thật)
- [x] T7.1 Model, MasterCode 20–23, admin
- [x] T7.4 Bộ máy lượt làm + `apps/core/quiz.py` (keigo vẫn xanh)
- [x] T7.5 S2, S3, nối SRS
- [x] T7.9a S1 + sidebar
- [x] Test trên PostgreSQL 16 (bản portable tạm, 11/10/2026): `apps.exam` 45/45 xanh; cả dự án
      chỉ còn 2 test `admin_panel` đỏ — đỏ SẴN trên `main` (đếm cứng 19 bảng, keigo đã thêm 12), không liên quan mốc 1
- [x] Chạy thật trên trình duyệt (runserver + DB tạm, dữ liệu mẫu 1.018 từ): làm trọn 10 câu bằng bàn phím,
      chấm không tải lại trang, nộp bài, kiểm DB: điểm, StudySession quiz, 7 từ sai -> relearning + sổ câu sai
- [ ] Dat dùng thử trên DB thật

#### Ghi chú khi code mốc 1 (11/10/2026) — để đối chiếu khi review
- **Danh hiệu "Kiểm tra" không cần sửa gamification:** nộp bài ghi một
  `StudySession(session_type="quiz")` (cách bài tập kính ngữ ghi kiểu `keigo`), nên
  streak, biểu đồ lịch sử và metric `QUIZ_HIGH_SCORE_COUNT` tự tính. T7.9b chỉ còn
  phần "dạng yếu" cho đề thi (mốc 2).
- **Sổ câu sai ghi từ mốc 1:** câu sai ở bài từ vựng đã ghi `WrongBookEntry` để lúc
  làm S8 (mốc 3) có sẵn dữ liệu thật. Thẻ "Sổ câu sai" ở S1 đã hiện số câu.
- **Phạm vi "từ đến hạn"** dùng đúng định nghĩa nợ ôn của `learning.services.count_backlog()`
  (từ ôn đến hạn + từ dở bước học), không lấy từ đang trong bước học 1–10 phút.
- **Tạo bài khi đang có bài dở** → đưa về bài dở + thông báo; S2 có nút "Bỏ bài này".
- **Đã kiểm tra:** 18 test thuần (biến thể cách đọc, ghép đáp án, chia dạng, hạn giờ,
  khoá câu) chạy xanh; bộ sinh câu chạy thử trên dữ liệu thật Supabase (chỉ đọc,
  12 câu / 0,67 giây); 4 template render với 3 theme, 375px không tràn ngang.
  Chạy test có DB tìm ra 1 lỗi: `select_for_update()` + `select_related("question")` bị PostgreSQL
  từ chối (FOR UPDATE trên phía nullable của LEFT JOIN) -> sửa bằng `of=("self",)`.
- **Dùng thật tìm ra 2 điểm, đã sửa:** nút "Kiểm tra" không ẩn khi có JS (`.btn` thắng `[hidden]`
  -> thêm `.ex-play [hidden]`); ô gộp nhiều dạng (`方針=方策=政策`, `A・B`, `A、B`) chỉ hỏi
  nghĩa / chọn từ, không hỏi cách đọc hay điền câu.

### Mốc 2 — Thi thử
- [x] Chốt nơi lưu audio (mục 0.3) — B. Supabase Storage, bucket public + `?v=` (11/10/2026)
- [ ] T7.2 Nhập 500 câu + `check_exam_data`
- [ ] T7.3 Audio
- [ ] T7.6 S4, S5, S6
- [ ] T7.7 S7
- [ ] Dat thi thử trọn 1 bộ đề, chỉnh `PART_MINUTES`

### Mốc 3 — Hoàn tất
- [ ] T7.8 Sổ câu sai
- [ ] T7.9b Danh hiệu + dạng yếu
- [ ] T7.11 Báo lỗi câu thi
- [ ] T7.10 Theme B/C, mobile, flows.js, db-schema
- [ ] Quyết định số phận SC06 quiz cũ
