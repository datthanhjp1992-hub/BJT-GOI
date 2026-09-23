"""
Bo loc + gom nhom dung cho SC18 (Bang tra dong tu kinh ngu) va SC17 (Trang bai hoc).

Tach khoi views.py theo dung khuon apps/vocabulary/selectors.py: view chi goi
ham o day, khong tu viet lai dieu kien loc.
"""
from dataclasses import dataclass, field
from itertools import groupby

from django.db.models import Count, Q

from apps.core.constants import keigo_pair_type_choices, keigo_style_choices
from apps.core.properties import label

from .models import KeigoForm, KeigoVerb

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


# =============================================================================
# SC17 -- Trang bai hoc (phuong an 3 "hoc tung muc mot", Dat chon 23/09/2026,
# mockup htmlTemplate/SC17_BaiHoc_PhuongAn.html).
#
# Mot chuong = mot DANH SACH MUC. Moi lan chi hien MOT muc, chon bang
# ?muc=<key> (link GET thuong, khong JavaScript -- dung khuon ?view= cua SC15).
# Ba loai muc, dung thu tu trong sach:
#   1. "dac-biet"      -- bang cac truong hop dac biet (chi chuong 1 va 2)
#   2. <pattern.code>  -- tung mau ngu phap, kem cau vi du
#   3. "cap-<type>"    -- tung bang cap tu KeigoPhrasePair (chuong 3, 6, 7)
# Key la slug on dinh (khong phai so thu tu) de link /keigo/<slug>/?muc=... van
# dung khi sau nay chen them mau vao giua chuong.
# =============================================================================
LESSON_ITEM_PARAM = "muc"
ITEM_IRREGULAR = "dac-biet"
PAIR_ITEM_PREFIX = "cap-"

KIND_IRREGULAR = "irregular"
KIND_PATTERN = "pattern"
KIND_PAIRS = "pairs"

# Bang "cac truong hop dac biet" sach in o DUNG hai cho: tr.4 (chuong 1, 尊敬語)
# va tr.7 (chuong 2, 謙譲語 I & II). Khong suy tu KeigoLesson.style_code vi
# chuong 2 de trong style_code (chuong hon hop kenjo/kenjo1/kenjo2), con chuong
# 6 co ca mau sonkei lan kenjo nhung la chuong quy tac CO quy tac -- suy tu mau
# se lam chuong 6 hien lai bang bat quy tac, sai voi sach.
LESSON_IRREGULAR_STYLES = {
    "ton-kinh-ngu": STYLE_COLUMNS["sonkei"],
    # Thu tu hien = thu tu trong sach: bang I, bang II (tr.7), roi cac dang
    # 拝~ chi co o tr.9 (style "kenjo" chung) -- KHONG dung STYLE_COLUMNS["kenjo"]
    # vi thu tu o do la kenjo -> kenjo1 -> kenjo2.
    "khiem-nhuong-ngu": ["kenjo1", "kenjo2", "kenjo"],
}

# Cac bang cap tu ma ve trai la cach noi SAI (hien × / ○). Cac bang con lai la
# "thuong -> lich su" (hien mui ten), cushion thi ve trai rong.
WRONG_PAIR_TYPES = {"wrong", "double", "baito"}


@dataclass
class LessonItem:
    key: str
    kind: str
    title: str
    badge: str = ""
    subtitle: str = ""
    pattern: object = None
    pair_type: str = ""
    url: str = ""
    # Chi dien cho muc DANG MO (load_item_detail), cac muc khac trong danh
    # sach khong can -- tranh truy van thua.
    detail: dict = field(default_factory=dict)


