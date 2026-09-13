from rest_framework import serializers

from .models import Topic, Vocabulary, ExampleSentence


class ExampleSentenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExampleSentence
        fields = ["id", "sentence_jp", "sentence_vi"]


class VocabularySerializer(serializers.ModelSerializer):
    examples = ExampleSentenceSerializer(many=True, read_only=True)

    class Meta:
        model = Vocabulary
        fields = ["id", "word", "reading", "meaning_vi", "bjt_level", "examples"]


class TopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Topic
        fields = ["id", "name", "slug", "icon_emoji", "description"]
