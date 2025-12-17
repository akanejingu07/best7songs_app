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

        # users テーブル作成（なければ）
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        );
        """)

        # posts テーブル作成（なければ）
        cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            user_id INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # songs テーブル作成（なければ）
        cur.execute("""
        CREATE TABLE IF NOT EXISTS songs (
            id SERIAL PRIMARY KEY,
            post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            url TEXT
        );
        """)

        # 既存の users テーブルに nickname や password があれば変更
        try:
            cur.execute("ALTER TABLE users RENAME COLUMN nickname TO username;")
        except Exception:
            pass  # 既に username なら無視

        try:
            cur.execute("ALTER TABLE users RENAME COLUMN password TO password_hash;")
        except Exception:
            pass  # 既に password_hash なら無視

        conn.commit()
        cur.close()
        conn.close()
        print("DB初期化完了（カラム修正済み）")
    except RuntimeError:
        print("DATABASE_URL が設定されていないため、DB初期化はスキップしました")

# アプリ起動時に DB 初期化
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
# ユーザー登録
# ----------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        password_hash = generate_password_hash(password)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
            (username, password_hash)
        )
        conn.commit()
        cur.close()
        conn.close()

        flash("登録が完了しました")
        return redirect(url_for("login"))

    return render_template("register.html")

# ----------------------
# ログイン
# ----------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, password_hash FROM users WHERE username=%s",
            (username,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row and check_password_hash(row[1], password):
            session["user_id"] = row[0]
            session["username"] = username
            flash("ログインしました")
            return redirect(url_for("index"))
        else:
            flash("ユーザー名またはパスワードが間違っています")

    return render_template("login.html")

# ----------------------
# ログアウト
# ----------------------
@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("ログアウトしました")
    return redirect(url_for("index"))

# ----------------------
# デバッグ用: users テーブルのカラム確認
# ----------------------
@app.route("/check_users_columns")
def check_users_columns():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='users';
        """)
        columns = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
        return f"users テーブルのカラム: {columns}"
    except Exception as e:
        return f"エラー発生: {e}"

# ----------------------
# Render対応のポート設定
# ----------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
