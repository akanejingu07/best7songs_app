from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
import psycopg2

# ----------------------
# アプリ設定
# ----------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

# ----------------------
# DB接続
# ----------------------
def get_connection():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(database_url)

# ----------------------
# 安全な DB 接続ラッパー
# ----------------------
def safe_connection():
    try:
        return get_connection()
    except RuntimeError:
        return None

# ----------------------
# DB初期化
# ----------------------
def init_db():
    conn = safe_connection()
    if not conn:
        print("DATABASE_URL が設定されていないため、DB初期化はスキップしました")
        return

    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        user_id INTEGER REFERENCES users(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS songs (
        id SERIAL PRIMARY KEY,
        post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        artist TEXT NOT NULL,
        url TEXT
    );
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("DB初期化完了")

# ----------------------
# DB初期化呼び出し
# ----------------------
init_db()

# ----------------------
# ログイン必須デコレーター
# ----------------------
def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("ログインしてください")
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper

# ----------------------
# トップページ
# ----------------------
@app.route("/")
def index():
    conn = safe_connection()
    if not conn:
        return "アプリは起動しています（DATABASE_URL 未設定）"

    cur = conn.cursor()
    cur.execute("SELECT id, username FROM posts ORDER BY created_at DESC")
    posts = [{"id": r[0], "username": r[1]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return render_template("index.html", posts=posts)

# ----------------------
# 投稿詳細
# ----------------------
@app.route("/detail/<int:id>")
def detail(id):
    conn = safe_connection()
    if not conn:
        return "DB未接続です（DATABASE_URL未設定）", 503

    cur = conn.cursor()
    cur.execute("SELECT username, user_id FROM posts WHERE id=%s", (id,))
    post_row = cur.fetchone()
    if not post_row:
        cur.close()
        conn.close()
        return "投稿が見つかりません", 404

    username = post_row[0]
    post_user_id = post_row[1]

    cur.execute(
        "SELECT title, artist, url FROM songs WHERE post_id=%s ORDER BY id",
        (id,)
    )
    songs = [{"title": r[0], "artist": r[1], "url": r[2]} for r in cur.fetchall()]

    cur.close()
    conn.close()
    return render_template("detail.html", username=username, songs=songs, post_id=id, post_user_id=post_user_id)

# ----------------------
# 他のルートも同様に safe_connection() を使う
# ----------------------
@app.route("/new", methods=["GET", "POST"])
@login_required
def new():
    conn = safe_connection()
    if not conn:
        return "DB未接続です（DATABASE_URL未設定）", 503

    if request.method == "POST":
        username = request.form.get("username")
        songs = []
        for i in range(1, 8):
            title = request.form.get(f"song_title_{i}")
            artist = request.form.get(f"artist_{i}")
            url = request.form.get(f"url_{i}")
            if title and artist:
                songs.append({"title": title, "artist": artist, "url": url})

        cur = conn.cursor()
        cur.execute("INSERT INTO posts (username, user_id) VALUES (%s, %s) RETURNING id",
                    (username, session["user_id"]))
        post_id = cur.fetchone()[0]

        for song in songs:
            cur.execute("INSERT INTO songs (post_id, title, artist, url) VALUES (%s, %s, %s, %s)",
                        (post_id, song["title"], song["artist"], song["url"]))

        conn.commit()
        cur.close()
        conn.close()

        flash("投稿が完了しました")
        return redirect(url_for("detail", id=post_id))

    conn.close()
    return render_template("new.html")

# ----------------------
# 省略: edit, delete, register, login, logout, share も同様に safe_connection() を使用
# ----------------------

# ----------------------
# ローカル起動用
# ----------------------
if __name__ == "__main__":
    app.run(debug=True)
