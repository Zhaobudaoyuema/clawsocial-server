"""Gomoku tests use a standalone app and a fresh on-disk DB, never production state."""
import importlib.util
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location('gomoku_test_module', Path(__file__).resolve().parents[1] / 'app/api/gomoku.py')
gomoku = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gomoku)


@pytest.fixture
def room(tmp_path, monkeypatch):
    monkeypatch.setenv('GOMOKU_DB', str(tmp_path / 'game.sqlite'))
    app = FastAPI(); app.include_router(gomoku.router)
    with TestClient(app) as c:
        r = c.post('/api/gomoku/rooms', json={}).json()
        yield c, r, '/api/gomoku/rooms/' + r['id']


def play(c, r, path, move, revision, role='human', **extra):
    return c.post(path+'/actions', headers={'X-Gomoku-Token': r['humanToken' if role == 'human' else 'agentToken']},
                  json={'move': move, 'expectedRevision': revision, 'explanation': '防守并准备下一步进攻。', **extra})


def test_auth_and_turn_and_conflict(room):
    c,r,p=room
    assert c.get(p).status_code == 404
    assert c.get(p, headers={'X-Gomoku-Token':'wrong'}).status_code == 403
    assert play(c,r,p,'H8',0,'agent').status_code == 409
    assert play(c,r,p,'H8',0).status_code == 200
    assert play(c,r,p,'G8',0,'agent').status_code == 409
    assert play(c,r,p,'H8',1,'agent').status_code == 409
    assert play(c,r,p,'P8',1,'agent').status_code == 422
    g=play(c,r,p,'G8',1,'agent',humanMoveReview='这一步占据中心。').json()
    assert g['rows'][7][6:8] == 'OX'
    assert g['moves'][-1]['review'] == '这一步占据中心。'


def test_winning_threat_and_finish(room):
    c,r,p=room
    for i,coord in enumerate(['A1','A3','B1','C3','C1','E3','D1','G3']):
        g=play(c,r,p,coord,i,'human' if i%2==0 else 'agent').json()
    assert 'E1' in g['immediateWinningMoves']['black']
    g=play(c,r,p,'E1',8).json()
    assert g['winner']=='black' and len(g['winningLine'])==5
    assert play(c,r,p,'I3',9,'agent').status_code==409


def test_undo_reset_and_capabilities(room):
    c,r,p=room
    play(c,r,p,'H8',0)
    play(c,r,p,'I8',1,'agent')
    h={'X-Gomoku-Token':r['humanToken']}
    a={'X-Gomoku-Token':r['agentToken']}
    assert c.post(p+'/actions',headers=a,json={'action':'reset','expectedRevision':2}).status_code==403
    g=c.post(p+'/actions',headers=h,json={'action':'undo','expectedRevision':2}).json()
    assert not g['moves'] and g['revision']==3 and g['yourTurn']
    assert c.get(p,headers=h).json()['revision']==3  # persisted across connections
    assert c.get('/gomoku').status_code==200


def test_agent_teaching_required(room):
    c,r,p=room
    play(c,r,p,'H8',0)
    assert play(c,r,p,'I8',1,'agent',explanation='').status_code==422


def test_terminal_human_move_can_be_reviewed(room):
    c,r,p=room
    for i,coord in enumerate(['A1','A3','B1','C3','C1','E3','D1','G3','E1']):
        play(c,r,p,coord,i,'human' if i%2==0 else 'agent')
    response=c.post(p+'/actions',headers={'X-Gomoku-Token':r['agentToken']},json={
        'action':'review','expectedRevision':9,'humanMoveReview':'E1 连成五子，抓住了获胜机会。'})
    assert response.status_code==200
    g=response.json()
    assert g['status']=='won' and g['moves'][-1]['review'].startswith('E1')
    assert len(g['moves'])==9


