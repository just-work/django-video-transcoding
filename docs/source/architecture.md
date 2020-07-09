Architecture
============

This document describes a typical architecture of Video-On-Demand website.

``` blockdiag::

  blockdiag {
    span_width=128;
    node_height=50;
    
    Sources -> Transcoder [label="source", folded];
    CMS -> RabbitMQ [label=tasks, style=dotted];
    RabbitMQ -> Transcoder [label=tasks, style=dotted];
    Transcoder -> Origin [label="mp4", folded];
    Origin -> Edge [label="HLS chunks"];
    Edge -> Player [label="cached chunks"];
    CMS [color=lightblue];
    Transcoder [color=lightblue];
    RabbitMQ [shape=flowchart.terminator];
    
    Player [shape=actor];
  }
```

Despite `django-video-transcoding` affects `CMS` and `Transcoding` only, we'll 
describe full video life cycle.

## Video life cycle

1. A new video file is uploaded to `Sources` storage. A link to this video file 
   is added to `CMS` as a new video object.
2. `CMS` sends a [Celery](https://github.com/celery/celery) task to `RabbitMQ` 
   (celery task broker).
3. Celery worker at `Transcoder` downloads source file from `Sources` storage 
   and makes an `mp4` file from it. Resulting file is uploaded to `Origin`, 
   which is a robust storage for transcoded video files.
4. After that video is marked as available for clients. Depending on `CMS` 
   implementation, video is linked with some CMS media objects like "movie" or
   "episode", etc... `CMS` now can provide a video stream link to `Player`
5. Player requests a video stream from `Edge` (a server with large disk cache 
   and broadband network interface), usually with 
   [HLS](https://en.wikipedia.org/wiki/HTTP_Live_Streaming) or 
   [MPEG-Dash](https://en.wikipedia.org/wiki/Dynamic_Adaptive_Streaming_over_HTTP)
   protocol, widely used for VOD in Internet.
6. In case of cache miss `Edge` requests video stream from `Origin` server. 
7. `Origin` extracts small chunks from mp4 file (i.e. with 
    [nginx-vod-module](https://github.com/kaltura/nginx-vod-module)).
8. `Player` receives next video chunk and plays it in web-browser. 

## Transcoding steps

``` seqdiag:: 

  seqdiag {
    CMS => RabbitMQ [label = "sends a task", return="ACK"];
    RabbitMQ ->> Transcoder [label = "receives a task"];
    Transcoder => DB [label = "marks session started"];
    Transcoder => Source [label = "requests source file", return="source file"];
    Transcoder -> Transcoder [label = "transcode file"];
    Transcoder => Origin [label = "store resulting file", return="201 created"];
    Transcoder => DB [label = "store video metadata"];
    Transcoder => DB [label = "marks session done"];
    RabbitMQ <-- Transcoder [label = "ACK"];
  }
```

1. Django at `CMS` puts a celery task
2. Celery worker at `Transcoder` node changes video status and process video:
    * download source file from `Sources`
    * transcodes it to a local temporary directory
    * upload result to `Origin`
3. Celery worker changes video status and saves result metadata (filename, 
    video characteristics and so on).

## Load balancing

### Transcoding

Transcoding video files requires lot's of CPU power, or even GPU. `ffmpeg` 
under the hood of `django-video-transcoding` utilizes all CPU cores, so every
physical host should launch single celery worker. When high transcoding 
throughput is required, new physical hosts should be added. Load balancing is 
done transparently as RabbitMQ clients handle messages independently.

### Storage

Storing video files has some performance concerns:

1. Video files are large, all content may not fit to a single server.
2. Lot's of disk IO is needed to handle multiple clients accessing different 
    video files.
3. Files could be damaged or disappear because of disk failures.

For now, transcoding saves each video file to every origin specified in 
settings. This does not solve problem #1, but is easy enough. To address a 
problem with very large content base following should be done:

* Implement `M:N` uploading strategy: store M file replicas on N servers
* Save origin list for video file
* Change video stream link generation (choose one of origin where file exists 
    and insert it to an edge link)
    
### Serving video

Sending video to multiple clients is limited with:

* Network bandwidth
* Disk iops
* CPU resources for HTTPS encryption
* CPU resources needed to make chunks from mp4 files
* Fault tolerance

These limitations lead to having multiple caching edge servers. Having multiple 
edges with disk cache is obvious enough; edge server failure is mitigated on the 
player side: it receives all edges list and can try each edge one-by-one.

``` blockdiag::

  blockdiag {
    Player -> Edges;
    Edges -> Origins;

    Edges [stacked];
    Origins [stacked];
  }
```

### Conclusion

Video-on-demand performance is a large and exciting topic; in some cases it 
could be addressed with simple approaches, in another lot's of work need to be 
done. Despite these advices above, `django-video-transcoding` does not provide
universal high-performance solution; it's purpose is simplicity and 
extensibility. 