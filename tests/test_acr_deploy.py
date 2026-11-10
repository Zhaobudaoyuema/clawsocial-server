"""Host deployment code: receiver validation, queueing and failure recovery."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import threading
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

spec = importlib.util.spec_from_file_location(
    'acr_deploy', Path(__file__).parents[1] / 'ops/acr-deploy/deploy.py',
)
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)
CONFIG = {'repository': 'registry.example/namespace/app', 'region': 'cn-beijing',
          'tag': 'v3', 'container': 'app', 'required_labels': {'version': '12'}}
DIGEST = 'sha256:' + 'a' * 64


def event():
    return {'repository': {'repo_full_name': 'namespace/app', 'region': 'cn-beijing'},
            'push_data': {'tag': 'v3', 'digest': DIGEST}}


@pytest.fixture
def state(tmp_path, monkeypatch):
    for name in ['queue', 'history', 'backups']:
        (tmp_path / name).mkdir()
    config = tmp_path / 'config.json'
    config.write_text(json.dumps(CONFIG))
    token = tmp_path / 'token'
    token.write_text('test-webhook-token')
    monkeypatch.setattr(deploy, 'STATE', tmp_path)
    monkeypatch.setattr(deploy, 'CONFIG', config)
    monkeypatch.setattr(deploy, 'TOKEN', token)
    return tmp_path


@pytest.mark.parametrize('section,key,value', [
    ('repository', 'repo_full_name', 'other/app'),
    ('repository', 'region', 'other-region'),
    ('push_data', 'tag', 'other-tag'),
    ('push_data', 'digest', 'sha256:bad; shell'),
])
def test_unapproved_events_rejected(section, key, value):
    payload = event()
    payload[section][key] = value
    with pytest.raises(ValueError):
        deploy.validate_event(payload, CONFIG)


def test_receiver_auth_rotation_and_duplicate_queue(state):
    server = deploy.HTTPServer(('127.0.0.1', 0), deploy.Receiver)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}/hooks/acr/clawsocial?token='

    def post(token, payload):
        request = Request(url + token, json.dumps(payload).encode(), method='POST')
        try:
            with urlopen(request, timeout=5) as response:
                return response.status
        except HTTPError as exc:
            return exc.code

    try:
        assert post('wrong', event()) == 403
        assert post('test-webhook-token', event()) == 202
        assert post('test-webhook-token', event()) == 202
        assert len(list((state / 'queue').glob('*.json'))) == 1
        assert post('test-webhook-token', []) == 400
        deploy.TOKEN.write_text('replacement')
        assert post('test-webhook-token', event()) == 403
        assert post('replacement', event()) == 202
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_environment_resolved_from_current_container():
    old = {'Config': {'Env': ['PATH=old-default', 'DB_PASSWORD=test-runtime-value']},
           'HostConfig': {'Binds': ['database:/var/lib/mysql', '/token:/token:ro']}}
    snapshot = copy.deepcopy(old)
    config = deploy.merged_config(old, {'Env': ['PATH=old-default']},
                                   {'Env': ['PATH=new-default'], 'Entrypoint': ['new-entrypoint']}, 'repo@digest')
    assert config == {'Env': ['PATH=new-default', 'DB_PASSWORD=test-runtime-value'],
                      'Entrypoint': ['new-entrypoint'], 'Image': 'repo@digest',
                      'HostConfig': old['HostConfig']}
    assert old == snapshot


@pytest.mark.parametrize('current_digest,current_id,expected', [
    ('sha256:' + 'b' * 64, 'same', 'stale_event_ignored'),
    (DIGEST, 'same', 'already_current'),
])
def test_stale_and_duplicate_events_do_not_restart(state, monkeypatch, current_digest, current_id, expected):
    actions = []
    monkeypatch.setattr(deploy, 'run', lambda args: actions.append(args))

    def api(method, path, payload=None):
        assert method == 'GET'
        if path.startswith('/images/'):
            return {'RepoDigests': [CONFIG['repository'] + '@' + current_digest],
                    'Id': current_id, 'Config': {'Labels': {'version': '12'}}}
        return {'Image': 'same', 'State': {'Health': {'Status': 'healthy'}}}

    monkeypatch.setattr(deploy, 'docker_api', api)
    assert deploy.deploy(DIGEST, CONFIG, state / 'queue/test.json') == expected
    assert actions == [['docker', 'pull', CONFIG['repository'] + ':v3']]


def test_rollback_stops_new_before_starting_old(monkeypatch):
    actions = []

    def api(method, path, payload=None):
        actions.append((method, path))
        if method == 'GET':
            return {'Name': '/app' if 'new' in path else '/app-rollback-stamp',
                    'State': {'Running': 'new' in path}}

    monkeypatch.setattr(deploy, 'docker_api', api)
    monkeypatch.setattr(deploy, 'wait_healthy', lambda container: actions.append(('healthy', container)))
    deploy.rollback({'new_id': 'new', 'old_id': 'old', 'stamp': 'stamp'}, 'app')
    assert actions == [
        ('GET', '/containers/new/json'), ('POST', '/containers/new/stop?t=60'),
        ('POST', '/containers/new/rename?name=app-failed-stamp'),
        ('GET', '/containers/old/json'), ('POST', '/containers/old/rename?name=app'),
        ('POST', '/containers/old/start'), ('healthy', 'old'),
    ]


def test_worker_recovers_interrupted_deployment(state, monkeypatch):
    active = {'new_id': 'new', 'old_id': 'old', 'stamp': 'interrupted',
              'queue': 'job.json', 'digest': DIGEST}
    (state / 'active.json').write_text(json.dumps(active))
    (state / 'queue/job.json').write_text(json.dumps({'digest': DIGEST}))
    calls = []
    monkeypatch.setattr(deploy, 'rollback', lambda active, name: calls.append(name))
    monkeypatch.setattr(deploy, 'docker_api', lambda *_args: [])
    deploy.worker()
    assert calls == ['app']
    assert not (state / 'active.json').exists()
    assert not (state / 'queue/job.json').exists()
    assert json.loads((state / 'history/interrupted.json').read_text())['status'] == 'interrupted_deployment_rolled_back'


def test_smoke_failure_rolls_back_after_switch(state, monkeypatch):
    actions = []

    def api(method, path, payload=None):
        actions.append((method, path))
        if path == '/images/' + CONFIG['repository'] + ':v3/json':
            return {'RepoDigests': [CONFIG['repository'] + '@' + DIGEST], 'Id': 'new-image',
                    'Config': {'Labels': {'version': '12'}}}
        if path == '/containers/app/json':
            return {'Id': 'old', 'Image': 'old-image', 'State': {'Running': True},
                    'Config': {}, 'HostConfig': {}}
        if path == '/images/old-image/json':
            return {'Config': {}}
        if path.startswith('/containers/create'):
            return {'Id': 'new'}

    def run(args):
        if args[:4] == ['docker', 'exec', 'new', 'python']:
            raise RuntimeError('smoke_failed')

    dump = SimpleNamespace(stdout=io.BytesIO(b'backup'), wait=lambda **kwargs: 0, poll=lambda: 0)
    monkeypatch.setattr(deploy.subprocess, 'Popen', lambda *args, **kwargs: dump)
    monkeypatch.setattr(deploy, 'docker_api', api)
    monkeypatch.setattr(deploy, 'run', run)
    monkeypatch.setattr(deploy, 'wait_healthy', lambda *_args: None)
    recovered = []
    monkeypatch.setattr(deploy, 'rollback', lambda active, name: recovered.append((active['old_id'], name)))
    with pytest.raises(RuntimeError, match='deployment_failed_rolled_back'):
        deploy.deploy(DIGEST, CONFIG, state / 'queue/job.json')
    assert recovered == [('old', 'app')]
    assert ('POST', '/containers/new/start') in actions
    assert not (state / 'active.json').exists()
