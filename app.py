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
# DB初期化
# ----------------------
def init_db():
    try:
        conn = get_connection()
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
    except RuntimeError:
        print("DATABASE_URL 未設定のため DB 初期化スキップ")

init_db()

# ----------------------
# ログイン必須デコレーター（修正版）
# ----------------------
def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("ログインしてください")
            return redirect(url_for("login_route"))
        return func(*args, **kwargs)
    return wrapper

# ----------------------
# トップページ
# ----------------------
@app.route("/")
def index():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, username FROM posts ORDER BY created_at DESC")
        posts = [{"id": r[0], "username": r[1]} for r in cur.fetchall()]
        cur.close()
        conn.close()
    except RuntimeError:
        posts = []
    return render_template("index.html", posts=posts)

# ----------------------
# 投稿詳細
# ----------------------
@app.route("/detail/<int:id>")
def detail(id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT username, user_id FROM posts WHERE id=%s", (id,))
    post = cur.fetchone()
    if not post:
        return "投稿が見つかりません", 404

    cur.execute(
        "SELECT title, artist, url FROM songs WHERE post_id=%s ORDER BY id",
        (id,)
    )
    songs = [{"title": r[0], "artist": r[1], "url": r[2]} for r in cur.fetchall()]

    cur.close()
    conn.close()

    return render_template(
        "detail.html",
        username=post[0],
        post_user_id=post[1],
        post_id=id,
        songs=songs
    )

# ----------------------
# 新規投稿
# ----------------------
@app.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        username = request.form.get("username")
        user_id = session["user_id"]

        songs = []
        for i in range(1, 8):
            title = request.form.get(f"song_title_{i}")
            artist = request.form.get(f"artist_{i}")
            url = request.form.get(f"url_{i}")
            if title and artist:
                songs.append((title, artist, url))

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO posts (username, user_id) VALUES (%s, %s) RETURNING id",
            (username, user_id)
        )
        post_id = cur.fetchone()[0]

        for song in songs:
            cur.execute(
                "INSERT INTO songs (post_id, title, artist, url) VALUES (%s, %s, %s, %s)",
                (post_id, *song)
            )

        conn.commit()
        cur.close()
        conn.close()

        flash("投稿が完了しました")
        return redirect(url_for("detail", id=post_id))

    return render_template("new.html")

# ----------------------
# 編集
# ----------------------
@app.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit(id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM posts WHERE id=%s", (id,))
    owner = cur.fetchone()
    if not owner or owner[0] != session["user_id"]:
        return "権限がありません", 403

    if request.method == "POST":
        username = request.form.get("username")
        cur.execute("UPDATE posts SET username=%s WHERE id=%s", (username, id))

        cur.execute("DELETE FROM songs WHERE post_id=%s", (id,))
        for i in range(1, 8):
            title = request.form.get(f"song_title_{i}")
            artist = request.form.get(f"artist_{i}")
            url = request.form.get(f"url_{i}")
            if title and artist:
                cur.execute(
                    "INSERT INTO songs (post_id, title, artist, url) VALUES (%s, %s, %s, %s)",
                    (id, title, artist, url)
                )

        conn.commit()
        cur.close()
        conn.close()

        flash("投稿を更新しました")
        return redirect(url_for("detail", id=id))

    cur.execute("SELECT username FROM posts WHERE id=%s", (id,))
    username = cur.fetchone()[0]
    cur.execute("SELECT title, artist, url FROM songs WHERE post_id=%s", (id,))
    songs = [{"title": r[0], "artist": r[1], "url": r[2]} for r in cur.fetchall()]

    cur.close()
    conn.close()
    return render_template("edit.html", username=username, songs=songs, post_id=id)

# ----------------------
# 削除
# ----------------------
@app.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete(id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM posts WHERE id=%s", (id,))
    owner = cur.fetchone()
    if not owner or owner[0] != session["user_id"]:
        return "権限がありません", 403

    cur.execute("DELETE FROM posts WHERE id=%s", (id,))
    conn.commit()
    cur.close()
    conn.close()

    flash("投稿を削除しました")
    return redirect(url_for("index"))

# ----------------------
# ユーザー登録
# ----------------------
@app.route("/register", methods=["GET", "POST"])
def register_route():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
            (username, generate_password_hash(password))
        )
        conn.commit()
        cur.close()
        conn.close()

        flash("登録完了しました")
        return redirect(url_for("login_route"))

    return render_template("register.html")

# ----------------------
# ログイン
# ----------------------
@app.route("/login", methods=["GET", "POST"])
def login_route():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, password_hash FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(user[1], password):
            session["user_id"] = user[0]
            session["username"] = username
            flash("ログインしました")
            return redirect(url_for("index"))
        flash("ログイン失敗")

    return render_template("login.html")

# ----------------------
# ログアウト
# ----------------------
@app.route("/logout")
@login_required
def logout_route():
    session.clear()
    flash("ログアウトしました")
    return redirect(url_for("index"))

# ----------------------
# 起動（Render対応）
# ----------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
