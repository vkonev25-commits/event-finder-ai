import os, json
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from supabase import create_client
import requests

app = Flask(__name__)
CORS(app)

# ---------- Конфигурация Supabase ----------
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ваш-проект.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "ваш-анонимный-ключ")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------- Yandex GPT ----------
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "")
AI_AVAILABLE = bool(YANDEX_API_KEY and YANDEX_FOLDER_ID)

print(f"AI_AVAILABLE: {AI_AVAILABLE} (key={'set' if YANDEX_API_KEY else 'missing'}, folder={'set' if YANDEX_FOLDER_ID else 'missing'})")

# ---------- Вспомогательные функции ----------
def get_user_id():
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        try:
            user = supabase.auth.get_user(token)
            return user.user.id
        except:
            pass
    return None

def ask_ai(prompt, max_tokens=500):
    if not AI_AVAILABLE:
        return None
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "x-folder-id": YANDEX_FOLDER_ID
    }
    body = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",  # или yandexgpt
        "completionOptions": {
            "stream": False,
            "temperature": 0.3,
            "maxTokens": str(max_tokens)
        },
        "messages": [{"role": "user", "text": prompt}]
    }
    try:
        resp = requests.post(url, json=body, headers=headers, timeout=30)
        print(f"Yandex GPT status: {resp.status_code}")
        if resp.status_code != 200:
            return None
        data = resp.json()
        if "result" in data and data["result"]["alternatives"]:
            return data["result"]["alternatives"][0]["message"]["text"]
        else:
            return None
    except Exception as e:
        print(f"AI request failed: {e}")
        return None

def fallback_recommendations():
    resp = supabase.table('events').select('*').limit(5).execute()
    return resp.data

def check_and_award_badges(user_id):
    resp = supabase.table('user_attendance').select('event_id', count='exact').eq('user_id', user_id).execute()
    cnt = resp.count
    badges = []
    if cnt >= 1:
        badges.append('Новичок')
    if cnt >= 5:
        badges.append('Исследователь')
    if cnt >= 10:
        badges.append('Знаток событий')
    for b in badges:
        supabase.table('badges').upsert({'user_id': user_id, 'badge': b}).execute()

# ---------- API: события ----------
@app.route('/api/events', methods=['GET'])
def get_events():
    query = supabase.table('events').select('*')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    event_type = request.args.get('type')
    search = request.args.get('search')
    if date_from:
        query = query.gte('date', date_from)
    if date_to:
        query = query.lte('date', date_to)
    if event_type and event_type != 'all':
        query = query.eq('type', event_type)
    if search:
        query = query.or_(f"title.ilike.%{search}%,description.ilike.%{search}%,location.ilike.%{search}%")
    resp = query.order('date,time').execute()
    return jsonify(resp.data)

@app.route('/api/like', methods=['POST'])
def like_event():
    user_id = get_user_id()
    if not user_id:
        return jsonify({"error": "Требуется авторизация"}), 401
    data = request.json
    event_id = data.get('event_id')
    existing = supabase.table('user_likes').select('*').eq('user_id', user_id).eq('event_id', event_id).execute()
    if not existing.data:
        supabase.table('user_likes').insert({'user_id': user_id, 'event_id': event_id}).execute()
    return jsonify({"status": "ok"})

@app.route('/api/interests', methods=['POST'])
def save_interests():
    user_id = get_user_id()
    if not user_id:
        return jsonify({"error": "Требуется авторизация"}), 401
    data = request.json
    interests = data.get('interests', '')
    supabase.table('user_interests').upsert({'user_id': user_id, 'interests': interests}).execute()
    return jsonify({"status": "ok"})

@app.route('/api/attend', methods=['POST'])
def attend_event():
    user_id = get_user_id()
    if not user_id:
        return jsonify({"error": "Требуется авторизация"}), 401
    data = request.json
    event_id = data.get('event_id')
    supabase.table('user_attendance').upsert({'user_id': user_id, 'event_id': event_id}).execute()
    check_and_award_badges(user_id)
    return jsonify({"status": "ok"})

