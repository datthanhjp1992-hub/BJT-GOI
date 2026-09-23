# BÁO CÁO KIỂM TRA — Đợt 1

## Phạm vi đã làm
- Trang 3 (Mục lục) → tạo `01_keigo_lesson.csv`

## Bảng số dòng

| File | Số dòng thêm đợt này | Tổng số dòng |
|---|---|---|
| 01_keigo_lesson.csv | 7 | 7 |

## Cách xác định "7 chương"

PDF không dùng từ "chương" một cách tường minh trong mục lục; mục lục chỉ có 4 mục
lớn (1. KÍNH NGỮ, 2. BẢNG CHIA ĐỘNG TỪ..., 3. THAM KHẢO, 4. BÀI TẬP). Vì yêu cầu là
7 chương và mục "4. BÀI TẬP" không được coi là lesson (theo quy định của file
07_exercise_set.csv: `lesson__slug để trống hết`), tôi đã lấy 7 mục con/mục lớn còn
lại làm 7 lesson, theo đúng thứ tự xuất hiện trong mục lục trang 3:

1. TÔN KÍNH NGỮ (mục con của 1. KÍNH NGỮ, tr.4)
2. KHIÊM NHƯỜNG NGỮ (mục con của 1. KÍNH NGỮ, tr.7)
3. THẾ LỊCH SỰ (mục con của 1. KÍNH NGỮ, tr.11)
4. ĐỘNG TỪ CHO/NHẬN (mục con của 1. KÍNH NGỮ, tr.12)
5. TỔNG HỢP ĐỘNG TỪ BẤT QUY TẮC CHIA VỀ KÍNH NGỮ (mục con của 2., tr.13)
6. MỘT SỐ QUY TẮC CHIA ĐỘNG TỪ CÓ QUY TẮC VỀ DẠNG KÍNH NGỮ (mục con của 2., tr.16)
7. THAM KHẢO (mục lớn 3., tr.19)

**⚠️ CẦN BẠN XÁC NHẬN**: Đây là suy luận của tôi để khớp con số "7 chương" bạn yêu
cầu, không phải một nhãn "chương" có sẵn trong PDF. Nếu ý bạn về "7 chương" khác với
cách chia này (ví dụ gộp/tách khác), xin nói rõ để tôi sửa lại file trước khi đi
tiếp — vì các file sau (04_keigo_pattern.csv, 06_keigo_phrase_pair.csv) sẽ tham
chiếu tới `lesson__slug` này làm khóa ngoại.

## style_code

- TÔN KÍNH NGỮ → `sonkei` (rõ ràng, toàn bộ chương nói về tôn kính ngữ)
- KHIÊM NHƯỜNG NGỮ → để trống (chương này gồm cả Khiêm nhường ngữ I và II lẫn lộn,
  không tách riêng theo mục lục)
- THẾ LỊCH SỰ → `teinei`
- ĐỘNG TỪ CHO/NHẬN → `juju`
- TỔNG HỢP ĐỘNG TỪ BẤT QUY TẮC... → để trống (bảng gồm cả 3 cột 尊敬語/謙譲語/丁寧語
  trộn lẫn)
- MỘT SỐ QUY TẮC CHIA ĐỘNG TỪ CÓ QUY TẮC... → để trống (cùng lý do, bảng có cả 3 cột
  敬語/文法/例文 cho cả 尊敬語 và 謙譲語 và 丁寧語)
- THAM KHẢO → để trống (nội dung hỗn hợp: lưu ý dùng sai kính ngữ, từ đệm, biến đổi
  danh từ...)

## summary_vi

Để trống cho cả 7 dòng — PDF không có đoạn tóm tắt tiếng Việt sẵn có cho các mục
lục này (chỉ có tiêu đề, không có mô tả).

## slug

Đặt theo tiêu đề, ASCII không dấu, gạch ngang, đảm bảo duy nhất:
ton-kinh-ngu, khiem-nhuong-ngu, the-lich-su, dong-tu-cho-nhan,
bang-chia-dong-tu-bat-quy-tac, mot-so-quy-tac-chia-dong-tu-co-quy-tac, tham-khao

## Kết quả 5 phép tự kiểm tra A–E

- A (ordering star_position vs correct_order): chưa áp dụng — file này không có
  câu hỏi ordering.
- B (số dòng exercise = question_count): chưa áp dụng — chưa làm phần bài tập.
- C (mỗi question__code có đúng 1 is_correct=true): chưa áp dụng.
- D (khóa ngoại tồn tại ở file cha): chưa áp dụng — 01_keigo_lesson.csv là file gốc,
  chưa có file con nào tham chiếu tới nó.
- E (không trùng code/slug): ĐÃ KIỂM — 7 slug đều duy nhất, không trùng nhau.

## Mâu thuẫn nội tại của PDF

Chưa phát hiện ở phạm vi trang 3 (chỉ là mục lục).

## Điểm cần bạn xác nhận trước khi đi tiếp

1. Cách chia "7 chương" như liệt kê ở trên có đúng ý bạn không?
2. Có đồng ý để `style_code` trống với các chương có nội dung hỗn hợp (Khiêm nhường
   ngữ, 2 bảng chia động từ, Tham khảo) không, hay bạn muốn tôi chọn một giá trị đại
   diện?

---

# BÁO CÁO KIỂM TRA — Đợt 2

## Phạm vi đã làm
- Trang 13-16 (bảng chia động từ 4 cột: 基本形 / 尊敬語 / 謙譲語 / 丁寧語)
- Đối chiếu is_irregular với trang 4 (尊敬語 đặc biệt) và trang 7 (謙譲語 đặc biệt) —
  hai bảng này đã có sẵn trong nội dung PDF đã upload, dùng để tính đúng cột
  is_irregular theo quy tắc bạn đưa ra, dù chưa "chính thức" xử lý làm file riêng cho
  trang 4/7 (sẽ làm ở đợt sau theo lệnh của bạn).

## Bảng số dòng

| File | Số dòng thêm đợt này | Tổng số dòng |
|---|---|---|
| 02_keigo_verb.csv | 34 | 34 |
| 03_keigo_form.csv | 124 | 124 |

## 02_keigo_verb.csv — các quyết định

- Đã loại bỏ đúng 2 dòng đầu bảng (使用方法, 行為をする人) theo đúng cảnh báo trong
  yêu cầu — không đưa vào file.
- `reading`: PDF không in furigana cho cột 基本形 ở bảng này (không có cú pháp
  {漢字|かんじ}), nên để trống cho toàn bộ 34 dòng.
- `meaning_vi`: đây là cột DUY NHẤT tôi được phép dịch (theo đúng NGUYÊN TẮC ngoại
  lệ), dịch nghĩa cơ bản 2-4 từ cho từng động từ. Đây là bản dịch tự tạo, không lấy
  từ PDF (PDF hoàn toàn không có nghĩa tiếng Việt ở bảng này).
- Khóa tự nhiên (plain_form, reading): đã kiểm — 34 plain_form đều duy nhất (đã chạy
  script `sort | uniq -d`, không có dòng trùng).
- Chưa bao gồm động từ gốc từ trang 4 và trang 7 (theo đúng phạm vi bạn giao "trang
  13-16"). Các động từ ở trang 4/7 không trùng với 34 động từ ở trang 13-16 (ví dụ
  くれる, 出かける, 出席する, 始める, 寝る, あげる, 誘う, 案内する, 説明する, たずねる)
  sẽ được NỐI THÊM vào file này ở đợt sau, tiếp tục display_order từ 35.

## 03_keigo_form.csv — các quyết định quan trọng cần bạn xem lại

### 1. Không đưa cột 丁寧語 vào file này (QUYẾT ĐỊNH SUY LUẬN — CẦN XÁC NHẬN)
File 03 mô tả là "bảng 4 cột" nhưng ví dụ minh họa chỉ nói về 尊敬語. Cột 丁寧語 trong
bảng trang 13-16 chỉ là dạng ～ます cơ bản (します, 言います...), không phải kính ngữ
đặc thù, và style_code `teinei` trong file 01 lesson đã dùng cho chương THẾ LỊCH SỰ
(mẫu 形容詞～うございます) — khác chủ đề. Vì vậy tôi KHÔNG đưa 34 dòng 丁寧語 vào file
03. Nếu bạn muốn có cả cột 丁寧語, xin nói rõ để tôi bổ sung 34 dòng nữa.

### 2. Phân loại kenjo1 vs kenjo2 (SUY LUẬN — CẦN XÁC NHẬN)
Bảng gốc chỉ có MỘT cột "謙譲語" chung, không tách I/II. Tôi tự phân loại theo quy tắc:
- Nếu từ đó xuất hiện đúng trong bảng "Khiêm nhường ngữ I" (trang 7) → kenjo1
- Nếu xuất hiện đúng trong bảng "Khiêm nhường ngữ II" (trang 7) → kenjo2
- Nếu KHÔNG xuất hiện ở cả hai: dùng heuristic riêng —
  - Dạng có お/ご~する, お/ご~いたす, X+いたす (X là danh từ 2 chữ Hán), ～させていただく,
    ～ていただく → kenjo1 (vì trang 17 liệt kê "お/ご～する／いたす" là MỘT mẫu ngữ
    pháp謙譲語 chung)
  - Dạng 拝+chữ Hán (拝見, 拝聴, 拝読, 拝借, 拝察, 拝受) → kenjo1 (theo đúng chỉ dẫn của
    bạn cho bảng trang 9, áp dụng luôn cho các từ 拝 khác xuất hiện ở bảng này)
  - Động từ độc lập không có お/ご (vd 承知する, 頂戴する, かしこまる, 失礼する, 愚考する,
    検討する, 参上する, 上がる, 賜る, 申し伝える) → kenjo2
- **ĐÂY LÀ SUY LUẬN CỦA TÔI, KHÔNG PHẢI DỮ LIỆU TRỰC TIẾP TỪ PDF.** Nếu bạn có quy tắc
  khác để phân biệt kenjo1/kenjo2, xin cho biết, tôi sẽ sửa lại toàn bộ cột
  `style_code` của file 03.

### 3. Các trường hợp is_irregular / khớp từ mơ hồ cần bạn xác nhận
- `来る` / kenjo1 / `伺う`: KHÔNG đánh true, vì bảng trang 7 (Khiêm nhường ngữ I) chỉ
  ghi うかがう ← 行く、聞く、たずねる — không có 来る trong danh sách gốc. Có thể đây là
  thiếu sót của sách, hoặc うかがう vốn dùng được cho cả 来る trong thực tế nhưng PDF
  không liệt kê. Tôi giữ đúng theo chữ trong PDF (false).
- `訪ねる` / kenjo1 / `伺う`, `お伺いする`: ĐÁNH true, vì tôi suy đoán "たずねる" trong
  bảng trang 7 (行く、聞く、たずねる ← うかがう) chính là 訪ねる (thăm), không phải
  尋ねる (hỏi) — đây là từ đồng âm mơ hồ trong tiếng Nhật viết hiragana. Nếu ý sách là
  尋ねる (hỏi) thì is_irregular của 2 dòng này phải đổi thành false.
- `与える` / kenjo1 / `差し上げる`: ĐÁNH true, suy đoán あげる (trong bảng trang 7:
  差し上げる←あげる) đồng nghĩa/tương đương 与える. Đây là 2 từ khác nhau về mặt chữ
  viết dù cùng nghĩa "cho, trao". Cần bạn xác nhận có nên coi là khớp hay không.
