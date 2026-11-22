"""CatBot - aplikasi utama Flask.

Menjalankan:  python app.py   ->  http://127.0.0.1:5000
"""
import os
import re
from datetime import timedelta

from authlib.integrations.flask_client import OAuth
from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from flask_login import (LoginManager, current_user, login_required,
                         login_user, logout_user)
from flask_wtf.csrf import CSRFError, CSRFProtect

from behavior_data import decode_behavior, get_decoder_options
from chatbot_engine import ChatbotEngine
from config import BASE_DIR, Config
from models import Cat, ChatHistory, Conversation, User, db, utcnow

# --------------------------------------------------------------------------- setup
app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
csrf = CSRFProtect(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Silakan masuk dulu ya 🐾"
login_manager.login_message_category = "info"

engine = ChatbotEngine(BASE_DIR / "intents.json")

# Google OAuth 2.0 (OpenID Connect) via Authlib
GOOGLE_ENABLED = bool(app.config["GOOGLE_CLIENT_ID"] and app.config["GOOGLE_CLIENT_SECRET"])
oauth = OAuth(app)
if GOOGLE_ENABLED:
    oauth.register(
        name="google",
        client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

with app.app_context():
    db.create_all()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BREEDS = ["Domestic Shorthair", "Domestic Longhair", "Kampung / Domestik", "Persia", "Anggora",
          "Maine Coon", "British Shorthair", "Ragdoll", "Bengal", "Siamese", "Scottish Fold",
          "Sphynx", "Campuran"]


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# --------------------------------------------------------------------------- helper
def local_time(dt):
    return dt + timedelta(hours=app.config["TZ_OFFSET_HOURS"])


def fmt_time(dt):
    return local_time(dt).strftime("%H.%M")


def day_label(dt):
    day, today = local_time(dt).date(), local_time(utcnow()).date()
    if day == today:
        return "HARI INI"
    if day == today - timedelta(days=1):
        return "KEMARIN"
    return day.strftime("%d/%m/%Y")


def safe_next(target):
    return target if target and target.startswith("/") and not target.startswith("//") else None


def owned_cat_or_404(cat_id):
    cat = db.session.get(Cat, cat_id)
    if cat is None or cat.user_id != current_user.id:
        abort(404)
    return cat


def user_cats():
    return Cat.query.filter_by(user_id=current_user.id).order_by(Cat.created_at.asc(), Cat.id.asc()).all()


def build_history(conversation):
    """Pesan satu percakapan dari database, urut lama -> baru (dengan pemisah hari)."""
    items, last_day = [], None
    for row in conversation.messages:
        label = day_label(row.timestamp)
        items.append({
            "sender": row.sender, "message": row.message, "time": fmt_time(row.timestamp),
            "intent": row.intent, "urgent": row.intent == "darurat_kesehatan",
            "day": label if label != last_day else None,
        })
        last_day = label
    return items


def conversation_list(cat, limit=50):
    """Daftar percakapan di sidebar (terbaru di atas) untuk satu kucing / chat umum."""
    rows = (Conversation.query
            .filter_by(user_id=current_user.id, cat_id=cat.id if cat else None)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .limit(limit).all())
    return [{"id": r.id, "title": r.title, "when": day_label(r.updated_at).capitalize()} for r in rows]


def make_title(message, size=40):
    text = " ".join(message.split())
    return text if len(text) <= size else text[: size - 1].rstrip() + "…"


def parse_cat_form(form):
    errors = []
    name = form.get("name", "").strip()
    breed = form.get("breed", "").strip() or "Domestic Shorthair"
    gender = form.get("gender", "")
    notes = form.get("notes", "").strip()
    try:
        years, months = int(form.get("age_years") or 0), int(form.get("age_months") or 0)
    except ValueError:
        years, months = -1, -1

    if not name:
        errors.append("Nama kucing wajib diisi.")
    elif len(name) > 60:
        errors.append("Nama kucing maksimal 60 karakter.")
    if len(breed) > 60:
        errors.append("Ras maksimal 60 karakter.")
    if gender not in ("Jantan", "Betina"):
        errors.append("Pilih jenis kelamin.")
    if not (0 <= years <= 30 and 0 <= months <= 11):
        errors.append("Umur tidak valid (bulan 0-11).")
        years = months = 0
    if len(notes) > 500:
        errors.append("Catatan maksimal 500 karakter.")

    data = {"name": name, "breed": breed, "gender": gender, "notes": notes,
            "age": round(years + months / 12, 2)}
    form_values = {**data, "age_years": years, "age_months": months}
    return data, form_values, errors


# --------------------------------------------------------------------------- context
@app.context_processor
def inject_globals():
    return {"google_enabled": GOOGLE_ENABLED, "is_guest": not current_user.is_authenticated}


@app.errorhandler(CSRFError)
def handle_csrf(_err):
    if request.path.startswith("/api/"):
        return jsonify(error="Sesi kedaluwarsa. Muat ulang halaman."), 400
    flash("Sesi kedaluwarsa, silakan coba lagi.", "warning")
    return redirect(request.referrer or url_for("index"))


@app.errorhandler(404)
def not_found(_err):
    return render_template("error.html", code=404, message="Halaman yang kamu cari tidak ditemukan."), 404


@app.errorhandler(500)
def server_error(_err):
    return render_template("error.html", code=500, message="Ada yang salah di sisi kami. Coba lagi nanti."), 500


# --------------------------------------------------------------------------- auth
@app.route("/")
def index():
    return redirect(url_for("dashboard" if current_user.is_authenticated else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(request.form.get("password", "")):
            login_user(user, remember=bool(request.form.get("remember")))
            session.pop("guest", None)
            return redirect(safe_next(request.args.get("next")) or url_for("dashboard"))
        flash("Email atau kata sandi salah.", "danger")
    return render_template("login.html", active_tab="login", form={})


@app.post("/register")
def register():
    form = {k: request.form.get(k, "").strip() for k in ("username", "email")}
    password, confirm = request.form.get("password", ""), request.form.get("confirm", "")
    email = form["email"].lower()
    error = None
    if not form["username"] or len(form["username"]) > 80:
        error = "Nama wajib diisi (maksimal 80 karakter)."
    elif not EMAIL_RE.match(email):
        error = "Format email tidak valid."
    elif len(password) < 8:
        error = "Kata sandi minimal 8 karakter."
    elif password != confirm:
        error = "Konfirmasi kata sandi tidak sama."
    elif User.query.filter_by(email=email).first():
        error = "Email sudah terdaftar. Silakan masuk."
    if error:
        flash(error, "danger")
        return render_template("login.html", active_tab="register", form=form), 400

    user = User(username=form["username"], email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    login_user(user)
    flash("Akun berhasil dibuat. Selamat datang di CatBot!", "success")
    return redirect(url_for("dashboard"))


@app.route("/login/google")
def login_google():
    if not GOOGLE_ENABLED:
        flash("Login Google belum dikonfigurasi (isi GOOGLE_CLIENT_ID dan GOOGLE_CLIENT_SECRET di .env).", "warning")
        return redirect(url_for("login"))
    return oauth.google.authorize_redirect(url_for("google_callback", _external=True))


@app.route("/auth/google/callback")
def google_callback():
    if not GOOGLE_ENABLED:
        abort(404)
    try:
        token = oauth.google.authorize_access_token()
    except Exception:
        flash("Login Google gagal atau dibatalkan.", "danger")
        return redirect(url_for("login"))

    info = token.get("userinfo") or {}
    google_id, email = info.get("sub"), (info.get("email") or "").lower()
    if not google_id or not email or not info.get("email_verified"):
        flash("Akun Google tidak memiliki email terverifikasi.", "danger")
        return redirect(url_for("login"))

    user = User.query.filter_by(google_id=google_id).first()
    if user is None:
        user = User.query.filter_by(email=email).first()  # tautkan ke akun email yang sama
        if user:
            user.google_id = google_id
        else:
            user = User(username=info.get("name") or email.split("@")[0], email=email,
                        google_id=google_id, avatar_url=info.get("picture"))
            db.session.add(user)
        db.session.commit()

    login_user(user, remember=True)
    session.pop("guest", None)
    return redirect(url_for("dashboard"))


@app.route("/guest")
def guest():
    session["guest"] = True
    return redirect(url_for("chat"))


@app.post("/logout")
def logout():
    logout_user()
    session.pop("guest", None)
    flash("Kamu sudah keluar. Sampai jumpa!", "info")
    return redirect(url_for("login"))


# --------------------------------------------------------------------------- CRUD kucing
@app.route("/kucingku")
@login_required
def dashboard():
    return render_template("dashboard.html", cats=user_cats())


@app.route("/kucingku/baru", methods=["GET", "POST"])
@login_required
def cat_new():
    values, errors = {"age_years": 0, "age_months": 0}, []
    if request.method == "POST":
        data, values, errors = parse_cat_form(request.form)
        if not errors:
            db.session.add(Cat(user_id=current_user.id, **data))
            db.session.commit()
            flash(f"{data['name']} berhasil ditambahkan 🐱", "success")
            return redirect(url_for("dashboard"))
        for e in errors:
            flash(e, "danger")
    return render_template("cat_form.html", cat=None, values=values, breeds=BREEDS)


@app.route("/kucingku/<int:cat_id>/edit", methods=["GET", "POST"])
@login_required
def cat_edit(cat_id):
    cat = owned_cat_or_404(cat_id)
    years, months = cat.age_parts
    values = {"name": cat.name, "breed": cat.breed, "gender": cat.gender, "notes": cat.notes or "",
              "age_years": years, "age_months": months}
    if request.method == "POST":
        data, values, errors = parse_cat_form(request.form)
        if not errors:
            for key, val in data.items():
                setattr(cat, key, val)
            db.session.commit()
            flash("Data kucing diperbarui.", "success")
            return redirect(url_for("dashboard"))
        for e in errors:
            flash(e, "danger")
    return render_template("cat_form.html", cat=cat, values=values, breeds=BREEDS)


@app.post("/kucingku/<int:cat_id>/hapus")
@login_required
def cat_delete(cat_id):
    cat = owned_cat_or_404(cat_id)
    name = cat.name
    db.session.delete(cat)  # riwayat chat kucing ini ikut terhapus (cascade)
    db.session.commit()
    flash(f"Profil {name} dihapus.", "info")
    return redirect(url_for("dashboard"))


# --------------------------------------------------------------------------- chat
@app.route("/konsultasi")
@app.route("/konsultasi/<int:cat_id>")
def chat(cat_id=None):
    """Tanpa ?c=<id> -> percakapan baru (kosong). Dengan ?c=<id> -> lanjutkan percakapan lama."""
    cat, cats, conversations, history, conv = None, [], [], [], None
    if current_user.is_authenticated:
        cats = user_cats()
        if cat_id is not None:
            cat = owned_cat_or_404(cat_id)
        conversations = conversation_list(cat)
        conv_id = request.args.get("c", type=int)
        if conv_id:
            conv = Conversation.query.filter_by(
                id=conv_id, user_id=current_user.id, cat_id=cat.id if cat else None).first_or_404()
            history = build_history(conv)
    elif cat_id is not None:
        flash("Masuk dulu untuk konsultasi khusus kucingmu ya 🐾", "info")
        return redirect(url_for("login", next=request.path))

    name = current_user.first_name if current_user.is_authenticated else None
    return render_template("chat.html", cat=cat, cats=cats, conv=conv, conversations=conversations,
                           history=history, welcome=engine.welcome(cat, name),
                           quick_replies=engine.quick_replies, disclaimer=engine.disclaimer)


@app.post("/api/chat")
def api_chat():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()[: app.config["MAX_MESSAGE_LENGTH"]]
    if not message:
        return jsonify(error="Pesan tidak boleh kosong."), 400

    cat, raw_cat_id = None, data.get("cat_id")
    if raw_cat_id not in (None, ""):
        if not current_user.is_authenticated:
            return jsonify(error="Masuk dulu untuk konsultasi khusus kucing."), 401
        try:
            cat = db.session.get(Cat, int(raw_cat_id))
        except (TypeError, ValueError):
            return jsonify(error="cat_id tidak valid."), 400
        if cat is None or cat.user_id != current_user.id:
            return jsonify(error="Kucing tidak ditemukan."), 404

    saved = current_user.is_authenticated
    cat_pk = cat.id if cat else None
    conv, is_new = None, False
    if saved:
        raw_conv = data.get("conversation_id")
        if raw_conv not in (None, ""):
            try:
                conv = Conversation.query.filter_by(
                    id=int(raw_conv), user_id=current_user.id, cat_id=cat_pk).first()
            except (TypeError, ValueError):
                return jsonify(error="conversation_id tidak valid."), 400
            if conv is None:
                return jsonify(error="Percakapan tidak ditemukan."), 404

    result = engine.respond(message, cat=cat)
    now = utcnow()
    if saved:  # tersimpan permanen -> bisa dilanjutkan kapan saja
        if conv is None:  # pesan pertama -> buat percakapan baru, judul dari pesan
            conv = Conversation(user_id=current_user.id, cat_id=cat_pk, title=make_title(message))
            db.session.add(conv)
            db.session.flush()
            is_new = True
        db.session.add_all([
            ChatHistory(user_id=current_user.id, cat_id=cat_pk, conversation_id=conv.id,
                        sender="user", message=message, timestamp=now),
            ChatHistory(user_id=current_user.id, cat_id=cat_pk, conversation_id=conv.id,
                        sender="bot", message=result["response"], intent=result["tag"],
                        timestamp=now + timedelta(milliseconds=1)),
        ])
        conv.updated_at = now
        db.session.commit()

    return jsonify(reply=result["response"], intent=result["tag"], urgent=result["urgent"],
                   time=fmt_time(now), saved=saved,
                   conversation_id=conv.id if conv else None,
                   title=conv.title if conv else None, is_new=is_new)


@app.post("/konsultasi/percakapan/<int:conv_id>/hapus")
@login_required
def delete_conversation(conv_id):
    conv = Conversation.query.filter_by(id=conv_id, user_id=current_user.id).first_or_404()
    cat_id = conv.cat_id
    db.session.delete(conv)  # pesan di dalamnya ikut terhapus (cascade)
    db.session.commit()
    flash("Percakapan dihapus.", "success")
    back = safe_next(request.form.get("back"))
    if back and f"c={conv_id}" not in back:  # yang dihapus bukan yang sedang dibuka
        return redirect(back)
    return redirect(url_for("chat", cat_id=cat_id) if cat_id else url_for("chat"))


@app.post("/konsultasi/hapus-riwayat")
@login_required
def clear_history():
    """Hapus SEMUA percakapan pada satu kucing / chat umum (opsional)."""
    cat_id = request.form.get("cat_id", type=int)
    if cat_id:
        owned_cat_or_404(cat_id)
    for conv in Conversation.query.filter_by(user_id=current_user.id, cat_id=cat_id).all():
        db.session.delete(conv)
    db.session.commit()
    flash("Semua percakapan dihapus.", "success")
    return redirect(url_for("chat", cat_id=cat_id) if cat_id else url_for("chat"))


# --------------------------------------------------------------------------- decoder
@app.route("/behavior-decoder")
def decoder():
    return render_template("decoder.html", decoder_options=get_decoder_options())


@app.post("/api/decoder")
def api_decoder():
    data = request.get_json(silent=True) or {}
    result = decode_behavior(tail=data.get("tail"), ears=data.get("ears"), sound=data.get("sound"))
    return jsonify(result), (200 if result.get("ok") else 400)


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", port=5000)
