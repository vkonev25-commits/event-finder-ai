// ---------- Конфигурация Supabase (замените на свои значения) ----------
const SUPABASE_URL = 'https://your-project.supabase.co';   // 👈 заменить
const SUPABASE_KEY = 'your-anon-key';                       // 👈 заменить
const supabaseClient = supabase.createClient(SUPABASE_URL, SUPABASE_KEY);

// ---------- Глобальные переменные ----------
let currentUser = null;
const allTypes = [
    'еда', 'культура', 'спорт', 'дети', 'музыка', 'театр', 'выставка',
    'кино', 'ярмарка', 'природа', 'экскурсия', 'ночная_жизнь', 'мастер-класс'
];
let selectedType = 'all';

// Карта
const map = L.map('map').setView([55.751244, 37.618423], 12);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution:'© OpenStreetMap'}).addTo(map);
const markersLayer = L.layerGroup().addTo(map);

// ---------- Авторизация ----------
async function initAuth() {
    const { data: { session } } = await supabaseClient.auth.getSession();
    currentUser = session?.user;
    updateAuthUI();
}
initAuth();

function updateAuthUI() {
    const loginBtn = document.getElementById('login-btn');
    const profileBtn = document.getElementById('profile-btn');
    if (currentUser) {
        loginBtn.style.display = 'none';
        profileBtn.style.display = 'inline-block';
        profileBtn.onclick = () => alert(`Вы вошли как ${currentUser.email || 'пользователь'}`);
    } else {
        loginBtn.style.display = 'inline-block';
        profileBtn.style.display = 'none';
    }
}

document.getElementById('login-btn').addEventListener('click', async () => {
    const provider = prompt('Выберите способ входа: google, yandex, vk, telegram');
    if (!provider) return;
    const { error } = await supabaseClient.auth.signInWithOAuth({ provider });
    if (error) alert('Ошибка входа: ' + error.message);
});

// Функция fetch с токеном
async function fetchWithAuth(url, options = {}) {
    if (currentUser) {
        const { data: { session } } = await supabaseClient.auth.getSession();
        if (session) {
            options.headers = {
                ...options.headers,
                'Authorization': `Bearer ${session.access_token}`
            };
        }
    }
    return fetch(url, options);
}

// ---------- Онбординг ----------
function nextSlide(num) {
    document.querySelectorAll('.onboard-slide').forEach(s => s.style.display = 'none');
    document.getElementById('slide' + num).style.display = 'block';
}
function finishOnboarding() {
    document.getElementById('onboarding').style.display = 'none';
    document.getElementById('interests-screen').style.display = 'flex';
    const container = document.getElementById('interests-tags');
    allTypes.forEach(t => {
        const el = document.createElement('span');
        el.className = 'tag';
        el.textContent = t;
        el.onclick = () => el.classList.toggle('selected');
        container.appendChild(el);
    });
    document.getElementById('main-app').style.display = 'flex';
}
function skipInterests() {
    document.getElementById('interests-screen').style.display = 'none';
    localStorage.setItem('onboarded', '1');
}
async function saveInterests() {
    const selected = [...document.querySelectorAll('#interests-tags .tag.selected')].map(t => t.textContent).join(',');
    if (currentUser) {
        await fetchWithAuth('/api/interests', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ interests: selected })
        });
    }
    document.getElementById('interests-screen').style.display = 'none';
    localStorage.setItem('onboarded', '1');
}

// ---------- Фильтры ----------
function buildTypeFilters() {
    const container = document.getElementById('type-filters');
    container.innerHTML = '';
    const allBtn = document.createElement('span');
    allBtn.className = 'tag' + (selectedType === 'all' ? ' selected' : '');
    allBtn.textContent = 'Все';
    allBtn.onclick = () => { selectedType = 'all'; updateFilters(); };
    container.appendChild(allBtn);
    allTypes.forEach(t => {
        const btn = document.createElement('span');
        btn.className = 'tag' + (selectedType === t ? ' selected' : '');
        btn.textContent = t;
        btn.onclick = () => { selectedType = (selectedType === t ? 'all' : t); updateFilters(); };
        container.appendChild(btn);
    });
}
function updateFilters() {
    buildTypeFilters();
    loadEvents();
}