- `知っている` / kenjo2 `存じる`, kenjo1 `存じ上げる`: ĐÁNH true, suy đoán 知っている
  (đang biết) ≈ 知る (biết) trong bảng trang 7. Là suy luận ngữ nghĩa, không phải khớp
  chữ tuyệt đối.
- `拝聴する` (của 聞く) và `拝読する` (của 読む): is_irregular hiện để **false** vì bảng
  trang 4/7 không có các từ này (chúng thuộc bảng riêng 拝+漢字一字 ở TRANG 9, chưa xử
  lý đợt này). **LƯU Ý QUAN TRỌNG**: khi làm đợt xử lý trang 9, theo quy tắc gộp trùng
  "mỗi cặp (verb, style_code, form) chỉ một dòng duy nhất", 2 dòng này (聞く,kenjo1,
  拝聴する) và (読む,kenjo1,拝読する) sẽ TRÙNG với dữ liệu từ bảng trang 9 — lúc đó tôi
  sẽ SỬA is_irregular của 2 dòng này thành **true** (theo đúng chỉ dẫn "style_code =
  kenjo1, is_irregular = true" cho bảng 拝+漢字一字), thay vì tạo dòng mới.
- Cụm `お(買い)求めになる`, `お買い(上げ)になる` (của 買う): giữ nguyên dấu ngoặc đơn
  nửa độ rộng y như PDF in, vì không chắc đây là biến thể tùy chọn hay là một phần cố
  định của từ. Chưa tách thành 2 biến thể (có 買い / không có 買い) — xin bạn xác nhận
  cách xử lý đúng.
- `賜る（たまわる）` (của 受け取る và もらう): đây là 2 dòng duy nhất trong đợt này PDF
  có in cách đọc kèm theo (furigana kiểu ngoặc đơn) → tôi đã tách vào cột `reading` =
  たまわる, cột `form` = 賜る.

## Kết quả 5 phép tự kiểm tra A–E (đợt 2)

- A (ordering): chưa áp dụng, chưa có câu hỏi ordering.
- B (số dòng = question_count): chưa áp dụng.
- C (mỗi question__code có đúng 1 is_correct=true): chưa áp dụng.
- D (khóa ngoại tồn tại ở file cha): ĐÃ KIỂM bằng script — toàn bộ
  `verb__plain_form` trong 03_keigo_form.csv đều tồn tại trong 02_keigo_verb.csv,
  không có giá trị mồ côi.
- E (không trùng code/slug/khóa): ĐÃ KIỂM bằng script —
  - 02: không có `plain_form` nào trùng lặp trong 34 dòng.
  - 03: không có bộ ba (verb__plain_form, style_code, form) nào trùng lặp trong 124
    dòng.

## Mâu thuẫn nội tại của PDF phát hiện được

- Bảng trang 15, dòng 考える: cột 謙譲語 liệt kê cả "検討する" (nghĩa "xem xét, cân
  nhắc") — về ngữ nghĩa đây không hẳn là dạng khiêm nhường đặc thù của 考える, có thể
  là lỗi biên soạn hoặc ý sách coi đây là cách nói khiêm tốn thay cho "tôi nghĩ/suy
  nghĩ" trong ngữ cảnh công việc. Tôi vẫn chép nguyên theo PDF, không tự sửa.
- Trang 4 và trang 7 liệt kê 出かける, 出席する, 始める, 寝る, くれる, あげる, 誘う,
  案内する, 説明する, 届ける, たずねる — đây là các động từ gốc KHÔNG xuất hiện trong
  bảng 34 động từ trang 13-16. Khi xử lý đợt trang 4/7, các động từ này sẽ là dòng MỚI
  bổ sung vào 02_keigo_verb.csv (không trùng với 34 dòng hiện có), tiếp tục
  display_order từ 35.

## Việc cần làm ở đợt sau (trang 4 và trang 7)

1. Bổ sung vào 02_keigo_verb.csv các động từ gốc mới xuất hiện ở trang 4/7 mà chưa có
   trong 34 dòng hiện tại.
2. Bổ sung vào 03_keigo_form.csv các dòng is_irregular=true tương ứng với từng mục
   trong 2 bảng đặc biệt trang 4 (尊敬語) và trang 7 (謙譲語I/II), đồng thời SOÁT LẠI
   xem có dòng nào đã có sẵn ở đợt 2 (trang 13-16) trùng (verb, style_code, form) hay
   không — nếu trùng thì KHÔNG tạo dòng mới, chỉ cập nhật is_irregular nếu cần.

---

# BÁO CÁO KIỂM TRA — Đợt 3

## Phạm vi đã làm
- Trang 4 (尊敬語 đặc biệt), trang 7 (謙譲語 I và II đặc biệt), trang 9 (拝+漢字一字)

## Bảng số dòng

| File | Số dòng thêm đợt này | Cập nhật dòng cũ | Tổng số dòng |
|---|---|---|---|
| 02_keigo_verb.csv | 14 | 0 | 48 |
| 03_keigo_form.csv | 18 | 5 (đổi is_irregular) | 142 |

## NGUYÊN TẮC ĐỐI CHIẾU TÔI ÁP DỤNG (quan trọng — cần bạn xác nhận)

Vì trang 4/7 dùng CHỮ HÁN/HIRAGANA cho động từ gốc đôi khi khác với động từ đã có ở
trang 13-16, tôi áp dụng nguyên tắc:
- **Biến thể chữ viết CÙNG một từ (kanji ↔ hiragana), không mơ hồ** (vd 参る = まいる,
  伺う = うかがう) → coi là CÙNG một từ, không tạo động từ mới.
- **Từ khác nhau về mặt chữ, kể cả gần nghĩa** (vd 与える ≠ あげる, たずねる mơ hồ có
  thể là 尋ねる HOẶC 訪ねる ≠ chắc chắn là 訪ねる) → coi là TỪ MỚI, tạo dòng riêng trong
  02, KHÔNG gộp vào động từ đã có. Đây là để tránh "sáng tác" một sự tương đương mà PDF
  không nói rõ.
- **Trường hợp 知っている / 知る**: tôi GIỮ NGUYÊN is_irregular=true cho 2 dòng
  (知っている,kenjo2,存じる) và (知っている,kenjo1,存じ上げる) từ đợt 2, vì chính bảng
  trang 13-16 (cùng một cuốn sách) đã tự ghép 知っている với các dạng 謙譲語 y hệt
  존じる/存じ上げる ở CÙNG một dòng bảng — đây không phải suy đoán của tôi, mà là dữ
  liệu trực tiếp trong sách. Đồng thời tôi VẪN thêm 知る làm động từ MỚI riêng (vì trang
  7 in chữ 知る, không phải 知っている) với is_irregular=true cho cả 2 dạng.

## SỬA LẠI (revert) 3 dòng đã tạo sai ở đợt 2 — XIN LƯU Ý

Sau khi đối chiếu kỹ với trang 4/7, tôi phát hiện 3 dòng ở đợt 2 đã bị tôi ĐOÁN quá
tay (gán is_irregular=true dựa trên suy đoán ngữ nghĩa, không có bằng chứng trực tiếp
trong PDF). Tôi đã SỬA LẠI các dòng này về `false`:

| verb__plain_form | style_code | form | is_irregular cũ | is_irregular mới | Lý do sửa |
|---|---|---|---|---|---|
| 訪ねる | kenjo1 | 伺う | true | **false** | Trang 7 ghi うかがう←行く、聞く、たずねる; たずねる mơ hồ (尋ねる/訪ねる), không chắc = 訪ねる |
| 訪ねる | kenjo1 | お伺いする | true | **false** | Cùng lý do trên |
| 与える | kenjo1 | 差し上げる | true | **false** | Trang 7 ghi 差し上げる←あげる (từ khác với 与える) |

## Cập nhật is_irregular false→true (từ bảng 拝+漢字 trang 9)

| verb__plain_form | style_code | form | is_irregular cũ | is_irregular mới |
|---|---|---|---|---|
| 聞く | kenjo1 | 拝聴する | false | **true** |
| 読む | kenjo1 | 拝読する | false | **true** |

(拝見する/見る và 拝借する/借りる đã là true sẵn từ đợt 2 nên không cần sửa.)

## 14 động từ mới thêm vào 02_keigo_verb.csv

くれる, 飲む, 出かける, 出席する, 始める, 寝る, たずねる, 知る, あげる, 届ける, 誘う,
案内する, 説明する, 推察する — tất cả `reading` để trống (PDF không in cách đọc/furigana
cho các từ này). `meaning_vi` do tôi dịch cơ bản 2-4 từ.

**Điểm cần bạn xác nhận riêng**: `たずねる` — tôi để `meaning_vi` là "hỏi/thăm" vì
chính bản thân từ này đã mơ hồ trong PDF (không có chữ Hán đi kèm để phân biệt 尋ねる
"hỏi" hay 訪ねる "thăm/ghé thăm"). Nếu bạn biết ý định của tác giả (dựa vào ngữ cảnh
"行く、聞く、たずねる" — có thể たずねる ở đây là để bổ sung nghĩa "hỏi" cho 聞く, hoặc để
chỉ "thăm viếng"), xin cho biết để tôi sửa nghĩa và (nếu cần) gộp lại với 訪ねる.

## 18 dòng mới thêm vào 03_keigo_form.csv

**Từ trang 4 (尊敬語, 9 dòng)**:
来る/来られる, くれる/くださる, 読む/読まれる, 飲む/召し上がる, 出かける/お出かけになる,
利用する/利用される, 出席する/ご出席になる, 始める/始められる, 寝る/お休みになる
— tất cả is_irregular=true.

**Từ trang 7 KNN I (7 dòng)**:
たずねる/うかがう, 知る/存じ上げる, あげる/差し上げる, 届ける/お届けする, 誘う/お誘いする,
案内する/ご案内する, 説明する/ご説明する — tất cả is_irregular=true, style_code=kenjo1.

**Từ trang 7 KNN II (1 dòng)**:
知る/存じる — is_irregular=true, style_code=kenjo2.

**Từ trang 9 (1 dòng)**:
推察する/拝察する — is_irregular=true, style_code=kenjo1 (theo đúng chỉ dẫn của bạn).
Đây cũng là lý do 推察する phải thêm làm động từ mới trong 02 (khác với 考える/思う đã
có 拝察する ở các dòng riêng — 3 verb khác nhau dùng chung form 拝察する, không phải
trùng lặp vì khóa là bộ 3 (verb, style_code, form)).

## Các cặp KHÔNG cần tạo dòng mới (đã true sẵn từ đợt 2, chỉ xác nhận khớp)

行く/いらっしゃる, 行く/おいでになる, 来る/いらっしゃる, 来る/おいでになる, 来る/見える,
いる/いらっしゃる, いる/おいでになる, 言う/おっしゃる, する/なさる, 見る/ご覧になる,
食べる/召し上がる, 着る/お召しになる, 行く/うかがう, 聞く/うかがう, 言う/申し上げる,
もらう/いただく, 会う/お目にかかる, 見せる/ご覧に入れる, 見せる/お目にかける,
見る/拝見する, 借りる/拝借する, 行く/参る, 来る/参る, 言う/申す, する/いたす, いる/おる,
思う/存じる, 利用する/ご利用になる.

## Kết quả 5 phép tự kiểm tra A–E (đợt 3)

- A, B, C: chưa áp dụng (chưa có dữ liệu bài tập).
- D (khóa ngoại): ĐÃ KIỂM bằng script — toàn bộ verb__plain_form trong
  03_keigo_form.csv (142 dòng) đều tồn tại trong 02_keigo_verb.csv (48 dòng), không có
  giá trị mồ côi.
- E (không trùng): ĐÃ KIỂM bằng script — 02 không trùng plain_form (48 dòng đều duy
  nhất); 03 không trùng bộ ba (verb__plain_form, style_code, form) trong 142 dòng.

## Mâu thuẫn / điểm mơ hồ nội tại của PDF phát hiện đợt này

1. `たずねる` (trang 7) không kèm chữ Hán → mơ hồ như đã nêu ở trên.
2. Trang 7 ghi cơ sở cho 差し上げる là "あげる" (không phải 与える) dù trang 13-16 dùng
   "与える" làm 基本形 — đây có thể là chủ ý của tác giả (与える và あげる là các mức độ
   trang trọng khác nhau của cùng hành động "cho"), tôi đã tách thành 2 verb riêng biệt
   để tôn trọng đúng chữ trong PDF.
3. Trang 13-16 gán 拝察する cho CẢ 思う LẪN 考える, còn trang 9 lại gán 拝察 cho
   "推察する" (một động từ thứ ba, không phải 思う hay 考える). Đây là điểm PDF tự mâu
   thuẫn/không nhất quán về động từ gốc của 拝察する — sách dùng 3 động từ gốc khác
   nhau (思う, 考える, 推察する) cho cùng 1 dạng khiêm nhường ngữ 拝察する ở 3 chỗ khác
   nhau. Tôi giữ cả 3 dòng riêng biệt, không gộp, không tự chọn cái nào "đúng".

## Việc cần làm ở đợt sau

Các trang còn lại của phần lý thuyết (trang 11-12: THẾ LỊCH SỰ + ĐỘNG TỪ CHO/NHẬN, và
trang 17-21: bảng ngữ pháp + THAM KHẢO) sẽ liên quan đến file 04_keigo_pattern.csv và
06_keigo_phrase_pair.csv — chờ lệnh của bạn.

---

# BÁO CÁO KIỂM TRA — Đợt 4

## Phạm vi đã làm
- Trang 5-6 (10 mẫu ngữ pháp TÔN KÍNH NGỮ, mục "*Các trường hợp đặc biệt" phần văn
  phạm, không nhầm với bảng trang 4)

## Bảng số dòng

| File | Số dòng thêm đợt này | Tổng số dòng |
|---|---|---|
| 04_keigo_pattern.csv | 10 | 10 |
| 05_keigo_example.csv | 26 | 26 |

## 04_keigo_pattern.csv — các quyết định

- `lesson__slug` = `ton-kinh-ngu` cho cả 10 dòng (thuộc chương TÔN KÍNH NGỮ, đã tạo ở
  đợt 1).
- `style_code` = `sonkei` cho cả 10 dòng.
- `title`: chép nguyên văn, kể cả 「」／〜.
- `formation`: chỉ điền khi công thức rõ ràng suy ra được từ tiêu đề (ví dụ お・ご～だ
  → "お/ご+N+だ"); để trống với các mẫu không có công thức rõ ràng: `～あがる` (vì các
  ví dụ dùng お召し上がり/おあがり/お届けにあがり không thống nhất một công thức đơn),
  `見える／お見えになる` (từ vựng đặc biệt, không phải công thức sản sinh), `めす` (động
  từ đơn, không phải công thức).
- `explanation_vi`: để TRỐNG toàn bộ 10 dòng — đây KHÔNG phải cột ngoại lệ được phép
  dịch (chỉ `meaning_vi` ở file 02 được phép), và PDF cũng không có giải thích tiếng
  Việt cho các mẫu này.

### ⚠️ ĐIỂM CẦN BẠN XÁC NHẬN: nghi ngờ lỗi chính tả trong PDF ở mẫu 4

Tiêu đề mẫu 4 in trong PDF là:
`N／Na です → N／Na でいっらしゃる`

Chữ cuối "でいっらしゃる" trông giống lỗi đánh máy của sách (vị trí つ nhỏ bị lệch) —
đúng ra phải là "でいらっしゃる" như chính các câu ví dụ ngay bên dưới đã dùng đúng
(「こちらは山本先生の奥様でいらっしゃいます」). Theo nguyên tắc CHỈ CHÉP KHÔNG SÁNG TÁC,
tôi đã copy NGUYÊN VĂN "でいっらしゃる" vào cột `title` (giữ đúng như PDF, kể cả có vẻ
là lỗi). Tuy nhiên ở cột `formation` (do tôi tự suy ra, không phải chép nguyên), tôi đã
viết công thức với chính tả ĐÚNG "でいらっしゃる" vì cột này không bắt buộc chép y
nguyên. Xin bạn xác nhận: giữ nguyên lỗi chính tả ở cột title như tôi đã làm, hay muốn
tôi sửa lại?

## 05_keigo_example.csv — các quyết định

- `sentence_vi`: để trống toàn bộ 26 dòng (đúng quy định — sách không dịch ví dụ).
- `speaker`: chỉ điền A/B cho 2 dòng thuộc đoạn hội thoại trong mẫu `sonkei-agaru`
  (「おじゃまします。」／「どうぞお上がり下さい。」); các dòng còn lại để trống.
- `is_correct`: true cho toàn bộ 26 dòng — không có câu nào bị đánh dấu × trong phạm
  vi trang 5-6.
- `pair_group`: chỉ điền =1 cho cặp hội thoại A/B trong `sonkei-agaru` (2 dòng); các
  dòng khác để trống.
- `display_order`: đánh số RIÊNG trong phạm vi từng `pattern__code` (bắt đầu lại từ 1
  cho mỗi mẫu), theo đúng quy tắc chung "tăng liên tục trong phạm vi bản ghi cha".

### ⚠️ ĐIỂM CẦN BẠN XÁC NHẬN: xử lý câu ví dụ nối bằng "／"

Mẫu `sonkei-agaru` có câu: "どうぞお召し上がりください。／どうぞおあがりください。" — đây
là 2 cách nói thay thế nhau (cả 2 đều đúng), không phải cặp sai-đúng, không phải hội
thoại. Tôi đã TÁCH thành 2 dòng riêng (display_order 1 và 2), KHÔNG gán chung
pair_group (vì không khớp định nghĩa "cặp sai-đúng" hay "hội thoại" mà quy tắc pair_group
đưa ra). Đây là quyết định suy luận của tôi, không phải chỉ dẫn tường minh — nếu bạn
muốn giữ nguyên là 1 dòng duy nhất (với dấu ／ ở giữa) hoặc muốn gán chung 1
pair_group, xin cho biết để tôi sửa lại.

- Câu ví dụ mẫu 7 (`sonkei-o-de-irassharu`) mỗi dòng PDF gồm 2 câu liền nhau (ví dụ
  "いつまでもお若くていらっしゃいますね。 若さの秘訣は何でしょうか。") — tôi giữ NGUYÊN
  thành 1 dòng duy nhất (không tách), vì đây không có nhãn hội thoại A/B và được trình
  bày liền mạch trong cùng 1 gạch đầu dòng của sách.

## Kết quả 5 phép tự kiểm tra A–E (đợt 4)

- A (ordering): chưa áp dụng.
- B (question_count): chưa áp dụng.
- C (is_correct duy nhất mỗi question): chưa áp dụng (chưa phải file câu hỏi bài tập).
- D (khóa ngoại): ĐÃ KIỂM bằng script —
  - `lesson__slug` trong 04 (ton-kinh-ngu) tồn tại trong 01_keigo_lesson.csv. ✓
  - `pattern__code` trong 05 đều tồn tại trong 04_keigo_pattern.csv, không mồ côi. ✓
- E (không trùng code): ĐÃ KIỂM — 10 `code` trong file 04 đều duy nhất (không trùng
  lẫn với 7 slug ở file 01 vì khác cột/khác file).

## Mâu thuẫn / điểm mơ hồ phát hiện đợt này

1. Lỗi chính tả nghi vấn "でいっらしゃる" ở tiêu đề mẫu 4 (đã nêu chi tiết ở trên).
2. Câu ví dụ nối bằng "／" trong mẫu 6 xử lý theo suy luận cá nhân (đã nêu ở trên).

## Việc cần làm ở đợt sau

Đợt tiếp theo có thể là trang 8-10 (7 mẫu khiêm nhường ngữ I còn lại — mục 1-13 trang
8-10) để tiếp tục 04/05, hoặc trang 11-12 (THẾ LỊCH SỰ + ĐỘNG TỪ CHO/NHẬN) — chờ lệnh
bạn.

---

# BÁO CÁO KIỂM TRA — Đợt 5

## Phạm vi đã làm
- Trang 8-10 (13 mẫu ngữ pháp KHIÊM NHƯỜNG NGỮ)

## Bảng số dòng

| File | Số dòng thêm đợt này | Tổng số dòng |
|---|---|---|
| 04_keigo_pattern.csv | 13 | 23 |
| 05_keigo_example.csv | 35 | 61 |

## 04_keigo_pattern.csv — các quyết định

- `lesson__slug` = `khiem-nhuong-ngu` cho cả 13 dòng, `display_order` đánh số RIÊNG
  1-13 trong phạm vi lesson này (không tiếp tục từ 11 của lesson ton-kinh-ngu).
- `code`: dùng tiền tố chung `kenjo-` (không phân biệt kenjo1/kenjo2 trong code),
  theo đúng ví dụ mẫu bạn đưa ra ban đầu ("kenjo-o-go-itadaku" — khớp chính xác mẫu 1
  của đợt này).

### ⚠️ ĐIỂM CẦN BẠN XÁC NHẬN: cột style_code ở cấp độ MẪU (không phải cấp từ vựng)

Không giống file 03 (là các TỪ đơn lẻ có thể đối chiếu trực tiếp với bảng Khiêm nhường
ngữ I/II trang 7), 13 MẪU NGỮ PHÁP ở trang 8-10 không được PDF phân loại rõ I hay II.
Tôi tự suy luận theo cấu trúc:
- Mẫu dùng お/ご~ (お/ご～いただく, お/ご～申し上げる, お/ご～できる, お/ご～願う) và
  mẫu 拝～（する）→ gán `kenjo1`
- Mẫu xây từ động từ thuộc nhóm KNN II (ておる ← おる, ～てまいる ← まいる) → gán
  `kenjo2`
- Mẫu 存じる・存じ上げる: gộp CẢ 2 từ (存じる=kenjo2, 存じ上げる=kenjo1) trong CÙNG một
  mẫu → để `style_code` TRỐNG (không ép về 1 giá trị).
- Các mẫu còn lại (うけたまわる, いただく, お目にかかる, お目にかける, ご覧に入れる) —
  đây là các TỪ VỰNG đơn (không phải công thức お/ご~) nhưng lại xuất hiện trực tiếp
  hoặc gần với danh sách Khiêm nhường ngữ I trang 7 (お目にかかる, お目にかける／ご覧に
  入れる, いただく đều nằm thẳng trong bảng KNN I) → gán `kenjo1`. Riêng `うけたまわる`
  KHÔNG có trong bảng KNN I/II nào — tôi gán `kenjo1` theo suy đoán (chức năng gần với
  いただく, không dùng お/ご) — **đây là phỏng đoán yếu nhất, xin bạn xác nhận riêng.**

**Nếu bạn có quy tắc khác để gán style_code cấp mẫu, xin cho biết, tôi sẽ sửa lại toàn
bộ cột này của cả 13 dòng.**

## 05_keigo_example.csv — các quyết định

- 35 câu ví dụ, is_correct=true toàn bộ (không có câu nào đánh dấu × trong trang
  8-10).
- Đã xử lý ĐÚNG 3 chỗ có furigana (ruby) thật sự trong PDF, theo cú pháp {漢字|かんじ}:
  - Mẫu `kenjo-uketamawaru`, câu 4: {由|よし}{承|うけたまわ}り (PDF in furigana tách
    rời cho từng chữ 由 và 承)
  - Mẫu `kenjo-hai`, câu 2: {僭越|せんえつ}ながら
  - Mẫu `kenjo-ome-ni-kakeru`, câu 5: {骨董品|こっとうひん}ではございません
- Đoạn hội thoại 客/係員 trong mẫu `kenjo-ome-ni-kakaru` → speaker=客/係員,
  pair_group=1 (2 dòng).
- Đoạn hội thoại A/B trong mẫu `kenjo-ome-ni-kakeru` → speaker=A/B, pair_group=1 (2
  dòng).

### ⚠️ ĐIỂM CẦN BẠN XÁC NHẬN: nghi ngờ thiếu chữ trong câu ví dụ

Câu đầu tiên của mẫu `kenjo-ome-ni-kakaru`:
"長いことご無沙汰しておりましたが、いかがお過ごしでしょうか。**度**お目にかかりたいと
思っておりますが、 なかなか時間がなく、失礼しております。"

Chữ "度" đứng một mình (không có "一" phía trước) trông giống thiếu chữ so với cách
dùng thông thường "一度" (một lần/một dịp). Tôi đã chép NGUYÊN VĂN đúng như trích xuất
được từ PDF (không tự thêm "一"), vì không chắc đây là lỗi in ấn của sách hay lỗi trong
quá trình trích xuất văn bản từ ảnh PDF mà tôi nhận được. Xin bạn kiểm tra lại bản gốc
và cho biết có cần sửa thành "一度お目にかかりたい" hay giữ nguyên như hiện tại.

### Chỗ khác: câu ví dụ dạng cụm từ không phải câu hoàn chỉnh

Mẫu `kenjo-o-go-dekiru` chỉ có ví dụ là cụm danh từ "ご紹介できる仕事" (không phải câu
hoàn chỉnh, không có dấu 。kết thúc) — tôi chép nguyên như PDF in, không tự thêm dấu
câu hay từ ngữ.

Mẫu `kenjo-ome-ni-kakeru` câu cuối "社長にお目にかけるような骨董品ではございません" PDF
cũng không có dấu 。 ở cuối — chép nguyên, không tự thêm.

## Kết quả 5 phép tự kiểm tra A–E (đợt 5)

- A, B, C: chưa áp dụng.
- D (khóa ngoại): ĐÃ KIỂM bằng script — `lesson__slug` khiem-nhuong-ngu tồn tại trong
  01; toàn bộ `pattern__code` trong 05 (đợt 5) tồn tại trong 04, không mồ côi.
- E (không trùng code): ĐÃ KIỂM — 13 code mới không trùng với 10 code sonkei đã có từ
  đợt 4 (tiền tố khác nhau: sonkei- vs kenjo-), và không trùng lẫn nhau.

## Mâu thuẫn / điểm mơ hồ phát hiện đợt này

1. Nghi thiếu chữ "一" trước "度お目にかかりたい" (đã nêu ở trên).
2. 2 ví dụ không phải câu hoàn chỉnh / thiếu dấu chấm cuối câu (ご紹介できる仕事; 社長に
   お目にかけるような骨董品ではございません) — chép nguyên theo PDF.
3. Cách phân loại style_code cấp mẫu (kenjo1/kenjo2/trống) là suy luận, cần bạn xác
   nhận (đã nêu chi tiết ở trên) — đặc biệt là `うけたまわる`.

## Việc cần làm ở đợt sau

Trang 11-12 (THẾ LỊCH SỰ: hình dung từ ～うございます, và ĐỘNG TỪ CHO/NHẬN: các mẫu
～てください/～てあげる/～てもらう...) sẽ tiếp tục vào 04/05, dùng lesson__slug
`the-lich-su` và `dong-tu-cho-nhan` — chờ lệnh bạn.

---

# BÁO CÁO KIỂM TRA — Đợt 6

## Phạm vi đã làm
- Trang 11 (THẾ LỊCH SỰ: 形容詞～うございます)
- Trang 12 (ĐỘNG TỪ CHO/NHẬN: 6 mẫu)
- Trang 17 (MỘT SỐ QUY TẮC CHIA ĐỘNG TỪ CÓ QUY TẮC — bảng 敬語/文法/例文)

## Bảng số dòng

| File | Số dòng thêm đợt này | Tổng số dòng |
|---|---|---|
| 04_keigo_pattern.csv | 17 | 40 |
| 05_keigo_example.csv | 63 (58 dòng mới + 5 dòng bổ sung vào mẫu đã có) | 124 |

## ⚠️ QUYẾT ĐỊNH QUAN TRỌNG CẦN BẠN XÁC NHẬN: gộp trang 17 vào mẫu đã có ở đợt 4/5

Bảng trang 17 liệt kê lại một số công thức đã từng xuất hiện dưới dạng "mẫu" riêng ở
trang 5 (TÔN KÍNH NGỮ) và trang 8 (KHIÊM NHƯỜNG NGỮ), kèm ví dụ MỚI. Vì mỗi dòng
04_keigo_pattern.csv chỉ thuộc 1 lesson__slug duy nhất, tôi KHÔNG tạo pattern trùng
lặp cho cùng một công thức ngữ pháp — thay vào đó tôi NỐI THÊM ví dụ mới (từ trang 17)
vào đúng pattern đã tồn tại từ trang 5/8, tiếp tục display_order:

| Công thức trang 17 | Ví dụ mới thêm | Gộp vào pattern__code (đã có từ) |
|---|---|---|
| お/ご～なさる | ご利用なさいますか？ | `sonkei-o-go-nasaru` (trang 5, đợt 4) |
| お/ご～だ/です | お待ちです。 | `sonkei-o-go-da` (trang 5, đợt 4) |
| お/ご～でいらっしゃる | お元気でいらっしゃる | `sonkei-de-irassharu` (trang 5, đợt 4) — xem lưu ý bên dưới |
| お／ご～申し上げる | ご報告申し上げます。 | `kenjo-o-go-moushiageru` (trang 8, đợt 5) |
| お／ご～いただく | お待ちいただきます。 | `kenjo-o-go-itadaku` (trang 8, đợt 5) |

**Lưu ý về お/ご～でいらっしゃる**: trang 17 liệt kê công thức này tách biệt với
「（お）～でいらっしゃる」(mẫu 7, trang 5, code `sonkei-o-de-irassharu`) — ví dụ trang
17 "お元気でいらっしゃる" dùng Na形容詞（元気）+でいらっしゃる, khớp SÁT với mô tả mẫu 4
"N／Na です → N／Na でいらっしゃる" (`sonkei-de-irassharu`) hơn là mẫu 7 (vốn dùng
い形容詞＋くて＋いらっしゃる). Tôi đã gộp vào `sonkei-de-irassharu`, nhưng đây là suy
luận — nếu bạn thấy nên tách thành pattern riêng hoặc gộp vào mẫu 7 thay vì mẫu 4, xin
cho biết.

**Còn lại của bảng trang 17 (10 công thức chưa từng xuất hiện) → tạo pattern MỚI**,
thuộc lesson `mot-so-quy-tac-chia-dong-tu-co-quy-tac`:
お/ご～になる, お/ご～くださる/ください, 「Vれる／Vられる」, quy tắc gắn敬称
(～さん/～様...), quy tắc gắn お/ご/貴/御, お／ご～する／いたす, お/ご～させていただきます,
quy tắc gắn お/ご/粗/弊/拝, quy tắc gắn ども/め, và 丁寧語 (nhóm quy tắc chung).

## Về pattern `teinei-hen-doi` (丁寧語, trang 17) — CÁCH XỬ LÝ ĐẶC BIỆT

Nội dung 丁寧語 trang 17 là DANH SÁCH QUY TẮC đánh số 1-10 (vd "です→でございます"),
không phải câu ví dụ đầy đủ. Vì file 05 chỉ có cột `sentence_jp` (không có cột riêng
cho "quy tắc biến đổi"), tôi đưa từng quy tắc vào làm 1 dòng ví dụ (12 dòng, đã tách
riêng "食事→お食事" và "説明→ご説明" thành 2 dòng thay vì gộp chung). Tôi CHƯA đưa vào
phần danh sách từ có お/ご đính kèm ở cuối bảng (お名前, お仕事, ご住所, ご両親...) vì đó
là danh sách từ vựng rời rạc, không phải "câu ví dụ" — nếu bạn muốn đưa vào (làm ví dụ
riêng cho từng từ), xin cho biết.

## Cùng cách xử lý cho `teinei-u-gozaimasu` (trang 11)

Bảng (1)(2)(3) liệt kê 11 cặp biến đổi tính từ (安い→安うございます...) — tôi đưa cả 11
cặp làm ví dụ riêng (không gộp theo nhóm 1/2/3, không gán pair_group vì đây là nhóm
theo quy luật âm biến, không phải cặp sai-đúng hay hội thoại).

## Xử lý câu hội thoại phát hiện thêm ở đợt này

- `teinei-u-gozaimasu`: câu "A「東大合格して、おめでとうございます。」B「ありがとうご
  ざいます。」" → tách 2 dòng, speaker=A/B, pair_group=1.
- `juju-te-kudasai` và `juju-te-agete-yatte-kudasai`: mỗi mẫu là đoạn hội thoại 3 lượt
  A-B-A → 3 dòng, cùng pair_group=1, speaker tương ứng A/B/A.

## Xử lý các cặp diễn giải "=" (không phải hội thoại, không phải sai-đúng)

`juju-te-moratte-kudasai` và `juju-te-kureru-temorau` mỗi mẫu có 2 câu nối bằng dấu
"=" trong PDF (thể hiện 2 cách nói tương đương nghĩa). Theo đúng quyết định nhất quán
từ đợt 4 (câu nối bằng "／"), tôi KHÔNG gán pair_group cho các cặp "=" này, coi là 2
dòng đơn độc lập. Xin xác nhận lại nếu bạn muốn thống nhất một cách xử lý khác cho tất
cả các cặp kiểu "＝" / "／" trong toàn bộ sách.

## Kết quả 5 phép tự kiểm tra A–E (đợt 6)

- A, B, C: chưa áp dụng.
- D (khóa ngoại): ĐÃ KIỂM bằng script — `lesson__slug` (the-lich-su, dong-tu-cho-nhan,
  mot-so-quy-tac-chia-dong-tu-co-quy-tac) đều tồn tại trong 01; `pattern__code` trong
  05 đều tồn tại trong 04, không mồ côi.
- E (không trùng): ĐÃ KIỂM — 17 code mới không trùng 23 code cũ; kiểm tra thêm cặp
  (pattern__code, display_order) trong 05 không có trùng lặp (không có lỗi đánh số).

## Mâu thuẫn / điểm mơ hồ phát hiện đợt này

1. Quyết định gộp 5 ví dụ trang 17 vào pattern đã có (đặc biệt điểm mơ hồ về
   お/ご～でいらっしゃる, đã nêu ở trên).
2. Cách đưa danh sách quy tắc 丁寧語 (không phải câu hoàn chỉnh) vào file 05 là cách xử
   lý suy luận riêng của tôi để không mất dữ liệu, không phải cấu trúc chuẩn của file.
3. Chưa đưa danh sách từ お/ご đính kèm cuối bảng 丁寧語 (お名前, お仕事, ご住所...) vào
   đâu cả — cần bạn quyết định có cần bổ sung không, và bổ sung vào đâu.

## Việc cần làm ở đợt sau

- Trang 18-21 (よくある間違った敬語の使用例, 二重敬語, プライベート→ビジネス, クッション言葉,
  日常言語→丁寧な言葉遣い) → file 06_keigo_phrase_pair.csv.
- Trang 19 phần "1.1 dùng quá mức" và "1.2 giới trẻ" có các cặp SAI/ĐÚNG rõ ràng (đánh
  dấu ×/〇) — đây sẽ là nơi cột `is_correct=false` lần đầu được dùng.

---

# BÁO CÁO KIỂM TRA — Đợt 7

## Phạm vi đã làm
- Trang 18 (よくある間違った敬語の使用例, プライベート→ビジネス)
- Trang 19 (1.1 二重敬語 "dùng quá mức", 1.2 thuật ngữ giới trẻ)
- Trang 20 (2. Từ đệm / クッション言葉)
- Trang 21 (3. Khác: 5 cặp どう→いかが + bảng 日常言語→丁寧な言葉遣い)

## Bảng số dòng

| File | Số dòng thêm đợt này | Tổng số dòng |
|---|---|---|
| 06_keigo_phrase_pair.csv | 63 | 63 |

## Phân bổ lesson__slug theo ranh giới trang (QUAN TRỌNG — cần bạn xác nhận)

Mục lục ghi "3. THAM KHẢO" bắt đầu từ trang 19, nên tôi suy luận:
- **wrong_usage, noun_business (trang 18)** → vẫn thuộc lesson
  `mot-so-quy-tac-chia-dong-tu-co-quy-tac` (phụ lục của mục "MỘT SỐ QUY TẮC..." trang
  16-18, CHƯA bước sang THAM KHẢO).
- **double_keigo, baito_keigo, cushion, daily_polite (trang 19-21)** → thuộc lesson
  `tham-khao`.

Đây là suy luận dựa trên ranh giới trang trong mục lục, không phải PDF nói rõ ràng
từng bảng thuộc lesson nào. Xin xác nhận cách chia này có đúng ý bạn không.

## Số dòng theo pair_type

| pair_type | Số dòng |
|---|---|
| wrong_usage | 5 |
| noun_business | 10 |
| double_keigo | 4 |
| baito_keigo | 5 |
| cushion | 21 |
| daily_polite | 18 |

`display_order` đánh số RIÊNG trong phạm vi mỗi `pair_type` (bắt đầu lại từ 1), vì
file này không có cột `code`/`id` riêng — tôi coi `pair_type` (kết hợp `lesson__slug`)
là "bản ghi cha" hợp lý nhất cho việc đánh số. Xin xác nhận cách hiểu này.

## Các quyết định / suy luận cần bạn xác nhận

### 1. double_keigo: 1 câu sai có 2 câu đúng thay thế
Ví dụ 1 (お読みになられる) có 1 câu × và 2 câu 〇. Tôi tách thành **2 dòng riêng**, cùng
`casual` (câu sai lặp lại), khác `polite` (2 lựa chọn đúng khác nhau), cùng
`group_label` là công thức giải thích lỗi ("お読みになられる＝「お読みになる」＋「れる・
られる」"). Đây là suy luận về cách trải dữ liệu của tôi, không phải chỉ dẫn tường
minh.

### 2. group_label chỉ dùng cho double_keigo và cushion
File chỉ định nghĩa rõ group_label cho `cushion` (tiêu đề nhóm màu cam). Tôi tự quyết
định ÁP DỤNG THÊM group_label cho `double_keigo` (dùng công thức giải thích lỗi làm
label, ví dụ "ご案内してさしあげる＝「ご案内する」＋「さしあげる」") vì PDF có sẵn các dòng
tiêu đề/giải thích riêng cho từng cặp. Các pair_type còn lại (wrong_usage,
noun_business, baito_keigo, daily_polite) để group_label TRỐNG vì PDF trình bày dạng
bảng phẳng, không có tiêu đề nhóm riêng cho từng dòng.

### 3. cushion: 2 câu ví dụ mở đầu không có tiêu đề cam, và 1 tiêu đề dạng trích dẫn
Mục "2. Từ đệm" có 2 câu ví dụ đầy đủ ngay sau tiêu đề chương (không có tiêu đề cam
riêng) → tôi để `group_label` TRỐNG cho 2 dòng đầu (display_order 1-2).
Tiêu đề "「恐れ入りますが...」そして「さしつかえなければ...」" trước 2 câu cuối — tôi coi
đây cũng là một group_label (dù về hình thức là câu trích dẫn, không hẳn là "tiêu đề
cam" điển hình như 2 tiêu đề kia) — xin xác nhận cách xử lý này.

### 4. cushion: đoạn hội thoại A/B trong nhóm "言いにくいとき／謝るとき／断るとき"
File 06 không có cột speaker (khác file 05). Tôi đưa cả 2 lượt lời (A：○○時に約束して
いたのですが... và B：まことに申しわけありませんが...ただいま...) làm 2 dòng `polite`
riêng biệt, cùng group_label, không có cách nào đánh dấu đây là hội thoại trong schema
hiện tại của file 06 — xin bạn xác nhận cách xử lý này là chấp nhận được.

### 5. baito_keigo dòng 2: vế đúng có chứa "／" nối 2 cách nói
"こちらコーヒーでございます。／をおもちいたしました。" — vế thứ hai bị cụt (thiếu chủ
ngữ/tân ngữ rõ ràng, có thể PDF ý là "（コーヒーを）お持ちいたしました。"). Tôi giữ
NGUYÊN VĂN như PDF in, KHÔNG tự suy diễn thêm chữ để hoàn chỉnh câu, vì làm vậy sẽ là
"sáng tác". Xin bạn kiểm tra lại bản gốc.

### 6. Trùng lặp giữa các pair_type khác nhau (không phải lỗi)
Cặp "今日 → 本日" xuất hiện ở CẢ `noun_business` (trang 18) LẪN `daily_polite` (trang
21) — đây không phải trùng lặp lỗi, vì 2 bảng khác nhau trong PDF đều liệt kê cặp này
(một bảng về "biến đổi danh từ kinh doanh", một bảng về "lời nói thường ngày → lịch
sự"). Tôi giữ cả 2 dòng như PDF trình bày.

## Kết quả 5 phép tự kiểm tra A–E (đợt 7)

- A, B, C: chưa áp dụng.
- D (khóa ngoại): ĐÃ KIỂM bằng script — toàn bộ `lesson__slug` dùng trong file 06
  (mot-so-quy-tac-chia-dong-tu-co-quy-tac, tham-khao) đều tồn tại trong
  01_keigo_lesson.csv.
- E (không trùng): ĐÃ KIỂM — không có cặp (pair_type, display_order) nào trùng lặp;
  đã xác nhận toàn bộ giá trị `pair_type` chỉ nằm trong đúng 6 giá trị cho phép
  (wrong_usage, noun_business, double_keigo, baito_keigo, cushion, daily_polite).

## Mâu thuẫn / điểm mơ hồ phát hiện đợt này

1. Ranh giới lesson__slug giữa trang 18 và trang 19 dựa trên suy luận từ mục lục
   (đã nêu ở mục "Phân bổ lesson__slug" phía trên).
2. Câu ví dụ "こちらコーヒーでございます。／をおもちいたしました。" có vẻ bị cụt/thiếu chữ
   (mục 5 ở trên).
3. Cách xử lý đoạn hội thoại A/B trong file 06 (không có cột speaker) — đã nêu ở mục 4.

## Việc cần làm ở đợt sau

Toàn bộ phần LÝ THUYẾT (trang 1-21) đã xử lý xong. Đợt tiếp theo sẽ chuyển sang phần
BÀI TẬP (trang 22-54): bắt đầu với LUYỆN TẬP (trang 22-24) cho 2 file
07_exercise_set.csv và 08_exercise_section.csv, sau đó 09/10 — chờ lệnh bạn.

---

# ĐỢT 7.1 — SỬA LỖI VÀ ĐẾM NGƯỢC

Đã thực hiện đúng 8 mục sửa lỗi theo yêu cầu. File 01 không đổi. Đã backup 5 file gốc
trước khi sửa (dùng script Python để đảm bảo chính xác ở quy mô sửa lớn, không sửa tay).

## [1] Bổ sung cột 丁寧語 vào 03_keigo_form.csv

Đã thêm 35 dòng (34 động từ, riêng いる có 2 dạng います／おります), style_code=teinei,
is_irregular=false, note_vi trống, verb__reading trống (PDF không in cách đọc).
`わかる` → `わかりました` (chép đúng như PDF in, không phải わかります — sách dùng dạng
quá khứ cho từ này).

## [2] Thêm dòng thiếu vào 06_keigo_phrase_pair.csv

Đã chèn dòng thứ 5 của bảng よくある間違った敬語の使用例:
casual = 資料は拝見されましたでしょうか。 / polite = 資料はご覧いただけますしたでしょうか。
(giữ nguyên lỗi chính tả "ご覧いただけますした" trong sách, không sửa). Đã đánh lại
display_order của pair_type wrong_usage thành 1..6.

## [3] Bỏ phân loại kenjo1/kenjo2 bịa, dùng mã `kenjo`

- 03_keigo_form.csv: 48 dòng đã đổi style_code từ kenjo1/kenjo2 → kenjo (gồm toàn bộ
  dòng is_irregular=false + 5 dòng 拝 trang 9 dù is_irregular=true).
- Đã kiểm chứng: KHÔNG còn dòng nào có style_code kenjo1/kenjo2 mà is_irregular=false.
- 04_keigo_pattern.csv: 13 dòng thuộc lesson `khiem-nhuong-ngu` đã đổi style_code
  thành `kenjo` (kể cả `kenjo-uketamawaru`, `kenjo-zonjiru-zonjiageru` — dòng này
  trước để trống, nay cũng đặt `kenjo`).
- CHƯA đổi 4 dòng thuộc trang 17 (kenjo-o-go-suru-itasu, kenjo-o-go-sasete-itadakimasu,
  kenjo-settoji-o-go-so-hei: kenjo1; kenjo-domo-me: kenjo2) vì yêu cầu chỉ nói "13 mẫu
  khiêm nhường" (đúng 13 mẫu trang 8-10), không nhắc tới 4 mẫu trang 17. **Xin xác nhận
  có cần áp dụng luôn cho 4 dòng này không** — nếu có tôi sẽ sửa tiếp.

## [4] Chuyển 23 dòng "quy tắc biến đổi" từ file 05 sang file 06

- Đã xóa khỏi 05: 11 dòng của `teinei-u-gozaimasu` (display_order cũ 6-16) + toàn bộ
  12 dòng của `teinei-hen-doi`. 5 dòng câu ví dụ còn lại của `teinei-u-gozaimasu` vẫn
  đúng display_order 1..5 (không cần đánh lại vì đã sẵn liên tục).
- Đã thêm vào 06: pair_type MỚI `adj_gozaimasu` (11 dòng, lesson=the-lich-su) và
  `teinei_rule` (12 dòng, lesson=mot-so-quy-tac-chia-dong-tu-co-quy-tac). 2 dòng quy
  tắc chung (không có →) đã để casual TRỐNG, đặt cả câu vào polite, đúng như cách xử
  lý cushion.
- **Lưu ý quan trọng**: file 06 giờ có TỔNG CỘNG 8 giá trị pair_type (6 giá trị gốc +
  2 giá trị mới adj_gozaimasu, teinei_rule) — khác với mô tả ban đầu "đúng 6 giá trị".
  Đây là thay đổi CHỦ ĐỘNG theo đúng yêu cầu sửa lỗi lần này, xin bạn lưu ý khi nạp dữ
  liệu vào hệ thống (constraint CHECK ở cột pair_type nếu có cần cập nhật thêm 2 giá
  trị này).
- Đã xóa dòng pattern `teinei-hen-doi` khỏi 04_keigo_pattern.csv.

## [5] Gộp 知る vào 知っている

- 02_keigo_verb.csv: đã xóa dòng `知る`, đánh lại display_order liên tục 1..47.
- 03_keigo_form.csv: đã xóa 2 dòng (知る,kenjo1,存じ上げる,true) và
  (知る,kenjo2,存じる,true) — đây là bản trùng, vì 知っている đã sẵn có đúng 2 dòng này
  từ đợt 3. Kết quả 知っている hiện có đúng 5 dòng: sonkei(ご存じです,false),
  kenjo2(存じる,true), kenjo1(存じ上げる,true), kenjo(承知する,false — đổi từ kenjo2 do
  mục 3), teinei(知っています,false — mới thêm ở mục 1). Khớp với 3 dạng謙譲語 yêu cầu
  (存じる, 存じ上げる, 承知する).
- KHÔNG gộp 与える/あげる, KHÔNG gộp 訪ねる/たずねる — giữ nguyên như đợt 3.

## [6] Sửa lỗi in ở tiêu đề mẫu sonkei-de-irassharu

Title đã sửa "でいっらしゃる"→"でいらっしゃる". explanation_vi đã ghi: "Bản in gốc trang 5
ghi nhầm là「でいっらしゃる」." — đây là ngoại lệ DUY NHẤT của nguyên tắc chép nguyên,
theo đúng chỉ đạo của bạn.

## [7] Điền reading cho 賜る

Cả 2 dòng (受け取る, 賜る) và (もらう, 賜る) trong 03_keigo_form.csv nay đều có
reading = たまわる.

## [8] PHÉP KIỂM TRA F — ĐẾM NGƯỢC TỪ PDF (trang 4-21)

Đã viết script Python đối chiếu TỪNG bảng/danh sách trang 4-21 với dữ liệu CSV hiện
tại (sau khi đã sửa xong mục 1-7 ở trên), đếm số cặp/số dòng thực có trong PDF so với
số cặp/số dòng tồn tại trong CSV.

| Bảng / danh sách | Trang | PDF có | CSV có | Khớp? |
|---|---|---|---|---|
| Bảng 尊敬語 đặc biệt (14 dòng sách → 23 cặp verb-form) | 4 | 23 | 23 | ✅ KHỚP |
| Bảng Khiêm nhường ngữ I (13 dòng sách → 16 cặp) | 7 | 16 | 16 | ✅ KHỚP |
| Bảng Khiêm nhường ngữ II (5 dòng sách → 7 cặp) | 7 | 7 | 7 | ✅ KHỚP |
| Bảng 拝+漢字一字 (5 dòng) | 9 | 5 | 5 | ✅ KHỚP |
| Bảng 4 cột — cột 基本形 (34 động từ) | 13-16 | 34 | 34 | ✅ KHỚP |
| Bảng 4 cột — cột 尊敬語 (atomic forms) | 13-16 | 62 | 62 | ✅ KHỚP |
| Bảng 4 cột — cột 謙譲語 (atomic forms) | 13-16 | 62 | 62 | ✅ KHỚP |
| Bảng 4 cột — cột 丁寧語 (atomic forms, MỚI bổ sung mục [1]) | 13-16 | 35 | 35 | ✅ KHỚP |
| 10 mẫu tôn kính ngữ (số pattern) | 5-6 | 10 | 10 | ✅ KHỚP |
| Tổng ví dụ của 10 mẫu tôn kính ngữ (26 gốc + 3 bổ sung từ trang 17) | 5-6 | 29 | 29 | ✅ KHỚP |
| 13 mẫu khiêm nhường ngữ (số pattern) | 8-10 | 13 | 13 | ✅ KHỚP |
| Tổng ví dụ của 13 mẫu khiêm nhường (35 gốc + 2 bổ sung từ trang 17) | 8-10 | 37 | 37 | ✅ KHỚP |
| 形容詞～うございます — câu ví dụ đầy đủ (không tính bảng biến đổi) | 11 | 5 | 5 | ✅ KHỚP |
| 形容詞～うございます — bảng biến đổi (1)(2)(3), nay ở file 06 | 11 | 11 | 11 | ✅ KHỚP |
| 6 mẫu động từ cho/nhận (số pattern) | 12 | 6 | 6 | ✅ KHỚP |
| Tổng ví dụ của 6 mẫu động từ cho/nhận | 12 | 12 | 12 | ✅ KHỚP |
| Số mẫu ngữ pháp MỚI từ trang 17 (không tính 2 mẫu gộp trùng + đã xóa teinei-hen-doi) | 17 | 9 | 9 | ✅ KHỚP |
| Tổng ví dụ của 9 mẫu mới trang 17 | 17 | 18 | 18 | ✅ KHỚP |
| 5 ví dụ trang 17 gộp vào mẫu đã có (nasaru/da/irassharu/moushiageru/itadaku) | 17 | 5 | 5 | ✅ KHỚP |
| 丁寧語 quy tắc biến đổi (10 mục sách → 12 dòng casual/polite), nay ở file 06 | 17 | 12 | 12 | ✅ KHỚP |
| Bảng よくある間違った敬語の使用例 (đã sửa đủ 6 dòng ở mục [2]) | 18 | 6 | 6 | ✅ KHỚP |
| Bảng プライベート→ビジネス (Biến đổi danh từ) | 18 | 10 | 10 | ✅ KHỚP |
| Mục 1.1 二重敬語 (4 cặp casual/polite từ 3 nhóm giải thích) | 19 | 4 | 4 | ✅ KHỚP |
| Mục 1.2 thuật ngữ giới trẻ | 19 | 5 | 5 | ✅ KHỚP |
| Mục 2 Từ đệm / クッション言葉 (2 câu mở đầu + 7+10 cụm 2 nhóm cam + 2 câu cuối) | 20 | 21 | 21 | ✅ KHỚP |
| Mục 3 (5 cặp どう→いかが) + bảng 日常言語→丁寧な言葉遣い (13 cặp) | 21 | 18 | 18 | ✅ KHỚP |

**Toàn bộ 26 phép đếm ngược đều KHỚP.** Không phát hiện dòng nào bị thiếu ở phạm vi
trang 4-21 sau khi sửa xong 8 mục trên. Script đếm được lưu tại
`/tmp/check_F.py` trong container làm việc (không phải phần xuất cho người dùng)
để có thể chạy lại đối chiếu bất kỳ lúc nào nếu cần.

### Cách tính đối chiếu (để minh bạch phương pháp đếm)
Với các bảng có ô chứa NHIỀU dạng gộp (vd "いらっしゃる・おいでになる ← 行く、来る、いる"),
"PDF có" được tính theo SỐ CẶP (verb, form) sau khi tách — không phải số dòng vật lý
in trên trang — vì đó là đơn vị dữ liệu thực sự cần có mặt trong CSV. Số dòng vật lý
gốc trên trang được ghi trong ngoặc ở cột "Bảng/danh sách" để đối chiếu ngược lại
bằng mắt nếu cần.

## Việc cần làm ở đợt sau

Chờ bạn xác nhận điểm còn mở ở mục [3] (4 dòng kenjo1/kenjo2 của trang 17 trong
04_keigo_pattern.csv có cần đổi thành `kenjo` luôn không). Sau đó tiếp tục sang phần
BÀI TẬP (trang 22 trở đi) theo lệnh của bạn.

---

# ĐỢT 8 — LUYỆN TẬP + BÀI TẬP 1-5

Đã đọc kỹ đáp án trang 52-53 TRƯỚC khi viết file, dùng script Python để tránh sai sót
transcription ở quy mô 94 câu / 311 phương án. File 01-06 không đổi.

## Số dòng thêm vào từng file

| File | Số dòng thêm | Ghi chú |
|---|---|---|
| 07_exercise_set.csv | 17 | Đủ cả 17 bộ đề ngay đợt này, tổng question_count = **262** (khớp yêu cầu) |
| 08_exercise_section.csv | 10 | 5 section của LUYỆN TẬP + 5 section (1 mỗi bộ) của BT1-5 |
| 09_question.csv | 94 | 34 (LUYỆN TẬP) + 10+10+10+15+15 (BT1-5) |
| 10_question_option.csv | 311 | 71 (LUYỆN TẬP) + 40+40+40+60+60 (BT1-5) |

## [A] Tách section — LUYỆN TẬP ra đúng 5 section

Đã tách đúng như yêu cầu: number=1 (問題1, 8 câu), number=2 (問題2, 16 câu), number=3/4/5
(3 đoạn hội thoại của 問題3, lần lượt 2/5/3 câu = 10 câu, cùng chung instruction_jp
"問題3"). passage_jp của mỗi đoạn đã thay các phương án trong ngoặc bằng `____` (không
để lộ đáp án trong đoạn văn dùng chung).

## [D] Tách phương án in trong ngoặc

Đã tách toàn bộ câu LUYỆN TẬP 問題1/2/3 — phương án gốc nằm trong （A／B）hoặc
（A／B／C）được đưa vào bảng 10_question_option.csv, stem_jp chỉ còn `____`. Số phương
án đúng theo sách: 問題1 có 6 câu 2-phương-án + 2 câu 3-phương-án (câu 6,7,8); 問題2 và
問題3 đều 2-phương-án cho tất cả câu.

## [E] Phân loại question_type theo TỪNG CÂU

BÀI TẬP 3 và 5: toàn bộ ordering. Đã soát riêng từng câu BT5 — phát hiện **câu 8 có
★ ở vị trí thứ 2** (khác 14 câu ordering còn lại trong đợt này đều ở vị trí thứ 3):
nguyên văn "引き続き＿＿ ＿★＿ ＿＿ ＿＿、こちらのページで報告させていただきます。" — đã
đặt star_position=2 cho riêng câu này, xác nhận khớp bằng phép A (script). Còn lại:
LUYỆN TẬP, BT1, BT2, BT4 đều mcq_blank.

## Kết quả kiểm tra A-G (chạy bằng script, không tính tay)

**A — star_position vs correct_order vs option đúng**: Tất cả 25 câu ordering (10 BT3
+ 15 BT5) đều KHỚP, kể cả câu BT5-q08 có star_position khác thường. Không có câu lệch.

**B — số dòng file 09 theo exercise_set vs question_count**:

| exercise_set | Kỳ vọng (đáp án trang 52-53) | Thực tế (file 09) | Khớp? |
|---|---|---|---|
| luyen-tap | 34 | 34 | ✅ |
| bai-tap-1 | 10 | 10 | ✅ |
| bai-tap-2 | 10 | 10 | ✅ |
| bai-tap-3 | 10 | 10 | ✅ |
| bai-tap-4 | 15 | 15 | ✅ |
| bai-tap-5 | 15 | 15 | ✅ |

**C — mỗi question__code có đúng 1 is_correct=true**: Toàn bộ 94/94 mã câu hỏi đều
đúng 1 dòng true. Không có vi phạm.

**D — khóa ngoại**: Không có `question__code` nào trong file 09 mà `exercise_set__slug`
không tồn tại ở file 07; không có (exercise_set, section_number) nào ở file 09 mà
không tồn tại ở file 08; không có dòng nào ở file 10 mà `question__code` không tồn tại
ở file 09. Tất cả đều sạch (kiểm bằng script đối chiếu tập hợp).

**E — không trùng code**: 94 mã câu hỏi trong file 09 đều duy nhất (94 code / 94 dòng).

**F — ĐẾM NGƯỢC TỪ PDF** (đối chiếu số câu thật trên từng trang với số dòng đã tạo):

| Bộ đề | Trang | PDF có | CSV có | Khớp? |
|---|---|---|---|---|
| LUYỆN TẬP 問題1 | 22 | 8 | 8 | ✅ KHỚP |
| LUYỆN TẬP 問題2 | 22-23 | 16 | 16 | ✅ KHỚP |
| LUYỆN TẬP 問題3, đoạn (1) | 23 | 2 | 2 | ✅ KHỚP |
| LUYỆN TẬP 問題3, đoạn (2) | 23-24 | 5 | 5 | ✅ KHỚP |
| LUYỆN TẬP 問題3, đoạn (3) | 24 | 3 | 3 | ✅ KHỚP |
| BÀI TẬP 1 | 25 | 10 | 10 | ✅ KHỚP |
| BÀI TẬP 2 | 26 | 10 | 10 | ✅ KHỚP |
| BÀI TẬP 3 | 27 | 10 | 10 | ✅ KHỚP |
| BÀI TẬP 4 | 28-29 | 15 | 15 | ✅ KHỚP |
| BÀI TẬP 5 | 29-30 | 15 | 15 | ✅ KHỚP |

Tôi đã thực sự đếm lại từng câu trên từng trang (không suy ra từ mục lục) — kết quả
khớp 100% với số dòng đã tạo. Không có câu nào bị thiếu.

**G — đếm số dòng correct_order khác rỗng**: **25** (đúng bằng 10 của BT3 + 15 của
BT5, khớp yêu cầu).

## question_count 17 bộ đề (đếm theo bảng đáp án trang 52-54, KHÔNG theo mục lục)

LUYỆN TẬP=34, BT1=10, BT2=10, BT3=10, BT4=**15** (mục lục ghi nhầm 10 câu), BT5=15,
BT6=10, BT7=10, BT8=10, BT9=10, BT10=10, BT11=14, BT12=15, BT13=19, BT14=18, BT15=20,
BT16=32. **Tổng = 262**, khớp đúng số bạn cho trước — tôi KHÔNG cần dừng lại báo cáo
lệch.

## Những chỗ tôi không chắc chắn (theo đúng nguyên tắc "chép phương án khả dĩ nhất +
ghi chú")

1. **File 09 có cột "number" (số câu trong 問題) tách biệt với "code"** — vì
   LUYỆN TẬP 問題3 được yêu cầu "đánh number liên tục 1..10" dù chia 3 section khác
   nhau, tôi hiểu cột `number` = vị trí câu hỏi trong PHẠM VI 問題 gốc (liên tục 1-10),
   KHÔNG reset về 1 khi sang section mới. Đây là suy luận của tôi từ cách đặt code
   (lt-m3-q01..q10) — xin xác nhận cách hiểu này đúng ý bạn.
2. **passage_jp của 3 đoạn LUYỆN TẬP 問題3** đã thay toàn bộ phương án trong ngoặc bằng
   `____` (không chỉ trong stem_jp mà cả trong đoạn văn dùng chung) — vì nếu để nguyên
   phương án trong passage_jp thì học sinh nhìn đoạn văn sẽ thấy đáp án của câu khác.
   Điều này khiến stem_jp của từng câu và đoạn tương ứng trong passage_jp có nội dung
   TRÙNG NHAU (không rút gọn) — đây là lựa chọn thiết kế của tôi, không phải chỉ dẫn
   tường minh, xin xác nhận.
3. **LUYỆN TẬP 問題3 câu 5** ("C「ああ、そう。じゃ、私が先方に直接お電話を＿＿。"): PDF
   không đóng ngoặc kép 」 trước khi ngắt đoạn (chuyển sang dòng 【○○会社に電話をかけて
   話している】) — tôi giữ nguyên dấu ngoặc mở chưa đóng, không tự thêm 」.
4. **（ピッピーッ）ở đầu LUYỆN TẬP 問題2 câu 14**: tôi coi là một phần của stem_jp (âm
   thanh mô phỏng, không phải context_note kiểu （レストランで）), không tách riêng.
5. Chưa động đến BÀI TẬP 6-16 (đợt sau) — đặc biệt lưu ý BÀI TẬP 6 và 8 có một số câu
   cuối là dạng ★ dù tiêu đề nói điền （ ）, sẽ cần soát từng câu kỹ ở đợt xử lý các bộ
   đó.

## Việc cần làm ở đợt sau

BÀI TẬP 6-10 (trang 32-35, đáp án trang 53) — lưu ý đặc biệt BÀI TẬP 6 và 8 có câu
dạng ★ trộn lẫn với câu （ ）trong cùng 1 bộ, phải soát từng câu — chờ lệnh bạn.

---

# ĐỢT 9 — BÀI TẬP 6-13

Đã đọc đáp án trang 53 TRƯỚC khi viết file, dùng script Python để tránh sai sót ở quy
mô 98 câu / 336 phương án. File 01-07 không đổi. Đã NỐI THÊM vào 08, 09, 10 (giữ
nguyên toàn bộ dòng cũ của đợt 8 — xác nhận bằng script đối chiếu tổng số dòng trước/
sau).

## Số dòng thêm vào từng file

| File | Số dòng thêm đợt này | Tổng sau đợt 9 |
|---|---|---|
| 08_exercise_section.csv | 10 | 20 |
| 09_question.csv | 98 | 192 |
| 10_question_option.csv | 336 | 703 |

## [A] Bẫy dạng câu hỏi — đã phát hiện đúng theo cảnh báo

Đã nhìn TỪNG CÂU thay vì theo tiêu đề 問題, phát hiện đúng như cảnh báo:
- **BÀI TẬP 6**: câu 1-6 mcq_blank, câu **7,8,9,10 là ordering** (đáp án in dạng
  "1(2413)", "3(4132)", "3(4132)", "4(2341)").
- **BÀI TẬP 8**: câu 1-5 mcq_blank, câu **6,7,8,9,10 là ordering** (đáp án
  "4(2341)","1(4213)","2(3241)","3(4231)","3(4132)").
- Phát hiện thêm: **BÀI TẬP 8 câu 8** có ★ ở vị trí thứ 2 (không phải vị trí 3 như
  14/15 câu ordering còn lại của đợt này) — nguyên văn "20日までに＿＿ ＿★＿ ＿＿ ＿＿でき
  ます。" Đã xác nhận đúng bằng phép A (digit thứ 2 của "3241" = "2" khớp đáp án ngoài
  ngoặc "2").
- Tổng cộng đúng **9 dòng correct_order khác rỗng** (4 của BT6 + 5 của BT8), khớp
  chính xác yêu cầu.

## [B] Bẫy đoạn văn — BÀI TẬP 12

Đã tách đúng 3 section theo yêu cầu:
- number=1: 問題1, câu 1-10, mcq_blank, passage_jp trống.
- number=2: 問題2 khung thứ nhất (đoạn "恩師のお宅へ年始に…"), chứa câu 11, 12 — cả 2 đều
  question_type=cloze_passage, stem_jp chỉ ghi "(11)"/"(12)", KHÔNG chép lại đoạn văn.
- number=3: 問題2 khung thứ hai (lá thư "こんにちは。…6年1組一同"), chứa câu 13, 14, 15 —
  cùng cách xử lý cloze_passage.
- Section 2 và 3 dùng CHUNG một instruction_jp
  "問題2 次の文章を読んで、（11）から（15）の中に入る最もよいものを、1・2・3・4から一つ選
  びなさい。".

## [C] Quy ước giữ nguyên từ đợt 8

`____` cho chỗ trống, `__★__` cho ô sao, giữ nguyên dạng `（11）`（12）...trong
passage_jp (không đổi thành `____`, vì đây là dạng cloze_passage khác với dạng
（A／B）). context_note đã dùng cho: BT13 câu 2 (`（手紙で）`) và câu 4 (`（メールで）`).
Không phát hiện thêm chỗ nào có furigana ruby thật sự trong trang 32-43 (không có ký
hiệu {漢字|かんじ} nào cần thêm ở đợt này). explanation_vi để trống toàn bộ 98 dòng.

## Kết quả kiểm tra A-G (chạy lại toàn bộ 192 câu của cả 2 đợt bằng script)

**A — star_position/correct_order/option đúng**: Toàn bộ 34 câu ordering (25 của đợt
8 + 9 của đợt 9) đều KHỚP, không có câu lệch, kể cả 2 trường hợp star_position khác
thường (BT5-q08 vị trí 2, BT8-q08 vị trí 2).

**B — số dòng theo exercise_set vs question_count**:

| exercise_set | Kỳ vọng | Thực tế | Khớp? |
|---|---|---|---|
| bai-tap-6 | 10 | 10 | ✅ |
| bai-tap-7 | 10 | 10 | ✅ |
| bai-tap-8 | 10 | 10 | ✅ |
| bai-tap-9 | 10 | 10 | ✅ |
| bai-tap-10 | 10 | 10 | ✅ |
| bai-tap-11 | 14 | 14 | ✅ |
| bai-tap-12 | 15 | 15 | ✅ |
| bai-tap-13 | 19 | 19 | ✅ |

**C — mỗi question__code có đúng 1 is_correct=true**: Toàn bộ 192/192 câu (cả 2 đợt)
đều đúng 1 dòng true, không có vi phạm.

**D — khóa ngoại**: Không có `question__code` nào mà `exercise_set__slug` không tồn
tại ở file 07; không có (exercise_set, section_number) nào ở file 09 mà không tồn tại
ở file 08 (đối chiếu cả 20 section); không có dòng nào ở file 10 mà `question__code`
không tồn tại ở file 09. Tất cả sạch.

**E — không trùng code**: 192 mã câu hỏi (cả 2 đợt) đều duy nhất.

**F — ĐẾM NGƯỢC TỪ PDF trang 32-43**:

| Bộ đề | Trang | PDF có | CSV có | Khớp? |
|---|---|---|---|---|
| BÀI TẬP 6 | 32 | 10 | 10 | ✅ KHỚP |
| BÀI TẬP 7 | 32-33 | 10 | 10 | ✅ KHỚP |
| BÀI TẬP 8 | 33 | 10 | 10 | ✅ KHỚP |
| BÀI TẬP 9 | 34 | 10 | 10 | ✅ KHỚP |
| BÀI TẬP 10 | 35 | 10 | 10 | ✅ KHỚP |
| BÀI TẬP 11 | 36-37 | 14 | 14 | ✅ KHỚP |
| BÀI TẬP 12 問題1 | 38 | 10 | 10 | ✅ KHỚP |
| BÀI TẬP 12 問題2 khung 1 | 39 | 2 | 2 | ✅ KHỚP |
| BÀI TẬP 12 問題2 khung 2 | 40 | 3 | 3 | ✅ KHỚP |
| BÀI TẬP 13 | 41-43 | 19 | 19 | ✅ KHỚP |

Đã đếm lại thực tế từng câu trên từng trang (không suy từ mục lục hay tiêu đề 問題) —
khớp 100%, không thiếu câu nào.

**G — đếm số dòng correct_order khác rỗng**:
- Riêng đợt 9 (BT6-13): **9** dòng — đúng yêu cầu.
- Tổng cả 2 đợt (đợt 8 + đợt 9): 34 dòng (25+9), dùng để đối chiếu chéo, không phải
  con số yêu cầu của đợt này.

## Những chỗ tôi không chắc chắn / quyết định cần lưu ý

1. **BÀI TẬP 12 câu 3**: đáp án đúng là "おありでしたら" (option 1) — về ngữ pháp hơi lạ
   vì thường sẽ mong đợi "おありでしたら" hay "おありましたら" nhưng sách cho đáp án là
   option 1 = "おありでしたら". Tôi chép đúng theo bảng đáp án trang 53 ("1 3 1 2 4 3 3
   4 2 4"), không tự suy luận lại ngữ pháp.
2. **Đoạn văn BÀI TẬP 12 khung 2 (lá thư)**: đã giữ nguyên toàn bộ cấu trúc dòng
   (chào hỏi, chữ ký "6年1組一同", ngày tháng, tên người nhận "田中よし子先生") vào
   passage_jp, kể cả những dòng không chứa chỗ trống nào — vì đây là "nguyên đoạn"
   theo đúng yêu cầu, không rút gọn.
3. Chưa xử lý BÀI TẬP 14-16 (trang 43-51, đáp án trang 53-54) — đợt sau.

## Việc cần làm ở đợt sau

BÀI TẬP 14-16 (trang 43-51, đáp án trang 53-54) — đây là các bộ đề cuối cùng. Cần đặc
biệt chú ý vì BÀI TẬP 16 có tới 32 câu (bộ lớn nhất) — chờ lệnh bạn.

---

# ĐỢT 10 — BÀI TẬP 14-16

Đã đọc đáp án trang 54 (và phần cuối trang 53 cho BT14) TRƯỚC khi viết file. Dùng
script Python, viết đầy đủ cả 32 câu của BÀI TẬP 16 trong một script (không cần dừng
giữa chừng vì không bị giới hạn bởi độ dài câu trả lời hiển thị — toàn bộ dữ liệu nằm
trong file script, không phải gõ tay trong khung chat). File 01-07 không đổi. Đã NỐI
THÊM vào 08, 09, 10.

## Số dòng thêm vào từng file

| File | Số dòng thêm đợt này | Tổng sau đợt 10 (toàn bộ 3 đợt) |
|---|---|---|
| 08_exercise_section.csv | 3 | 23 |
| 09_question.csv | 70 | 262 |
| 10_question_option.csv | 280 | 983 |

## Cấu trúc đúng như yêu cầu

Cả 3 bộ đều mcq_blank thuần, mỗi bộ 1 section (number=1), passage_jp trống, không có
câu ordering nào. context_note dùng cho: BT14 câu 16 (`（電話で）`), câu 17 (`（パーティ
ーで）`); BT16 câu 16 (`（メールで）`).

## ⚠️ LỖI PHÁT HIỆN VÀ ĐÃ SỬA TRONG CHÍNH ĐỢT NÀY

Khi chạy phép D (khóa ngoại), phát hiện tôi đã QUÊN thêm 3 dòng section
(bai-tap-14/15/16, number=1) vào file 08_exercise_section.csv — dẫn đến toàn bộ 70
question__code của BT14-16 bị "mồ côi" so với file 08 (không tìm thấy cặp
(exercise_set, section_number) tương ứng). Đã phát hiện NGAY qua chính phép kiểm tra
D (không phải do bạn báo lại), và đã sửa bằng cách bổ sung 3 dòng thiếu, sau đó chạy
lại toàn bộ phép D — xác nhận sạch. Đây là lỗi thao tác (quên một bước ghi file), không
phải lỗi dữ liệu nội dung câu hỏi/đáp án.

## Kết quả kiểm tra A-G (chạy trên toàn bộ 262 câu của cả 3 đợt)

**A**: Toàn bộ 34 câu ordering (từ đợt 8+9) đều KHỚP. BT14-16 không có câu ordering
nào nên không phát sinh thêm phép thử A.

**B**:

| exercise_set | Kỳ vọng | Thực tế | Khớp? |
|---|---|---|---|
| bai-tap-14 | 18 | 18 | ✅ |
| bai-tap-15 | 20 | 20 | ✅ |
| bai-tap-16 | 32 | 32 | ✅ |

**C**: Toàn bộ 262/262 question__code đều đúng 1 dòng is_correct=true.

**D**: Sau khi sửa lỗi thiếu section nêu trên — sạch hoàn toàn (không còn orphan nào
ở cả 3 chiều: 09↔07, 09↔08, 10↔09).

**E**: 262 mã câu hỏi (toàn bộ 3 đợt) đều duy nhất, không trùng.

**F — ĐẾM NGƯỢC TỪ PDF trang 43-51**:

| Bộ đề | Trang | PDF có | CSV có | Khớp? |
|---|---|---|---|---|
| BÀI TẬP 14 | 43-45 | 18 | 18 | ✅ KHỚP |
| BÀI TẬP 15 | 46-48 | 20 | 20 | ✅ KHỚP |
| BÀI TẬP 16 | 48-51 | 32 | 32 | ✅ KHỚP |

Đã đếm lại thực tế từng câu trên từng trang, đặc biệt BÀI TẬP 16 (32 câu, bộ lớn
nhất) — đếm đủ từ câu 1 đến câu 32, không rút gọn, không gộp câu, không bỏ phương án
nào (mỗi câu đều đủ 4 phương án).

**G**: Số dòng correct_order khác rỗng trong BT14-16 = **0** — đúng yêu cầu.

## Những chỗ không chắc chắn phát sinh ở đợt này

Không có điểm ngữ nghĩa/ngữ pháp nào đáng ngờ mới trong đợt này — 70 câu đều rõ ràng,
đáp án khớp logic ngữ pháp thông thường. Điểm duy nhất đáng ghi nhận là lỗi thao tác
(thiếu section) đã nêu và sửa ở trên.

---

# TỔNG KẾT PHẦN BÀI TẬP

## Bảng đối chiếu 17 bộ đề: question_count (file 07) vs số dòng thật (file 09)

| slug | question_count (07) | số dòng thật (09) | khớp? |
|---|---|---|---|
| luyen-tap | 34 | 34 | ✅ |
| bai-tap-1 | 10 | 10 | ✅ |
| bai-tap-2 | 10 | 10 | ✅ |
| bai-tap-3 | 10 | 10 | ✅ |
| bai-tap-4 | 15 | 15 | ✅ |
| bai-tap-5 | 15 | 15 | ✅ |
| bai-tap-6 | 10 | 10 | ✅ |
| bai-tap-7 | 10 | 10 | ✅ |
| bai-tap-8 | 10 | 10 | ✅ |
| bai-tap-9 | 10 | 10 | ✅ |
| bai-tap-10 | 10 | 10 | ✅ |
| bai-tap-11 | 14 | 14 | ✅ |
| bai-tap-12 | 15 | 15 | ✅ |
| bai-tap-13 | 19 | 19 | ✅ |
| bai-tap-14 | 18 | 18 | ✅ |
| bai-tap-15 | 20 | 20 | ✅ |
| bai-tap-16 | 32 | 32 | ✅ |
| **TỔNG** | **262** | **262** | **✅ KHỚP TUYỆT ĐỐI** |

## Các phép kiểm tra tổng toàn cục

- **Tổng số dòng file 09 = 262** ✅ (đúng bằng tổng question_count file 07)
- **Tổng số dòng có `correct_order` khác rỗng = 34** ✅ (25 câu ordering của BT3, BT5 +
  4 câu của BT6 + 5 câu của BT8)
- **Tổng số dòng có `question_type = cloze_passage` = 5** ✅ (đúng 5 câu 11-15 của
  BÀI TẬP 12, phần 問題2: bt12-q11, bt12-q12, bt12-q13, bt12-q14, bt12-q15)
- **Mọi question__code trong file 10 có đúng 1 dòng is_correct=true**: ĐÃ KIỂM bằng
  script trên toàn bộ 262 code — **không có code nào vi phạm**.
- Khóa ngoại toàn cục (09↔07, 09↔08, 10↔09): sạch hoàn toàn sau khi sửa lỗi thiếu
  section ở đợt 10.
- Không có `code` nào trùng trong toàn bộ 262 dòng file 09.
- File 08 hiện có 23 section (5 của LUYỆN TẬP + 3 của BÀI TẬP 12 + 15 bộ còn lại × 1
  section = 5+3+15 = 23).
- Kỹ thuật: cả 4 file (07,08,09,10) đều UTF-8 không BOM, xuống dòng LF, không có dòng
  nào bị lệch cấu trúc cột khi đọc lại bằng `csv.reader`.

## TOÀN BỘ NHỮNG ĐIỂM KHÔNG CHẮC CHẮN — GOM TỪ CẢ 3 ĐỢT (8, 9, 10)

### Từ đợt 8
1. **Cách hiểu cột `number` trong file 09** cho LUYỆN TẬP 問題3: tôi hiểu là đánh số
   liên tục 1-10 trong phạm vi 問題 gốc (không reset về 1 khi chuyển section 3→4→5).
   Đây là suy luận từ cách đặt `code` (lt-m3-q01..q10), không phải chỉ dẫn tường minh.
2. **passage_jp và stem_jp của LUYỆN TẬP 問題3 bị trùng nội dung có chủ đích**: mỗi câu
   hỏi lặp lại đúng câu chứa chỗ trống của nó (đã có sẵn trong passage_jp) để không bắt
   người đọc phải tự dò trong đoạn văn dài. Đây là lựa chọn thiết kế của tôi.
3. Câu 5 của LUYỆN TẬP 問題3 (đoạn 2): PDF không đóng dấu 」trước khi ngắt sang dòng
   【○○会社に電話をかけて話している】— tôi giữ nguyên dấu ngoặc mở chưa đóng.
4. （ピッピーッ）ở đầu LUYỆN TẬP 問題2 câu 14: coi là một phần của stem_jp, không tách
   thành context_note.

### Từ đợt 9
5. Không có điểm ngữ nghĩa mới đáng ngờ; BÀI TẬP 12 câu 3 đáp án sách chọn
   "おありでしたら" — tôi chép đúng theo bảng đáp án dù hơi lạ về ngữ pháp trực giác,
   không tự suy luận lại.
6. Đoạn văn BÀI TẬP 12 khung 2 (lá thư) giữ nguyên toàn bộ cấu trúc dòng (chào hỏi,
   chữ ký, ngày tháng, tên người nhận) vào passage_jp — không rút gọn.

### Từ đợt 10
7. Không phát sinh điểm ngữ nghĩa mới. Duy nhất có lỗi THAO TÁC (quên thêm 3 dòng
   section vào file 08) — đã tự phát hiện qua phép D và sửa ngay trong cùng đợt, đã
   xác nhận lại bằng cách chạy lại toàn bộ phép kiểm tra sau khi sửa.

### Điểm xuyên suốt cả 3 đợt cần bạn đặc biệt lưu ý
8. Toàn bộ `sentence_vi`/`explanation_vi` trong các bảng bài tập đều để TRỐNG theo
   đúng quy định gốc (sách không dịch, không có lời giải) — không phải thiếu sót.
9. Hai câu có `star_position` khác thường (không phải vị trí 3 như đa số câu ordering
   còn lại): **BÀI TẬP 5 câu 8** (vị trí 2) và **BÀI TẬP 8 câu 8** (vị trí 2) — cả hai
   đã được xác nhận đúng qua phép kiểm tra A của script, không phải suy đoán.

## Kết luận

Toàn bộ phần BÀI TẬP (07, 08, 09, 10) đã hoàn thành đủ 17/17 bộ đề, 262/262 câu hỏi,
983 phương án. Tất cả phép kiểm tra A-G và phép đếm ngược F qua cả 3 đợt (8, 9, 10)
đều khớp tuyệt đối với PDF, không còn dòng nào bị thiếu hoặc lệch đã biết ngoài các
điểm suy luận/thiết kế đã liệt kê ở trên (không phải lỗi dữ liệu).
