(function () {
  'use strict';

  const DB_NAME = 'vp-offline';
  const DB_VERSION = 2;
  const STORE = 'pending_expenses';

  function openDb() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
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

  function getCsrfToken() {
    const c = document.cookie.split(';').map(s => s.trim()).find(s => s.startsWith('csrftoken='));
    return c ? c.split('=')[1] : '';
  }

  async function queueExpense(dayPk, description, category, amount) {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).add({
        dayPk, description, category, amount,
        csrfToken: getCsrfToken(),
        queuedAt: Date.now(),
      });
      tx.oncomplete = resolve;
      tx.onerror = e => reject(e.target.error);
    });
  }

  async function getPendingCount() {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly');
      const req = tx.objectStore(STORE).count();
      req.onsuccess = () => resolve(req.result);
      req.onerror = e => reject(e.target.error);
    });
  }

  async function flushQueue() {
    if (!navigator.onLine) return;
    const db = await openDb();
    const items = await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly');
      const req = tx.objectStore(STORE).getAll();
      req.onsuccess = () => resolve(req.result);
      req.onerror = e => reject(e.target.error);
    });

    let synced = 0;
    for (const item of items) {
      try {
        const res = await fetch('/api/expenses/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': item.csrfToken || getCsrfToken(),
          },
          body: JSON.stringify({
            day_pk: item.dayPk,
            description: item.description,
            category: item.category,
            amount: item.amount,
          }),
        });
        if (res.ok || res.status === 400) {
          const tx = db.transaction(STORE, 'readwrite');
          tx.objectStore(STORE).delete(item.id);
          await new Promise(r => { tx.oncomplete = r; });
          if (res.ok) synced++;
        }
      } catch {
        break; // Network dropped mid-flush
      }
    }

    updateBadge();
    if (synced > 0) {
      showToast(`${synced} offline expense${synced > 1 ? 's' : ''} synced.`, 'success');
    }
  }

  function updateBadge() {
    getPendingCount().then(count => {
      const badge = document.getElementById('offline-pending-badge');
      if (!badge) return;
      if (count > 0) {
        badge.textContent = `${count} pending`;
        badge.style.display = 'inline-flex';
      } else {
        badge.style.display = 'none';
      }
    });
  }

  function updateOnlineStatus() {
    const ind = document.getElementById('offline-indicator');
    if (ind) ind.style.display = navigator.onLine ? 'none' : 'inline-flex';
    if (navigator.onLine) flushQueue();
  }

  function showToast(message, type) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const id = 'toast-' + Date.now();
    const cls = type === 'success' ? 'text-bg-success' : type === 'warning' ? 'text-bg-warning' : 'text-bg-secondary';
    container.insertAdjacentHTML('beforeend',
      `<div id="${id}" class="toast align-items-center ${cls} border-0" role="alert">
        <div class="d-flex">
          <div class="toast-body">${message}</div>
          <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
      </div>`
    );
    const el = document.getElementById(id);
    const toast = new bootstrap.Toast(el, { delay: 4000 });
    toast.show();
    el.addEventListener('hidden.bs.toast', () => el.remove());
  }

  // Event wiring
  window.addEventListener('online', updateOnlineStatus);
  window.addEventListener('offline', updateOnlineStatus);

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('message', e => {
      if (e.data?.type === 'queue-updated') updateBadge();
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    updateBadge();
    updateOnlineStatus();
  });

  // Public API
  window.VP = window.VP || {};
  window.VP.queueExpense = queueExpense;
  window.VP.flushQueue = flushQueue;
  window.VP.showToast = showToast;
  window.VP.updateBadge = updateBadge;
})();
