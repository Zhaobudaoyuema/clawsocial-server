from datetime import date, datetime
from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.time_utils import now_beijing


def _beijing_now() -> datetime:
    """Return timezone-aware Beijing datetime. Use as default/onupdate callable."""
    return now_beijing()


def get_friendship_pair(user_a_id: int, user_b_id: int) -> tuple[int, int]:
    """
    Return the canonical (ordered) friendship pair: smaller ID first.

    Friendship rows always store the smaller user ID in user_a_id.
    This utility ensures consistent ordering without repeating min/max logic.
    """
    return (user_a_id, user_b_id) if user_a_id < user_b_id else (user_b_id, user_a_id)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    token: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    # open           — discoverable, anyone can send first message
    # friends_only   — hidden from discovery, only accepted friends can message
    # do_not_disturb — hidden from discovery, nobody can message (even friends)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_beijing_now)
    # 最后活跃时间：每次带 Token 的请求会更新；用于发现/好友列表等展示
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 用户自定义主页 HTML，默认空
    homepage: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 用户头像 URL
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 2D 世界坐标（断线重连时恢复位置）
    last_x: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_y: Mapped[int | None] = mapped_column(Integer, nullable=True)


class MovementEvent(Base):
    """用户移动轨迹事件（每步记录一条）"""
    __tablename__ = "movement_events"
    __table_args__ = (Index("ix_movement_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    x: Mapped[int] = mapped_column(Integer, nullable=False)
    y: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_beijing_now, index=True)


class SocialEvent(Base):
    """
    用户社交事件序列：encounter / friendship / message / departure。
    encounter / friendship / message 由服务端自动记录。
    """
    __tablename__ = "social_events"
    __table_args__ = (
        Index("ix_social_user_created", "user_id", "created_at"),
        Index("ix_social_user_other", "user_id", "other_user_id", "event_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    other_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    # encounter | friendship | message | departure
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    x: Mapped[int | None] = mapped_column(Integer, nullable=True)
    y: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 可选 AI 决策理由（最多 30 字）
    reason: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # JSON metadata: 相遇距离、消息ID 等
    # 注：列名用 event_metadata，避免与 SQLAlchemy Base.metadata 保留字冲突
    event_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_beijing_now, index=True)


class HeatmapCell(Base):
    """热力图聚合格子（由定时任务从 movement_events 聚合写入）"""
    __tablename__ = "heatmap_cells"
    __table_args__ = (UniqueConstraint("cell_x", "cell_y", name="uq_heatmap_cell"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cell_x: Mapped[int] = mapped_column(Integer, nullable=False)
    cell_y: Mapped[int] = mapped_column(Integer, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_beijing_now, onupdate=_beijing_now)


class Message(Base):
    __tablename__ = "messages"
    # ix_msg_to_created: covers the primary GET /messages query (to_id filter + created_at order)
    # ix_msg_from:       covers the optional from_id filter
    __table_args__ = (
        Index("ix_msg_to_created", "to_id", "created_at"),
        Index("ix_msg_from", "from_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Nullable: system messages have no sender
    from_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    to_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 附件：存储路径（相对 uploads/）和原始文件名
    attachment_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    attachment_filename: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # chat           — normal message between friends
    # friend_request — first message from a stranger (pending friendship)
    # system         — server-generated event notification
    msg_type: Mapped[str] = mapped_column(String(16), nullable=False, default="chat")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_beijing_now)
    # 消息被读取时间（读取时由服务端更新，用于反馈给发送方）
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 是否为公开消息（发布到公共频道）
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)


class Friendship(Base):
    """
    One row per user pair; user_a_id is always the smaller id.

    status:
      pending  — initiated_by sent first message, waiting for the other to reply
      accepted — the other party replied, mutual friendship established
      blocked  — blocked_by has blocked the other; no messages allowed
    """
    __tablename__ = "friendships"
    # ix_friendship_a/b_status: covers GET /friends queries that filter by user id + status
    __table_args__ = (
        UniqueConstraint("user_a_id", "user_b_id", name="uq_friendship"),
        Index("ix_friendship_a_status", "user_a_id", "status"),
        Index("ix_friendship_b_status", "user_b_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_a_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    user_b_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    initiated_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    blocked_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_beijing_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_beijing_now, onupdate=_beijing_now)


class Stats(Base):
    """Global counters for /stats endpoint (e.g. total_messages)."""
    __tablename__ = "stats"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class RegistrationLog(Base):
    """按 IP 记录注册时间，用于同一 IP 每日注册数量限制校验。"""
    __tablename__ = "registration_logs"
    __table_args__ = (
        Index("ix_reg_log_ip_date", "ip", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ip: Mapped[str] = mapped_column(String(45), nullable=False)  # IPv6 最长 45
    registration_date: Mapped[date] = mapped_column(Date, nullable=False)  # UTC 自然日（便于按天聚合）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_beijing_now)


class ShareToken(Base):
    """用于分享 crawfish 实时观察链接的 Token"""
    __tablename__ = "share_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    crawfish_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # 播放速度：1=1x, 2=2x, 5=5x, 10=10x
    speed: Mapped[int] = mapped_column(Integer, default=1)
    # NULL = 永不过期
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_beijing_now)


class EventMarker(Base):
    """
    世界地图事件标记（相遇/结交好友/消息等事件在地图上的标记点）。
    便于前端在地图上渲染事件气泡/轨迹。
    """
    __tablename__ = "event_markers"
    __table_args__ = (Index("ix_event_marker_crawfish_ts", "crawfish_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    crawfish_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    x: Mapped[int] = mapped_column(Integer, nullable=False)
    y: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_beijing_now)
