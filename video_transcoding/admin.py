from django.contrib import admin

from video_transcoding import models
from django.utils.translation import ugettext_lazy as _


@admin.register(models.Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('basename', 'source', 'status_display')
    list_filter = ('status',)
    search_fields = ('source', '=basename')

    def status_display(self, obj):
        return obj.get_status_display()

    status_display.short_description = _('Status')

    def add_view(self, *args, **kwargs):
        fields, self.fields = self.fields, ('source',)
        try:
            return super().add_view(*args, **kwargs)
        finally:
            self.fields = fields
