"""Run against the CI container; no real social-media downloads."""
import json
import time
import urllib.error
import urllib.request

base = 'http://127.0.0.1:10000'
for attempt in range(60):
    try:
        with urllib.request.urlopen(base + '/healthz', timeout=2) as response:
            assert json.load(response)['status'] == 'ok'
        break
    except (OSError, urllib.error.URLError):
        time.sleep(1)
else:
    raise SystemExit('Container did not become healthy.')

with urllib.request.urlopen(base + '/api/config', timeout=5) as response:
    config = json.load(response)
    cookie = response.headers['Set-Cookie'].split(';')[0]
assert config['hosted'] and config['ffmpeg'] and config['node']
assert config['downloads'] is None
for asset in ['/', '/static/app.js', '/static/style.css', '/static/mobile.css']:
    with urllib.request.urlopen(base + asset, timeout=5) as response:
        assert response.status == 200
request = urllib.request.Request(base + '/api/jobs', data=json.dumps({'url':'https://127.0.0.1/private'}).encode(),
    headers={'Content-Type':'application/json','Cookie':cookie,'X-ClipDock-Token':config['token']})
try:
    urllib.request.urlopen(request, timeout=5)
    raise AssertionError('Unsafe URL was accepted.')
except urllib.error.HTTPError as error:
    assert error.code == 400
print('Container health, Python/Node/FFmpeg, bundled UI and hosted request validation passed.')
