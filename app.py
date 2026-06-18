import os, json, sqlite3
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

# Импорты для AI – необязательны
try:
    import openai
    from bs4 import BeautifulSoup
    import requests as req_lib
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

app = Flask(__name__)
CORS(app)

# Конфигурация OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
if OPENAI_API_KEY and AI_AVAILABLE:
    openai.api_key = OPENAI_API_KEY
else:
    AI_AVAILABLE = False

DB = 'events.db'

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, type TEXT NOT NULL, date TEXT NOT NULL,
        time TEXT DEFAULT '12:00', location TEXT NOT NULL,
        lat REAL NOT NULL, lon REAL NOT NULL, price TEXT DEFAULT 'бесплатно',
        description TEXT DEFAULT '', source_url TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL, event_id INTEGER NOT NULL,
        FOREIGN KEY(event_id) REFERENCES events(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_interests (
        user_id TEXT PRIMARY KEY, interests TEXT DEFAULT ''
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_attendance (
        user_id TEXT NOT NULL, event_id INTEGER NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(user_id, event_id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS badges (
        user_id TEXT NOT NULL, badge TEXT NOT NULL,
        PRIMARY KEY(user_id, badge)
    )''')
    conn.commit()
    conn.close()

init_db()

# Предзаполнение событий, если база пуста
def seed_events():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM events")
    if c.fetchone()[0] == 0:
        defaults = [
            ("Фестиваль уличной еды", "еда", "2026-06-20", "12:00", "Центральный парк", 55.751244, 37.618423, "бесплатно", "Лучшие фудтраки города"),
            ("Выставка «История края»", "культура", "2026-06-22", "10:00", "Краеведческий музей", 55.755826, 37.6173, "300 ₽", "Уникальные экспонаты"),
            ("Ночной велопробег", "спорт", "2026-06-25", "22:00", "Набережная реки", 55.7485, 37.6184, "бесплатно", "Маршрут 20 км"),
            ("Джазовый вечер", "культура", "2026-06-20", "19:00", "Сад Эрмитаж", 55.7702, 37.6096, "500 ₽", "Живая музыка"),
            ("Гончарный мастер-класс", "дети", "2026-06-24", "11:00", "Арт-пространство", 55.7616, 37.5932, "800 ₽", "Для детей и взрослых")
        ]
        c.executemany("INSERT INTO events (title, type, date, time, location, lat, lon, price, description) VALUES (?,?,?,?,?,?,?,?,?)", defaults)
        conn.commit()
    conn.close()

seed_events()

# Вспомогательные функции AI
def ask_ai(prompt, max_tokens=500):
    if not AI_AVAILABLE:
        return None
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=max_tokens
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"AI error: {e}")
        return None

# --------------- Базовые API ---------------
@app.route('/api/events', methods=['GET'])
def get_events():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    query = "SELECT * FROM events WHERE 1=1"
    params = []
    for arg, col in [('date_from', 'date'), ('date_to', 'date'), ('type', 'type')]:
        val = request.args.get(arg)
        if val:
            if arg == 'date_from':
                query += f" AND {col} >= ?"
                params.append(val)
            elif arg == 'date_to':
                query += f" AND {col} <= ?"
                params.append(val)
            elif arg == 'type' and val != 'all':
                query += " AND type = ?"
                params.append(val)
    search = request.args.get('search')
    if search:
        query += " AND (title LIKE ? OR location LIKE ? OR description LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])
    query += " ORDER BY date ASC, time ASC"
    c.execute(query, params)
    events = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(events)

@app.route('/api/like', methods=['POST'])
def like_event():
    data = request.json
    user_id = data.get('user_id', 'anonymous')
    event_id = data.get('event_id')
    if not event_id:
        return jsonify({"error": "event_id required"}), 400
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id FROM user_likes WHERE user_id = ? AND event_id = ?", (user_id, event_id))
    if not c.fetchone():
        c.execute("INSERT INTO user_likes (user_id, event_id) VALUES (?,?)", (user_id, event_id))
        conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/interests', methods=['POST'])
def save_interests():
    data = request.json
    user_id = data.get('user_id')
    interests = data.get('interests', '')
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO user_interests (user_id, interests) VALUES (?,?)", (user_id, interests))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

# --------------- Социальные функции ---------------
@app.route('/api/attend', methods=['POST'])
def attend_event():
    data = request.json
    user_id = data.get('user_id', 'anonymous')
    event_id = data.get('event_id')
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO user_attendance (user_id, event_id) VALUES (?,?)", (user_id, event_id))
    conn.commit()
    # Выдача бейджей
    check_and_award_badges(user_id, conn)
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/event/<int:event_id>/attendees')
def event_attendees(event_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT user_id FROM user_attendance WHERE event_id = ?", (event_id,))
    attendees = [row[0] for row in c.fetchall()]
    conn.close()
    return jsonify({"count": len(attendees), "attendees": attendees})

def check_and_award_badges(user_id, conn):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM user_attendance WHERE user_id = ?", (user_id,))
    cnt = c.fetchone()[0]
    badges = []
    if cnt >= 1 and not has_badge(c, user_id, "Новичок"):
        badges.append(("Новичок",))
    if cnt >= 5 and not has_badge(c, user_id, "Исследователь"):
        badges.append(("Исследователь",))
    if cnt >= 10 and not has_badge(c, user_id, "Знаток событий"):
        badges.append(("Знаток событий",))
    # Проверка типов событий
    c.execute("SELECT DISTINCT e.type FROM user_attendance ua JOIN events e ON ua.event_id = e.id WHERE ua.user_id = ?", (user_id,))
    types = [t[0] for t in c.fetchall()]
    if "еда" in types and not has_badge(c, user_id, "Гурман"):
        badges.append(("Гурман",))
    if "спорт" in types and not has_badge(c, user_id, "Спортсмен"):
        badges.append(("Спортсмен",))
    if "культура" in types and not has_badge(c, user_id, "Эстет"):
        badges.append(("Эстет",))
    for b in badges:
        c.execute("INSERT OR IGNORE INTO badges (user_id, badge) VALUES (?,?)", (user_id, b[0]))
    conn.commit()

def has_badge(c, user_id, badge):
    c.execute("SELECT 1 FROM badges WHERE user_id=? AND badge=?", (user_id, badge))
    return c.fetchone() is not None

@app.route('/api/badges/<user_id>')
def get_badges(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT badge FROM badges WHERE user_id=?", (user_id,))
    badges = [row[0] for row in c.fetchall()]
    conn.close()
    return jsonify(badges)

# --------------- AI-функции ---------------
@app.route('/api/ai/recommendations')
def ai_recommendations():
    user_id = request.args.get('user_id', 'anonymous')
    if not AI_AVAILABLE:
        return jsonify(fallback_recommendations(user_id))
    # ... логика та же, что и раньше, но с учётом интересов
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT interests FROM user_interests WHERE user_id=?", (user_id,))
    row = c.fetchone()
    interests = row['interests'] if row else ""
    c.execute("SELECT e.title, e.description FROM user_likes ul JOIN events e ON ul.event_id=e.id WHERE ul.user_id=?", (user_id,))
    liked = [dict(r) for r in c.fetchall()]
    c.execute("SELECT * FROM events")
    all_events = [dict(r) for r in c.fetchall()]
    conn.close()
    if not liked:
        # Если нет лайков, но есть интересы – добавляем их в промпт
        if interests:
            prompt = f"Пользователь интересуется: {interests}. Выбери 5 событий из JSON и дай причину.\nJSON: {json.dumps(all_events[:20], ensure_ascii=False)}"
        else:
            return jsonify(all_events[:5])
    else:
        liked_text = "\n".join([f"- {e['title']}: {e['description']}" for e in liked])
        prompt = f"Пользователю нравились:\n{liked_text}\nИнтересы: {interests}\nВыбери до 5 событий, наиболее подходящих, и укажи причину. Верни JSON [{event_id, reason}]."
    resp = ask_ai(prompt)
    if not resp:
        return jsonify(fallback_recommendations(user_id))
    # Парсим ответ и формируем результат
    try:
        recs = json.loads(resp)
    except:
        return jsonify(fallback_recommendations(user_id))
    event_map = {e['id']: e for e in all_events}
    result = []
    for rec in recs:
        ev = event_map.get(rec['event_id'])
        if ev:
            ev['reason'] = rec.get('reason', '')
            result.append(ev)
    return jsonify(result)

def fallback_recommendations(user_id):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM events ORDER BY date LIMIT 5")
    events = [dict(r) for r in c.fetchall()]
    conn.close()
    return events

@app.route('/api/ai/plan', methods=['POST'])
def ai_plan():
    data = request.json
    user_id = data.get('user_id', 'anonymous')
    date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    lat = data.get('lat', 55.75)
    lon = data.get('lon', 37.62)
    if not AI_AVAILABLE:
        return jsonify({"error": "AI not available"}), 503
    # Получаем события на эту дату и рядом (в радиусе ~10 км)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM events WHERE date = ? ORDER BY time", (date,))
    events_today = [dict(r) for r in c.fetchall()]
    conn.close()
    if not events_today:
        return jsonify({"plan": "На этот день событий не найдено."})
    prompt = f"""Составь план на {date} для пользователя. Есть события: {json.dumps(events_today, ensure_ascii=False)}.
Пользователь находится в точке ({lat},{lon}). Выбери 2-3 события, распредели их по времени, учти расстояния (1 км ≈ 3 мин пешком). Добавь рекомендацию, где пообедать или выпить кофе поблизости. Ответь в формате JSON: {{"plan": "описание плана", "events": [id1, id2]}}"""
    resp = ask_ai(prompt)
    if not resp:
        return jsonify({"plan": "Не удалось составить план."})
    return jsonify(json.loads(resp))

@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    data = request.json
    message = data.get('message', '')
    user_id = data.get('user_id', 'anonymous')
    if not message or not AI_AVAILABLE:
        return jsonify({"reply": "Извините, AI сейчас недоступен."})
    # Собираем контекст: интересы, лайки, предстоящие события
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT interests FROM user_interests WHERE user_id=?", (user_id,))
    row = c.fetchone()
    interests = row['interests'] if row else "не указаны"
    c.execute("SELECT e.title FROM user_likes ul JOIN events e ON ul.event_id=e.id WHERE ul.user_id=? LIMIT 5", (user_id,))
    liked = [r['title'] for r in c.fetchall()]
    c.execute("SELECT title, date, time, location FROM events WHERE date >= ? ORDER BY date LIMIT 10", (datetime.now().strftime('%Y-%m-%d'),))
    upcoming = [dict(r) for r in c.fetchall()]
    conn.close()
    context = f"Интересы: {interests}. Любимые события: {', '.join(liked) if liked else 'нет'}. Предстоящие: {json.dumps(upcoming, ensure_ascii=False)}"
    prompt = f"Ты — ассистент по мероприятиям. Контекст: {context}\nВопрос: {message}\nОтветь дружелюбно и по делу, предложи события из списка."
    reply = ask_ai(prompt, max_tokens=300)
    return jsonify({"reply": reply or "Не получилось ответить."})

@app.route('/api/ai/parse-url', methods=['POST'])
def ai_parse_url():
    if not AI_AVAILABLE:
        return jsonify({"error": "AI not available"}), 503
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({"error": "URL required"}), 400
    try:
        resp = req_lib.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        text = soup.get_text()[:5000]
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    prompt = f"""Извлеки события из текста, верни JSON-массив с полями: title, date (YYYY-MM-DD), time, location, type, price, description.
Текст: {text}
JSON:"""
    ai_resp = ask_ai(prompt, max_tokens=1000)
    if not ai_resp:
        return jsonify({"error": "AI failed"}), 500
    try:
        events = json.loads(ai_resp)
    except:
        return jsonify({"error": "Invalid JSON from AI"}), 500
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    added = []
    for ev in events:
        if not ev.get('title') or not ev.get('date'):
            continue
        c.execute("INSERT INTO events (title, type, date, time, location, lat, lon, price, description, source_url) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (ev['title'], ev.get('type','другое'), ev['date'], ev.get('time','12:00'), ev.get('location',''), ev.get('lat',0), ev.get('lon',0), ev.get('price','бесплатно'), ev.get('description',''), url))
        added.append(c.lastrowid)
    conn.commit()
    conn.close()
    return jsonify({"added": len(added)})

# --------------- Статика и главная ---------------
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
    