// ---------- Загрузка событий ----------
async function loadEvents() {
    const params = new URLSearchParams({
        search: document.getElementById('search').value,
        date_from: document.getElementById('date_from').value,
        date_to: document.getElementById('date_to').value,
        type: selectedType
    });
    const resp = await fetch('/api/events?' + params);
    const events = await resp.json();
    renderList(events);
    renderMarkers(events);
}

function renderList(events) {
    const container = document.getElementById('list-container');
    container.innerHTML = '';
    events.forEach(ev => {
        const card = document.createElement('div');
        card.className = `event-card type-${ev.type}`;
        const yandexUrl = `https://yandex.ru/maps/?ll=${ev.lon},${ev.lat}&z=16&text=${encodeURIComponent(ev.title)}`;
        const dgisUrl = `https://2gis.ru/geo/${ev.lon},${ev.lat}/center/${ev.lon},${ev.lat}/zoom/16`;
        const isLiked = localStorage.getItem('liked_' + ev.id) === '1';
        card.innerHTML = `
            <span class="like-btn" data-id="${ev.id}">${isLiked ? '❤️' : '🤍'}</span>
            <h3>${ev.title} <span class="badge">${ev.type}</span></h3>
            <div class="meta">
                <span>📅 ${ev.date} ${ev.time}</span>
                <span>📍 ${ev.location}</span>
                <span>💰 ${ev.price}</span>
            </div>
            <div style="margin-top: 8px; display: flex; gap: 10px; align-items: center;">
                <button class="attend-btn" data-id="${ev.id}">Пойду 👍</button>
                <span class="attendees-count" id="count-${ev.id}"></span>
                <a href="${yandexUrl}" target="_blank" class="map-link" title="Яндекс Карты">📍Я</a>
                <a href="${dgisUrl}" target="_blank" class="map-link" title="2ГИС">📍2</a>
                <button class="share-btn" data-title="${ev.title}" data-date="${ev.date}" data-location="${ev.location}">🔗</button>
            </div>
        `;
        container.appendChild(card);

        // Лайк
        card.querySelector('.like-btn').addEventListener('click', async (e) => {
            e.stopPropagation();
            const btn = e.target;
            const id = ev.id;
            if (currentUser) {
                const resp = await fetchWithAuth('/api/like', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ event_id: id })
                });
                if (resp.ok) {
                    localStorage.setItem('liked_' + id, '1');
                    btn.classList.add('liked');
                    btn.textContent = '❤️';
                } else {
                    alert('Не удалось сохранить лайк');
                }
            } else {
                localStorage.setItem('liked_' + id, '1');
                btn.classList.add('liked');
                btn.textContent = '❤️';
            }
        });

        // Отметка "Пойду"
        card.querySelector('.attend-btn').addEventListener('click', async (e) => {
            e.stopPropagation();
            const attendBtn = e.target;
            if (currentUser) {
                await fetchWithAuth('/api/attend', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ event_id: ev.id })
                });
                attendBtn.classList.add('going');
                attendBtn.textContent = '✓ Вы идёте';
            } else {
                attendBtn.classList.add('going');
                attendBtn.textContent = '✓ Вы идёте (локально)';
            }
            loadAttendees(ev.id);
        });

        // Шеринг
        card.querySelector('.share-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            const { title, date, location } = e.target.dataset;
            if (navigator.share) {
                navigator.share({ title, text: `${title} (${date}) в ${location}. Приходите!`, url: window.location.href });
            } else {
                alert(`${title}\n${date}\n${location}`);
            }
        });

        card.addEventListener('click', (e) => {
            if (e.target.tagName === 'A' || e.target.classList.contains('share-btn') || e.target.classList.contains('like-btn') || e.target.classList.contains('attend-btn')) return;
            map.setView([ev.lat, ev.lon], 15);
        });
        loadAttendees(ev.id);
    });
}

async function loadAttendees(eventId) {
    const resp = await fetch(`/api/event/${eventId}/attendees`);
    const data = await resp.json();
    const span = document.getElementById(`count-${eventId}`);
    if (span) span.textContent = data.count ? ` (${data.count})` : '';
}

function renderMarkers(events) {
    markersLayer.clearLayers();
    events.forEach(ev => {
        L.marker([ev.lat, ev.lon]).addTo(markersLayer).bindPopup(`<b>${ev.title}</b><br>${ev.date} ${ev.time}`);
    });
}

