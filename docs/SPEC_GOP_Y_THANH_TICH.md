# Spec — Hệ thống Góp ý & Thành tích (Contribution & Gamification)

Tài liệu thiết kế cho tính năng mới: người dùng góp ý từ mới / sửa nghĩa / bình luận dưới từ
vựng, admin duyệt qua hòm thư góp ý, hệ thống tính điểm + gán danh hiệu cho người đóng góp
nhiều. Viết theo đúng format `CHANGELOG_YEU_CAU.md` để tham chiếu khi lên Django.

**Trạng thái:** Bản nháp — các con số điểm thưởng và tên danh hiệu ở mục 4, 5 là **đề xuất**,
cần bạn duyệt/chỉnh trước khi code Python. Phần thiết kế bảng/luồng nghiệp vụ đã tương đối chắc,
ít thay đổi hơn.

---

## 1. Tổng quan tính năng

Từ 6 gạch đầu dòng ý tưởng ban đầu, gom thành 3 khối:

1. **Góp ý nội dung** — user đề xuất từ mới, hoặc sửa nghĩa/cách dùng của từ đã có, hoặc viết
   bình luận bổ sung nghĩa/cách dùng ngay dưới màn hình học từ vựng.
2. **Kiểm duyệt** — mọi góp ý (từ mới / sửa nghĩa / bình luận) đều vào chung 1 "hòm thư góp ý"
   để admin đọc, duyệt hoặc từ chối, và phản hồi lại cho người gửi.
3. **Gamification** — góp ý được duyệt sẽ cộng điểm cho user; điểm tích lũy quyết định danh
   hiệu (badge) hiển thị trên hồ sơ.

Toàn bộ các bảng mã (loại góp ý, trạng thái, danh hiệu, loại hành động tính điểm) đều quản lý
tập trung qua bảng dùng chung **MasterCode**, theo đúng yêu cầu của bạn — không tạo `choices`
rải rác trong từng model nữa.

---

## 2. Bảng MasterCode

### 2.1 Cấu trúc bảng

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `code_type` | varchar(10) | Nhóm code, ví dụ `"01"` = Danh hiệu |
| `code` | varchar(10) | Mã trong nhóm đó, ví dụ `"001"` |
| `code_name` | varchar(150) | Tên hiển thị, ví dụ `"Tân Binh"` |
| `mother_code` | varchar(10), null | Mã cha **trong cùng `code_type`** — null = cấp cao nhất |
| `description` | varchar(255), blank | Mô tả thêm (tuỳ chọn) |
| `sort_order` | int, default 0 | Thứ tự hiển thị trong nhóm |
| `is_active` | boolean, default true | Ẩn/hiện mà không cần xoá dữ liệu |
| `created_by/at`, `updated_by/at` | — | Kế thừa `AuditableModel` như mọi bảng khác |

Khoá duy nhất: `(code_type, code)`. Đúng ví dụ bạn đưa ra:
`code_type="01", code="001", mother_code=null, code_name="Tân Binh"`.

`mother_code` dùng khi 1 nhóm code cần phân cấp — ví dụ nhóm **Trạng thái góp ý** có thể có
code cha `"DA_XU_LY"` gom 2 code con `"DA_DUYET"` và `"TU_CHOI"`, phục vụ lọc/báo cáo sau này
mà không phải sửa code hiện có.

### 2.2 Danh sách `code_type` dùng cho tính năng này

| code_type | Ý nghĩa |
|---|---|
| `01` | Danh hiệu (Badge) |
| `02` | Loại góp ý (Contribution type) |
| `03` | Trạng thái góp ý (Contribution status) |
| `04` | Loại hành động tính điểm (Point action) |

> Gợi ý (không bắt buộc làm ngay): sau này có thể chuyển luôn `BJT_LEVEL_CHOICES`
> (`apps/core/constants.py`) và `UI_THEME_CHOICES` vào MasterCode (`code_type = "05"`,
> `"06"`) để toàn bộ mã trong hệ thống nằm 1 chỗ. Không đổi ngay để tránh phá vỡ code đang
> chạy tốt của SC08/SC09.

