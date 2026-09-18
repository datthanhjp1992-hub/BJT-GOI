"""
Test cho SC05_DanhSachTuVung.

Chạy: python manage.py test apps.vocabulary

Ghi chú: nhánh TÌM KIẾM (`?q=`) dùng TrigramSimilarity nên bắt buộc phải có
extension pg_trgm — test tìm kiếm ở lớp SearchTests sẽ tự bỏ qua nếu database
đang chạy không bật được extension đó.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.test import TestCase
from django.urls import reverse

from apps.core.properties import label, message
from apps.learning.models import UserVocabularyProgress

from .models import Topic, Vocabulary, VocabularyTopic
from .selectors import DEFAULT_SESSION_LIMIT
from .views import PAGE_SIZE

User = get_user_model()


def _pg_trgm_available():
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM pg_extension WHERE extname = 'pg_trgm'")
        return cursor.fetchone()[0] > 0


class VocabularyTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="dat", password="MatKhauRatManh123")
        self.client.force_login(self.user)
        self.topic = Topic.objects.create(name="Nhà hàng", slug="nha-hang")

    def _word(self, word, reading, meaning, topic=True):
        vocab = Vocabulary.objects.create(
            word=word, reading=reading, meaning_vi=meaning,
        )
        if topic:
            VocabularyTopic.objects.create(vocabulary=vocab, topic=self.topic)
        return vocab

    def _filtered(self, url=None, **params):
        """GET màn danh sách ở trạng thái ĐÃ BẤM LỌC.

        Từ 18/09/2026 trang không tự nạp dữ liệu nữa: không có cờ `filtered`
        (và không có tham số lọc nào) thì view trả về trang trống. Test nào
        cần bảng kết quả phải đi qua helper này.
        """
        params.setdefault("filtered", "1")
        return self.client.get(url or reverse("vocabulary:index"), params)


class ListViewTests(VocabularyTestCase):
    def test_requires_login(self):
        self.client.logout()
        url = reverse("vocabulary:index")
        self.assertRedirects(self.client.get(url), reverse("accounts:login") + "?next=" + url)

    def test_index_lists_every_word(self):
        self._word("注文する", "ちゅうもんする", "gọi món")
        self._word("予約", "よやく", "đặt chỗ trước")
        self._word("孤児", "こじ", "từ không thuộc chủ đề nào", topic=False)

        response = self._filtered()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "vocabulary/list.html")
        self.assertEqual(response.context["total_count"], 3)
        self.assertIsNone(response.context["topic"])
        self.assertContains(response, "ちゅうもんする")

    def test_topic_route_filters(self):
        self._word("注文する", "ちゅうもんする", "gọi món")
        other = Topic.objects.create(name="Gia đình", slug="gia-dinh")
        vocab = self._word("家族", "かぞく", "gia đình", topic=False)
        VocabularyTopic.objects.create(vocabulary=vocab, topic=other)

        response = self.client.get(reverse("vocabulary:list", args=["nha-hang"]))
        self.assertEqual(response.context["total_count"], 1)
        self.assertEqual(response.context["topic"], self.topic)
        self.assertNotContains(response, "かぞく")

    def test_unknown_topic_returns_404(self):
        self.assertEqual(
            self.client.get(reverse("vocabulary:list", args=["khong-ton-tai"])).status_code,
            404,
        )

    def test_topic_filter(self):
        """Chủ đề là cách phân loại DUY NHẤT sau khi bỏ cấp độ BJT."""
        self._word("注文する", "ちゅうもんする", "gọi món")           # chủ đề Nhà hàng
        khac = Topic.objects.create(name="Họp hành", slug="hop-hanh", name_ja="会議・打合せ")
        vocab = self._word("議事録", "ぎじろく", "biên bản họp", topic=False)
        VocabularyTopic.objects.create(vocabulary=vocab, topic=khac)

        response = self.client.get(reverse("vocabulary:list", args=["hop-hanh"]))
        self.assertEqual(response.context["total_count"], 1)
        self.assertEqual(response.context["topic"], khac)
        self.assertContains(response, "ぎじろく")
        self.assertNotContains(response, "ちゅうもんする")

    def test_multi_topic_filter_is_union(self):
        """Chọn nhiều chủ đề = HOẶC: từ chỉ cần thuộc MỘT trong số đó."""
        self._word("注文する", "ちゅうもんする", "gọi món")            # chủ đề Nhà hàng
        khac = Topic.objects.create(name="Họp hành", slug="hop-hanh")
        vocab = self._word("議事録", "ぎじろく", "biên bản họp", topic=False)
        VocabularyTopic.objects.create(vocabulary=vocab, topic=khac)
        self._word("孤児", "こじ", "từ mồ côi", topic=False)

        response = self._filtered(topic=["nha-hang", "hop-hanh"])
        self.assertEqual(response.context["total_count"], 2)
        self.assertEqual(
            [t.slug for t in response.context["selected_topics"]], ["nha-hang", "hop-hanh"]
        )
        # Nhiều chủ đề thì không chủ đề nào là "chủ đề của trang".
        self.assertIsNone(response.context["topic"])
        self.assertNotContains(response, "こじ")

    def test_word_in_two_selected_topics_is_not_duplicated(self):
        """Join M2M nhân bản dòng — .distinct() phải chặn việc đếm hai lần."""
        khac = Topic.objects.create(name="Họp hành", slug="hop-hanh")
        vocab = self._word("注文する", "ちゅうもんする", "gọi món")    # đã có Nhà hàng
        VocabularyTopic.objects.create(vocabulary=vocab, topic=khac)

        response = self._filtered(topic=["nha-hang", "hop-hanh"])
        self.assertEqual(response.context["total_count"], 1)

    def test_filter_link_toggles_topic_on_and_off(self):
        """Chưa chọn thì link THÊM chủ đề, đang chọn thì link BỎ chủ đề."""
        khac = Topic.objects.create(name="Họp hành", slug="hop-hanh")

        response = self._filtered(topic=["nha-hang"])
        links = {f["topic"].slug: f for f in response.context["topic_filters"]}
        self.assertTrue(links["nha-hang"]["is_selected"])
        self.assertNotIn("topic=", links["nha-hang"]["query"])          # bấm lần 2 -> bỏ lọc
        self.assertFalse(links[khac.slug]["is_selected"])
        self.assertIn("topic=nha-hang", links[khac.slug]["query"])      # cộng dồn, không thay thế
        self.assertIn("topic=hop-hanh", links[khac.slug]["query"])

    def test_filter_link_keeps_the_search_keyword(self):
        response = self._filtered(q="ちゅうもん", topic=["nha-hang"])
        for f in response.context["topic_filters"]:
            self.assertIn("q=", f["query"])
        self.assertIn("q=", response.context["clear_query"])

    def test_unknown_topic_in_query_is_ignored_not_404(self):
        """Slug rác trên query string chỉ bị lờ đi (khác slug rác trên route)."""
        self._word("注文する", "ちゅうもんする", "gọi món")

        response = self._filtered(topic="khong-ton-tai")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_topics"], [])
        self.assertEqual(response.context["total_count"], 1)

    def test_route_topic_merges_with_query_topics(self):
        """Link cũ /topic/<slug>/ vẫn chạy và cộng thêm được chủ đề khác."""
        khac = Topic.objects.create(name="Họp hành", slug="hop-hanh")
        vocab = self._word("議事録", "ぎじろく", "biên bản họp", topic=False)
        VocabularyTopic.objects.create(vocabulary=vocab, topic=khac)
        self._word("注文する", "ちゅうもんする", "gọi món")

        response = self.client.get(
            reverse("vocabulary:list", args=["nha-hang"]), {"topic": "hop-hanh"}
        )
        self.assertEqual(response.context["total_count"], 2)

    def test_pagination_link_keeps_every_selected_topic(self):
        khac = Topic.objects.create(name="Họp hành", slug="hop-hanh")
        for i in range(PAGE_SIZE + 1):
            vocab = self._word(f"語{i}", f"ご{i}", f"từ {i}", topic=False)
            VocabularyTopic.objects.create(vocabulary=vocab, topic=khac)

        response = self._filtered(topic=["nha-hang", "hop-hanh"])
        self.assertIn("topic=nha-hang", response.context["pagination_query"])
        self.assertIn("topic=hop-hanh", response.context["pagination_query"])
        self.assertNotIn("page=", response.context["pagination_query"])

    def test_search_form_keeps_selected_topics(self):
        """Ô tìm kiếm phải mang theo chủ đề đang lọc (hidden input)."""
        response = self._filtered(topic=["nha-hang"])
        self.assertContains(response, 'name="topic" value="nha-hang"')

    def test_topic_filter_is_a_searchable_dropdown(self):
        """Chủ đề nằm trong dropdown <details> có checkbox + ô tìm nhanh.

        Ô tìm chạy bằng JS nên test chỉ canh phần server phải dựng đúng: khung
        dropdown, ô tìm, và data-topic-search chứa cả tên Việt / tên Nhật /
        slug để gõ kiểu nào cũng ra.
        """
        Topic.objects.create(name="Họp hành", slug="hop-hanh", name_ja="会議・打合せ")

        response = self.client.get(reverse("vocabulary:index"))
        self.assertContains(response, 'id="topic-dropdown"')
        self.assertContains(response, 'id="topic-search"')
        self.assertContains(response, 'data-search="Họp hành 会議・打合せ hop-hanh"')
        self.assertContains(response, '<input type="checkbox" name="topic" value="hop-hanh">')

    def test_dropdown_search_box_is_not_submitted(self):
        """Ô tìm nhanh không có name -> không lẫn vào query string của form lọc."""
        response = self.client.get(reverse("vocabulary:index"))
        self.assertNotContains(response, 'id="topic-search" name=')
        self.assertNotContains(response, 'name="topic-search"')

    def test_topic_shows_both_names(self):
        """Tên Nhật và tên Việt để hai ô riêng, UI ghép lại khi hiển thị."""
        khac = Topic.objects.create(name="Họp hành", slug="hop-hanh", name_ja="会議・打合せ")
        self.assertEqual(khac.display_name, "会議・打合せ (Họp hành)")
        self.assertEqual(Topic(name="Chỉ Việt").display_name, "Chỉ Việt")

        response = self.client.get(reverse("vocabulary:list", args=["hop-hanh"]))
        self.assertContains(response, "会議・打合せ")
        self.assertContains(response, "Họp hành")

    def test_study_status_per_word(self):
        new = self._word("注文する", "ちゅうもんする", "gọi món")
        learning = self._word("予約", "よやく", "đặt chỗ")
        mastered = self._word("会計", "かいけい", "tính tiền")
        UserVocabularyProgress.objects.create(user=self.user, vocabulary=learning)
        UserVocabularyProgress.objects.create(
            user=self.user, vocabulary=mastered, is_mastered=True
        )

        response = self._filtered()
        status_by_id = {w.pk: w.study_status for w in response.context["page_obj"].object_list}
        self.assertEqual(status_by_id[new.pk], "new")
        self.assertEqual(status_by_id[learning.pk], "learning")
        self.assertEqual(status_by_id[mastered.pk], "mastered")
        self.assertContains(response, label("vocabulary.list.tag.status.mastered"))

    def test_status_is_per_user(self):
        vocab = self._word("注文する", "ちゅうもんする", "gọi món")
        other = User.objects.create_user(username="khac", password="x")
        UserVocabularyProgress.objects.create(user=other, vocabulary=vocab, is_mastered=True)

        response = self._filtered()
        self.assertEqual(response.context["page_obj"].object_list[0].study_status, "new")

    def test_orphan_word_has_no_review_link(self):
        self._word("孤児", "こじ", "từ mồ côi", topic=False)
        response = self._filtered()
        self.assertIsNone(response.context["page_obj"].object_list[0].primary_topic)

    def test_empty_state(self):
        """Đã lọc nhưng không khớp từ nào -> báo rỗng."""
        response = self._filtered(q="")
        self.assertContains(response, message("vocabulary.list.empty"))

    def test_page_is_blank_until_the_user_filters(self):
        """Vào trang trần: hiện khu bộ lọc, KHÔNG truy vấn bảng từ vựng."""
        self._word("注文する", "ちゅうもんする", "gọi món")

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(reverse("vocabulary:index"))

        self.assertFalse(response.context["is_filtered"])
        self.assertIsNone(response.context["page_obj"])
        self.assertContains(response, message("vocabulary.list.hint.not_filtered"))
        self.assertNotContains(response, "ちゅうもんする")
        # Điều kiện cốt lõi: không có câu SQL nào đụng vào bảng từ vựng.
        vocabulary_table = Vocabulary._meta.db_table
        self.assertEqual(
            [q["sql"] for q in captured.captured_queries if vocabulary_table in q["sql"]],
            [],
        )

    def test_topic_route_loads_data_without_the_flag(self):
        """Link cũ /vocabulary/topic/<slug>/ tự nó đã là một bộ lọc."""
        self._word("注文する", "ちゅうもんする", "gọi món")
        response = self.client.get(reverse("vocabulary:list", args=["nha-hang"]))
        self.assertTrue(response.context["is_filtered"])
        self.assertContains(response, "ちゅうもんする")

    def test_status_filter_new_only(self):
        new = self._word("注文する", "ちゅうもんする", "gọi món")
        learning = self._word("予約", "よやく", "đặt chỗ")
        mastered = self._word("会計", "かいけい", "tính tiền")
        UserVocabularyProgress.objects.create(user=self.user, vocabulary=learning)
        UserVocabularyProgress.objects.create(
            user=self.user, vocabulary=mastered, is_mastered=True
        )

        response = self._filtered(status="new")
        self.assertEqual(
            [w.pk for w in response.context["page_obj"].object_list], [new.pk]
        )

    def test_status_filter_accepts_several_values(self):
        self._word("注文する", "ちゅうもんする", "gọi món")
        learning = self._word("予約", "よやく", "đặt chỗ")
        mastered = self._word("会計", "かいけい", "tính tiền")
        UserVocabularyProgress.objects.create(user=self.user, vocabulary=learning)
        UserVocabularyProgress.objects.create(
            user=self.user, vocabulary=mastered, is_mastered=True
        )

        response = self._filtered(status=["learning", "mastered"])
        self.assertEqual(
            sorted(w.pk for w in response.context["page_obj"].object_list),
            sorted([learning.pk, mastered.pk]),
        )

    def test_status_filter_is_per_user(self):
        """"Chưa học" phải xét tiến độ của CHÍNH người đang đăng nhập."""
        vocab = self._word("注文する", "ちゅうもんする", "gọi món")
        other = User.objects.create_user(username="khac", password="x")
        UserVocabularyProgress.objects.create(user=other, vocabulary=vocab)

        response = self._filtered(status="new")
        self.assertEqual(response.context["total_count"], 1)

    def test_unknown_status_is_ignored(self):
        self._word("注文する", "ちゅうもんする", "gọi món")
        response = self._filtered(status="rac")
        self.assertEqual(response.context["selected_statuses"], [])
        self.assertEqual(response.context["total_count"], 1)

    def test_session_limit_falls_back_to_default(self):
        response = self._filtered(limit="999")
        self.assertEqual(response.context["session_limit"], DEFAULT_SESSION_LIMIT)
        response = self._filtered(limit="50")
        self.assertEqual(response.context["session_limit"], 50)

    def test_table_shows_50_rows_per_page(self):
        self.assertEqual(PAGE_SIZE, 50)
        for index in range(PAGE_SIZE + 2):
            self._word("語%03d" % index, "ご%03d" % index, "nghĩa %03d" % index)

        response = self._filtered()
        self.assertEqual(len(response.context["page_obj"].object_list), 50)
        self.assertEqual(response.context["paginator"].num_pages, 2)

    def test_start_study_button_carries_the_filter(self):
        self._word("注文する", "ちゅうもんする", "gọi món")
        response = self._filtered(topic="nha-hang", status="new", limit="10")
        self.assertContains(response, reverse("learning:study_start"))
        self.assertContains(response, '<input type="hidden" name="topic" value="nha-hang">', html=False)
        self.assertContains(response, '<input type="hidden" name="status" value="new">', html=False)
        self.assertContains(response, '<input type="hidden" name="limit" value="10">', html=False)

    def test_pagination_keeps_filters(self):
        for index in range(PAGE_SIZE + 3):
            self._word("語%02d" % index, "ご%02d" % index, "nghĩa %02d" % index)

        first = self.client.get(reverse("vocabulary:list", args=["nha-hang"]), {"page": 1})
        self.assertEqual(len(first.context["page_obj"].object_list), PAGE_SIZE)
        self.assertNotIn("page=", first.context["pagination_query"])

        second = self._filtered(page=2)
        self.assertEqual(len(second.context["page_obj"].object_list), 3)
        # `page` không được lặp lại trong querystring phân trang.
        self.assertNotIn("page=", second.context["pagination_query"])


class SearchTests(VocabularyTestCase):
    def setUp(self):
        super().setUp()
        if not _pg_trgm_available():
            self.skipTest("database đang chạy không có extension pg_trgm")

    def test_search_matches_reading(self):
        self._word("注文する", "ちゅうもんする", "gọi món")
        self._word("会計", "かいけい", "tính tiền")

        response = self._filtered(q="ちゅうもん")
        self.assertEqual(response.context["total_count"], 1)
        self.assertContains(response, "注文する")

    def test_search_is_combined_with_topic_filter(self):
        self._word("注文する", "ちゅうもんする", "gọi món")            # chủ đề Nhà hàng
        khac = Topic.objects.create(name="Họp hành", slug="hop-hanh", name_ja="会議・打合せ")
        vocab = self._word("注文書", "ちゅうもんしょ", "đơn đặt hàng", topic=False)
        VocabularyTopic.objects.create(vocabulary=vocab, topic=khac)

        response = self.client.get(
            reverse("vocabulary:list", args=["hop-hanh"]), {"q": "ちゅうもん"}
        )
        self.assertEqual(response.context["total_count"], 1)
        self.assertContains(response, "注文書")


class SearchQuerySetTests(VocabularyTestCase):
    def test_search_sql_uses_trigram_similarity(self):
        """Không cần pg_trgm để kiểm tra: chỉ soi SQL mà ORM sinh ra.

        Cốt để phát hiện sớm nếu ai đó lỡ đổi .search() thành icontains thuần
        — lúc đó index GIN ở Meta.indexes thành vô dụng.
        """
        sql = str(Vocabulary.objects.search("ちゅうもん").query).lower()
        self.assertIn("similarity(", sql)
        self.assertIn("order by", sql)

    def test_empty_query_returns_nothing(self):
        self._word("注文する", "ちゅうもんする", "gọi món")
        self.assertEqual(Vocabulary.objects.search("   ").count(), 0)


class AdminTopicAssignmentTests(TestCase):
    """Gán chủ đề cho từ vựng phải làm được ngay trong Django admin.

    Bẫy đã gặp thật: `Vocabulary.topics` là M2M đi qua through model, mà Django
    loại mọi M2M kiểu đó khỏi ModelForm — màn "Thêm vocabulary" im lặng mất phần
    chủ đề, không báo lỗi gì. Phải có inline của VocabularyTopic thay thế.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser(
            username="sieuquantri", password="MatKhauRatManh123", email="a@b.c",
        )
        self.client.force_login(self.admin)

    def test_add_form_offers_the_topic_inline(self):
        response = self.client.get("/admin/vocabulary/vocabulary/add/")
        self.assertEqual(response.status_code, 200)
        # `topic_links` là related_name của VocabularyTopic -> tiền tố của formset.
        self.assertContains(response, "topic_links-TOTAL_FORMS")

    def test_saving_through_the_inline_fills_audit_columns(self):
        """Inline đi qua save() nên có created_by — khác `topics.add()`."""
        topic = Topic.objects.create(name="Họp hành", slug="hop-hanh", name_ja="会議・打合せ")
        response = self.client.post(
            "/admin/vocabulary/vocabulary/add/",
            {
                "word": "議事録", "reading": "ぎじろく", "meaning_vi": "biên bản họp",
                "audio_url": "",
                "topic_links-TOTAL_FORMS": "1", "topic_links-INITIAL_FORMS": "0",
                "topic_links-MIN_NUM_FORMS": "0", "topic_links-MAX_NUM_FORMS": "1000",
                "topic_links-0-topic": str(topic.pk),
                "examples-TOTAL_FORMS": "0", "examples-INITIAL_FORMS": "0",
                "examples-MIN_NUM_FORMS": "0", "examples-MAX_NUM_FORMS": "1000",
            },
        )
        self.assertEqual(response.status_code, 302, getattr(response, "context", None))
        vocab = Vocabulary.objects.get(word="議事録")
        self.assertEqual([t.slug for t in vocab.topics.all()], ["hop-hanh"])
        self.assertEqual(VocabularyTopic.objects.get().created_by, self.admin)

    def test_topic_admin_lists_word_count(self):
        Topic.objects.create(name="Họp hành", slug="hop-hanh")
        response = self.client.get("/admin/vocabulary/topic/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Họp hành")
