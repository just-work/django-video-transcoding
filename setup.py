from setuptools import setup

setup(
    name='django_video_transcoding',
    version='0.0.1',
    packages=[
        'video_transcoding',
        'video_transcoding.migrations'
    ],
    url='https://github.com/just-work/django-video-transcoding',
    license='BSD',
    author='Sergey Tikhonov',
    author_email='zimbler@gmail.com',
    description='Simple video transcoding application for Django framework',
    requires=[
        'Django',
        'requests',
        'Celery',
        'redis',
        'pymediainfo',
        'fffw', 'django-model-utils'
    ]
)