def lesson_items(lesson):
    """Danh sach muc cua mot chuong, dung thu tu hien trong sach."""
    items = []

    styles = LESSON_IRREGULAR_STYLES.get(lesson.slug)
    if styles and KeigoForm.objects.filter(is_irregular=True, style_code__in=styles).exists():
        items.append(LessonItem(key=ITEM_IRREGULAR, kind=KIND_IRREGULAR, badge="★",
                                title=label("keigo.lesson.irregular.title")))

    patterns = lesson.patterns.annotate(example_count=Count("examples")).order_by("display_order", "id")
    for number, pattern in enumerate(patterns, start=1):
        items.append(LessonItem(key=pattern.code, kind=KIND_PATTERN, badge=str(number),
                                title=pattern.title, subtitle=pattern.formation, pattern=pattern))

    present = set(lesson.phrase_pairs.values_list("pair_type", flat=True))
    for code, name in keigo_pair_type_choices():  # thu tu sort_order MasterCode 15
        if code in present:
            items.append(LessonItem(key=PAIR_ITEM_PREFIX + code, kind=KIND_PAIRS, badge="※",
                                    title=name, pair_type=code))
    return items


def pick_item(items, key):
    """(index, item) cua muc dang mo. Key la / trong -> muc dau tien."""
    for index, item in enumerate(items):
        if item.key == key:
            return index, item
    return 0, items[0]


def example_blocks(examples):
    """Gom cau vi du thanh khoi hien thi.

    Cac dong LIEN KE cung `pair_group` -> mot khoi hoi thoai (hien ten nguoi
    noi). Dong khong co pair_group -> mot cau rieng. Xem keigo-thiet-ke.md 2.5.
    """
    blocks = []
    for group, rows in groupby(examples, key=lambda e: e.pair_group):
        rows = list(rows)
        if group is None:
            blocks.extend({"kind": "sentence", "example": e} for e in rows)
        else:
            blocks.append({"kind": "dialog", "lines": rows})
    return blocks


def irregular_groups(lesson):
    """[{style_code, verbs:[{verb, forms:[...]}]}] -- chuong 2 tach rieng
    謙譲語 I / II / chung dung nhu hai bang nho trang 7."""
    styles = LESSON_IRREGULAR_STYLES.get(lesson.slug, [])
    forms = (KeigoForm.objects.filter(is_irregular=True, style_code__in=styles)
             .select_related("verb")
             .order_by("verb__display_order", "verb_id", "display_order"))
    groups = []
    for style in styles:
        verbs = []
        for verb, rows in groupby((f for f in forms if f.style_code == style), key=lambda f: f.verb):
            verbs.append({"verb": verb, "forms": list(rows)})
        if verbs:
            groups.append({"style_code": style, "verbs": verbs})
    return groups


def load_item_detail(lesson, item):
    """Nap noi dung cua DUNG muc dang mo vao item.detail."""
    if item.kind == KIND_PATTERN:
        examples = item.pattern.examples.order_by("display_order", "id")
        item.detail = {"blocks": example_blocks(examples)}
    elif item.kind == KIND_IRREGULAR:
        groups = irregular_groups(lesson)
        item.detail = {"groups": groups, "show_group_heading": len(groups) > 1}
    elif item.kind == KIND_PAIRS:
        pairs = lesson.phrase_pairs.filter(pair_type=item.pair_type).order_by("display_order", "id")
        item.detail = {
            "is_wrong_type": item.pair_type in WRONG_PAIR_TYPES,
            "groups": [{"label": lbl, "pairs": list(rows)}
                       for lbl, rows in groupby(pairs, key=lambda p: p.group_label)],
        }
    return item


def lesson_stats(lesson):
    """So lieu dau trang -- chi so > 0 moi hien (lam o template)."""
    styles = LESSON_IRREGULAR_STYLES.get(lesson.slug)
    return {
        "pattern_count": lesson.patterns.count(),
        "example_count": lesson.patterns.aggregate(n=Count("examples"))["n"] or 0,
        "irregular_count": (KeigoForm.objects.filter(is_irregular=True, style_code__in=styles).count()
                            if styles else 0),
        "pair_count": lesson.phrase_pairs.count(),
    }
