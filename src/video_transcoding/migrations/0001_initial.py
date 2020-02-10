# Generated by Django 3.0.3 on 2020-02-10 05:42

import django.core.validators
from django.db import migrations, models
import django.utils.timezone
import model_utils.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Video',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('status', models.SmallIntegerField(choices=[(0, 'created'), (1, 'queued'), (2, 'process'), (3, 'done'), (4, 'error')], default=0)),
                ('error', models.TextField(blank=True, null=True)),
                ('task_id', models.UUIDField(blank=True, null=True)),
                ('source', models.URLField(validators=[django.core.validators.URLValidator(schemes=('ftp', 'http'))])),
                ('basename', models.UUIDField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Video',
                'verbose_name_plural': 'Video',
            },
        ),
    ]