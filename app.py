import os, json, sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

# Yandex GPT настройки
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "")
AI_AVAILABLE = bool(YANDEX_API_KEY and YANDEX_FOLDER_ID)

# Отладочный вывод
print(f"AI_AVAILABLE: {AI_AVAILABLE} (key={'set' if YANDEX_API_KEY else 'missing'}, folder={'set' if YANDEX_FOLDER_ID else 'missing'})")

DB = 'events.db'

# -------------------------------------------
# База данных
# -------------------------------------------
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

def seed_events():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM events")
    if c.fetchone()[0] == 0:
        defaults = [
            ("Фестиваль уличной еды", "еда", "2026-06-20", "12:00", "Центральный парк", 55.751244, 37.618423, "бесплатно", "Лучшие фудтраки города"),
            ("Выставка «История края»", "выставка", "2026-06-22", "10:00", "Краеведческий музей", 55.755826, 37.6173, "300 ₽", "Уникальные экспонаты"),
            ("Ночной велопробег", "спорт", "2026-06-25", "22:00", "Набережная реки", 55.7485, 37.6184, "бесплатно", "Маршрут 20 км"),
            ("Джазовый вечер", "музыка", "2026-06-20", "19:00", "Сад Эрмитаж", 55.7702, 37.6096, "500 ₽", "Живая музыка"),
            ("Гончарный мастер-класс", "мастер-класс", "2026-06-24", "11:00", "Арт-пространство", 55.7616, 37.5932, "800 ₽", "Для детей и взрослых"),
            ("Театральная премьера", "театр", "2026-06-23", "19:00", "Драмтеатр", 55.7600, 37.6200, "1000 ₽", "Спектакль по классике"),
            ("Кино под открытым небом", "кино", "2026-06-21", "21:00", "Парк Горького", 55.7510, 37.6170, "бесплатно", "Ретро-фильмы"),
            ("Эко-прогулка", "природа", "2026-06-26", "09:00", "Лесопарк", 55.7800, 37.5900, "бесплатно", "Пеший маршрут с гидом"),
            ("Ночной клуб", "ночная_жизнь", "2026-06-27", "23:00", "Клуб 'Тоннель'", 55.7700, 37.6100, "1500 ₽", "Лучшие диджеи"),
            ("Ярмарка ремёсел", "ярмарка", "2026-06-28", "10:00", "Площадь", 55.7550, 37.6180, "бесплатно", "Изделия ручной работы")
        ]
        c.executemany("INSERT INTO events (title, type, date, time, location, lat, lon, price, description) VALUES (?,?,?,?,?,?,?,?,?)", defaults)
        conn.commit()
    conn.close()

seed_events()

# -------------------------------------------
# Вспомогательные функции
# -------------------------------------------
def ask_ai(prompt, max_tokens=500):
    """Отправляет промпт в Yandex GPT и возвращает текст ответа или None при ошибке"""
    if not AI_AVAILABLE:
        return None
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "x-folder-id": YANDEX_FOLDER_ID
    }
    body = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt",  # основная модель
        "completionOptions": {
            "stream": False,
            "temperature": 0.3,
            "maxTokens": str(max_tokens)
        },
        "messages": [{"role": "user", "text": prompt}]
    }
    try:
        resp = requests.post(url, json=body, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"Yandex GPT error {resp.status_code}: {resp.text}")
            return None
        data = resp.json()
        if "result" in data and data["result"]["alternatives"]:
            return data["result"]["alternatives"][0]["message"]["text"]
        else:
            print("Yandex GPT empty response:", data)
            return None
    except Exception as e:
        print(f"AI request failed: {e}")
        return None

def fallback_recommendations(lat=None, lon=None):
    """Возвращает до 5 ближайших событий, если координаты переданы, иначе последние по дате"""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if lat is not None and lon is not None:
        # Сортировка по расстоянию (приблизительно)
        c.execute("SELECT *, ((lat - ?)*(lat - ?) + (lon - ?)*(lon - ?)) AS dist FROM events ORDER BY dist LIMIT 5", (lat, lat, lon, lon))
    else:
        c.execute("SELECT * FROM events ORDER BY date LIMIT 5")
    events = [dict(row) for row in c.fetchall()]
    conn.close()
    return events

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
    c.execute("SELECT DISTINCT e.type FROM user_attendance ua JOIN events e ON ua.event_id = e.id WHERE ua.user_id = ?", (user_id,))
    types = [t[0] for t in c.fetchall()]
    badge_map = {
        "еда": "Гурман",
        "спорт": "Спортсмен",
        "культура": "Эстет",
        "музыка": "Мелодия",
        "театр": "Театрал",
        "выставка": "Знаток искусства",
        "кино": "Киноман",
        "природа": "Эко-воин",
        "ночная_жизнь": "Ночной житель",
        "ярмарка": "Коллекционер",
        "мастер-класс": "Мастеровитый",
        "экскурсия": "Следопыт"
    }
    for t in types:
        if t in badge_map and not has_badge(c, user_id, badge_map[t]):
            badges.append((badge_map[t],))
    for b in badges:
        c.execute("INSERT OR IGNORE INTO badges (user_id, badge) VALUES (?,?)", (user_id, b[0]))
    conn.commit()

def has_badge(c, user_id, badge):
    c.execute("SELECT 1 FROM badges WHERE user_id=? AND badge=?", (user_id, badge))
    return c.fetchone() is not None

