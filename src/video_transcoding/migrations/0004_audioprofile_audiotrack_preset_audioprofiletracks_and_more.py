# Generated by Django 5.0.9 on 2024-10-14 11:15

import django.db.models.deletion
import django.utils.timezone
import model_utils.fields
from django.db import migrations, models

from video_transcoding import defaults


class Migration(migrations.Migration):

    dependencies = [
        ('video_transcoding', '0003_auto_20200525_1130'),
    ]

    operations = [
        migrations.CreateModel(
            name='AudioProfile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('name', models.SlugField(max_length=255, verbose_name='name')),
                ('order_number', models.SmallIntegerField(default=0, verbose_name='order number')),
                ('condition', models.JSONField(default=dict, verbose_name='condition')),
            ],
            options={
                'verbose_name': 'Audio profile',
                'verbose_name_plural': 'Audio profiles',
                'ordering': ['order_number'],
            },
        ),
        migrations.CreateModel(
            name='AudioTrack',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('name', models.SlugField(max_length=255, verbose_name='name')),
                ('params', models.JSONField(default=dict, verbose_name='params')),
            ],
            options={
                'verbose_name': 'Audio track',
                'verbose_name_plural': 'Audio tracks',
            },
        ),
        migrations.CreateModel(
            name='Preset',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('name', models.SlugField(max_length=255, unique=True, verbose_name='name')),
            ],
            options={
                'verbose_name': 'Preset',
                'verbose_name_plural': 'Presets',
            },
        ),
        migrations.CreateModel(
            name='AudioProfileTracks',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_number', models.SmallIntegerField(default=0, verbose_name='order number')),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video_transcoding.audioprofile', verbose_name='profile')),
                ('track', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video_transcoding.audiotrack', verbose_name='track')),
            ],
            options={
                'verbose_name': 'Audio profile track',
                'verbose_name_plural': 'Audio profile tracks',
                'ordering': ['order_number'],
                'unique_together': {('profile', 'track')},
                'verbose_name': 'Audio profile track',
                'verbose_name_plural': 'Audio profile tracks',
            },
        ),
        migrations.AddField(
            model_name='audioprofile',
            name='audio',
            field=models.ManyToManyField(through='video_transcoding.AudioProfileTracks', to='video_transcoding.audiotrack', verbose_name='Audio tracks'),
        ),
        migrations.AddField(
            model_name='audiotrack',
            name='preset',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='audio_tracks', to='video_transcoding.preset', verbose_name='preset'),
        ),
        migrations.AddField(
            model_name='audioprofile',
            name='preset',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='audio_profiles', to='video_transcoding.preset', verbose_name='preset'),
        ),
        migrations.AddField(
            model_name='video',
            name='preset',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='video_transcoding.preset', verbose_name='preset'),
        ),
        migrations.CreateModel(
            name='VideoProfile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('name', models.SlugField(max_length=255, verbose_name='name')),
                ('order_number', models.SmallIntegerField(default=0, verbose_name='order number')),
                ('condition', models.JSONField(default=dict, verbose_name='condition')),
                ('preset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='video_profiles', to='video_transcoding.preset', verbose_name='preset')),
            ],
            options={
                'verbose_name': 'Video profile',
                'verbose_name_plural': 'Video profiles',
                'ordering': ['order_number'],
            },
        ),
        migrations.CreateModel(
            name='VideoTrack',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('name', models.SlugField(max_length=255, verbose_name='name')),
                ('params', models.JSONField(default=dict, verbose_name='params')),
                ('preset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='video_tracks', to='video_transcoding.preset', verbose_name='preset')),
            ],
            options={
                'verbose_name': 'Video track',
                'verbose_name_plural': 'Video tracks',
                'unique_together': {('name', 'preset')},
                'verbose_name': 'Video track',
                'verbose_name_plural': 'Video tracks',
            },
        ),
        migrations.CreateModel(
            name='VideoProfileTracks',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_number', models.SmallIntegerField(default=0, verbose_name='order number')),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video_transcoding.videoprofile', verbose_name='profile')),
                ('track', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video_transcoding.videotrack', verbose_name='track')),
            ],
            options={
                'verbose_name': 'Video profile track',
                'verbose_name_plural': 'Video profile tracks',
                'ordering': ['order_number'],
                'unique_together': {('profile', 'track')},
                'verbose_name': 'Video profile track',
                'verbose_name_plural': 'Video profile tracks',
            },
        ),
        migrations.AddField(
            model_name='videoprofile',
            name='video',
            field=models.ManyToManyField(through='video_transcoding.VideoProfileTracks', to='video_transcoding.videotrack', verbose_name='Video tracks'),
        ),
        migrations.AlterUniqueTogether(
            name='audiotrack',
            unique_together={('name', 'preset')},
        ),
        migrations.AlterUniqueTogether(
            name='audioprofile',
            unique_together={('name', 'preset')},
        ),
        migrations.AlterUniqueTogether(
            name='videoprofile',
            unique_together={('name', 'preset')},
        ),
        migrations.AlterModelOptions(
            name='audioprofile',
            options={'ordering': ['order_number'], 'verbose_name': 'Audio profile', 'verbose_name_plural': 'Audio profiles'},
        ),
        migrations.AlterModelOptions(
            name='audiotrack',
            options={'verbose_name': 'Audio track', 'verbose_name_plural': 'Audio tracks'},
        ),
        migrations.AlterModelOptions(
            name='videoprofile',
            options={'ordering': ['order_number'], 'verbose_name': 'Video profile', 'verbose_name_plural': 'Video profiles'},
        ),
        migrations.AlterField(
            model_name='audioprofile',
            name='audio',
            field=models.ManyToManyField(through='video_transcoding.AudioProfileTracks', to='video_transcoding.audiotrack', verbose_name='Audio tracks'),
        ),
        migrations.AlterField(
            model_name='audioprofile',
            name='condition',
            field=models.JSONField(default=dict, verbose_name='condition'),
        ),
        migrations.AlterField(
            model_name='audioprofile',
            name='name',
            field=models.SlugField(max_length=255, verbose_name='name'),
        ),
        migrations.AlterField(
            model_name='audioprofile',
            name='order_number',
            field=models.SmallIntegerField(default=0, verbose_name='order number'),
        ),
        migrations.AlterField(
            model_name='audioprofile',
            name='preset',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='audio_profiles', to='video_transcoding.preset', verbose_name='preset'),
        ),
        migrations.AlterField(
            model_name='audioprofiletracks',
            name='profile',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video_transcoding.audioprofile', verbose_name='profile'),
        ),
        migrations.AlterField(
            model_name='audioprofiletracks',
            name='track',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video_transcoding.audiotrack', verbose_name='track'),
        ),
        migrations.AlterField(
            model_name='audiotrack',
            name='name',
            field=models.SlugField(max_length=255, verbose_name='name'),
        ),
        migrations.AlterField(
            model_name='audiotrack',
            name='params',
            field=models.JSONField(default=dict, verbose_name='params'),
        ),
        migrations.AlterField(
            model_name='audiotrack',
            name='preset',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='audio_tracks', to='video_transcoding.preset', verbose_name='preset'),
        ),
        migrations.AlterField(
            model_name='videoprofile',
            name='condition',
            field=models.JSONField(default=dict, verbose_name='condition'),
        ),
        migrations.AlterField(
            model_name='videoprofile',
            name='name',
            field=models.SlugField(max_length=255, verbose_name='name'),
        ),
        migrations.AlterField(
            model_name='videoprofile',
            name='order_number',
            field=models.SmallIntegerField(default=0, verbose_name='order number'),
        ),
        migrations.AlterField(
            model_name='videoprofile',
            name='preset',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='video_profiles', to='video_transcoding.preset', verbose_name='preset'),
        ),
        migrations.AlterField(
            model_name='videoprofile',
            name='video',
            field=models.ManyToManyField(through='video_transcoding.VideoProfileTracks', to='video_transcoding.videotrack', verbose_name='Video tracks'),
        ),
        migrations.AlterField(
            model_name='videoprofiletracks',
            name='profile',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video_transcoding.videoprofile', verbose_name='profile'),
        ),
        migrations.AlterField(
            model_name='videoprofiletracks',
            name='track',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='video_transcoding.videotrack', verbose_name='track'),
        ),
    ]

    if defaults.VIDEO_MODEL == 'video_transcoding.Video':
        operations.extend([
            migrations.AddField(
                model_name='video',
                name='preset',
                field=models.ForeignKey(blank=True, null=True,
                                        on_delete=django.db.models.deletion.SET_NULL,
                                        to='video_transcoding.preset'),
            ),
        ])