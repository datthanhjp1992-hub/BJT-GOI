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

from .models import KeigoForm, KeigoPhrasePair, KeigoVerb

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


# =============================================================================
# SC19 -- Loi thuong gap (Dat duyet mockup 24/09/2026,
# htmlTemplate/SC19_LoiThuongGap_A.html -- doc 7 quyet dinh o dau file do).
#
# KHONG them model: xep lai CUNG bang KeigoPhrasePair ma SC17 dang hien, nhung
# gom theo pair_type XUYEN chuong (SC17 rai 87 cap o chuong 3, 6, 7).
#   ?view=<pair_type>  tab dang mo (la / trong -> tab dau tien co du lieu)
#   ?q=                tim trong CA 8 nhom, bo qua ?view=
#   ?an=1              tu kiem tra -- che ve lich su bang <details>
# =============================================================================
PITFALL_VIEW_PARAM = "view"
PITFALL_CHECK_PARAM = "an"
PITFALL_DEFAULT_VIEW = "wrong"
CUSHION_PAIR_TYPE = "cushion"

# 3 cum hien thi -- KHONG co trong DB. Suy tu DUNG quy tac SC17 dang dung
# (WRONG_PAIR_TYPES -> × / ○; cushion -> ve casual rong; con lai -> bang "→"),
# nen them mot pair_type moi vao MasterCode 15 la tu roi vao cum "conv".
PITFALL_KIND_XO = "xo"
PITFALL_KIND_CONV = "conv"
PITFALL_KIND_CUSHION = "cush"
PITFALL_KIND_ORDER = [PITFALL_KIND_XO, PITFALL_KIND_CONV, PITFALL_KIND_CUSHION]


def pitfall_kind(pair_type):
    if pair_type in WRONG_PAIR_TYPES:
        return PITFALL_KIND_XO
    if pair_type == CUSHION_PAIR_TYPE:
        return PITFALL_KIND_CUSHION
    return PITFALL_KIND_CONV


@dataclass
class PitfallType:
    code: str
    name: str
    description: str
    kind: str
    count: int = 0            # tong so dong cua nhom
    match_count: int = 0      # so dong khop ?q= (khong tim thi = count)
    lesson: object = None     # chuong chua nhom nay (de link ve SC17)
    url: str = ""             # link tab -- view dien
    lesson_url: str = ""      # link "Xem trong chuong N" -- view dien
    lesson_number: int = 0
    groups: list = field(default_factory=list)  # chi dien cho nhom DANG HIEN


def _pair_type_meta():
    """[(code, code_name, description)] theo sort_order MasterCode 15.

    Doc thang MasterCode vi can ca `description` (ghi chu "Bang ... (tr.18)"
    hien lam kicker), ma keigo_pair_type_choices() chi tra (code, name)."""
    from apps.core.constants import CODE_TYPE_KEIGO_PAIR_TYPE
    from apps.core.models import MasterCode

    return list(MasterCode.objects.filter(code_type=CODE_TYPE_KEIGO_PAIR_TYPE, is_active=True)
                .order_by("sort_order", "code")
                .values_list("code", "code_name", "description"))


def _search_q(query):
    return (Q(casual__icontains=query) | Q(polite__icontains=query)
            | Q(group_label__icontains=query) | Q(note_vi__icontains=query))


def pitfall_groups(kind, pairs):
    """Gom cac dong cua MOT nhom thanh khoi hien thi: [{label, items}].

    Cac dong LIEN KE cung group_label -> mot khoi (co tieu de neu label khac rong).
    - xo  : trong moi khoi, dong LIEN KE cung ve `casual` gop thanh MOT ×
            voi N ○ (double #1-#2 cung 「資料をお読みになられましたか。」).
            item = {"casual": str, "answers": [KeigoPhrasePair, ...]}
    - conv: item = KeigoPhrasePair; dong casual rong (2 quy tac chung cua
            teinei) template hien thanh dong tieu de chia bang.
    - cush: item = KeigoPhrasePair (chi co polite).
    """
    groups = []
    for lbl, rows in groupby(pairs, key=lambda p: p.group_label):
        rows = list(rows)
        if kind == PITFALL_KIND_XO:
            items = []
            for casual, same in groupby(rows, key=lambda p: p.casual):
                items.append({"casual": casual, "answers": list(same)})
        else:
            items = rows
        groups.append({"label": lbl, "items": items})
    return groups


def pitfall_page(view="", query=""):
    """Du lieu cho SC19. Tra dict:
      types    : [PitfallType] moi nhom CO du lieu, theo sort_order MasterCode
      clusters : [(kind, [PitfallType])] -- cum rong bi bo
      view     : ma tab dang mo (da chuan hoa)
      shown    : [PitfallType] cac nhom hien noi dung (1 nhom, hoac moi nhom khop ?q=)
      total / match_total / lesson_count
    """
    query = (query or "").strip()
    base = KeigoPhrasePair.objects.all()
    counts = dict(base.values_list("pair_type").annotate(n=Count("id")))
    matches = (dict(base.filter(_search_q(query)).values_list("pair_type").annotate(n=Count("id")))
               if query else counts)

    types = [PitfallType(code=code, name=name, description=desc, kind=pitfall_kind(code),
                         count=counts[code], match_count=matches.get(code, 0))
             for code, name, desc in _pair_type_meta() if counts.get(code)]
    codes = [t.code for t in types]
    if view not in codes:
        view = PITFALL_DEFAULT_VIEW if PITFALL_DEFAULT_VIEW in codes else (codes[0] if codes else "")

    shown = [t for t in types if t.match_count] if query else [t for t in types if t.code == view]
    if shown:
        pairs = (base.filter(pair_type__in=[t.code for t in shown])
                 .select_related("lesson").order_by("pair_type", "display_order", "id"))
        if query:
            pairs = pairs.filter(_search_q(query))
        by_type = {code: list(rows) for code, rows in groupby(pairs, key=lambda p: p.pair_type)}
        for t in shown:
            rows = by_type.get(t.code, [])
            t.lesson = rows[0].lesson if rows else None
            t.groups = pitfall_groups(t.kind, rows)

    clusters = [(kind, [t for t in types if t.kind == kind]) for kind in PITFALL_KIND_ORDER]
    return {
        "types": types,
        "clusters": [(kind, ts) for kind, ts in clusters if ts],
        "view": view,
        "shown": shown,
        "total": sum(counts.values()),
        "match_total": sum(t.match_count for t in types),
        "lesson_count": base.values("lesson").distinct().count(),
    }