// ---------- AI-рекомендации ----------
async function openRecommendations() {
    document.getElementById('rec-modal').style.display = 'flex';
    document.getElementById('rec-content').innerHTML = '<p>Загрузка...</p>';
    let lat, lon;
    if (navigator.geolocation) {
        try {
            const pos = await new Promise((resolve, reject) =>
                navigator.geolocation.getCurrentPosition(resolve, reject)
            );
            lat = pos.coords.latitude;
            lon = pos.coords.longitude;
        } catch(e) {}
    }
    const params = new URLSearchParams();
    if (lat) params.append('lat', lat);
    if (lon) params.append('lon', lon);
    const resp = await fetchWithAuth('/api/ai/recommendations?' + params);
    const recs = await resp.json();
    const html = recs.map(r => `
        <div class="event-card type-${r.type}" onclick="map.setView([${r.lat},${r.lon}],15);document.getElementById('rec-modal').style.display='none'">
            <strong>${r.title}</strong> <span class="badge">${r.type}</span><br>
            <small>${r.date} ${r.time} | ${r.location}</small>
            ${r.reason ? `<div style="color:#e65100; font-style:italic;">💡 ${r.reason}</div>` : ''}
        </div>
    `).join('');
    document.getElementById('rec-content').innerHTML = html || 'Нет рекомендаций. Поставьте лайки.';
}

// ---------- План на день ----------
async function openPlanModal() {
    document.getElementById('plan-modal').style.display = 'flex';
    document.getElementById('plan-content').innerHTML = '<p>Составляем план...</p>';
    navigator.geolocation.getCurrentPosition(async pos => {
        const resp = await fetchWithAuth('/api/ai/plan', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                lat: pos.coords.latitude,
                lon: pos.coords.longitude
            })
        });
        const data = await resp.json();
        document.getElementById('plan-content').innerHTML = `<p>${data.plan}</p>`;
    }, () => {
        document.getElementById('plan-content').innerHTML = 'Не удалось получить геолокацию.';
    });
}

// ---------- Чат-бот ----------
document.getElementById('ai-btn').addEventListener('dblclick', () => {
    const chat = document.getElementById('chat-widget');
    chat.style.display = chat.style.display === 'flex' ? 'none' : 'flex';
});
async function sendChat() {
    const input = document.getElementById('chat-input');
    const msg = input.value.trim();
    if (!msg) return;
    const chatMessages = document.getElementById('chat-messages');
    chatMessages.innerHTML += `<div style="text-align:right; margin:5px"><b>Вы:</b> ${msg}</div>`;
    input.value = '';
    chatMessages.innerHTML += `<div style="text-align:left; margin:5px"><i>AI печатает...</i></div>`;
    const resp = await fetchWithAuth('/api/ai/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ message: msg })
    });
    const data = await resp.json();
    chatMessages.removeChild(chatMessages.lastChild);
    chatMessages.innerHTML += `<div style="text-align:left; margin:5px"><b>🤖 AI:</b> ${data.reply}</div>`;
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ---------- Бейджи ----------
async function showBadges() {
    if (!currentUser) {
        alert('Войдите, чтобы увидеть бейджи');
        return;
    }
    const resp = await fetchWithAuth('/api/badges');
    const badges = await resp.json();
    alert('Ваши бейджи: ' + (badges.join(', ') || 'пока нет'));
}
document.getElementById('profile-btn').addEventListener('click', showBadges);

// ---------- Офлайн-индикатор ----------
window.addEventListener('online', () => document.getElementById('offline-indicator').style.display = 'none');
window.addEventListener('offline', () => document.getElementById('offline-indicator').style.display = 'block');
if (!navigator.onLine) document.getElementById('offline-indicator').style.display = 'block';

// ---------- Закрытие модалок ----------
document.querySelectorAll('.modal').forEach(m => m.addEventListener('click', function(e){ if(e.target===this) this.style.display='none'; }));

// ---------- Старт ----------
buildTypeFilters();
if (!localStorage.getItem('onboarded')) {
    document.getElementById('main-app').style.display = 'none';
} else {
    document.getElementById('onboarding').style.display = 'none';
    document.getElementById('interests-screen').style.display = 'none';
}
document.getElementById('search').addEventListener('input', loadEvents);
document.getElementById('date_from').addEventListener('change', loadEvents);
document.getElementById('date_to').addEventListener('change', loadEvents);
loadEvents();
