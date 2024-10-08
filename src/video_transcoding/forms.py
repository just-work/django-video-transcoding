from typing import List, Any, Dict

from django import forms
from django.utils.translation import gettext_lazy as _

from video_transcoding import models

FORCE_KEY_FRAMES = "expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+4))"


class NestedJSONForm(forms.ModelForm):
    json_field: str
    nested_fields: List[str]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        try:
            data = self.initial[self.json_field]
        except KeyError:
            return
        for k in self.nested_fields:
            try:
                self.fields[f'_{k}'].initial = data[k]
            except KeyError:
                pass

    def clean(self) -> Dict[str, Any]:
        cd = self.cleaned_data
        missing = set()
        for k in self.nested_fields:
            if f'_{k}' not in cd:
                missing.add(f'_{k}')
        if not missing:
            cd[self.json_field] = {k: cd[f'_{k}'] for k in self.nested_fields}
        return cd


class VideoProfileForm(NestedJSONForm):
    json_field = 'condition'
    nested_fields = ['min_bitrate', 'min_width', 'min_height', 'min_frame_rate',
                     'min_dar', 'max_dar']

    class Meta:
        model = models.VideoProfile
        fields = '__all__'

    condition = forms.JSONField(disabled=True,
                                required=False,
                                widget=forms.HiddenInput(),
                                initial={})
    _min_bitrate = forms.IntegerField(label=_('Min bitrate'))
    _min_width = forms.IntegerField(label=_('Min width'))
    _min_height = forms.IntegerField(label=_('Min height'))
    _min_frame_rate = forms.FloatField(label=_('Min frame rate'))
    _min_dar = forms.FloatField(label=_('Min aspect'))
    _max_dar = forms.FloatField(label=_('Max aspect'))


class AudioProfileForm(NestedJSONForm):
    json_field = 'condition'
    nested_fields = ['min_bitrate', 'min_sample_rate']

    class Meta:
        model = models.AudioProfile
        fields = '__all__'

    condition = forms.JSONField(disabled=True,
                                required=False,
                                widget=forms.HiddenInput(),
                                initial={})
    _min_bitrate = forms.IntegerField(label=_('Min bitrate'))
    _min_sample_rate = forms.IntegerField(label=_('Min sample rate'))


class VideoTrackForm(NestedJSONForm):
    json_field = 'params'
    nested_fields = [
        'codec',
        'constant_rate_factor',
        'preset',
        'max_rate',
        'buf_size',
        'profile',
        'pix_fmt',
        'width',
        'height',
        'frame_rate',
        'gop_size',
        'force_key_frames',
    ]

    class Meta:
        model = models.VideoTrack
        fields = '__all__'

    params = forms.JSONField(disabled=True,
                             required=False,
                             widget=forms.HiddenInput(),
                             initial={})
    _codec = forms.CharField(label=_('Codec'), initial='libx264')
    _constant_rate_factor = forms.IntegerField(
        label=_('CRF'),
        help_text=_('Constant rate factor or CRF value for ffmpeg'),
        initial=23)
    _preset = forms.CharField(label=_('Preset'), initial='slow')
    _max_rate = forms.IntegerField(label=_('Max rate'))
    _buf_size = forms.IntegerField(label=_('Buf size'))
    _profile = forms.CharField(label=_('Profile'), initial='main')
    _pix_fmt = forms.CharField(label=_('Pix fmt'), initial='yuv420p')
    _width = forms.IntegerField(label=_('Width'))
    _height = forms.IntegerField(label=_('Height'))
    _frame_rate = forms.FloatField(label=_('Frame rate'), initial=30.0)
    _gop_size = forms.IntegerField(
        label=_('GOP size'),
        help_text=_('Group of pictures size'),
        initial=30)
    _force_key_frames = forms.CharField(
        label=_('Force key frames'),
        help_text=_('ffmpeg -force_key_frames option value'),
        initial=FORCE_KEY_FRAMES)


class AudioTrackForm(NestedJSONForm):
    json_field = 'params'
    nested_fields = [
        'codec',
        'bitrate',
        'channels',
        'sample_rate',
    ]

    class Meta:
        model = models.AudioTrack
        fields = '__all__'

    params = forms.JSONField(disabled=True,
                             required=False,
                             widget=forms.HiddenInput(),
                             initial={})
    _codec = forms.CharField(label=_('Codec'), initial='libfdk_aac')
    _bitrate = forms.IntegerField(label=_('Bitrate'))
    _channels = forms.IntegerField(label=_('Channels'), initial=2)
    _sample_rate = forms.IntegerField(label=_('Sample rate'), initial=48000)
