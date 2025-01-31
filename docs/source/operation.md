Operation
=========

This document describes `django-video-transcoding` operation details.

### Proper shutdown

Processing video files is a very long operation, so waiting for celery task
complition while shutting down is inacceptable. On the other hand, if celery
worker processes are killed, lost tasks an zombie ffmpeg processes may appear.

* if you are running transcoder in a container, make sure that celery master 
  process has pid 1 (docker will send SIGTERM to it by default)
* for separate celery app make sure that it sets process group for all workers
  and propagates SIGUSR1 to trigger graceful worker shutdown

### Resumable workers

For modern cloud-based installations an optimal solution is to use 
[Preemptible VM instances](https://cloud.google.com/compute/docs/instances/preemptible).
On the one hand they are inexpensive, but on the another these VMs can be 
shut down at any time.

Transcoding VOD files is a very time and CPU consuming operation, 
so the implemetation should support resumable transcoding.

For large container-based deployments (docker, K8s) resumable transcoding 
simplifies hardware failure handling and release management.

Django-video-transcoding implements resumable strategy for transcoding:

* It splits source file into 1-minute chunks while downloading
* Each chunk is transcoded independently
* At the end all chunks are concatenated and segmented to HLS streams
* After restart each step can be skipped if it's result already exists

So, temporary storage should be persistent and host-independent. We recommend
mounting `S3` bucket as a file system.

### Getting sources

`ffmpeg` supports a large number of ingest protocols, such as `http` and `ftp`.
This allows downloading source video and splitting it to chunks in a single pass.
The main drawback is inability to tune some protocol options, especially for
`ftp`. We recommend to use `http` for source videos.

### Storing temporary files

For some reasons the `segment` muxer is used to split source video into chunks,
and this muxer does not support setting http method. If temporary storage
is accessed via HTTP, it must support storing files via `POST` requests.

### Serving HLS streams

Serving video requires high network bandwidth and fast drives, 
especially if number of users is large. It's recommended to use CDN to protect
video storage from high repetitive load. 

* Use `CloudFront` with `S3` or there analogues from other cloud providers
* Or use `CDN` provider in front of HTTP server
* For self-hosted solutions distribute network load across multiple edge servers
  (round robin is supported by multiple hosts in `VIDEO_EDGES` env variable).
