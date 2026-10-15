#!/bin/sh
# Netlify build: publish only the two pages, and proxy /api/* to the FastAPI
# backend so the browser talks to a single site (no CORS, same /api paths).
set -eu

if [ -z "${BACKEND_URL:-}" ]; then
    echo "BACKEND_URL is not set. Add it in Netlify: Site configuration > Environment variables" >&2
    echo "  e.g. BACKEND_URL=https://your-app.up.railway.app" >&2
    exit 1
fi
backend="${BACKEND_URL%/}"
case "$backend" in
    https://*) ;;
    *) echo "BACKEND_URL must start with https:// (got: $backend)" >&2; exit 1 ;;
esac

rm -rf dist
mkdir dist
cp index.html login.html dist/

cat > dist/_redirects <<EOF
/api/*  ${backend}/api/:splat  200!
/login  /login.html  200
EOF

echo "Published index.html and login.html; proxying /api/* to ${backend}"