### 2.3 Seed data đề xuất

**`code_type = "01"` — Danh hiệu** (xem mục 5 để biết ngưỡng điểm)

| code | code_name | mother_code |
|---|---|---|
| 001 | Tân Binh | null |
| 002 | Tích Cực | null |
| 003 | Chuyên Gia | null |
| 004 | Cố Vấn | null |
| 005 | Huyền Thoại | null |

**`code_type = "02"` — Loại góp ý**

| code | code_name | mother_code |
|---|---|---|
| 001 | Từ mới | null |
| 002 | Sửa nghĩa / cách dùng | null |
| 003 | Bình luận từ vựng | null |

**`code_type = "03"` — Trạng thái góp ý**

| code | code_name | mother_code |
|---|---|---|
| 001 | Chờ duyệt | null |
| 002 | Đã duyệt | null |
| 003 | Từ chối | null |

**`code_type = "04"` — Hành động tính điểm** (xem mục 4 để biết số điểm)

| code | code_name | mother_code |
|---|---|---|
| 001 | Gửi góp ý từ mới | null |
| 002 | Từ mới được duyệt | null |
| 003 | Gửi sửa nghĩa/cách dùng | null |
| 004 | Sửa nghĩa được duyệt | null |
| 005 | Bình luận được duyệt | null |

### 2.4 Helper dùng chung (thiết kế, code Python làm ở bước sau)

```python
# apps/core/utils.py
def get_code_name(code_type: str, code: str) -> str:
    """Tra code_name từ MasterCode, có cache (vd. Django cache, TTL vài phút),
    invalidate cache trong MasterCode.save()/delete(). Trả '' nếu không tìm thấy
    thay vì raise, để UI không vỡ khi thiếu seed data."""
```

Template filter tương ứng (`{{ contribution.status_code|code_name:"03" }}`) để dùng trực tiếp
trong HTML, tránh phải join thủ công mỗi nơi.

---

## 3. Model `Contribution` (góp ý)

Gộp cả 3 loại góp ý (từ mới / sửa nghĩa / bình luận) vào **1 bảng duy nhất**, phân biệt bằng
`contribution_type` — vì cả 3 đều đi qua chung 1 luồng duyệt và chung 1 hòm thư, tách 3 bảng sẽ
phải viết 3 lần logic hòm thư giống hệt nhau.

```python
class Contribution(AuditableModel):
    user = models.ForeignKey(User, related_name="contributions", on_delete=models.CASCADE)

    contribution_type_code = models.CharField(max_length=10)  # MasterCode code_type="02"
    status_code = models.CharField(max_length=10, default="001")  # MasterCode code_type="03"

    # Dùng cho "Sửa nghĩa" và "Bình luận" — từ đang được góp ý.
    # Để trống với "Từ mới" (chưa tồn tại trong hệ thống).
    target_vocabulary = models.ForeignKey(
        Vocabulary, null=True, blank=True, related_name="contributions", on_delete=models.CASCADE
    )

    # Dùng cho "Từ mới" / "Sửa nghĩa": nội dung đề xuất.
    proposed_word = models.CharField(max_length=100, blank=True)
    proposed_reading = models.CharField(max_length=150, blank=True)
    proposed_meaning_vi = models.CharField(max_length=255, blank=True)
    proposed_bjt_level = models.CharField(max_length=3, blank=True)
    proposed_topic = models.ForeignKey(Topic, null=True, blank=True, on_delete=models.SET_NULL)

    # Dùng cho "Bình luận": nội dung hiển thị công khai dưới từ vựng sau khi duyệt.
    comment_text = models.TextField(blank=True)

    # Phần admin xử lý
    reviewed_by = models.ForeignKey(User, null=True, blank=True, related_name="+", on_delete=models.SET_NULL)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_response = models.TextField(blank=True)  # phản hồi cho user, hiện ở "Góp ý của tôi"
    points_awarded = models.PositiveIntegerField(default=0)  # ghi lại số điểm đã cộng, để đối chiếu

    class Meta:
        indexes = [
            models.Index(fields=["status_code"]),
            models.Index(fields=["contribution_type_code", "target_vocabulary"]),
        ]
        ordering = ["-created_at"]
```