# -------------------------------------------
# API: события
# -------------------------------------------
@app.route('/api/events', methods=['GET'])
def get_events():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    query = "SELECT * FROM events WHERE 1=1"
    params = []
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    event_type = request.args.get('type')
    if event_type and event_type != 'all':
        query += " AND type = ?"
        params.append(event_type)
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

# -------------------------------------------
# Социальные функции
# -------------------------------------------
@app.route('/api/attend', methods=['POST'])
def attend_event():
    data = request.json
    user_id = data.get('user_id', 'anonymous')
    event_id = data.get('event_id')
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO user_attendance (user_id, event_id) VALUES (?,?)", (user_id, event_id))
    conn.commit()
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

@app.route('/api/badges/<user_id>')
def get_badges(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT badge FROM badges WHERE user_id=?", (user_id,))
    badges = [row[0] for row in c.fetchall()]
    conn.close()
    return jsonify(badges)

# -------------------------------------------
# AI-функции (Yandex GPT)
# -------------------------------------------
@app.route('/api/ai/recommendations')
def ai_recommendations():
    user_id = request.args.get('user_id', 'anonymous')
    # Поддержка геолокации для fallback
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)

    if not AI_AVAILABLE:
        return jsonify(fallback_recommendations(lat, lon))

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

    liked_text = "\n".join([f"- {e['title']}: {e['description']}" for e in liked]) if liked else "нет данных"
    events_json = json.dumps(all_events[:30], ensure_ascii=False)
    prompt = f"""Пользователь интересуется: {interests}.
Ему понравились события:
{liked_text}
Доступные события: {events_json}
Выбери до 5 наиболее подходящих событий и для каждого напиши короткую причину (1 предложение) на русском.
Ответ верни строго в JSON-массиве: [{{"event_id": число, "reason": строка}}]"""
    ai_resp = ask_ai(prompt, max_tokens=400)
    if not ai_resp:
        return jsonify(fallback_recommendations(lat, lon))
    try:
        recs = json.loads(ai_resp.strip().lstrip('```json').rstrip('```').strip())
    except:
        return jsonify(fallback_recommendations(lat, lon))

    event_map = {e['id']: e for e in all_events}
    result = []
    for rec in recs:
        ev = event_map.get(rec['event_id'])
        if ev:
            ev_copy = dict(ev)
            ev_copy['reason'] = rec.get('reason', '')
            result.append(ev_copy)
    return jsonify(result)

# Остальные эндпоинты (plan, chat, parse-url) остаются без изменений
@app.route('/api/ai/plan', methods=['POST'])
def ai_plan():
    if not AI_AVAILABLE:
        return jsonify({"plan": "AI сейчас недоступен"}), 503
    data = request.json
    user_id = data.get('user_id', 'anonymous')
    date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    lat = data.get('lat', 55.75)
    lon = data.get('lon', 37.62)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM events WHERE date = ? ORDER BY time", (date,))
    events_today = [dict(r) for r in c.fetchall()]
    conn.close()
    if not events_today:
        return jsonify({"plan": "На этот день событий не найдено."})
    prompt = f"""Составь план на {date} для пользователя.
События: {json.dumps(events_today, ensure_ascii=False)}
Текущая позиция: ({lat}, {lon}). Выбери 2-3 события, распредели по времени, учти перемещения (1 км ≈ 3 мин пешком).
Добавь рекомендацию, где пообедать или выпить кофе поблизости.
Ответь в JSON: {{"plan": "текст плана", "events": [id1, id2]}}"""
    ai_resp = ask_ai(prompt, max_tokens=500)
    if not ai_resp:
        return jsonify({"plan": "Не удалось составить план."})
    try:
        return jsonify(json.loads(ai_resp.strip().lstrip('```json').rstrip('```').strip()))
    except:
        return jsonify({"plan": "Не удалось разобрать ответ AI."})

@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    if not AI_AVAILABLE:
        return jsonify({"reply": "AI сейчас недоступен."})
    data = request.json
    message = data.get('message', '')
    user_id = data.get('user_id', 'anonymous')
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
        from bs4 import BeautifulSoup
        resp = requests.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        text = soup.get_text()[:5000]
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    prompt = f"""Извлеки события из текста. Верни JSON-массив с полями: title, date (YYYY-MM-DD), time, location, type, price, description.
Текст: {text}
JSON:"""
    ai_resp = ask_ai(prompt, max_tokens=1000)
    if not ai_resp:
        return jsonify({"error": "AI failed"}), 500
    try:
        events = json.loads(ai_resp.strip().lstrip('```json').rstrip('```').strip())
    except:
        return jsonify({"error": "Invalid JSON"}), 500
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    added = 0
    for ev in events:
        if not ev.get('title') or not ev.get('date'):
            continue
        c.execute("INSERT INTO events (title, type, date, time, location, lat, lon, price, description, source_url) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (ev['title'], ev.get('type','другое'), ev['date'], ev.get('time','12:00'), ev.get('location',''),
                   ev.get('lat',0), ev.get('lon',0), ev.get('price','бесплатно'), ev.get('description',''), url))
        added += 1
    conn.commit()
    conn.close()
    return jsonify({"added": added})

# -------------------------------------------
# Главная страница
# -------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
    