# Ghi chú thay đổi theo yêu cầu (vòng cập nhật gần nhất)

## 1. Bỏ chức năng nghe phát âm (đọc từ)
- Đã xóa nút "🔊 Nghe phát âm" khỏi màn hình Flashcard (SC04) ở cả 3 style.
- Không cần thiết kế audio player / TTS trong scope hiện tại.

## 2. Style có thể chọn trong Cài đặt
- Thêm màn hình mới **SC08_CaiDat** (Cài đặt): user chọn 1 trong 3 style (A/B/C) bằng cách bấm vào thẻ preview màu.
- Toàn bộ token thiết kế của 3 style được ghi lại trong file **STYLE_GUIDE.md** — dùng file này làm nguồn tham chiếu khi phát triển màn hình mới, để đảm bảo đồng bộ giao diện.
- Gợi ý schema: bảng `users` cần thêm cột `ui_theme` (enum: `A`, `B`, `C`, mặc định `A`).

## 3. Trang hồ sơ cá nhân riêng
- Thêm màn hình mới **SC09_ThongTinCaNhan**: hiển thị avatar, tên, email, ngày tham gia, thống kê học tập (số từ đã thuộc, streak, trình độ hiện tại), thông tin tài khoản có thể chỉnh sửa, và danh sách chủ đề đã học gần đây.

## 4. Audit columns cho toàn bộ table
- Mọi bảng trong DB (users, vocabularies, topics, vocabulary_topics, example_sentences, user_vocabulary_progress, study_sessions, user_wordlists, v.v.) sẽ có thêm 4 cột chuẩn để audit:
  - `created_by` (FK tới users, nullable — hệ thống tự tạo thì để null hoặc "system")
  - `created_at` (datetime, auto_now_add)
  - `updated_by` (FK tới users, nullable)
  - `updated_at` (datetime, auto_now)
- Khi lên Django: tạo 1 `abstract base model` (ví dụ `AuditableModel`) chứa 4 field này, mọi model khác kế thừa từ đó để tránh lặp code.
  ```python
  class AuditableModel(models.Model):
      created_by = models.ForeignKey("accounts.User", null=True, blank=True,
                                      related_name="+", on_delete=models.SET_NULL)
      created_at = models.DateTimeField(auto_now_add=True)
      updated_by = models.ForeignKey("accounts.User", null=True, blank=True,
                                      related_name="+", on_delete=models.SET_NULL)
      updated_at = models.DateTimeField(auto_now=True)

      class Meta:
          abstract = True
  ```
- `created_by` / `updated_by` nên được set tự động trong `save()` override hoặc middleware lấy `request.user` (cần truyền context qua form/serializer khi save).

## 5. Đổi trọng tâm từ JLPT sang BJT
- Toàn bộ nhãn cấp độ trên các màn hình đã đổi từ N5–N1 (JLPT) sang **J5–J1 (BJT — Business Japanese Proficiency Test)**.
- Các vị trí đã cập nhật: SC02 (chọn trình độ khi đăng ký), SC03 (dashboard — chủ đề gợi ý), SC05 (bộ lọc cấp độ), SC07 (bảng quản trị user), SC08/SC09 (trình độ mục tiêu).
- Gợi ý schema: cột `jlpt_level` trong bảng `vocabularies`/`users` nên đổi tên thành `bjt_level` (hoặc dùng tên trung lập hơn như `level`, giá trị enum `J5, J4, J3, J2, J1, J1+`).
- Lưu ý nghiệp vụ: thang điểm BJT thật ra chấm theo điểm số 0–800 (không phải hệ N như JLPT); các mức J5→J1+ ở đây dùng làm nhãn phân loại nội dung học cho đơn giản, không phải điểm thi chính thức. Cần xác nhận lại với đội nghiệp vụ nếu muốn bám sát thang điểm BJT thật khi lên sản phẩm chính thức.

## 6. Tính năng mới: Tạo PDF luyện viết
- Thêm màn hình mới **SC10_LuyenVietPdf**: cho phép user chọn nhiều từ vựng (checkbox), tùy chỉnh số dòng luyện viết/từ, bật/tắt chữ mờ để đồ theo và hiển thị cách đọc/nghĩa, sau đó tạo & tải file PDF.
- Đã tạo **file PDF mẫu thật** (`mau_luyen_viet.pdf`) minh họa định dạng: mỗi từ có 1 dòng tiêu đề (kanji/kana, cách đọc, nghĩa) + các hàng ô vuông kiểu genkoyoshi, ô đầu tiên có chữ mờ để đồ theo.
- Gợi ý kỹ thuật khi lên Django: dùng `reportlab` (Python) để generate PDF server-side, tương tự script mẫu; font tiếng Nhật nên render bằng ảnh (Pillow + freetype) hoặc dùng font TTF thuần glyf (không phải CFF/OpenType) để tương thích trực tiếp với reportlab's `TTFont`.
- Cân nhắc thêm bảng `practice_sheets` (user_id, vocab_ids (JSON/M2M), created_at) để lưu lịch sử các phiếu đã tạo, cho phép user tải lại sau này.