### 3.1 Luồng trạng thái

```
Chờ duyệt (001) --admin duyệt--> Đã duyệt (002) --> cộng điểm, cập nhật badge, gửi phản hồi
                --admin từ chối--> Từ chối (003) --> gửi phản hồi (không cộng điểm)
```

- **Từ mới được duyệt**: admin tick "duyệt" → hệ thống tạo bản ghi `Vocabulary` mới từ
  `proposed_word/reading/meaning_vi/bjt_level` (admin có thể sửa lại trước khi lưu, xem SC12).
- **Sửa nghĩa được duyệt**: admin duyệt → hệ thống cập nhật trực tiếp field tương ứng trên
  `target_vocabulary` (chỉ overwrite field có giá trị đề xuất, không đụng field khác).
- **Bình luận được duyệt**: không sửa `Vocabulary`, chỉ đổi `status_code` → comment bắt đầu
  hiển thị công khai. Vì vậy truy vấn "danh sách comment dưới 1 từ" luôn là:
  `Contribution.objects.filter(contribution_type_code="003", target_vocabulary=vocab, status_code="002")`.
- **Từ chối**: bắt buộc admin nhập `admin_response` (lý do), không cộng điểm, không có "trừ
  điểm" (tránh làm nản người mới góp ý — có thể bật lại sau nếu phát sinh spam).

### 3.2 Vì sao bình luận cũng phải qua duyệt

Yêu cầu gốc ghi "comment sẽ hiển thị trực tiếp dưới phần học từ vựng" — đây là hiểu về **vị
trí hiển thị** (ngay dưới flashcard/chi tiết từ), không phải "hiện ngay lập tức không qua
kiểm duyệt". Gộp chung luồng duyệt với 2 loại góp ý kia để: (1) admin chỉ cần 1 hòm thư duy
nhất thay vì 2 nơi, (2) tránh nội dung sai/spam hiển thị công khai ngay trong app học tiếng
Nhật. Nếu bạn muốn bình luận hiện ngay không cần duyệt, chỉ cần đổi `status_code` mặc định khi
tạo thành `"002"` (Đã duyệt) — phần model/luồng còn lại giữ nguyên.

---

## 4. Điểm thưởng (đề xuất — cần bạn duyệt số)

```python
class PointRule(AuditableModel):
    action_code = models.CharField(max_length=10, unique=True)  # MasterCode code_type="04"
    points = models.IntegerField()
```

| action_code | Hành động | Điểm đề xuất | Lý do |
|---|---|---|---|
| 001 | Gửi góp ý từ mới | +1 | Khuyến khích gửi, không quá cao để tránh spam số lượng |
| 002 | Từ mới được duyệt & thêm vào hệ thống | +10 | Giá trị nội dung cao nhất — tạo ra từ mới thật sự |
| 003 | Gửi sửa nghĩa/cách dùng | +1 | Tương tự (001) |
| 004 | Sửa nghĩa được duyệt | +5 | Cải thiện nội dung có sẵn, giá trị thấp hơn tạo mới |
| 005 | Bình luận được duyệt | +2 | Đóng góp nhẹ, tần suất cao hơn nên điểm thấp hơn |

Ghi log mỗi lần cộng điểm để audit và hiển thị lịch sử ở SC13:

```python
class UserPointTransaction(AuditableModel):
    user = models.ForeignKey(User, related_name="point_transactions", on_delete=models.CASCADE)
    action_code = models.CharField(max_length=10)  # MasterCode code_type="04"
    points = models.IntegerField()
    contribution = models.ForeignKey(Contribution, null=True, blank=True, on_delete=models.SET_NULL)
```

`User.total_points` (thêm field mới trong `apps/accounts/models.py`) = tổng `points` của toàn
bộ transaction, cập nhật (denormalize) ngay trong `save()` của `UserPointTransaction` hoặc qua
signal, để không phải `SUM()` mỗi lần hiển thị điểm ở navbar/profile.

---

## 5. Danh hiệu — Badge (đề xuất — cần bạn duyệt tên & ngưỡng)

