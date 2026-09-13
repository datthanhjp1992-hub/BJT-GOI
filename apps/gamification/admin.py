from django.contrib import admin

from apps.gamification.models import (
    Contribution, PointRule, UserPointTransaction,
    BadgeCategory, BadgeTier, UserPinnedBadge,
)


@admin.register(Contribution)
class ContributionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "contribution_type_code", "status_code", "created_at", "reviewed_by")
    list_filter = ("contribution_type_code", "status_code")
    search_fields = ("proposed_word", "comment_text", "user__username")


@admin.register(PointRule)
class PointRuleAdmin(admin.ModelAdmin):
    list_display = ("action_code", "points")


@admin.register(UserPointTransaction)
class UserPointTransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "action_code", "points", "created_at", "contribution")
    list_filter = ("action_code",)


class BadgeTierInline(admin.TabularInline):
    model = BadgeTier
    extra = 1


@admin.register(BadgeCategory)
class BadgeCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code_type", "metric", "is_active", "sort_order")
    inlines = [BadgeTierInline]


@admin.register(UserPinnedBadge)
class UserPinnedBadgeAdmin(admin.ModelAdmin):
    list_display = ("user", "category", "display_order")
