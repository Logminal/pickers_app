from django.contrib import admin

from .models import AdditionalWork, Act, ChecklistItem, Photo, PhotoReport, PhotoSlotDefinition, PhotoSlotTemplate


class PhotoSlotDefinitionInline(admin.TabularInline):
    model = PhotoSlotDefinition
    extra = 1


@admin.register(PhotoSlotTemplate)
class PhotoSlotTemplateAdmin(admin.ModelAdmin):
    inlines = [PhotoSlotDefinitionInline]


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 0


class ChecklistItemInline(admin.TabularInline):
    model = ChecklistItem
    extra = 0


@admin.register(PhotoReport)
class PhotoReportAdmin(admin.ModelAdmin):
    list_display = ('order', 'status', 'comment', 'submitted_at')
    list_filter = ('status',)
    readonly_fields = ('submitted_at',)
    inlines = [PhotoInline, ChecklistItemInline]


@admin.register(Act)
class ActAdmin(admin.ModelAdmin):
    list_display = ('order', 'uploaded_by', 'is_readable_confirmed', 'created_at')
    list_filter = ('is_readable_confirmed',)


@admin.register(AdditionalWork)
class AdditionalWorkAdmin(admin.ModelAdmin):
    list_display = ('order', 'description', 'price', 'added_by', 'created_at')
