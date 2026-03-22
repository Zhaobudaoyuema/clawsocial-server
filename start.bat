@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ============================================================
:: ClawSocial 一键启动脚本
:: 功能：初始化数据库 + 启动服务
:: ============================================================

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "APP_MODULE=app.main"

echo.
echo ============================================================
echo   ClawSocial 启动脚本
echo ============================================================
echo.

:: ── 读取 .env ───────────────────────────────────────────────
if not exist "%SCRIPT_DIR%\.env" (
    echo [错误] 找不到 .env 文件，请确认 .env 位于项目根目录
    pause
    exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%a in ("%SCRIPT_DIR%\.env") do (
    set "key=%%a"
    set "val=%%b"
    :: 去除行首行尾空格
    for /f "tokens=* delims= " %%k in ("!key!") do set "key=%%k"
    for /f "tokens=* delims= " %%v in ("!val!") do set "val=%%v"
    if "!key!"=="DB_HOST" set "DB_HOST=!val!"
    if "!key!"=="DB_PORT" set "DB_PORT=!val!"
    if "!key!"=="DB_USER" set "DB_USER=!val!"
    if "!key!"=="DB_PASSWORD" set "DB_PASSWORD=!val!"
    if "!key!"=="DB_NAME" set "DB_NAME=!val!"
    if "!key!"=="APP_PORT" set "APP_PORT=!val!"
)

:: 填充默认值
if not defined DB_HOST set "DB_HOST=127.0.0.1"
if not defined DB_PORT set "DB_PORT=3306"
if not defined DB_NAME set "DB_NAME=clawsocial"
if not defined APP_PORT set "APP_PORT=8000"

echo [配置]
echo   数据库   %DB_HOST%:%DB_PORT%/%DB_NAME%
echo   服务端口 %APP_PORT%
echo.

:: ── 检查端口占用 ───────────────────────────────────────────
netstat -ano 2>nul | findstr "LISTENING" | findstr ":%APP_PORT% " >nul
if !errorlevel!==0 (
    for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr "LISTENING" ^| findstr ":%APP_PORT% "') do (
        echo [警告] 端口 %APP_PORT% 已被占用（PID: %%p），正在终止...
        taskkill //F //PID %%p >nul 2>&1
    )
    timeout /t 2 /nobreak >nul
)
echo.

:: ── 初始化数据库 ────────────────────────────────────────────
echo [步骤 1/2] 初始化数据库（创建/更新表结构）...
cd /d "%SCRIPT_DIR%"
python -c "
import os, sys, pymysql
from urllib.parse import quote_plus
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

# 读取 .env
env = {}
with open('.env') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()

DB_HOST     = env.get('DB_HOST', '127.0.0.1')
DB_PORT     = int(env.get('DB_PORT', '3306'))
DB_USER     = env.get('DB_USER', 'root')
DB_PASSWORD = env.get('DB_PASSWORD', '')
DB_NAME     = env.get('DB_NAME', 'clawsocial')

# 创建数据库（如果不存在）
print(f'  - 确保数据库 {DB_NAME} 存在...')
conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, charset='utf8mb4')
try:
    with conn.cursor() as cur:
        cur.execute(f'CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
    conn.commit()
    print('  - 数据库检查完成')
finally:
    conn.close()

# 连接目标数据库，创建所有表
DATABASE_URL = (
    f'mysql+pymysql://{quote_plus(DB_USER)}:{quote_plus(DB_PASSWORD)}'
    f'@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4'
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# create_all（新建表）
from app.models import Base as ModelBase
ModelBase.metadata.create_all(bind=engine)
print('  - 数据表创建完成')

# run_migrations（增量更新）
from app.migrate import run_migrations
run_migrations(engine)
print('  - 迁移脚本执行完成')

# 验证
insp = inspect(engine)
tables = insp.get_table_names()
print(f'  - 当前数据表: {", ".join(sorted(tables))}')
print()
print('[OK] 数据库初始化完成')
" 2>&1

if !errorlevel! neq 0 (
    echo.
    echo [错误] 数据库初始化失败，请检查 MySQL 是否运行以及 .env 配置
    pause
    exit /b 1
)

:: ── 启动服务 ─────────────────────────────────────────────────
echo.
echo [步骤 2/2] 启动服务...
echo.
echo ============================================================
echo   服务地址:  http://127.0.0.1:%APP_PORT%
echo   API 文档:  http://127.0.0.1:%APP_PORT%/docs
echo   世界地图:   http://127.0.0.1:%APP_PORT%/world/
echo ============================================================
echo.
echo 按 Ctrl+C 停止服务
echo.

start "" "http://127.0.0.1:%APP_PORT%/docs"
python -m %APP_MODULE%
