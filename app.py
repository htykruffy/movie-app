from flask import Flask, render_template, request, redirect, url_for, session
import requests
import psycopg2
import psycopg2.extras
import os
from contextlib import contextmanager

app = Flask(__name__)
app.secret_key = 'your-secret-key'

TMDB_API_KEY = "ab6258adcf2845eb64ad01e30ec639d5"
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w200"


db_url = os.environ.get('DATEBASE_URL')
# @contextmanager
# def get_db():
#     db = psycopg2.connect(
#         host="localhost",
#         database="postgres",
#         user="hiratayuki",
#         password="password",
#         port=5432
#     )
#     try:
#         yield db
#     finally:
#         db.close()

# @contextmanager
# def get_db():
#     conn = psycopg2.connect(db_url, sslmode='require')
#     return conn


@contextmanager
def get_db():
    conn = psycopg2.connect(
        host="...",
        database="...",
        user="...",
        password="...",
        port=5432
    )
    try:
        yield conn
    finally:
        conn.close()

def search_movies_from_tmdb(query):
    params = {
        "api_key": TMDB_API_KEY,
        "query": query,
        "language": "ja-JP"
    }
    res = requests.get(TMDB_SEARCH_URL, params=params)
    data = res.json()
    movies = []
    for item in data.get("results", []):
        poster_path = item.get("poster_path")
        title = item.get("title")
        movie_id = item.get("id")
        if poster_path and title and movie_id:
            movies.append({
                "id": movie_id,
                "title": title,
                "api_url": f"{TMDB_IMAGE_BASE_URL}{poster_path}"
            })
    return movies

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    query = request.args.get('query')
    movies = search_movies_from_tmdb(query) if query else []

    return render_template('index.html', username=session['username'], movies=movies)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['user_name']
        password = request.form['pass']
        action = request.form.get('action')

        if action == '新規作成':
            return signup(username, password)
        else:
            return login_user(username, password)

    return render_template('login.html')

def signup(username, password):
    if not username or not password:
        return render_template('login.html', error='ユーザー名とパスワードを入力してください')

    with get_db() as db:
        with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute('SELECT * FROM users WHERE name = %s', (username,))
            existing_user = cur.fetchone()
            if existing_user:
                return render_template('login.html', error='このユーザー名は既に使用されています')

            cur.execute('INSERT INTO users (name, pass) VALUES (%s, %s)', (username, password))
            db.commit()

            cur.execute('SELECT * FROM users WHERE name = %s', (username,))
            user = cur.fetchone()

            session['user_id'] = user['id']
            session['username'] = user['name']
            return redirect(url_for('index'))

def login_user(username, password):
    with get_db() as db:
        with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute('SELECT * FROM users WHERE name = %s AND pass = %s', (username, password))
            user = cur.fetchone()

            if user:
                session['user_id'] = user['id']
                session['username'] = user['name']
                return redirect(url_for('index'))
            else:
                return render_template('login.html', error='ユーザー名またはパスワードが間違っています')

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/movie/<int:movie_id>')
def movie_detail(movie_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    movie_url = f"https://api.themoviedb.org/3/movie/{movie_id}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "ja-JP"
    }
    res = requests.get(movie_url, params=params)
    movie = res.json()

    with get_db() as db:
        with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute('SELECT * FROM movies WHERE user_id = %s AND movie_id = %s', (session['user_id'], movie_id))
            saved_movie = cur.fetchone()

            cur.execute('''
                SELECT r.comment, u.name as username 
                FROM reviews r 
                JOIN users u ON r.user_id = u.id 
                WHERE r.movie_id = %s 
                ORDER BY r.id DESC
            ''', (movie_id,))
            reviews = cur.fetchall()

    return render_template("detail.html", movie=movie, saved_movie=saved_movie, reviews=reviews)

@app.route('/movie/<int:movie_id>/review', methods=['POST'])
def add_review(movie_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    comment = request.form.get('comment')

    with get_db() as db:
        with db.cursor() as cur:
            cur.execute('INSERT INTO reviews (movie_id, user_id, comment) VALUES (%s, %s, %s)',
                        (movie_id, session['user_id'], comment))
            db.commit()

    return redirect(url_for('movie_detail', movie_id=movie_id))

@app.route('/mylist')
def mylist():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    with get_db() as db:
        with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute('SELECT * FROM movies WHERE user_id = %s AND watched = 1', (session['user_id'],))
            watched_movies = cur.fetchall()

            cur.execute('SELECT * FROM movies WHERE user_id = %s AND watched = 0', (session['user_id'],))
            to_watch_movies = cur.fetchall()

    watched_details = []
    for movie in watched_movies:
        res = requests.get(f"https://api.themoviedb.org/3/movie/{movie['movie_id']}",
                           params={"api_key": TMDB_API_KEY, "language": "ja-JP"})
        watched_details.append(res.json())

    to_watch_details = []
    for movie in to_watch_movies:
        res = requests.get(f"https://api.themoviedb.org/3/movie/{movie['movie_id']}",
                           params={"api_key": TMDB_API_KEY, "language": "ja-JP"})
        to_watch_details.append(res.json())

    return render_template('mylist.html', watched_movies=watched_details, to_watch_movies=to_watch_details)

@app.route('/movie/<int:movie_id>/save', methods=['POST'])
def save_movie(movie_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    status = request.form.get('status')
    watched = 1 if status == 'watched' else 0

    with get_db() as db:
        with db.cursor() as cur:
            cur.execute('SELECT * FROM movies WHERE user_id = %s AND movie_id = %s',
                        (session['user_id'], movie_id))
            existing = cur.fetchone()

            if existing:
                cur.execute('UPDATE movies SET watched = %s WHERE user_id = %s AND movie_id = %s',
                            (watched, session['user_id'], movie_id))
            else:
                cur.execute('INSERT INTO movies (user_id, movie_id, watched) VALUES (%s, %s, %s)',
                            (session['user_id'], movie_id, watched))
            db.commit()

    return redirect(url_for('mylist'))

@app.route('/delete_account', methods=['POST'])
def delete_account():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    with get_db() as db:
        with db.cursor() as cur:
            cur.execute('DELETE FROM reviews WHERE user_id = %s', (session['user_id'],))
            cur.execute('DELETE FROM movies WHERE user_id = %s', (session['user_id'],))
            cur.execute('DELETE FROM users WHERE id = %s', (session['user_id'],))
            db.commit()

    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)