@app.route('/api/event/<int:event_id>/attendees')
def event_attendees(event_id):
    resp = supabase.table('user_attendance').select('user_id', count='exact').eq('event_id', event_id).execute()
    return jsonify({"count": resp.count, "attendees": resp.data})

@app.route('/api/badges')
def get_badges():
    user_id = get_user_id()
    if not user_id:
        return jsonify([])
    resp = supabase.table('badges').select('badge').eq('user_id', user_id).execute()
    return jsonify([r['badge'] for r in resp.data])

# ---------- AI-эндпоинты ----------
@app.route('/api/ai/recommendations')
def ai_recommendations():
    user_id = get_user_id() or 'anonymous'
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)

    if not AI_AVAILABLE:
        return jsonify(fallback_recommendations())

    # Получаем интересы пользователя
    interests = ""
    liked = []
    if user_id != 'anonymous':
        resp_int = supabase.table('user_interests').select('interests').eq('user_id', user_id).execute()
        if resp_int.data:
            interests = resp_int.data[0]['interests']
        resp_liked = supabase.table('user_likes').select('event_id').eq('user_id', user_id).execute()
        liked_ids = [row['event_id'] for row in resp_liked.data]
        if liked_ids:
            resp_events = supabase.table('events').select('title,description').in_('id', liked_ids).execute()
            liked = resp_events.data
    all_events = supabase.table('events').select('*').limit(30).execute().data

    liked_text = "\n".join([f"- {e['title']}: {e['description']}" for e in liked]) if liked else "нет данных"
    events_json = json.dumps(all_events, ensure_ascii=False)
    prompt = f"""Пользователь интересуется: {interests}.
Ему понравились события:
{liked_text}
Доступные события: {events_json}
Выбери до 5 наиболее подходящих событий и для каждого напиши короткую причину (1 предложение) на русском.
Ответ верни строго в JSON-массиве: [{{"event_id": число, "reason": строка}}]"""
    ai_resp = ask_ai(prompt, max_tokens=400)
    if not ai_resp:
        return jsonify(fallback_recommendations())
    try:
        recs = json.loads(ai_resp.strip().lstrip('```json').rstrip('```').strip())
    except:
        return jsonify(fallback_recommendations())
    event_map = {e['id']: e for e in all_events}
    result = []
    for rec in recs:
        ev = event_map.get(rec['event_id'])
        if ev:
            ev_copy = dict(ev)
            ev_copy['reason'] = rec.get('reason', '')
            result.append(ev_copy)
    return jsonify(result)

@app.route('/api/ai/plan', methods=['POST'])
def ai_plan():
    if not AI_AVAILABLE:
        return jsonify({"plan": "AI сейчас недоступен"}), 503
    data = request.json
    date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    lat = data.get('lat', 55.75)
    lon = data.get('lon', 37.62)
    events_today = supabase.table('events').select('*').eq('date', date).execute().data
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
    user_id = get_user_id() or 'anonymous'
    interests = ""
    liked = []
    if user_id != 'anonymous':
        resp_int = supabase.table('user_interests').select('interests').eq('user_id', user_id).execute()
        if resp_int.data:
            interests = resp_int.data[0]['interests']
        resp_liked = supabase.table('user_likes').select('event_id').eq('user_id', user_id).execute()
        liked_ids = [row['event_id'] for row in resp_liked.data]
        if liked_ids:
            resp_events = supabase.table('events').select('title').in_('id', liked_ids).execute()
            liked = [e['title'] for e in resp_events.data]
    upcoming = supabase.table('events').select('title,date,time,location').gte('date', datetime.now().strftime('%Y-%m-%d')).limit(10).execute().data
    context = f"Интересы: {interests}. Любимые события: {', '.join(liked) if liked else 'нет'}. Предстоящие: {json.dumps(upcoming, ensure_ascii=False)}"
    prompt = f"Ты — ассистент по мероприятиям. Контекст: {context}\nВопрос: {message}\nОтветь дружелюбно и по делу, предложи события из списка."
    reply = ask_ai(prompt, max_tokens=300)
    return jsonify({"reply": reply or "Не получилось ответить."})

# ---------- Главная страница ----------
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
    