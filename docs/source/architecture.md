Architecture
============

This document describes a typical architecture of Video-On-Demand website.

Components
----------

``` blockdiag::

  blockdiag {
    node_width = 128;
    node_height = 40;
    span_width=128;
    span_height=60;
    
    CMS -> Broker [label="tasks", style=dotted];
    Transcoder <- Sources [label="src", thick, folded];
    Broker -> Transcoder [label="tasks", style=dotted];
    Transcoder -> Storage [label="HLS", folded, thick];
    Transcoder <-> TMP [label="files", thick];
    Storage -> CDN [label="HLS chunks"];
    CDN -> Player [label="cached chunks"];
    CMS [color=lightblue];
    Sources [shape = flowchart.database];
    Transcoder [color=lightblue];
    Broker [shape=flowchart.terminator];
    Storage [shape = flowchart.database];
    TMP [shape = flowchart.database];
    Player [shape=actor];
  }

```

* `Sources` storage contains original media for video content
* `CMS` stores video content list. 
* When a new video is created in `CMS`, it sends transcoding task via `Broker`
  to `Transcoder`
* `Transcoder` downloads source media from `Sources` storage
* `Transcoder` stores intermediate files at `TMP` storage 
  for resumable processing support
* `Transcoder` stores final HLS segments at `Storage`
* `Player` requests HLS segments from `CDN`
* `CDN` requests segments from `Storage` and caches them for scalability. 

Video processing steps
----------------------

``` seqdiag:: 

  seqdiag {
    CMS;Broker;DB;Transcoder;

    CMS => DB [label = "new video created"];
    CMS => Broker [label = "sends a task", return="ACK"];
    Broker -->> Transcoder [label = "receives a task"] {
      Transcoder => DB [label = "marks session started"];
      Transcoder -> Transcoder [label = "transcode video"];
      Transcoder => DB [label = "store video metadata"];
      Transcoder => DB [label = "marks session done"];
    }
    Broker <<-- Transcoder [label = "ACK"];
  }
```

1. A new video created in `CMS`
2. `CMS` puts a new task to a Celery task `Broker`
3. Celery worker at `Transcoder` node changes video status and transcodes video
4. Celery worker changes video status and saves result metadata (filename, 
    video characteristics etc...).

Transcoding steps
-----------------

``` seqdiag:: 

  seqdiag {
    Transcoder;Sources;TMP;Storage;
    === Split source ===
    Transcoder -->> Sources [label = "requests source file"]{
      Transcoder -->> TMP [label = "splits source to chunks", note="source\nchunks"];
      Transcoder <<-- TMP;
    }
    Transcoder <<-- Sources [label = "source file"]
    === Chunk transcode loop ===
    Transcoder -->> TMP [label = "read src chunk"] {
      Transcoder -->> TMP [label = "write transcoded chunk", note="transcoded\nchunk"];
      Transcoder <<-- TMP;
    }
    Transcoder <<-- TMP [label = "source chunk"];
    === Segment result ===
    Transcoder -->> TMP [label = "read transcoded chunks"] { 
      Transcoder -->> Storage [label = "segment to HLS", note="HLS\nsegments"];
      Transcoder <<-- Storage;
    }
    Transcoder <<-- TMP "chunks";
  }
```

1. `Transcoder` downloads and splits source file into chunks
2. Source chunks are stored at `TMP` storage to support resumable processing
3. `Transcoder` processes source chunks one-by-one and stores results at `TMP`
4. `Transcoder` concatenates all resulting chunks from `TMP` storage,
   segments them to HLS and saves at `Storage`.

## Fault tolerance

Transcoding video files is a long-time operation, anything can happen while
transcoder is active:

* Hardware failure
* Container failure
* Storage failure
* Network failure
* New release deployment
* Container/VM eviction (i.e. for preemptible VMs)

Django-video-transcoder addresses some of this failures:

* It relies on a fault-tolerant distributed storage for temporary files
* This allows to resume video processing from the checkpoint
  (last successfully transcoded chunk), even if transcoding is continued at
  another host
* Transcoder tracks processing state at the database to prevent multiple
  worker to process same video
* Automatic task retry feature allows to handle temporary failures without
  manual steps

## Load balancing

### Transcoding

Transcoding video files requires lot's of CPU power, or even GPU. `ffmpeg` 
under the hood of `django-video-transcoding` utilizes all CPU cores, so every
physical host should launch single celery worker. When high transcoding 
throughput is required, new physical hosts should be added. Load balancing is 
done transparently as Celery task broker clients handle messages independently.

### Storage

Storing video files has some performance concerns:

1. Videos are large, all content may not fit to a single server.
2. Lot's of disk IO is needed to handle multiple clients accessing different 
    video files.
3. Files could be damaged or disappear because of disk failures.

It's recommended to use production-ready distributed storage solution, the
easiest option is `S3`-compatible service from cloud provider.

### Serving video

Sending video to multiple clients is limited with:

* Network bandwidth
* Disk iops
* CPU resources for HTTPS encryption
* Fault tolerance

The easiest way to handle all these problems is to use `CDN` in front of 
your video storage.

### Conclusion

Video-on-demand performance is a large and exciting topic; in some cases it 
could be addressed with simple approaches, in another lot's of work need to be 
done. Despite these advices above, `django-video-transcoding` does not provide
universal high-performance solution; it's purpose is simplicity and 
extensibility.