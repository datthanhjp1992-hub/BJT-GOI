"""
View của app practice_sheets: SC10 — tạo phiếu PDF.

Hai loại phiếu trên CÙNG một màn (`sheet_type`): ô kẻ luyện viết, và phiếu ôn
lại từ. Dùng chung phần chọn từ nên không tách thành hai trang.

Hai nguồn từ:
1. Chọn từ đã có trong hệ thống -> lưu qua bảng nối PracticeSheetWord.
2. Tải file CSV/Excel của riêng mình -> KHÔNG ghi gì vào bảng Vocabulary, chỉ
   cất vào PracticeSheet.custom_words. Quyết định của Dat: người học phải in
   được danh sách riêng mà không cần quyền admin và không làm bẩn từ điển chung.
"""
import logging

from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render

from apps.core import dataio
from apps.core.constants import SHEET_TYPE_RECALL
from apps.core.properties import message
from apps.core.utils import topic_filter_bar
from apps.vocabulary import selectors as vocab_selectors
from apps.vocabulary.models import Topic, Vocabulary

from .forms import SOURCE_UPLOAD, PracticeSheetForm
from .models import PracticeSheet, PracticeSheetWord
from .pdf_generator import PracticeSheetFontError, generate_sheet_pdf
from .wordsource import MAX_WORDS_PER_SHEET, WordItem, parse_word_file, template_headers

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
WORD_PICKER_LIMIT = 200

CONTENT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _selected_query(selected_topics, query=""):
    """Query string của đúng bộ lọc đang áp (dùng cho action của form POST)."""
    params = QueryDict(mutable=True)
    params.setlist("topic", [t.slug for t in selected_topics])
    if query:
        params["q"] = query
    encoded = params.urlencode()
    return ("?" + encoded) if encoded else ""


def _picker_context(request):
    """Danh sách từ để tích chọn, lọc theo chủ đề qua ?topic=<slug> (lặp được).

    Lọc theo CHỦ ĐỀ chứ không theo cấp độ BJT — cấp độ đã bị gỡ khỏi DB ngày
    13/09; mockup SC10 còn cột "Cấp độ" là bản cũ, đừng port ngược.

    Chọn được NHIỀU chủ đề, quan hệ HOẶC — giống thanh lọc ở SC05. Dùng chung
    `topic_filter_bar()` để hai màn không lệch hành vi.
    """
    topics = list(Topic.objects.all().order_by("name"))
    selected_topics, topic_filters, clear_query = topic_filter_bar(request, topics)
    query = (request.GET.get("q") or "").strip()

    # Dùng CHUNG bộ lọc với SC05 (apps.vocabulary.selectors) thay vì tự viết lại
    # điều kiện: hai màn cùng nói "chủ đề + từ khoá" thì phải cho ra cùng tập từ.
    words = vocab_selectors.filter_vocabulary(
        request.user, topics=selected_topics, query=query
    )
    word_total = words.count()

    return {
        "words": words[:WORD_PICKER_LIMIT],
        "word_total": word_total,
        "word_limit": WORD_PICKER_LIMIT,
        "word_query": query,
        "topics": topics,
        "selected_topics": selected_topics,
        "topic_filters": topic_filters,
        "clear_query": clear_query,
        # Form POST về đúng URL đang lọc, để lúc render lại (lỗi validate) danh
        # sách từ không nhảy về "tất cả chủ đề".
        "picker_action": request.path + _selected_query(selected_topics, query),
    }


def _render_create(request, form, extra=None):
    context = {
        "form": form,
        "active_nav": "practice_sheet",
        "max_words": MAX_WORDS_PER_SHEET,
        "SHEET_TYPE_RECALL": SHEET_TYPE_RECALL,
    }
    context.update(_picker_context(request))
    context.update(extra or {})
    return render(request, "practice_sheets/create.html", context)


