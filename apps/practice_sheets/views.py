"""
View của app practice_sheets: SC10_LuyenVietPdf.
"""
import logging

from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.properties import message
from apps.vocabulary.models import Vocabulary

from .models import PracticeSheet
from .pdf_generator import PracticeSheetFontError, generate_practice_pdf

logger = logging.getLogger(__name__)


@login_required
def create_view(request):
    """SC10_LuyenVietPdf."""
    if request.method == "POST":
        word_ids = request.POST.getlist("word_ids")
        words = list(Vocabulary.objects.filter(id__in=word_ids))
        lines_per_word = int(request.POST.get("lines_per_word", 2))
        show_guide = request.POST.get("show_guide_character") == "on"
        show_meta = request.POST.get("show_reading_and_meaning") == "on"

        try:
            filename, pdf_content = generate_practice_pdf(
                words,
                lines_per_word=lines_per_word,
                show_guide_character=show_guide,
                show_reading_and_meaning=show_meta,
            )
        except PracticeSheetFontError:
            # Máy chủ thiếu font (hay gặp trên PaaS không cho apt install).
            # Không để 500 — báo người dùng và ghi chi tiết vào log cho admin.
            logger.exception("Thiếu font khi sinh PDF luyện viết")
            flash.error(request, message("practice_sheets.generate.error.font_missing"))
            return redirect("practice_sheets:create")

        sheet = PracticeSheet.objects.create(
            user=request.user,
            lines_per_word=lines_per_word,
            show_guide_character=show_guide,
            show_reading_and_meaning=show_meta,
        )
        sheet.words.set(words)
        sheet.pdf_file.save(filename, pdf_content)
        flash.success(request, message("practice_sheets.generate.success", count=len(words)))
        return redirect("practice_sheets:download", pk=sheet.pk)

    words = Vocabulary.objects.all()[:50]
    return render(
        request,
        "practice_sheets/create.html",
        {"words": words, "active_nav": "practice_sheet"},
    )


@login_required
def download_view(request, pk):
    # get_object_or_404 chứ không phải .get(): sheet của người khác trả 404,
    # không phải DoesNotExist -> 500.
    sheet = get_object_or_404(PracticeSheet, pk=pk, user=request.user)
    return FileResponse(
        sheet.pdf_file.open("rb"), as_attachment=True, filename="phieu_luyen_viet.pdf"
    )