```python
class BadgeTier(AuditableModel):
    code = models.CharField(max_length=10, unique=True)  # khớp MasterCode code_type="01"
    min_points = models.PositiveIntegerField()
    icon_emoji = models.CharField(max_length=8, blank=True)

    class Meta:
        ordering = ["min_points"]
```

| code | Danh hiệu | Điểm tối thiểu | Icon đề xuất |
|---|---|---|---|
| 001 | Tân Binh | 0 | 🌱 |
| 002 | Tích Cực | 50 | 🌿 |
| 003 | Chuyên Gia | 200 | 🌟 |
| 004 | Cố Vấn | 500 | 🏆 |
| 005 | Huyền Thoại | 1000 | 👑 |

Badge hiện tại của user = `BadgeTier` có `min_points` lớn nhất mà `min_points <= user.total_points`
— tính lại và lưu cache vào `User.current_badge_code` mỗi khi `total_points` đổi, để hiển thị
nhanh ở navbar mà không phải query lại `BadgeTier` mỗi request.

---

## 6. Luồng nghiệp vụ tổng thể

```
[User] mở SC11 (Góp ý) hoặc bấm "💬 Góp ý / Bình luận" dưới SC04 (Flashcard)
   │
   ▼
Tạo Contribution (status = Chờ duyệt) ── (+1đ nếu là từ mới/sửa nghĩa, xem mục 4)
   │
   ▼
[Admin] mở SC12 (Hòm thư góp ý) — lọc theo loại / trạng thái / từ
   │
   ├── Duyệt ──► cập nhật Vocabulary (nếu là từ mới/sửa nghĩa)
   │             cộng điểm theo PointRule tương ứng
   │             cập nhật User.total_points + current_badge_code
   │             ghi admin_response, gửi phản hồi cho user
   │
   └── Từ chối ─► ghi admin_response (bắt buộc), không cộng điểm, gửi phản hồi cho user

[User] xem lại trạng thái + phản hồi ở SC11 tab "Góp ý của tôi", xem điểm/danh hiệu ở SC13.
Bình luận đã duyệt hiện công khai ngay dưới SC04 cho mọi user khác xem.
```

---

## 7. Màn hình liên quan

| Màn hình | Nội dung | Trạng thái |
|---|---|---|
| **SC04_HocTuVung** | Thêm khối "💬 Góp ý / Bình luận" bên dưới flashcard: nút mở nhanh form sửa nghĩa cho từ đang học, và danh sách bình luận đã duyệt của từ đó. | Đã cập nhật mockup style A |
| **SC11_GopYTuVung** (mới) | Form góp ý — chọn loại (Từ mới / Sửa nghĩa / Bình luận), nhập nội dung; có tab "Góp ý của tôi" xem lịch sử + phản hồi admin. | Mockup mới, style A |
| **SC12_HopThuGopY** (mới) | Màn hình admin — danh sách góp ý theo trạng thái, xem chi tiết, duyệt/từ chối kèm phản hồi. Nằm trong `admin-layout` giống SC07. | Mockup mới, style A |
| **SC13_ThanhTich** (mới) | Điểm, danh hiệu hiện tại, thanh tiến độ tới danh hiệu kế tiếp, lịch sử điểm, bảng xếp hạng top người đóng góp. | Mockup mới, style A |

Style B/C cho 3 màn hình mới + phần cập nhật SC04 sẽ làm sau khi bạn duyệt nội dung/luồng ở
style A, để tránh phải sửa lại cả 3 style nếu có thay đổi.

---

## 8. Việc cần bạn xác nhận trước khi code Python

- [ ] Số điểm ở mục 4 và ngưỡng danh hiệu ở mục 5 — dùng số đề xuất hay đổi lại?
- [ ] Tên 5 danh hiệu có cần đổi không (ví dụ đặt tên gắn với BJT level thay vì số điểm)?
- [ ] Bình luận có cần qua duyệt như đề xuất ở mục 3.2, hay muốn hiện ngay lập tức?
- [ ] Góp ý bị từ chối có cần cho user gửi lại (sửa nội dung rồi resubmit) hay tạo góp ý mới?
- [ ] Admin nào được quyền duyệt — mọi user `is_staff`, hay cần thêm quyền riêng (ví dụ
      `can_review_contributions`) tách biệt với admin kỹ thuật?

