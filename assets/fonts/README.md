# assets/fonts

Nơi đặt font cho tính năng **SC10 — PDF luyện viết** khi máy chủ không cài sẵn
font hệ thống (đúng trường hợp Render: ảnh chạy không có `fonts-dejavu` lẫn
`fonts-noto-cjk`, và gói free không cho `apt install`).

`apps/practice_sheets/pdf_generator.py` dò theo thứ tự:

1. Biến môi trường `PRACTICE_SHEET_FONT_DIR` (tiếng Việt) /
   `PRACTICE_SHEET_JP_FONT` (tiếng Nhật)
2. **Thư mục này**
3. Đường dẫn font hệ thống (Debian/Ubuntu, Fedora, Arch, macOS, Windows)

## Đang có sẵn trong repo (14/09/2026)

| File | Dùng cho | Giấy phép |
|---|---|---|
| `DejaVuSans.ttf` / `-Bold` / `-Oblique` | chữ Việt | Bitstream Vera / Arev — cho phép phát hành lại |
| `ipag.ttf` (IPAGothic) | chữ Nhật | IPA Font License 1.0 — xem `ipag-LICENSE.txt` |

Chọn IPAGothic thay cho Noto Sans JP vì kanji/kana của nó rộng đều nhau nên rơi
vào ô vuông genkoyoshi rất cân, và bản .ttf đơn lẻ chỉ ~6 MB. **Giấy phép IPA
bắt buộc phát hành kèm nguyên văn license và KHÔNG được đổi tên file** — nên
đừng đổi `ipag.ttf` thành tên khác, và đừng xoá `ipag-LICENSE.txt`.

`pdf_generator.py` vẫn dò Noto trước, nên máy nào cài sẵn Noto CJK thì dùng
bản quen mắt hơn; ipag.ttf là mức lùi luôn có.

## Nếu muốn thay bằng font khác

| File | Dùng cho | Lấy ở đâu |
|---|---|---|
| `DejaVuSans.ttf` | chữ Việt, thân bài | dejavu-fonts.github.io (giấy phép Bitstream Vera/Arev, cho phép phát hành lại) |
| `DejaVuSans-Bold.ttf` | tiêu đề | nt |
| `DejaVuSans-Oblique.ttf` | phụ đề | nt |
| `NotoSansCJK-Regular.ttc` hoặc `NotoSansJP-Regular.ttf` | chữ Nhật | github.com/notofonts (SIL OFL) |

Bộ CJK khá nặng (~16 MB bản .ttc đủ 4 ngôn ngữ; bản `NotoSansJP-Regular.ttf`
chỉ tiếng Nhật nhẹ hơn nhiều — nên dùng bản này).

Thiếu font thì **web vẫn chạy bình thường**, chỉ riêng màn tạo PDF báo lỗi.