def _words_from_upload(request):
    """(items, lỗi đã flash?) — đọc file người dùng tải lên."""
    upload = request.FILES.get("word_file")
    if upload is None:
        flash.error(request, message("practice_sheets.upload.error.no_file"))
        return None
    if upload.size > MAX_UPLOAD_BYTES:
        flash.error(
            request,
            message("practice_sheets.upload.error.file_too_large",
                    max_mb=MAX_UPLOAD_BYTES // (1024 * 1024)),
        )
        return None
    try:
        items, skipped = parse_word_file(upload.read(), upload.name)
    except dataio.DataFileError as exc:
        flash.error(request, message(exc.message_key, **exc.params))
        return None
    flash.success(
        request,
        message("practice_sheets.upload.success", count=len(items), filename=upload.name),
    )
    if skipped:
        flash.info(request, message("practice_sheets.upload.skipped_rows", count=skipped))
    return items


def _words_from_picker(request):
    """Giữ ĐÚNG thứ tự người dùng tích chọn thay vì thứ tự id trong DB.

    `filter(id__in=...)` trả về theo thứ tự của DB, không theo thứ tự trong
    form — in ra sẽ lộn xộn so với lúc chọn.
    """
    raw_ids = [i for i in request.POST.getlist("word_ids") if str(i).strip().isdigit()]
    by_id = {v.pk: v for v in Vocabulary.objects.filter(pk__in=raw_ids)}
    seen = set()
    words = []
    for raw in raw_ids:
        pk = int(raw)
        if pk in by_id and pk not in seen:
            seen.add(pk)
            words.append(by_id[pk])
    return words


@login_required
def create_view(request):
    """SC10 — chọn từ, chọn loại phiếu, sinh PDF."""
    if request.method != "POST":
        return _render_create(request, PracticeSheetForm())

    form = PracticeSheetForm(request.POST)
    if not form.is_valid():
        return _render_create(request, form)

    source = form.cleaned_data["source"]
    vocabularies = []
    custom_items = []
    if source == SOURCE_UPLOAD:
        custom_items = _words_from_upload(request)
        if custom_items is None:
            return _render_create(request, form)
        items = custom_items
    else:
        vocabularies = _words_from_picker(request)
        items = [WordItem.from_vocabulary(v) for v in vocabularies]

    if not items:
        flash.error(request, message("practice_sheets.generate.error.no_words"))
        return _render_create(request, form)
    if len(items) > MAX_WORDS_PER_SHEET:
        flash.error(
            request,
            message("practice_sheets.upload.error.too_many_words",
                    max_words=MAX_WORDS_PER_SHEET, word_count=len(items)),
        )
        return _render_create(request, form)

    sheet_type = form.cleaned_data["sheet_type"]
    options = form.sheet_options
    try:
        filename, pdf_content = generate_sheet_pdf(sheet_type, items, **options)
    except PracticeSheetFontError:
        # Máy chủ thiếu font (hay gặp trên PaaS không cho apt install).
        # Không để 500 — báo người dùng và ghi chi tiết vào log cho admin.
        logger.exception("Thiếu font khi sinh PDF luyện viết")
        flash.error(request, message("practice_sheets.generate.error.font_missing"))
        return _render_create(request, form)

    # Một transaction: sinh PDF hỏng giữa chừng thì không để lại bản ghi rỗng,
    # và bảng nối không bị ghi một nửa.
    with transaction.atomic():
        sheet = PracticeSheet.objects.create(
            user=request.user,
            sheet_type=sheet_type,
            lines_per_word=options["lines_per_word"],
            show_guide_character=options["show_guide_character"],
            show_reading_and_meaning=options["show_reading_and_meaning"],
            recall_direction=options["recall_direction"],
            include_sentence_box=options["include_sentence_box"],
            include_answer_key=options["include_answer_key"],
            shuffle_order=options["shuffle_order"],
            custom_words=[i.as_dict() for i in custom_items] if custom_items else [],
        )
        # create() từng dòng chứ KHÔNG sheet.words.set(): .set() đi qua
        # bulk_create nên bỏ qua save(), bảng nối sẽ trống created_by.
        for vocabulary in vocabularies:
            PracticeSheetWord.objects.create(sheet=sheet, vocabulary=vocabulary)
        sheet.pdf_file.save(filename, pdf_content)

    flash.success(request, message("practice_sheets.generate.success", count=len(items)))
    return redirect("practice_sheets:download", pk=sheet.pk)


@login_required
def download_view(request, pk):
    # get_object_or_404 chứ không phải .get(): sheet của người khác trả 404,
    # không phải DoesNotExist -> 500.
    sheet = get_object_or_404(PracticeSheet, pk=pk, user=request.user)
    name = "phieu_on_tap.pdf" if sheet.sheet_type == SHEET_TYPE_RECALL else "phieu_luyen_viet.pdf"
    return FileResponse(sheet.pdf_file.open("rb"), as_attachment=True, filename=name)


@login_required
def template_view(request, fmt):
    """File mẫu để người học điền danh sách từ của riêng mình.

    Ba cột trùng ba cột đầu của mẫu gộp bên SC07b nên file xuất từ màn quản trị
    dùng thẳng được ở đây.
    """
    if fmt not in CONTENT_TYPES:
        from django.http import Http404

        raise Http404
    headers = template_headers()
    sample = [
        ["打ち合わせ", "うちあわせ", "buổi họp, trao đổi công việc"],
        ["見積もり", "みつもり", "báo giá, dự trù"],
    ]
    guide = [
        ["Cột", "Bắt buộc", "Ghi chú"],
        ["word", "x", "Từ vựng dạng Kanji/Kana, vd 打ち合わせ"],
        ["reading", "", "Cách đọc (furigana), vd うちあわせ"],
        ["meaning_vi", "", "Nghĩa tiếng Việt"],
        [],
        ["Giới hạn", "", f"Tối đa {MAX_WORDS_PER_SHEET} từ mỗi phiếu, file tối đa 5 MB"],
        ["Lưu ý", "", "File này CHỈ dùng để in phiếu — không ghi gì vào từ điển chung."],
        ["Tiêu đề cột", "", "Chấp nhận cả 'Từ vựng' / 'Cách đọc' / 'Nghĩa tiếng Việt'."],
    ]
    if fmt == "csv":
        payload = dataio.write_csv(headers, sample)
    else:
        payload = dataio.write_xlsx(headers, sample, guide_rows=guide, sheet_title="tu_vung")
    from django.http import HttpResponse

    response = HttpResponse(payload, content_type=CONTENT_TYPES[fmt])
    response["Content-Disposition"] = f'attachment; filename="mau_danh_sach_tu_vung.{fmt}"'
    return response