---

## 9. Cập nhật vòng 2 — hết hardcode, nhiều nhóm danh hiệu, tuỳ chỉnh ghim

**Đã lên code thật** (không còn chỉ là spec) cho phần này — xem
`apps/core/mastercode.py`, `apps/core/models.py` (MasterCode),
`apps/gamification/models.py`, `apps/gamification/services.py`,
`apps/core/management/commands/seed_mastercode.py`,
`apps/gamification/management/commands/seed_gamification.py`.

### 9.1 Hết hardcode — MasterCode helper (`apps/core/mastercode.py`)

Toàn bộ nơi trước đây định nghĩa `choices=[...]` cứng (bao gồm cả
`BJT_LEVEL_CHOICES`, `UI_THEME_CHOICES` trong `apps/core/constants.py` mà
trước đó ghi chú "gợi ý migrate sau") nay đã chuyển hẳn sang MasterCode:

- `apps/core/mastercode.py` — 5 hàm dùng chung, có cache (Django cache
  framework, TTL 5 phút, tự xoá khi MasterCode thay đổi qua signal ở
  `apps/core/signals.py`):
  - `get_code_name(code_type, code)` — mã → tên.
  - `get_code_by_name(code_type, code_name)` — chiều ngược, tên → mã.
  - `get_choices(code_type)` — trả `[(code, name), ...]` dùng thẳng làm
    `choices=` (Django CharField chấp nhận `choices` là callable, nên field
    vẫn khai báo bình thường: `choices=bjt_level_choices` — không có `()`).
  - `get_children(code_type, mother_code)` — lấy code con (phân cấp qua
    `mother_code`).
  - `invalidate_cache(...)` — gọi tự động qua signal, hiếm khi cần gọi tay.
- `apps/core/constants.py` — chỉ còn giữ **hằng số `CODE_TYPE_*`** (vd
  `CODE_TYPE_BJT_LEVEL = "05"`) để không rải magic string, KHÔNG còn danh
  sách `choices` cứng nào.
- `apps/core/management/commands/seed_mastercode.py` — nguồn seed DUY NHẤT
  cho tên hiển thị của mọi code_type (BJT level, theme, loại/trạng thái góp
  ý, hành động tính điểm, tên từng bậc của cả 3 nhóm danh hiệu). Chạy
  `python manage.py seed_mastercode` sau `migrate`. Idempotent — sửa tên gì
  trong `SEED_DATA` rồi chạy lại là cập nhật, không tạo trùng.

**Lưu ý về giới hạn thực tế**: `BadgeCategory.metric` (mục 9.2) và
`Contribution.contribution_type_code` dùng làm khoá rẽ nhánh code (mục 3) là
2 chỗ CÒN choices Python cố định — vì đây là lựa chọn kỹ thuật quyết định
CHẠY HÀM NÀO, không phải dữ liệu hiển thị đơn thuần. Thêm 1 "loại" mới ở đây
luôn cần thêm code tính toán tương ứng (vd metric mới = phải viết hàm đếm
mới trong `services.get_metric_value`), nên không thể chỉ thêm data mà tự
chạy được — khác với tên hiển thị hay ngưỡng số (thuần data, sửa xong dùng
ngay không cần đụng code).

### 9.2 Nhiều nhóm danh hiệu — mỗi nhóm 1 `code_type` riêng

Theo đúng yêu cầu "badge riêng nằm ở codeType riêng": danh hiệu không còn
chỉ tính theo điểm đóng góp, mà mở rộng thành nhiều **BadgeCategory** độc
lập, mỗi category ứng với 1 `code_type` riêng trong MasterCode:

