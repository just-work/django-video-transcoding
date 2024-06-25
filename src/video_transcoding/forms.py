from typing import List, Any

from django import forms

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
        cd[self.json_field] = {k: cd[f'_{k}'] for k in self.nested_fields}
        return cd


class VideoProfileForm(NestedJSONForm):
    json_field = 'condition'
    nested_fields = ['min_bitrate', 'min_width', 'min_height', 'min_frame_rate']

    class Meta:
        model = models.VideoProfile
        fields = '__all__'

    condition = forms.JSONField(disabled=True,
                                required=False,
                                widget=forms.HiddenInput(),
                                initial={})
    _min_bitrate = forms.IntegerField()
    _min_width = forms.IntegerField()
    _min_height = forms.IntegerField()
    _min_frame_rate = forms.FloatField()


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
    _min_bitrate = forms.IntegerField()
    _min_sample_rate = forms.IntegerField()


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
    _codec = forms.CharField(initial='libx264')
    _constant_rate_factor = forms.IntegerField(initial=23)
    _preset = forms.CharField(initial='slow')
    _max_rate = forms.IntegerField()
    _buf_size = forms.IntegerField()
    _profile = forms.CharField(initial='main')
    _pix_fmt = forms.CharField(initial='yuv420p')
    _width = forms.IntegerField()
    _height = forms.IntegerField()
    _frame_rate = forms.FloatField(initial=30.0)
    _gop_size = forms.IntegerField(initial=30)
    _force_key_frames = forms.CharField(initial=FORCE_KEY_FRAMES)


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
    _codec = forms.CharField(initial='libfdk_aac')
    _bitrate = forms.IntegerField()
    _channels = forms.IntegerField(initial=2)
    _sample_rate = forms.IntegerField(initial=48000)