def test_integrated_app_preserves_error_status(client):
    assert client.get('/api/gomoku/rooms/missing').status_code==404
    assert client.post('/api/gomoku/rooms',json={'humanColor':'invalid'}).status_code==422


@pytest.fixture
def relay_client(tmp_path, monkeypatch):
    monkeypatch.setenv('GOMOKU_DB', str(tmp_path / 'relay.sqlite'))
    app = FastAPI()
    app.include_router(gomoku.router)
    with TestClient(app) as client:
        yield client


def test_relay_black_center_and_roles(relay_client):
    c = relay_client
    r = c.post('/api/gomoku/rooms', json={'mode': 'relay', 'ownColor': 'black'}).json()
    p = '/api/gomoku/rooms/' + r['id']
    h = {'X-Gomoku-Token': r['humanToken']}
    a = {'X-Gomoku-Token': r['agentToken']}
    g = c.get(p, headers=h).json()
    assert (g['humanColor'], g['agentColor'], g['nextColor'], g['yourTurn']) == ('white', 'black', 'white', True)
    assert [(m['color'], m['at']) for m in g['moves']] == [('black', 'H8')]
    assert play(c, r, p, 'I9', 0, 'agent', explanation='').status_code == 409
    assert play(c, r, p, 'I8', 0).status_code == 200
    response = c.post(p + '/actions', headers=a, json={'move': 'I9', 'expectedRevision': 1})
    assert response.status_code == 200
    g = response.json()
    assert [(m['color'], m['at']) for m in g['moves']] == [('black', 'H8'), ('white', 'I8'), ('black', 'I9')]
    assert g['moves'][-1]['explanation'] == ''
    assert c.post(p + '/actions', headers=a, json={'move': 'J9', 'expectedRevision': 1}).status_code == 409
    assert c.post(p + '/actions', headers=a, json={'move': 'J9', 'expectedRevision': 2}).status_code == 409


def test_relay_white_waits_for_recorded_opponent(relay_client):
    c = relay_client
    r = c.post('/api/gomoku/rooms', json={'mode': 'relay', 'ownColor': 'white'}).json()
    p = '/api/gomoku/rooms/' + r['id']
    a = {'X-Gomoku-Token': r['agentToken']}
    g = c.get(p, headers=a).json()
    assert (g['moves'], g['yourTurn'], g['humanColor'], g['agentColor']) == ([], False, 'black', 'white')
    assert play(c, r, p, 'H8', 0).status_code == 200
    assert c.post(p + '/actions', headers=a, json={'move': 'I8', 'expectedRevision': 1}).status_code == 200


def test_relay_undo_and_reset_keep_our_black_opening(relay_client):
    c = relay_client
    r = c.post('/api/gomoku/rooms', json={'mode': 'relay', 'ownColor': 'black'}).json()
    p = '/api/gomoku/rooms/' + r['id']
    h = {'X-Gomoku-Token': r['humanToken']}
    play(c, r, p, 'I8', 0)
    play(c, r, p, 'I9', 1, 'agent', explanation='')
    for action, revision in [('undo', 2), ('reset', 3), ('undo', 4)]:
        g = c.post(p + '/actions', headers=h, json={'action': action, 'expectedRevision': revision}).json()
        assert [(m['color'], m['at']) for m in g['moves']] == [('black', 'H8')]
        assert g['yourTurn'] and g['revision'] == revision + 1


def test_wait_turn_auth_change_and_timeout(relay_client):
    c = relay_client
    r = c.post('/api/gomoku/rooms', json={'mode': 'relay', 'ownColor': 'white'}).json()
    p = '/api/gomoku/rooms/' + r['id']
    a = {'X-Gomoku-Token': r['agentToken']}
    assert c.get(p + '/turn?afterRevision=0&timeout=1').status_code == 404
    assert c.get(p + '/turn?afterRevision=0&timeout=16', headers=a).status_code == 422
    g = c.get(p + '/turn?afterRevision=-1&timeout=1', headers=a).json()
    assert g['revision'] == 0 and not g['yourTurn'] and 'timeout' not in g
    g = c.get(p + '/turn?afterRevision=0&timeout=1', headers=a).json()
    assert g['timeout'] and g['revision'] == 0
    play(c, r, p, 'H8', 0)
    g = c.get(p + '/turn?afterRevision=0&timeout=1', headers=a).json()
    assert g['yourTurn'] and g['revision'] == 1 and 'timeout' not in g