| code_type | BadgeCategory | Đại lượng xét bậc (`metric`) | Bậc đề xuất (seed) |
|---|---|---|---|
| `01` | Đóng góp cộng đồng 🌟 | Tổng điểm đóng góp | Tân Binh(0) → Tích Cực(50) → Chuyên Gia(200) → Cố Vấn(500) → Huyền Thoại(1000) |
| `07` | Học tập 📚 | Số từ đã học thuộc (`is_mastered=True`) | Người Mới Học(50) → Chăm Chỉ(200) → Ham Học Hỏi(500) → Học Giả(1000) → Bậc Thầy Từ Vựng(2000) |
| `08` | Kiểm tra 🎯 | Số bài kiểm tra đạt ≥80% câu đúng | Khởi Động(1) → Tay Vững(10) → Thiện Xạ(30) → Bất Bại(50) |

Cấu trúc: `BadgeCategory` (1 nhóm, biết tính theo đại lượng gì) —
`BadgeTier` (các bậc trong nhóm đó, `code` khớp với MasterCode ở
`code_type = category.code_type`, `min_value` là ngưỡng số). Tên bậc lấy từ
MasterCode qua `category.tier_name(code)`, ngưỡng số lấy từ `BadgeTier` —
tách 2 nơi vì tên là "hiển thị" (MasterCode) còn ngưỡng là "quy tắc nghiệp
vụ" (bảng riêng, không lẫn vào bảng mã dùng chung).

**Thêm 1 nhóm danh hiệu mới** (vd "Chuyên cần" theo số ngày streak) chỉ cần:
1. Thêm `CODE_TYPE_BADGE_STREAK = "09"` vào `apps/core/constants.py`.
2. Seed tên các bậc vào `SEED_DATA[CODE_TYPE_BADGE_STREAK]` trong
   `seed_mastercode.py`.
3. Thêm 1 metric mới (`METRIC_STREAK_DAYS`) + hàm tính trong
   `services.get_metric_value` — **đây là chỗ duy nhất cần viết code**, vì
   phải biết cách đếm streak từ `StudySession`.
4. Thêm entry vào `BADGE_CATEGORY_SEED` trong `seed_gamification.py` (tên,
   metric, icon, danh sách ngưỡng).

Không cần sửa model, admin, hay view nào khác — `BadgeCategory`/`BadgeTier`
đã generic sẵn.

### 9.3 Tuỳ chỉnh — user tự ghim danh hiệu muốn hiển thị

`UserPinnedBadge` (`apps/gamification/models.py`) + service tương ứng trong
`apps/gamification/services.py`:

- `pin_badge(user, category)` — ghim 1 category. Validate: (1) user phải đã
  đạt ≥1 bậc ở category đó (không cho ghim danh hiệu chưa đạt), (2) tối đa
  `MAX_PINNED_BADGES = 3` danh hiệu cùng lúc.
- `unpin_badge(user, category)` — bỏ ghim.
- `get_display_badge(user)` — danh hiệu hiển thị nổi bật ở navbar/hồ sơ: ưu
  tiên danh hiệu đã ghim (`display_order` thấp nhất), fallback về nhóm
  "Đóng góp cộng đồng" nếu user chưa ghim gì — đảm bảo luôn có gì đó để
  hiển thị, không bao giờ trống.

Ở màn hình (SC13, style A — B/C làm sau khi bạn duyệt), phần này sẽ thể
hiện thành: mỗi BadgeCategory hiển thị như 1 khối card riêng (bậc hiện tại +
progress bar tới bậc kế), kèm nút "📌 Ghim danh hiệu này" / "Bỏ ghim" trên
từng khối — người dùng chọn tối đa 3 khối để hiện icon ở navbar thay vì hệ
thống tự chọn theo điểm đóng góp như bản trước.

### 9.4 Việc cần bạn xác nhận thêm

- [ ] 3 nhóm danh hiệu (Đóng góp / Học tập / Kiểm tra) đã đủ chưa, hay cần
      thêm nhóm nào khác ngay từ đầu (vd "Chuyên cần" theo streak)?
- [ ] Ngưỡng "đạt điểm cao" cho nhóm Kiểm tra — đề xuất tạm là ≥80% câu
      đúng/bài, đúng ý bạn chưa hay cần % khác / theo cấp độ BJT của bài?
- [ ] `MAX_PINNED_BADGES = 3` có hợp lý không, hay muốn cho ghim nhiều/ít
      hơn?
