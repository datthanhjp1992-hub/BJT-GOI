from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from django.shortcuts import render, redirect

from apps.vocabulary.models import Vocabulary
from .models import PracticeSheet
from .pdf_generator import generate_practice_pdf


@login_required
def create_view(request):
    # SC10_LuyenVietPdf
    if request.method == "POST":
        word_ids = request.POST.getlist("word_ids")
        words = list(Vocabulary.objects.filter(id__in=word_ids))
        lines_per_word = int(request.POST.get("lines_per_word", 2))
        show_guide = request.POST.get("show_guide_character") == "on"
        show_meta = request.POST.get("show_reading_and_meaning") == "on"

        filename, pdf_content = generate_practice_pdf(
            words, lines_per_word=lines_per_word,
            show_guide_character=show_guide, show_reading_and_meaning=show_meta,
        )
        sheet = PracticeSheet.objects.create(
            user=request.user, lines_per_word=lines_per_word,
            show_guide_character=show_guide, show_reading_and_meaning=show_meta,
        )
        sheet.words.set(words)
        sheet.pdf_file.save(filename, pdf_content)
        return redirect("practice_sheets:download", pk=sheet.pk)

    words = Vocabulary.objects.all()[:50]
    return render(request, "practice_sheets/create.html", {"words": words})


@login_required
def download_view(request, pk):
    sheet = PracticeSheet.objects.get(pk=pk, user=request.user)
    return FileResponse(sheet.pdf_file.open("rb"), as_attachment=True, filename="phieu_luyen_viet.pdf")
