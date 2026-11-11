"""Shared, capability-authenticated Gomoku rooms; no model or SSH credentials."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

router = APIRouter(tags=['gomoku'])
COLS = 'ABCDEFGHIJKLMNO'
DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))


def connect():
    # Keep private state outside /files; default uploads parent is preserved by deployment.
    path = Path(os.getenv('GOMOKU_DB', '/app/logs/gomoku/rooms.sqlite3' if Path('/app').exists() else str(Path(__file__).resolve().parents[2] / 'logs/gomoku/rooms.sqlite3')))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS rooms (id TEXT PRIMARY KEY, human TEXT NOT NULL, agent TEXT NOT NULL, data TEXT NOT NULL, touched REAL NOT NULL)')
    return db


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def load(db, room, token):
    row = db.execute('SELECT human,agent,data FROM rooms WHERE id=?', (room,)).fetchone()
    if not row or not token:
        raise HTTPException(404, '棋局不存在或链接无效')
    hashed = digest(token)
    role = 'human' if secrets.compare_digest(hashed, row[0]) else 'agent' if secrets.compare_digest(hashed, row[1]) else None
    if not role:
        raise HTTPException(403, '棋局链接无效')
    return json.loads(row[2]), role


def board_of(game):
    board = [['.' for _ in range(15)] for _ in range(15)]
    for m in game['moves']:
        x, y = parse(m['at'])
        board[y][x] = 'X' if m['color'] == 'black' else 'O'
    return board


def parse(at):
    if not re.fullmatch(r'[A-O](?:[1-9]|1[0-5])', at):
        raise HTTPException(422, '坐标应为 A1–O15，例如 H8')
    return COLS.index(at[0]), int(at[1:]) - 1


def winning_line(board, x, y, color):
    for dx, dy in DIRECTIONS:
        line = [(x, y)]
        for sign in (-1, 1):
            a, b = x + dx * sign, y + dy * sign
            while 0 <= a < 15 and 0 <= b < 15 and board[b][a] == color:
                line.append((a, b)); a += dx * sign; b += dy * sign
        if len(line) >= 5:
            return [f'{COLS[a]}{b+1}' for a, b in line]
    return []


def immediate_wins(board, color):
    result = []
    for y in range(15):
        for x in range(15):
            if board[y][x] == '.':
                board[y][x] = color
                if winning_line(board, x, y, color):
                    result.append(f'{COLS[x]}{y+1}')
                board[y][x] = '.'
    return result


def snapshot(game, role):
    board = board_of(game)
    human = game['humanColor']
    agent = 'white' if human == 'black' else 'black'
    next_color = 'black' if len(game['moves']) % 2 == 0 else 'white'
    move_deadline = game.get('turnStartedAt')
    move_deadline = move_deadline + 15 if move_deadline is not None and game.get('mode') == 'relay' and game['status'] == 'playing' and next_color == agent else None
    return {**game, 'serverTime': time.time(), 'moveDeadline': move_deadline, 'role': role, 'agentColor': agent, 'nextColor': next_color,
            'yourTurn': game['status'] == 'playing' and next_color == (human if role == 'human' else agent),
            'rows': [''.join(row) for row in board],
            'immediateWinningMoves': {'black': immediate_wins(board, 'X'), 'white': immediate_wins(board, 'O')},
            'agentOnline': time.time() - game.get('agentSeen', 0) < 35}


def restore_opening(game):
    if game.get('mode') == 'relay' and game['humanColor'] == 'white' and not game['moves']:
        game['moves'].append({'number': 1, 'color': 'black', 'at': 'H8',
                              'review': '', 'explanation': '', 'highlights': []})


class NewGame(BaseModel):
    humanColor: Literal['black', 'white'] = 'black'
    mode: Literal['match', 'relay'] = 'match'
    ownColor: Literal['black', 'white'] = 'black'


class Action(BaseModel):
    expectedRevision: int = Field(ge=0)
    action: Literal['move', 'undo', 'reset', 'resign', 'heartbeat', 'review'] = 'move'
    move: str = Field(default='', max_length=3)
    humanMoveReview: str = Field(default='', max_length=1800)
    explanation: str = Field(default='', max_length=1800)
    highlights: list[str] = Field(default_factory=list, max_length=15)


@router.get('/gomoku', include_in_schema=False)
@router.get('/gomoku/', include_in_schema=False)
def page():
    return FileResponse(Path(__file__).resolve().parents[1] / 'gomoku/index.html', headers={'Cache-Control': 'no-cache', 'Referrer-Policy': 'no-referrer'})


@router.post('/api/gomoku/rooms')
def create(body: NewGame):
    room, human, agent = secrets.token_urlsafe(12), secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    human_color = ('white' if body.ownColor == 'black' else 'black') if body.mode == 'relay' else body.humanColor
    game = {'id': room, 'revision': 0, 'mode': body.mode, 'humanColor': human_color, 'status': 'playing', 'winner': None, 'winningLine': [], 'moves': [], 'agentSeen': 0, 'turnStartedAt': time.time()}
    restore_opening(game)
    with connect() as db:
        db.execute('INSERT INTO rooms VALUES (?,?,?,?,?)', (room, digest(human), digest(agent), json.dumps(game), time.time()))
    return {'id': room, 'humanToken': human, 'agentToken': agent}


@router.get('/api/gomoku/rooms/{room}')
def get_room(room: str, x_gomoku_token: str = Header(default='')):
    with connect() as db:
        game, role = load(db, room, x_gomoku_token)
    return snapshot(game, role)


@router.post('/api/gomoku/rooms/{room}/actions')
def action(room: str, body: Action, x_gomoku_token: str = Header(default='')):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        game, role = load(db, room, x_gomoku_token)
        if body.action == 'heartbeat':
            if role == 'agent':
                game['agentSeen'] = time.time()
        else:
            if body.expectedRevision != game['revision']:
                raise HTTPException(409, '棋局已变化，请重新读取棋盘')
            if body.action in ('undo', 'reset'):
                if role != 'human':
                    raise HTTPException(403, '只有玩家可以悔棋或重新开始')
                if body.action == 'reset':
                    game['moves'] = []
                elif game['moves']:
                    game['moves'].pop()
                    if game['moves'] and ('black' if len(game['moves']) % 2 == 0 else 'white') != game['humanColor']:
                        game['moves'].pop()
                restore_opening(game)
                game.update(status='playing', winner=None, winningLine=[])
            elif body.action == 'review':
                if role != 'agent' or not game['moves'] or game['moves'][-1]['color'] != game['humanColor']:
                    raise HTTPException(409, '只能点评玩家最近的一手')
                if not body.humanMoveReview.strip():
                    raise HTTPException(422, '请提供点评')
                game['moves'][-1]['review'] = body.humanMoveReview
                game['agentSeen'] = time.time()
            elif body.action == 'resign':
                if game['status'] != 'playing':
                    raise HTTPException(409, '棋局已结束')
                own = game['humanColor'] if role == 'human' else ('white' if game['humanColor'] == 'black' else 'black')
                game.update(status='resigned', winner='white' if own == 'black' else 'black')
            else:
                if game['status'] != 'playing':
                    raise HTTPException(409, '棋局已结束')
                color = 'black' if len(game['moves']) % 2 == 0 else 'white'
                if (color == game['humanColor']) != (role == 'human'):
                    raise HTTPException(409, '还没轮到你')
                x, y = parse(body.move)
                board = board_of(game)
                if board[y][x] != '.':
                    raise HTTPException(409, '这个位置已有棋子')
                for h in body.highlights:
                    parse(h)
                if role == 'agent' and game.get('mode', 'match') == 'match' and not body.explanation.strip():
                    raise HTTPException(422, '请为这一手提供简短讲解')
                game['moves'].append({'number': len(game['moves']) + 1, 'color': color, 'at': body.move,
                                      'review': body.humanMoveReview if role == 'agent' else '',
                                      'explanation': body.explanation if role == 'agent' else '',
                                      'highlights': body.highlights if role == 'agent' else []})
                board[y][x] = 'X' if color == 'black' else 'O'
                line = winning_line(board, x, y, board[y][x])
                if line:
                    game.update(status='won', winner=color, winningLine=line)
                elif len(game['moves']) == 225:
                    game.update(status='draw')
                if role == 'agent':
                    game['agentSeen'] = time.time()
            if body.action in ('move', 'undo', 'reset'):
                game['turnStartedAt'] = time.time()
            game['revision'] += 1
        db.execute('UPDATE rooms SET data=?,touched=? WHERE id=?', (json.dumps(game, ensure_ascii=False), time.time(), room))
    return snapshot(game, role)


@router.get('/api/gomoku/rooms/{room}/turn')
async def wait_turn(room: str, afterRevision: int = -1, timeout: int = 15,
                    x_gomoku_token: str = Header(default='')):
    # Bound each native tool call below the client's 20-second execution limit.
    if not 1 <= timeout <= 15:
        raise HTTPException(422, '等待时间应为 1–15 秒')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        game, role = load(db, room, x_gomoku_token)
        if role == 'agent':
            game['agentSeen'] = time.time()
            db.execute('UPDATE rooms SET data=? WHERE id=?', (json.dumps(game, ensure_ascii=False), room))
    deadline = time.monotonic() + timeout
    while game['revision'] == afterRevision and game['status'] == 'playing':
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {**snapshot(game, role), 'timeout': True}
        await asyncio.sleep(min(0.2, remaining))
        with connect() as db:
            game, role = load(db, room, x_gomoku_token)
    return snapshot(game, role)
