from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import os
import psycopg2

app = Flask(__name__)

def get_connection():
    database_url = os.environ.get("DATABASE_URL")
    return psycopg2.connect(database_url)
    
# ----------------------
# デコレーター
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
# ルート
# ----------------------
@app.route("/")
def index():
    conn = get_connection()
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
    conn = get_connection()
    cur = conn.cursor()

    # 投稿者情報取得
    cur.execute("SELECT username, user_id FROM posts WHERE id=%s", (id,))
    post_row = cur.fetchone()
    if not post_row:
        return "投稿が見つかりません", 404
    username = post_row[0]
    post_user_id = post_row[1]  # ← ここで取得

    # 7曲取得
    cur.execute("SELECT title, artist, url FROM songs WHERE post_id=%s ORDER BY id", (id,))
    songs = [
        {"title": row[0], "artist": row[1], "url": row[2]}
        for row in cur.fetchall()
    ]

    cur.close()
    conn.close()

    # テンプレートに渡す
    return render_template(
        "detail.html",
        username=username,
        songs=songs,
        post_id=id,
        post_user_id=post_user_id
    )

# ----------------------
# 新規投稿
# ----------------------
@app.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        username = request.form.get("username")
        songs = []
        for i in range(1, 8):
            title = request.form.get(f"song_title_{i}")
            artist = request.form.get(f"artist_{i}")
            url = request.form.get(f"url_{i}")
            if title and artist:
                songs.append({"title": title, "artist": artist, "url": url})

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO posts (username, user_id) VALUES (%s, %s) RETURNING id", (username, session["user_id"]))
        post_id = cur.fetchone()[0]

        for song in songs:
            cur.execute(
                "INSERT INTO songs (post_id, title, artist, url) VALUES (%s, %s, %s, %s)",
                (post_id, song["title"], song["artist"], song["url"])
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
    row = cur.fetchone()
    if not row:
        return "投稿が見つかりません", 404
    if session["user_id"] != row[0]:
        return "権限がありません", 403

    if request.method == "POST":
        username = request.form.get("username")
        cur.execute("UPDATE posts SET username=%s WHERE id=%s", (username, id))
        for i in range(1, 8):
            title = request.form.get(f"song_title_{i}")
            artist = request.form.get(f"artist_{i}")
            url = request.form.get(f"url_{i}")
            if title and artist:
                cur.execute("""
                    UPDATE songs
                    SET title=%s, artist=%s, url=%s
                    WHERE post_id=%s AND id=(SELECT id FROM songs WHERE post_id=%s ORDER BY id LIMIT 1 OFFSET %s)
                """, (title, artist, url, id, id, i-1))
        conn.commit()
        cur.close()
        conn.close()
        flash("投稿を更新しました")
        return redirect(url_for("detail", id=id))

    cur.execute("SELECT username FROM posts WHERE id=%s", (id,))
    username = cur.fetchone()[0]
    cur.execute("SELECT title, artist, url FROM songs WHERE post_id=%s ORDER BY id", (id,))
    songs = [{"title": r[0], "artist": r[1], "url": r[2]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return render_template("edit.html", post_id=id, username=username, songs=songs)

# ----------------------
# 削除
# ----------------------
@app.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete(id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM posts WHERE id=%s", (id,))
    row = cur.fetchone()

    if not row:
        return "投稿が見つかりません", 404

    if session["user_id"] != row[0]:
        return "権限がありません", 403

    cur.execute("DELETE FROM posts WHERE id=%s", (id,))
    conn.commit()

    cur.close()
    conn.close()

    flash("投稿を削除しました")
    return redirect(url_for("index"))


# ----------------------
# 登録
# ----------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        password_hash = generate_password_hash(password)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, password_hash))
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
        cur.execute("SELECT id, password_hash FROM users WHERE username=%s", (username,))
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
            return redirect(url_for("login"))

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
# 共有リンク
# ----------------------
@app.route("/share/<int:id>")
def share(id):
    return redirect(url_for("detail", id=id))

# ----------------------
# 起動
# ----------------------
if __name__ == "__main__":
    app.run()
