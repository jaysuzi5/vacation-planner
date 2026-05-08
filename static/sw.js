const CACHE_NAME = 'vp-shell-v2';
const STATIC_ORIGINS = ['cdn.jsdelivr.net', 'fonts.googleapis.com', 'fonts.gstatic.com'];
const SKIP_PATHS = ['/api/', '/admin/', '/accounts/'];

// ── Install: precache shell + offline fallback page ─────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache =>
      Promise.allSettled([
        cache.add('/'),
        cache.add('/offline/'),
      ])
    )
  );
  self.skipWaiting();
});

// ── Activate: evict old named caches ────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// ── Fetch ────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Pass through: non-GET, API, admin, auth
  if (request.method !== 'GET') return;
  if (SKIP_PATHS.some(p => url.pathname.startsWith(p))) return;

  const isAsset =
    url.pathname.startsWith('/static/') || STATIC_ORIGINS.includes(url.hostname);
  const isNav =
    url.origin === self.location.origin &&
    (request.mode === 'navigate' ||
     request.headers.get('accept')?.includes('text/html'));

  if (isAsset) {
    // Cache-first — static resources rarely change; serve instantly from cache
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(res => {
          if (res.ok || res.type === 'opaque') {
            caches.open(CACHE_NAME).then(c => c.put(request, res.clone()));
          }
          return res;
        });
      })
    );
  } else if (isNav) {
    // Network-first for page navigations; cache on success; offline page as last resort
    event.respondWith(
      fetch(request)
        .then(res => {
          if (res.ok) {
            caches.open(CACHE_NAME).then(c => c.put(request, res.clone()));
          }
          return res;
        })
        .catch(() =>
          caches.match(request).then(cached => {
            if (cached) return cached;
            return caches.match('/offline/');
          })
        )
    );
  }
});

// ── Background Sync: flush offline queues ────────────────────────────────────
const SW_DB = 'vp-offline';
const SW_DB_VERSION = 2;

function swOpenDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(SW_DB, SW_DB_VERSION);
    req.onupgradeneeded = e => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains('pending_expenses')) {
        db.createObjectStore('pending_expenses', { keyPath: 'id', autoIncrement: true });
      }
      if (!db.objectStoreNames.contains('pending_journals')) {
        db.createObjectStore('pending_journals', { keyPath: 'id', autoIncrement: true });
      }
    };
    req.onsuccess = e => resolve(e.target.result);
    req.onerror = e => reject(e.target.error);
  });
}

self.addEventListener('sync', event => {
  if (event.tag === 'flush-expenses') {
    event.waitUntil(swFlushExpenses());
  } else if (event.tag === 'flush-journals') {
    event.waitUntil(swFlushJournals());
  }
});

async function swFlushExpenses() {
  const db = await swOpenDb();
  const items = await new Promise((resolve, reject) => {
    const tx = db.transaction('pending_expenses', 'readonly');
    const req = tx.objectStore('pending_expenses').getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = e => reject(e.target.error);
  });

  for (const item of items) {
    try {
      const res = await fetch('/api/expenses/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': item.csrfToken || '',
        },
        credentials: 'include',
        body: JSON.stringify({
          day_pk: item.dayPk,
          description: item.description,
          category: item.category,
          amount: item.amount,
        }),
      });
      if (res.ok || res.status === 400) {
        const tx = db.transaction('pending_expenses', 'readwrite');
        tx.objectStore('pending_expenses').delete(item.id);
        await new Promise(r => { tx.oncomplete = r; });
      }
    } catch {
      break;
    }
  }

  const clients = await self.clients.matchAll({ type: 'window' });
  clients.forEach(c => c.postMessage({ type: 'queue-updated' }));
}

async function swFlushJournals() {
  const db = await swOpenDb();
  const items = await new Promise((resolve, reject) => {
    const tx = db.transaction('pending_journals', 'readonly');
    const req = tx.objectStore('pending_journals').getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = e => reject(e.target.error);
  });

  for (const item of items) {
    try {
      const res = await fetch('/api/journal/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': item.csrfToken || '',
        },
        credentials: 'include',
        body: JSON.stringify({ day_pk: item.dayPk, text: item.text }),
      });
      if (res.ok || res.status === 400) {
        const tx = db.transaction('pending_journals', 'readwrite');
        tx.objectStore('pending_journals').delete(item.id);
        await new Promise(r => { tx.oncomplete = r; });
      }
    } catch {
      break;
    }
  }

  const clients = await self.clients.matchAll({ type: 'window' });
  clients.forEach(c => c.postMessage({ type: 'journal-queue-updated' }));
}
