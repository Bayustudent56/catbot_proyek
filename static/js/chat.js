(() => {
  const app = document.getElementById('chatApp');
  const body = document.getElementById('chatBody');
  const form = document.getElementById('composer');
  const input = document.getElementById('msgInput');
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const convList = document.getElementById('convList');
  let convId = app.dataset.convId || null;
  let busy = false;

  const scrollDown = () => { body.scrollTop = body.scrollHeight; };

  function addMessage(sender, text, time, urgent = false) {
    const wrap = document.createElement('div');
    wrap.className = `msg msg-${sender}${urgent ? ' urgent' : ''}`;
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = text; // textContent: aman dari XSS
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.textContent = `${sender === 'user' ? 'Kamu' : 'CatBot'} · ${time}`;
    wrap.append(bubble, meta);
    body.appendChild(wrap);
    scrollDown();
    return wrap;
  }

  function showTyping() {
    const el = document.createElement('div');
    el.className = 'msg msg-bot typing';
    el.innerHTML = '<div class="bubble"><span></span><span></span><span></span></div>';
    body.appendChild(el);
    scrollDown();
    return el;
  }

  const nowLabel = () => new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }).replace(':', '.');

  async function send(text) {
    text = text.trim();
    if (!text || busy) return;
    busy = true;
    addMessage('user', text, nowLabel());
    input.value = '';
    const typing = showTyping();
    try {
      const res = await fetch(app.dataset.sendUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ message: text, cat_id: app.dataset.catId || null, conversation_id: convId }),
      });
      const data = await res.json();
      typing.remove();
      if (!res.ok) throw new Error(data.error || 'Gagal mengirim pesan.');
      addMessage('bot', data.reply, data.time, data.urgent);
      if (data.conversation_id) syncConversation(data);
    } catch (err) {
      typing.remove();
      addMessage('bot', `⚠️ ${err.message}`, nowLabel());
    } finally {
      busy = false;
      input.focus();
    }
  }

  // ---- Sidebar riwayat: tambah percakapan baru / naikkan ke atas -------------------
  function buildConvItem(id, title) {
    const item = document.createElement('div');
    item.className = 'conv on';
    item.dataset.convId = id;

    const link = document.createElement('a');
    link.href = `${convList.dataset.chatUrl}?c=${id}`;
    const icon = document.createElement('i');
    icon.className = 'bi bi-chat-left-text';
    const txt = document.createElement('span');
    const strong = document.createElement('strong');
    strong.textContent = title;
    const small = document.createElement('small');
    small.textContent = 'Hari ini';
    txt.append(strong, small);
    link.append(icon, txt);

    const del = document.createElement('form');
    del.method = 'post';
    del.className = 'conv-del';
    del.action = convList.dataset.deleteUrl.replace('/0/', `/${id}/`);
    del.innerHTML = '<input type="hidden" name="csrf_token"><input type="hidden" name="back" value="">'
      + '<button type="submit" title="Hapus percakapan ini"><i class="bi bi-trash3"></i></button>';
    del.elements.csrf_token.value = csrf;

    item.append(link, del);
    return item;
  }

  function syncConversation(data) {
    if (!convId) {
      convId = String(data.conversation_id);
      history.replaceState(null, '', `${location.pathname}?c=${convId}`); // URL bisa dibuka lagi
    }
    if (!convList) return;
    convList.querySelectorAll('.conv.on').forEach(c => c.classList.remove('on'));
    let item = convList.querySelector(`[data-conv-id="${convId}"]`);
    if (!item) item = buildConvItem(convId, data.title);
    item.classList.add('on');
    convList.prepend(item);
    const empty = convList.querySelector('.conv-empty');
    if (empty) empty.classList.add('d-none');
    const clearAll = document.getElementById('clearAllBtn');
    if (clearAll) clearAll.classList.remove('d-none');
  }

  // Hapus satu percakapan: konfirmasi dulu, lalu kirim halaman saat ini agar tidak berpindah
  document.addEventListener('submit', (e) => {
    if (!e.target.matches('.conv-del')) return;
    if (!confirm('Hapus percakapan ini? Tindakan ini tidak bisa dibatalkan.')) { e.preventDefault(); return; }
    e.target.elements.back.value = location.pathname + location.search;
  });

  form.addEventListener('submit', (e) => { e.preventDefault(); send(input.value); });
  document.querySelectorAll('.chip').forEach(chip =>
    chip.addEventListener('click', () => send(chip.dataset.message)));

  scrollDown();
})();
