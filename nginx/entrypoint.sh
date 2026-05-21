#!/bin/sh
set -e
htpasswd -nbm "$APP_USER" "$APP_PASSWORD" > /etc/nginx/.htpasswd
exec nginx -g "daemon off;"
