const userId = localStorage.getItem('userId') || 'user_' + Date.now();
localStorage.setItem('userId', userId);
let currentEvents = [];
const allTypes = [
    'еда', 'культура', 'спорт', 'дети', 'музыка', 'театр', 'выставка',
    'кино', 'ярмарка', 'природа', 'экскурсия', 'ночная_жизнь', 'мастер-класс'
];
let selectedType = 'all';

// Карта
const map = L.map('map').setView([55.751244, 37.618423], 12);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution:'© OpenStreetMap'}).addTo(map);
const markersLayer = L.layerGroup().addTo(map);

// Онбординг
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
    await fetch('/api/interests', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, interests: selected})
    });
    document.getElementById('interests-screen').style.display = 'none';
    localStorage.setItem('onboarded', '1');
}

// Фильтры типов
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

// Загрузка событий
async function loadEvents() {
    const params = new URLSearchParams({
        search: document.getElementById('search').value,
        date_from: document.getElementById('date_from').value,
        date_to: document.getElementById('date_to').value,
        type: selectedType
    });
    try {
        const resp = await fetch('/api/events?' + params);
        currentEvents = await resp.json();
        renderList(currentEvents);
        renderMarkers(currentEvents);
    } catch(e) { console.log('Offline or error', e); }
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
                <a href="${yandexUrl}" target="_blank" class="map-link" title="Открыть в Яндекс Картах">📍Я</a>
                <a href="${dgisUrl}" target="_blank" class="map-link" title="Открыть в 2ГИС">📍2</a>
                <button class="share-btn" data-title="${ev.title}" data-date="${ev.date}" data-location="${ev.location}">🔗</button>
            </div>
        `;
        container.appendChild(card);

        // лайк
        card.querySelector('.like-btn').addEventListener('click', async (e) => {
            e.stopPropagation();
            const btn = e.target;
            const id = ev.id;
            await fetch('/api/like', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({user_id: userId, event_id: id})
            });
            localStorage.setItem('liked_' + id, '1');
            btn.classList.add('liked');
            btn.textContent = '❤️';
        });

        // отметка "Пойду"
        const attendBtn = card.querySelector('.attend-btn');
        attendBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            await fetch('/api/attend', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({user_id: userId, event_id: ev.id})
            });
            attendBtn.classList.add('going');
            attendBtn.textContent = '✓ Вы идёте';
            loadAttendees(ev.id);
        });

        // кнопка "Поделиться"
        card.querySelector('.share-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            const title = e.target.dataset.title;
            const date = e.target.dataset.date;
            const location = e.target.dataset.location;
            if (navigator.share) {
                navigator.share({
                    title: title,
                    text: `${title} (${date}) в ${location}. Приходите!`,
                    url: window.location.href
                });
            } else {
                alert(`Событие: ${title}\nДата: ${date}\nМесто: ${location}\nСсылка: ${window.location.href}`);
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

// AI Рекомендации
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
    const params = new URLSearchParams({ user_id: userId });
    if (lat) params.append('lat', lat);
    if (lon) params.append('lon', lon);
    const resp = await fetch('/api/ai/recommendations?' + params);
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

// План на день
async function openPlanModal() {
    document.getElementById('plan-modal').style.display = 'flex';
    document.getElementById('plan-content').innerHTML = '<p>Составляем план...</p>';
    navigator.geolocation.getCurrentPosition(async pos => {
        const resp = await fetch('/api/ai/plan', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({user_id:userId, lat:pos.coords.latitude, lon:pos.coords.longitude})
        });
        const data = await resp.json();
        document.getElementById('plan-content').innerHTML = `<p>${data.plan}</p>`;
    }, () => {
        document.getElementById('plan-content').innerHTML = 'Не удалось получить геолокацию.';
    });
}

// Чат-бот
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
    const resp = await fetch('/api/ai/chat', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({user_id: userId, message: msg})
    });
    const data = await resp.json();
    chatMessages.removeChild(chatMessages.lastChild);
    chatMessages.innerHTML += `<div style="text-align:left; margin:5px"><b>🤖 AI:</b> ${data.reply}</div>`;
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Бейджи
async function showBadges() {
    const resp = await fetch('/api/badges/' + userId);
    const badges = await resp.json();
    alert('Ваши бейджи: ' + (badges.join(', ') || 'пока нет'));
}
document.getElementById('profile-btn').onclick = showBadges;

// Офлайн-индикатор
window.addEventListener('online', () => document.getElementById('offline-indicator').style.display = 'none');
window.addEventListener('offline', () => document.getElementById('offline-indicator').style.display = 'block');
if (!navigator.onLine) document.getElementById('offline-indicator').style.display = 'block';

// Закрытие модалок
document.querySelectorAll('.modal').forEach(m => m.addEventListener('click', function(e){ if(e.target===this) this.style.display='none'; }));

// Инициализация
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
