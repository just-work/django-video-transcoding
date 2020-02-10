#!/bin/sh
chown -R nobody:root /opt/static/ && \
/usr/local/nginx/sbin/nginx -c /usr/local/nginx/conf/nginx.conf -g "daemon off;"