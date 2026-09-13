from django.contrib import admin

from .models import UserVocabularyProgress, StudySession, UserWordlist

admin.site.register(UserVocabularyProgress)
admin.site.register(StudySession)
admin.site.register(UserWordlist)