def test_wait_turn_wakes_when_opponent_records_move(relay_client):
    from concurrent.futures import ThreadPoolExecutor
    import time

    c = relay_client
    r = c.post('/api/gomoku/rooms', json={'mode': 'relay', 'ownColor': 'white'}).json()
    p = '/api/gomoku/rooms/' + r['id']
    with ThreadPoolExecutor(max_workers=1) as pool:
        waiting = pool.submit(c.get, p + '/turn?afterRevision=0&timeout=2',
                              headers={'X-Gomoku-Token': r['agentToken']})
        time.sleep(0.1)
        assert play(c, r, p, 'H8', 0).status_code == 200
        g = waiting.result(timeout=3).json()
    assert g['revision'] == 1 and g['yourTurn'] and 'timeout' not in g


def test_relay_deadline_survives_reads_and_heartbeat(relay_client, monkeypatch):
    clock = {'now': 1000.0}
    monkeypatch.setattr(gomoku.time, 'time', lambda: clock['now'])
    c = relay_client
    r = c.post('/api/gomoku/rooms', json={'mode': 'relay', 'ownColor': 'white'}).json()
    p = '/api/gomoku/rooms/' + r['id']
    a = {'X-Gomoku-Token': r['agentToken']}
    assert c.get(p, headers=a).json()['moveDeadline'] is None
    clock['now'] = 1010.0
    g = play(c, r, p, 'A1', 0).json()
    assert (g['turnStartedAt'], g['moveDeadline'], g['serverTime']) == (1010.0, 1025.0, 1010.0)
    clock['now'] = 1020.0
    g = c.post(p + '/actions', headers=a, json={'action': 'heartbeat', 'expectedRevision': 1}).json()
    assert (g['moveDeadline'], g['serverTime'], g['revision']) == (1025.0, 1020.0, 1)
    assert c.get(p, headers=a).json()['moveDeadline'] == 1025.0
    clock['now'] = 1026.0
    # A timeout is a visible warning, not automatic forfeiture or a random move.
    assert c.get(p, headers=a).json()['moveDeadline'] == 1025.0
    g = c.post(p + '/actions', headers=a, json={'move': 'O15', 'expectedRevision': 1}).json()
    assert g['moveDeadline'] is None and g['status'] == 'playing'
    clock['now'] = 1030.0
    g = play(c, r, p, 'A2', 2).json()
    assert g['moveDeadline'] == 1045.0


def test_relay_deadline_clears_on_undo_and_reset(relay_client):
    c = relay_client
    r = c.post('/api/gomoku/rooms', json={'mode': 'relay', 'ownColor': 'black'}).json()
    p = '/api/gomoku/rooms/' + r['id']
    h = {'X-Gomoku-Token': r['humanToken']}
    assert c.get(p, headers=h).json()['moveDeadline'] is None
    assert play(c, r, p, 'A15', 0).json()['moveDeadline'] is not None
    for action, revision in [('undo', 1), ('reset', 2)]:
        g = c.post(p + '/actions', headers=h, json={'action': action, 'expectedRevision': revision}).json()
        assert g['moveDeadline'] is None and len(g['moves']) == 1


def test_existing_rooms_without_timer_remain_readable():
    g = {'id': 'old', 'humanColor': 'black', 'status': 'playing', 'winner': None,
         'winningLine': [], 'moves': [], 'revision': 0}
    assert gomoku.snapshot(g, 'agent')['moveDeadline'] is None
