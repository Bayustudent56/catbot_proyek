"""Model database CatBot (SQLAlchemy).

Relasi:
    User 1 ─── * Cat            (satu pengguna punya banyak kucing)
    User 1 ─── * Conversation   (banyak percakapan per pengguna)
    Cat  1 ─── * Conversation   (cat_id NULL = chat umum)
    Conversation 1 ─── * ChatHistory  (pesan di dalam satu percakapan)
Aturan Behavior Decoder disimpan di behavior_data.py (hardcode terdokumentasi),
sehingga tidak memerlukan tabel BehaviorRules.
"""
from datetime import datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


def utcnow() -> datetime:
    """Waktu UTC naive (aman untuk SQLite & MySQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)  # NULL jika hanya login Google
    google_id = db.Column(db.String(255), unique=True, nullable=True)
    avatar_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    cats = db.relationship("Cat", backref="owner", cascade="all, delete-orphan", lazy=True)
    chats = db.relationship("ChatHistory", backref="user", cascade="all, delete-orphan", lazy=True)
    conversations = db.relationship("Conversation", backref="user", cascade="all, delete-orphan", lazy=True)

    def set_password(self, raw: str) -> None:
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        return bool(self.password_hash) and check_password_hash(self.password_hash, raw)

    @property
    def first_name(self) -> str:
        return (self.username or "Teman").split()[0]


class Cat(db.Model):
    __tablename__ = "cats"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(60), nullable=False)
    breed = db.Column(db.String(60), nullable=False, default="Domestic Shorthair")
    age = db.Column(db.Float, nullable=False, default=0)  # dalam tahun (0.5 = 6 bulan)
    gender = db.Column(db.String(10), nullable=False, default="Jantan")
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    chats = db.relationship("ChatHistory", backref="cat", cascade="all, delete-orphan", lazy=True)
    conversations = db.relationship("Conversation", backref="cat", cascade="all, delete-orphan", lazy=True)

    @property
    def age_parts(self) -> tuple[int, int]:
        total = round((self.age or 0) * 12)
        return divmod(total, 12)  # (tahun, bulan)

    @property
    def age_label(self) -> str:
        years, months = self.age_parts
        if years == 0:
            return f"{months} bulan"
        return f"{years} tahun" + (f" {months} bulan" if months else "")


class Conversation(db.Model):
    """Satu percakapan (utas chat). Satu kucing / chat umum bisa punya banyak percakapan."""
    __tablename__ = "conversations"
    __table_args__ = (db.Index("ix_conv_scope", "user_id", "cat_id", "updated_at"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    cat_id = db.Column(db.Integer, db.ForeignKey("cats.id"), nullable=True)  # NULL = chat umum
    title = db.Column(db.String(120), nullable=False, default="Percakapan baru")
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    messages = db.relationship("ChatHistory", backref="conversation", cascade="all, delete-orphan",
                               order_by="ChatHistory.id", lazy=True)


class ChatHistory(db.Model):
    __tablename__ = "chat_history"
    __table_args__ = (
        db.CheckConstraint("sender IN ('user', 'bot')", name="ck_chat_sender"),
        db.Index("ix_chat_scope_time", "user_id", "cat_id", "timestamp"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    cat_id = db.Column(db.Integer, db.ForeignKey("cats.id"), nullable=True)  # NULL = chat umum
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False, index=True)
    sender = db.Column(db.String(10), nullable=False)  # 'user' | 'bot'
    message = db.Column(db.Text, nullable=False)
    intent = db.Column(db.String(50), nullable=True)  # tag intent (khusus pesan bot)
    timestamp = db.Column(db.DateTime, default=utcnow, nullable=False)
