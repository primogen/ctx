(function () {
  const nav = document.getElementById('dashboard-nav');
  if (!nav) return;
  const storageKey = nav.dataset.navStorageKey;
  const defaultKeys = JSON.parse(nav.dataset.navDefaultKeys || '[]');
  const reset = document.getElementById('nav-reset');
  function links() { return Array.from(nav.querySelectorAll('a[data-nav-key]')); }
  function linkFor(key) { return nav.querySelector('a[data-nav-key="' + CSS.escape(key) + '"]'); }
  function applyOrder(order) {
    const valid = Array.isArray(order) ? order.filter(key => defaultKeys.includes(key)) : [];
    const merged = valid.concat(defaultKeys.filter(key => !valid.includes(key)));
    merged.forEach(key => { const link = linkFor(key); if (link) nav.appendChild(link); });
    if (reset) nav.appendChild(reset);
  }
  function saveOrder() {
    try { localStorage.setItem(storageKey, JSON.stringify(links().map(a => a.dataset.navKey))); } catch (_) {}
  }
  function clearDragState() {
    links().forEach(item => item.classList.remove('nav-drag-over', 'nav-dragging'));
  }
  function insertionTarget(clientX, clientY) {
    const candidates = links().filter(link => link !== dragged);
    if (!candidates.length) return reset;
    const sameRow = candidates.filter(link => {
      const rect = link.getBoundingClientRect();
      return clientY >= rect.top - 8 && clientY <= rect.bottom + 8;
    });
    const pool = sameRow.length ? sameRow : candidates;
    for (const link of pool) {
      const rect = link.getBoundingClientRect();
      if (clientX < rect.left + rect.width / 2) return link;
    }
    return reset;
  }
  function resetOrder() {
    try { localStorage.removeItem(storageKey); } catch (_) {}
    applyOrder(defaultKeys);
  }
  try { applyOrder(JSON.parse(localStorage.getItem(storageKey) || '[]')); } catch (_) { applyOrder(defaultKeys); }
  let dragged = null;
  links().forEach(link => {
    link.addEventListener('dragstart', event => {
      dragged = link;
      link.classList.add('nav-dragging');
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', link.dataset.navKey || '');
      }
    });
    link.addEventListener('dragend', () => {
      clearDragState();
      if (reset) nav.appendChild(reset);
      saveOrder();
      dragged = null;
    });
  });
  nav.addEventListener('dragover', event => {
    if (!dragged) return;
    event.preventDefault();
    const target = insertionTarget(event.clientX, event.clientY);
    links().forEach(item => item.classList.remove('nav-drag-over'));
    if (target && target !== dragged) {
      if (target.dataset && target.dataset.navKey) target.classList.add('nav-drag-over');
      nav.insertBefore(dragged, target);
      if (reset) nav.appendChild(reset);
    }
  });
  nav.addEventListener('drop', event => {
    if (!dragged) return;
    event.preventDefault();
    clearDragState();
    if (reset) nav.appendChild(reset);
    saveOrder();
  });
  if (reset) reset.addEventListener('click', resetOrder);
})();
