from rest_framework import serializers

from .models import UserVocabularyProgress


class ReviewResultSerializer(serializers.Serializer):
    vocabulary_id = serializers.IntegerField()
    quality_key = serializers.ChoiceField(choices=["quen", "kho", "nho", "de"])
