#!/usr/bin/env python3
"""ACR receiver and serialized Docker deployment worker (Python stdlib only)."""
import copy
import gzip
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlsplit

CONFIG = Path('/etc/clawsocial-deploy/config.json')
STATE = Path('/var/lib/clawsocial-deploy')
TOKEN = Path('/etc/clawsocial-deploy/webhook.token')


def validate_event(payload, config):
    repo, push = payload.get('repository'), payload.get('push_data')
    if not isinstance(repo, dict) or not isinstance(push, dict):
        raise ValueError('invalid_event')
    expected = config['repository'].split('/', 1)[1]
    if (repo.get('repo_full_name') != expected
            or repo.get('region') != config['region']
            or push.get('tag') != config['tag']):
        raise ValueError('unexpected_repository_or_tag')
    digest = push.get('digest')
    if not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise ValueError('invalid_digest')
    return digest


def save_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


class Receiver(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        # Default access logs include the URL credential.
        pass

    def reply(self, code, status):
        data = json.dumps({'status': status}).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        url = urlsplit(self.path)
        supplied = parse_qs(url.query).get('token', [])
        expected = TOKEN.read_text().strip()
        if (url.path != '/hooks/acr/clawsocial' or not expected or len(supplied) != 1
                or not secrets.compare_digest(supplied[0], expected)):
            self.reply(403, 'forbidden')
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384 or self.headers.get('Transfer-Encoding'):
                raise ValueError('invalid_body_size')
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('invalid_event')
            digest = validate_event(payload, json.loads(CONFIG.read_text()))
        except (ValueError, TypeError):
            self.reply(400, 'invalid_event')
            return
        queue = STATE / 'queue'
        path = queue / (digest.split(':')[1] + '.json')
        if not path.exists():
            save_json(path, {'digest': digest})
        self.reply(202, 'queued')

    def setup(self):
        super().setup()
        self.connection.settimeout(10)


class Docker(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(90)
        self.sock.connect('/var/run/docker.sock')


def docker_api(method, path, payload=None):
    conn = Docker('localhost', timeout=90)
    conn.request(method, path, json.dumps(payload) if payload is not None else None,
                 {'Content-Type': 'application/json'})
    response = conn.getresponse()
    body, status = response.read(), response.status
    conn.close()
    if status >= 300:
        raise RuntimeError(f'docker_api_status_{status}')
    return json.loads(body) if body else None


def run(args, **kwargs):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=600, **kwargs)
    if result.returncode:
        raise RuntimeError('command_failed_' + args[0])
    return result.stdout


def merged_config(old, old_defaults, new_defaults, image):
    config = copy.deepcopy(new_defaults)
    defaults = dict(item.split('=', 1) for item in old_defaults.get('Env', []))
    env = dict(item.split('=', 1) for item in config.get('Env', []))
    for item in old['Config'].get('Env', []):
        key, value = item.split('=', 1)
        if defaults.get(key) != value:
            env[key] = value
    config['Env'] = [key + '=' + value for key, value in env.items()]
    config['Image'] = image
    config['HostConfig'] = copy.deepcopy(old['HostConfig'])
    return config


def rollback(active, name):
    new = docker_api('GET', '/containers/' + active['new_id'] + '/json')
    if new['State']['Running']:
        docker_api('POST', '/containers/' + active['new_id'] + '/stop?t=60')
    if new['Name'] == '/' + name:
        docker_api('POST', '/containers/' + active['new_id'] + '/rename?name=' + name + '-failed-' + active['stamp'])
    old = docker_api('GET', '/containers/' + active['old_id'] + '/json')
    if old['Name'] != '/' + name:
        docker_api('POST', '/containers/' + active['old_id'] + '/rename?name=' + name)
    if not old['State']['Running']:
        docker_api('POST', '/containers/' + active['old_id'] + '/start')
    wait_healthy(active['old_id'])


def wait_healthy(container_id):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        state = docker_api('GET', '/containers/' + container_id + '/json')['State']
        if state.get('Health', {}).get('Status') == 'healthy':
            return
        if not state['Running']:
            raise RuntimeError('container_stopped')
        time.sleep(3)
    raise RuntimeError('healthcheck_timeout')


SMOKE = """
import json, urllib.request, urllib.error
from pathlib import Path
for path in ['/health','/stats','/','/world/','/blog/','/drop/']:
    assert urllib.request.urlopen('http://127.0.0.1:8000'+path,timeout=5).status==200
try:
    urllib.request.urlopen('http://127.0.0.1:8000/api/remote-command/targets',timeout=5)
except urllib.error.HTTPError as e:
    assert e.code==401
else:
    raise AssertionError('v12_auth_missing')
import os
token=os.environ.get('REMOTE_COMMAND_OPERATOR_TOKEN') or Path(os.environ.get('REMOTE_COMMAND_OPERATOR_TOKEN_FILE','/app/remote-command-operator.token')).read_text().strip()
req=urllib.request.Request('http://127.0.0.1:8000/api/remote-command/targets',headers={'Authorization':'Bearer '+token})
assert urllib.request.urlopen(req,timeout=5).status==200
assert urllib.request.urlopen('http://127.0.0.1:8000/legacy-v11/api/remote-command/targets',timeout=5).status==200
"""


def deploy(digest, config, queue_path):
    if shutil.disk_usage(STATE).free < 2 * 1024**3:
        raise RuntimeError('insufficient_disk_space')
    tag = config['repository'] + ':' + config['tag']
    run(['docker', 'pull', tag])
    image = docker_api('GET', '/images/' + tag + '/json')
    immutable = config['repository'] + '@' + digest
    if immutable not in image.get('RepoDigests', []):
        return 'stale_event_ignored'
    for key, value in config['required_labels'].items():
        if image['Config'].get('Labels', {}).get(key) != value:
            raise RuntimeError('image_compatibility_check_failed')
    old = docker_api('GET', '/containers/' + config['container'] + '/json')
    if old['Image'] == image['Id'] and old['State'].get('Health', {}).get('Status') == 'healthy':
        return 'already_current'
    if not old['State']['Running']:
        raise RuntimeError('current_container_not_running')
    stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3)
    backup = STATE / 'backups' / stamp
    backup.mkdir(parents=True, mode=0o700)
    # Dump contains database contents and remains readable only by root.
    with (backup / 'database.sql.gz').open('wb') as output:
        dump = subprocess.Popen(['docker','exec',old['Id'],'mariadb-dump','-u','root',
                                 '--single-transaction','--routines','--events','--all-databases'],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            with gzip.GzipFile(fileobj=output, mode='wb') as compressed:
                shutil.copyfileobj(dump.stdout, compressed)
            if dump.wait(timeout=60):
                raise RuntimeError('database_backup_failed')
        finally:
            if dump.poll() is None:
                dump.kill()
                dump.wait()
    defaults = docker_api('GET', '/images/' + old['Image'] + '/json')['Config']
    payload = merged_config(old, defaults, image['Config'], immutable)
    new = docker_api('POST', '/containers/create?name=' + config['container'] + '-candidate-' + stamp, payload)
    active = {'old_id': old['Id'], 'new_id': new['Id'], 'stamp': stamp,
              'queue': queue_path.name, 'digest': digest}
    save_json(STATE / 'active.json', active)
    try:
        run(['docker','exec',old['Id'],'mariadb-admin','-u','root','shutdown'])
        docker_api('POST', '/containers/' + old['Id'] + '/stop?t=60')
        for directory in ['uploads', 'logs']:
            dest = backup / directory
            run(['docker','cp','-a',old['Id'] + ':/app/' + directory,str(dest)])
            run(['docker','cp','-a',str(dest) + '/.',new['Id'] + ':/app/' + directory + '/'])
        docker_api('POST', '/containers/' + old['Id'] + '/rename?name=' + config['container'] + '-rollback-' + stamp)
        docker_api('POST', '/containers/' + new['Id'] + '/rename?name=' + config['container'])
        docker_api('POST', '/containers/' + new['Id'] + '/start')
        wait_healthy(new['Id'])
        run(['docker','exec',new['Id'],'python','-c',SMOKE])
    except Exception:
        rollback(active, config['container'])
        (STATE / 'active.json').unlink()
        raise RuntimeError('deployment_failed_rolled_back') from None
    (STATE / 'active.json').unlink()
    return 'deployed'


def worker():
    config = json.loads(CONFIG.read_text())
    active_path = STATE / 'active.json'
    if active_path.exists():
        active = json.loads(active_path.read_text())
        rollback(active, config['container'])
        active_path.unlink()
        record = STATE / 'queue' / active['queue']
        record.unlink(missing_ok=True)
        save_json(STATE / 'history' / (active['stamp'] + '.json'),
                  {'digest': active['digest'], 'status': 'interrupted_deployment_rolled_back'})
    for path in sorted((STATE / 'queue').glob('*.json')):
        digest = json.loads(path.read_text())['digest']
        try:
            status = deploy(digest, config, path)
        except Exception as exc:
            if active_path.exists():
                # Recovery failed: preserve transaction and queue; systemd must report failure.
                raise
            status = 'failed_' + type(exc).__name__ + '_' + str(exc)
        save_json(STATE / 'history' / (time.strftime('%Y%m%d-%H%M%S') + '-' + path.name),
                  {'digest': digest, 'status': status, 'completed_at': time.time()})
        path.unlink()
        print(json.dumps({'digest': digest, 'status': status}), flush=True)
    # Prune only backups created by this worker; keep the latest three.
    backups = sorted((STATE / 'backups').iterdir())
    for path in backups[:-3]:
        if path.is_dir() and re.fullmatch(r'\d{8}-\d{6}-[0-9a-f]{6}', path.name):
            shutil.rmtree(path)
    containers = docker_api('GET', '/containers/json?all=1')
    for kind in ['rollback', 'failed']:
        pattern = re.escape('/' + config['container'] + '-' + kind + '-') + r'\d{8}-\d{6}-[0-9a-f]{6}'
        owned = sorted((item for item in containers if item['State'] != 'running'
                        and any(re.fullmatch(pattern, name) for name in item['Names'])),
                       key=lambda item: item['Created'], reverse=True)
        for item in owned[2:]:
            docker_api('DELETE', '/containers/' + item['Id'])
            # No force: Docker refuses removal if another container still uses this image.
            try:
                docker_api('DELETE', '/images/' + item['ImageID'])
            except RuntimeError:
                pass


if __name__ == '__main__':
    os.umask(0o077)
    if sys.argv[1:] == ['serve']:
        HTTPServer(('127.0.0.1', 8790), Receiver).serve_forever()
    elif sys.argv[1:] == ['worker']:
        worker()
    else:
        raise SystemExit('usage: deploy.py serve|worker')
