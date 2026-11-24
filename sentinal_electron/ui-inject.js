// Injected by the Electron app into the Sentinel page after it loads (see main.js).
// Desktop-only conveniences. The page itself is unchanged.
//   Ctrl+N  new chat
//   Esc     close open side panels
//   window title follows the open chat
//   desktop notification when a reply finishes while the window is in the background
(function () {
  if (window.__sentinelInjected) return;
  window.__sentinelInjected = true;

  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'n') {
      e.preventDefault();
      if (typeof newChat === 'function') newChat();
      return;
    }
    if (e.key === 'Escape' && typeof closeDrawers === 'function') {
      closeDrawers();
    }
  });

  // Window title follows the open chat. The chat row also holds the rename (✎) and delete (×)
  // buttons, so those characters are removed from the name.
  function updateTitle() {
    var active = document.querySelector('#chathist .ch-item.active');
    var name = active ? String(active.textContent || '').split('\n')[0] : '';
    name = name.replace(/[✎×✏]/g, '').replace(/\s+/g, ' ').trim();
    document.title = name ? 'Sentinel V2 - ' + name.slice(0, 60) : 'Sentinel V2';
  }
  var hist = document.getElementById('chathist');
  if (hist) new MutationObserver(updateTitle).observe(hist, { subtree: true, childList: true, attributes: true, attributeFilter: ['class'] });
  updateTitle();

  // Notifications. Ignore the first 15 seconds, so restored history does not notify on launch.
  var armedAt = Date.now() + 15000;
  var msgs = document.getElementById('msgs');
  if (!msgs || !window.sentinelEnv || typeof window.sentinelEnv.notify !== 'function') return;

  // A reply's bubble is added before its text streams in, so wait until the text stops changing
  // for 1.5 seconds, then notify (only if the window is not focused).
  function watchReply(wrap, bubble) {
    var timer = null;
    var obs = new MutationObserver(schedule);
    function schedule() {
      clearTimeout(timer);
      timer = setTimeout(function () {
        obs.disconnect();
        if (document.hasFocus()) return;
        var text = (bubble.textContent || '').trim();
        if (text) window.sentinelEnv.notify('Sentinel replied', text);
      }, 1500);
    }
    obs.observe(wrap, { childList: true, subtree: true, characterData: true });
    schedule();
  }

  var observer = new MutationObserver(function (records) {
    if (Date.now() < armedAt) return;
    records.forEach(function (rec) {
      rec.addedNodes.forEach(function (node) {
        if (!(node instanceof HTMLElement)) return;
        if (node.id === '_t' || node.classList.contains('user')) return;   // typing dots and the user's own messages
        var bubble = node.querySelector('.bubble');
        if (bubble) watchReply(node, bubble);
      });
    });
  });
  observer.observe(msgs, { childList: true });
  console.log('[sentinel] desktop notifications armed (15s warm-up)');
})();
