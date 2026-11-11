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