- [ ] Có cần cho phép admin tạo BadgeCategory mới ngay từ trang admin (tự
      chọn metric có sẵn), hay chỉ dev thêm qua code như mục 9.2 là đủ ở
      giai đoạn này?

---

## 10. Cập nhật vòng 3 — `label.properties` / `message.properties`

Bổ sung thêm 1 tầng "không hardcode" nữa, tách biệt với MasterCode (mục 9):

| | MasterCode | label / message.properties |
|---|---|---|
| Dùng cho | Dữ liệu MÃ hoá gắn với business logic (cấp độ BJT, trạng thái góp ý, tên bậc danh hiệu...) — có `code` để lưu trong DB, so sánh, rẽ nhánh | Chuỗi hiển thị THUẦN TUÝ — nút bấm, tiêu đề, tên field, thông báo lỗi/thành công — không có khái niệm "mã", chỉ có key -> text |
| Lưu ở đâu | Bảng `MasterCode` trong DB | File `.properties` trên đĩa, đọc lúc chạy |
| Sửa bằng | Trang admin (`/admin/core/mastercode/`) hoặc sửa `SEED_DATA` rồi chạy lại seed | Sửa trực tiếp file rồi `python manage.py reload_properties` |
| Ví dụ | `code_type="03", code="002"` -> "Đã duyệt" (dùng để so sánh `if status_code == "002"`) | `contribution.inbox.button.approve_and_add` -> "Duyệt & thêm vào hệ thống" (chỉ để hiển thị, không so sánh) |

Nói cách khác: **tên 1 trạng thái dùng để hiển thị TAG màu trên UI** vẫn có
thể trùng chữ với **label 1 cái nút**, nhưng chúng đi qua 2 hệ khác nhau vì
mục đích khác nhau — trạng thái là dữ liệu nghiệp vụ (đổi được qua thời
gian, gắn với logic), còn label/message thuần là câu chữ (đổi tuỳ ý, không
ảnh hưởng logic, tiện cho việc sau này dịch đa ngôn ngữ nếu cần).

### 10.1 File đã tạo

- **`label.properties`** (project root) — 163 key, chia theo scope `common`
  (dùng chung: nav, nút, field, tag trạng thái...) và scope riêng theo từng
  feature (`accounts`, `vocabulary`, `learning`, `practice_sheets`,
  `contribution`, `badge`, `admin`). Quy ước đặt key ghi ngay đầu file.
- **`message.properties`** (project root) — 35 key: lỗi validate dùng chung
  (`common.validation.*`), lỗi/thành công riêng từng feature. Hỗ trợ
  placeholder `{ten_bien}` (str.format), vd
  `contribution.approve.success = "Đã duyệt góp ý và cộng {points} điểm..."`.
- **`apps/core/properties.py`** — loader, có cache (giống mastercode.py):
  `label(key)`, `message(key, **kwargs)`, `reload_cache()`.
- **`apps/core/templatetags/properties_tags.py`** — tag `{% label %}` /
  `{% message %}` dùng trong template.
- **`apps/core/management/commands/reload_properties.py`** — xoá cache sau
  khi sửa tay 2 file trên server đang chạy.

### 10.2 Việc cần bạn xác nhận thêm

- [ ] 163 label / 35 message hiện đã bao phủ hết các màn hình mockup
      (SC01-SC13) chưa, hay có màn/nút nào bạn thấy thiếu thì báo để bổ
      sung trước khi bắt đầu code view thật?
- [ ] Các bản mockup style B/C hiện có vài chỗ diễn đạt "vui vẻ" hơn style A
      (thêm emoji, câu chữ khác 1 chút, vd style C ghi "Xin chào, Admin 👋"
      thay vì "Xin chào, Admin") — 2 file `.properties` này đang dùng
      **1 bản text DUY NHẤT cho cả 3 theme** (icon/emoji trang trí để CSS lo,
      không trộn vào text). Bạn có đồng ý thống nhất 1 bản text như vậy, hay
      muốn giữ khác biệt giọng văn theo từng theme (sẽ cần key riêng theo
      theme, phức tạp hơn)?

