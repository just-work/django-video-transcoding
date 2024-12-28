import random
from typing import Any, TypeVar, Callable, Union

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.utils.functional import Promise
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from video_transcoding import helpers, models, defaults, forms

C = TypeVar("C", bound=Callable)


def short_description(name: Union[str, Promise]) -> Callable[[C], C]:
    """ Sets short description for function."""

    def inner(func: C) -> C:
        setattr(func, 'short_description', name)
        return func

    return inner


# noinspection PyUnresolvedReferences
class VideoAdmin(admin.ModelAdmin):
    list_display = ('basename', 'source', 'status_display')
    list_filter = ('status',)
    search_fields = ('source', '=basename')
    actions = ['transcode']
    readonly_fields = ('created', 'modified', 'video_player')

    class Media:
        js = ('https://cdn.jsdelivr.net/npm/hls.js@1',)

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

    @short_description(_('Video player'))
    def video_player(self, obj: models.Video) -> str:
        if obj.basename is None:
            return ""
        edge = random.choice(defaults.VIDEO_EDGES)
        source = obj.format_video_url(edge)
        return mark_safe('''
<video id="video" width="480px" height="270px" controls></video>
<script>
  var video = document.getElementById('video');
  var videoSrc = '%s';
  if (Hls.isSupported()) {
    var hls = new Hls();
    hls.loadSource(videoSrc);
    hls.attachMedia(video);
  } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = videoSrc;
  }
</script>
''' % (source,))

    def add_view(self,
                 request: HttpRequest,
                 form_url: str = '',
                 extra_context: Any = None
                 ) -> HttpResponse:
        fields, self.fields = self.fields, ('source', 'preset')
        try:
            return super().add_view(request, form_url, extra_context)
        finally:
            self.fields = fields


if defaults.VIDEO_MODEL == 'video_transcoding.Video':
    admin.register(models.Video)(VideoAdmin)


# noinspection PyUnresolvedReferences
class TrackAdmin(admin.ModelAdmin):
    list_display = ('name', 'preset', 'created', 'modified')
    list_filter = ('preset',)
    readonly_fields = ('created', 'modified')
    search_fields = ('=name',)


@admin.register(models.VideoTrack)
class VideoTrackAdmin(TrackAdmin):
    form = forms.VideoTrackForm


@admin.register(models.AudioTrack)
class AudioTrackAdmin(TrackAdmin):
    form = forms.AudioTrackForm


class ProfileTracksInline(admin.TabularInline):
    list_display = ('track', 'order_number')
    extra = 0
    autocomplete_fields = ('track',)


class VideoProfileTracksInline(ProfileTracksInline):
    model = models.VideoProfileTracks


class AudioProfileTracksInline(ProfileTracksInline):
    model = models.AudioProfileTracks


# noinspection PyUnresolvedReferences
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'preset', 'order_number', 'created', 'modified')
    list_filter = ('preset',)
    readonly_fields = ('created', 'modified')
    search_fields = ('=name',)
    ordering = ('preset', 'order_number',)


@admin.register(models.VideoProfile)
class VideoProfileAdmin(ProfileAdmin):
    inlines = [VideoProfileTracksInline]
    form = forms.VideoProfileForm


@admin.register(models.AudioProfile)
class AudioProfileAdmin(ProfileAdmin):
    inlines = [AudioProfileTracksInline]
    form = forms.AudioProfileForm


class ProfileInline(admin.TabularInline):
    list_display = ('name',)
    extra = 0
    readonly_fields = ('condition',)


class VideoProfileInline(ProfileInline):
    model = models.VideoProfile


class AudioProfileInline(ProfileInline):
    model = models.AudioProfile


# noinspection PyUnresolvedReferences
@admin.register(models.Preset)
class PresetAdmin(admin.ModelAdmin):
    list_display = ('name', 'created', 'modified')
    readonly_fields = ('created', 'modified')
    search_fields = ('=name',)

    inlines = [VideoProfileInline, AudioProfileInline]
