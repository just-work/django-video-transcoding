from typing import Any, Optional, TypeVar, Callable

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.utils.translation import gettext_lazy as _

from video_transcoding import helpers, models

C = TypeVar("C", bound=Callable)


def short_description(name: str) -> Callable[[C], C]:
    """ Sets short description for function."""

    def inner(func: C) -> C:
        setattr(func, 'short_description', name)
        return func

    return inner


@admin.register(models.Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('basename', 'source', 'status_display')
    list_filter = ('status',)
    search_fields = ('source', '=basename')
    actions = admin.ModelAdmin.actions + ["transcode"]

    @short_description(_("Status"))
    def status_display(self, obj: models.Video) -> str:
        return obj.get_status_display()

    # noinspection PyUnusedLocal
    @short_description(_('Send transcode task'))
    def transcode(self,
                  request: HttpRequest,
                  queryset: "QuerySet[models.Video]") -> None:
        for video in queryset:
            helpers.send_transcode_task(video)

    def add_view(self,
                 request: HttpRequest,
                 form_url: str = '',
                 extra_context: Any = None
                 ) -> HttpResponse:
        fields, self.fields = self.fields, ('source',)
        try:
            return super().add_view(request, form_url, extra_context)
        finally:
            self.fields = fields
