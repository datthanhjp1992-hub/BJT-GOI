"""
Bo loc + gom nhom dung cho SC18 (Bang tra dong tu kinh ngu).

Tach khoi views.py theo dung khuon apps/vocabulary/selectors.py: view chi goi
ham o day, khong tu viet lai dieu kien loc.
"""
from django.db.models import Q

from apps.core.constants import keigo_style_choices

from .models import KeigoVerb

# --- Ten tham so tren query string ------------------------------------------
SEARCH_PARAM = "q"
STYLE_PARAM = "loai"
IRREGULAR_PARAM = "batquytac"

# "" = "Tat ca" -- khong phai mot style_code that, chi la lua chon UI mac dinh.
STYLE_ALL = ""

# 3 cot hien thi cua bang tra -- KHONG phai het 7 ma MasterCode 14. Cot 謙譲語
# gom ca kenjo/kenjo1/kenjo2 vi sach chi tach I/II o dung hai bang nho trang 7
# (xem docstring KeigoForm o models.py); bikago/juju khong xuat hien trong
# bang chia dong tu nen khong can cot rieng o man nay.
STYLE_COLUMNS = {
    "sonkei": ["sonkei"],
    "kenjo": ["kenjo", "kenjo1", "kenjo2"],
    "teinei": ["teinei"],
}


def style_filter_choices():
    """[(code, code_name), ...] cho dai .tag-filter -- dung 3 ma cot, dung thu
    tu bang (sonkei -> kenjo -> teinei), khong theo sort_order cua MasterCode."""
    names = dict(keigo_style_choices())
    return [(code, names[code]) for code in STYLE_COLUMNS if code in names]


def clean_style(raw):
    """Ma la (sua URL bang tay) roi ve STYLE_ALL."""
    return raw if raw in STYLE_COLUMNS else STYLE_ALL


def filter_verbs(query="", style=STYLE_ALL, irregular_only=False):
    """KeigoVerb khop bo loc, kem prefetch `forms` de template khong N+1.

    `style` + `irregular_only` dung CHUNG mot filter() de doi hoi DUNG MOT
    dong KeigoForm thoa ca hai dieu kien (vd "chi dang dac biet cua 尊敬語") --
    multi-valued relation trong CUNG mot filter() ap dung tren CUNG mot hang
    lien ket, khac voi goi filter() nhieu lan (se ra hai join rieng). Tim kiem
    dung RIENG vi no duoc phep khop mot dong form khac voi dong vua loc style.
    """
    verbs = KeigoVerb.objects.prefetch_related("forms")
    style = clean_style(style)

    condition = Q()
    has_condition = False
    if style:
        condition &= Q(forms__style_code__in=STYLE_COLUMNS[style])
        has_condition = True
    if irregular_only:
        condition &= Q(forms__is_irregular=True)
        has_condition = True
    if has_condition:
        verbs = verbs.filter(condition)

    query = (query or "").strip()
    if query:
        verbs = verbs.filter(
            Q(plain_form__icontains=query)
            | Q(meaning_vi__icontains=query)
            | Q(forms__form__icontains=query)
            | Q(forms__reading__icontains=query)
        )

    if has_condition or query:
        verbs = verbs.distinct()
    return verbs.order_by("display_order", "plain_form")


def attach_columns(verbs):
    """Gan `sonkei_forms` / `kenjo_forms` / `teinei_forms` len tung verb DA
    prefetch `forms` -- de template lap thang qua 3 thuoc tinh, khong tu nhom
    trong template (Django template language khong group-by duoc gon gang).

    Nhan iterable, tra list (ep list vi phai lap `verbs` nhieu lan ben duoi).
    """
    verbs = list(verbs)
    for verb in verbs:
        forms = list(verb.forms.all())  # da prefetch, khong phat sinh query
        for column, codes in STYLE_COLUMNS.items():
            setattr(verb, f"{column}_forms", [f for f in forms if f.style_code in codes])
    return verbs
