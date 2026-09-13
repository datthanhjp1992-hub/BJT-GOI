# assets/fonts

Nơi đặt font cho tính năng **SC10 — PDF luyện viết** khi máy chủ không cài sẵn
font hệ thống (đúng trường hợp Render: ảnh chạy không có `fonts-dejavu` lẫn
`fonts-noto-cjk`, và gói free không cho `apt install`).

`apps/practice_sheets/pdf_generator.py` dò theo thứ tự:

1. Biến môi trường `PRACTICE_SHEET_FONT_DIR` (tiếng Việt) /
   `PRACTICE_SHEET_JP_FONT` (tiếng Nhật)
2. **Thư mục này**
3. Đường dẫn font hệ thống (Debian/Ubuntu, Fedora, Arch, macOS, Windows)

## Cần những file nào

| File | Dùng cho | Lấy ở đâu |
|---|---|---|
| `DejaVuSans.ttf` | chữ Việt, thân bài | dejavu-fonts.github.io (giấy phép Bitstream Vera/Arev, cho phép phát hành lại) |
| `DejaVuSans-Bold.ttf` | tiêu đề | nt |
| `DejaVuSans-Oblique.ttf` | phụ đề | nt |
| `NotoSansCJK-Regular.ttc` hoặc `NotoSansJP-Regular.ttf` | chữ Nhật | github.com/notofonts (SIL OFL) |

Bộ CJK khá nặng (~16 MB bản .ttc đủ 4 ngôn ngữ; bản `NotoSansJP-Regular.ttf`
chỉ tiếng Nhật nhẹ hơn nhiều — nên dùng bản này).

Thiếu font thì **web vẫn chạy bình thường**, chỉ riêng màn tạo PDF báo lỗi.
