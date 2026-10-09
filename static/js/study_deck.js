// Học liền mạch — spec.md T4.3 (06/10/2026).
//
// Trước đây: chấm thẻ = POST study/review/<id>/ -> 302 -> GET study/, người học
// chờ ~2,5 s mới thấy thẻ kế. Giờ study_view nhúng sẵn bộ thẻ vào trang
// (<script type="application/json" id="study-deck">, views._study_deck). File
// này:
//   1. Chọn thẻ kế theo ĐÚNG luật của views._next_queue_word (thẻ vừa hoàn tác
//      -> hàng đợi -> thẻ đang học tới hạn sớm nhất) và hiện NGAY.
//   2. Xếp lệnh chấm / hoàn tác vào hàng chờ, gửi ngầm theo LÔ tới
//      views.study_sync_view — một request mỗi lúc (session nằm trong DB, hai
//      request ghi cùng lúc sẽ đè nhau). Server trả trạng thái mới của thẻ
//      (còn ở bước học không, tới hạn lúc nào) để xếp lần gặp lại.
//   3. Lỗi mạng: thử lại 1 s -> 3 s -> 10 s, báo "mất kết nối" nhưng vẫn học
//      tiếp; hàng chờ lưu localStorage, đóng tab thì gửi nốt bằng sendBeacon.
//      Mỗi lệnh có `seq` — server bỏ qua lệnh đã xử lý, gửi trùng không sao.
//   4. Hết thẻ: đợi hàng chờ trống rồi xin server phần tổng kết như cũ
//      (GET study/ kèm X-Card-Partial).
//
// Không có #study-deck (SC04 theo chủ đề, trình duyệt cũ) thì file này không
// làm gì — main.js chạy y như trước. Phím tắt / vuốt / lật thẻ vẫn ở main.js:
// chúng bấm nút chấm, ta chặn sự kiện submit ở pha capture trước main.js.
// Mọi chữ hiển thị đến từ server (deck.text, template) — không viết cứng ở đây.
(function () {
  "use strict";

  if (!window.fetch || !window.FormData || !document.querySelector) { return; }

  var PARTIAL_HEADER = "X-Card-Partial";
  var STORAGE_PREFIX = "bjt.study.pending.";
  var RETRY_DELAYS = [1000, 3000, 10000];   // sau lần cuối: cứ 10 s thử lại
  var OFFLINE_AFTER = 3;                    // thất bại liên tiếp -> hiện thanh báo
  var PREFETCH_AHEAD = 10;                  // còn ≤ 10 thẻ đã tải thì tải thêm
  var CARDS_PER_FETCH = 50;                 // = views.DECK_BATCH
  var UNDO_MAX = 20;                        // = views.UNDO_MAX

  var deck = null;          // trạng thái phiên đang chạy (null = không có bộ thẻ)
  var lastSubmitter = null;

  function panel() { return document.querySelector("[data-card-panel]"); }
  function q(sel) { var p = panel(); return p ? p.querySelector(sel) : null; }
  function fill(template, values) {
    return Object.keys(values).reduce(function (text, key) {
      return text.split("{" + key + "}").join(String(values[key]));
    }, template || "");
  }
  function now() { return Date.now() + (deck ? deck.clockSkew : 0); }
  function parseTime(iso) { var t = Date.parse(iso); return isNaN(t) ? 0 : t; }
  function remove(list, id) {
    var i = list.indexOf(id);
    if (i !== -1) { list.splice(i, 1); }
  }
  function storage() {
    try { return window.localStorage; } catch (e) { return null; }
  }

  // -------------------------------------------------------------------------
  // Khởi tạo từ #study-deck (lần tải trang đầu, hoặc khi panel được thay mới)
  // -------------------------------------------------------------------------
  function readDeck() {
    var node = q("#study-deck");
    if (!node || node.getAttribute("data-used")) { return null; }
    node.setAttribute("data-used", "1");
    try { return JSON.parse(node.textContent); } catch (e) { return null; }
  }

  function start() {
    var data = readDeck();
    if (!data) {
      // Panel mới không có bộ thẻ (màn tổng kết, SC04...) -> thôi điều khiển.
      if (!q("#study-deck")) { deck = null; }
      return;
    }
    var learning = {};
    data.learning.forEach(function (row) { learning[row.id] = row.due ? parseTime(row.due) : 0; });
    var token = q('.grade-form input[name="csrfmiddlewaretoken"]');
    deck = {
      session: data.session,
      seq: data.seq,                 // seq của lệnh cuối cùng đã tạo
      acked: data.seq,               // seq cuối cùng server đã xử lý
      clockSkew: parseTime(data.now) - Date.now(),
      total: data.total,
      touch: data.touch,
      queue: data.queue.slice(),
      learning: learning,            // id -> due (ms) | null = chờ server trả lời
      seen: {},
      cards: data.cards,
      qualities: data.qualities,
      urls: data.urls,
      text: data.text,
      csrf: token ? token.value : "",
      current: data.current,
      forced: null,
      undoStack: [],                 // ảnh chụp trạng thái để hoàn tác tại chỗ
      serverUndo: data.undo,         // mục hoàn tác trên cùng mà server biết
      outbox: [],                    // lệnh chưa được server xác nhận
      inflight: null,                // lô đang gửi
      pendingByCard: {},             // id -> số lệnh chưa xác nhận
      failures: 0,
      retryTimer: null,
      loadingCards: false,
      missing: {},
      waiting: false,
      finishing: false,
      afterFlush: []
    };
    data.seen.forEach(function (id) { deck.seen[id] = true; });

    // Lệnh còn sót từ lần trước (mất mạng / đóng tab) mà server chưa nhận:
    // gửi nốt rồi tải lại màn học theo trạng thái mới của server.
    var leftover = loadOutbox().filter(function (op) { return op.seq > data.seq; });
    if (leftover.length) {
      deck.outbox = leftover;
      deck.seq = leftover[leftover.length - 1].seq;
      leftover.forEach(function (op) { bump(op.vocab, 1); });
      setBusy(true);
      deck.afterFlush.push(reloadPanel);
      flush();
      return;
    }
    saveOutbox();
    prefetch();
  }

  // -------------------------------------------------------------------------
  // Chọn thẻ kế — bản sao của views._next_queue_word
  // -------------------------------------------------------------------------
  function pickNext() {
    if (deck.forced !== null) {
      return deck.cards[deck.forced] ? { id: deck.forced, ahead: 0 } : { need: true };
    }
    for (var i = 0; i < deck.queue.length; i++) {
      var id = deck.queue[i];
      if (deck.cards[id]) { return { id: id, ahead: 0 }; }
      if (!deck.missing[id]) { return { need: true }; }
    }
    var known = [];
    var pending = false;
    Object.keys(deck.learning).forEach(function (key) {
      var due = deck.learning[key];
      if (due === null) { pending = true; } else { known.push({ id: Number(key), due: due }); }
    });
    known.sort(function (a, b) { return (a.due - b.due) || (a.id - b.id); });
    var best = known[0];
    var t = now();
    if (best && best.due <= t) {
      return deck.cards[best.id] ? { id: best.id, ahead: 0 } : { need: true };
    }
    // Thẻ vừa chấm chưa biết lúc nào quay lại: có thể nó tới hạn trước `best`.
    if (pending) { return { wait: true }; }
    if (best) {
      if (!deck.cards[best.id]) { return { need: true }; }
      return { id: best.id, ahead: Math.max(1, Math.round((best.due - t) / 60000)) };
    }
    return null;
  }

  function advance() {
    if (!deck) { return; }
    var next = pickNext();
    if (next === null) { finish(); return; }
    if (next.need || next.wait) {
      deck.waiting = true;
      setBusy(true);
      if (next.need) { prefetch(true); } else { flush(); }
      return;
    }
    deck.waiting = false;
    setBusy(false);
    render(next.id, next.ahead);
    prefetch();
  }

  function finish() {
    deck.finishing = true;
    setBusy(true);
    whenFlushed(reloadPanel);
  }

  // -------------------------------------------------------------------------
  // Vẽ thẻ — chỉ đổi nội dung, khung trang giữ nguyên
  // -------------------------------------------------------------------------
  function render(id, ahead) {
    var card = deck.cards[id];
    var root = q("[data-study-card]");
    if (!root || !card) { return; }
    deck.current = id;

    root.classList.remove("is-revealed");
    var flash = root.querySelector("[data-flashcard]");
    flash.classList.remove("is-flipped", "is-swiping", "swipe-left", "swipe-right", "swipe-up");
    flash.style.transform = "";
    flash.querySelector(".jp").textContent = card.word;
    flash.querySelector(".reading").textContent = card.reading;
    flash.querySelector(".meaning").textContent = card.meaning;

    var stateTag = root.querySelector("[data-state-tag]");
    stateTag.textContent = deck.text.states[card.state] || card.state;
    stateTag.classList.toggle("level", card.state !== "review");
    var repeat = root.querySelector("[data-repeat-tag]");
    if (repeat) { repeat.hidden = !deck.seen[id]; }

    root.querySelector("[data-card-extra]").innerHTML = card.extra;

    var form = root.querySelector(".grade-form");
    form.action = deck.urls.review.replace(/\/0\/$/, "/" + id + "/");
    form.querySelectorAll("[data-grade-key]").forEach(function (button) {
      var delay = button.querySelector(".btn-grade-delay");
      if (delay && card.previews) { delay.textContent = card.previews[button.value] || ""; }
    });

    var aheadNote = root.querySelector("[data-ahead-note]");
    if (aheadNote) {
      aheadNote.hidden = !ahead;
      aheadNote.textContent = ahead ? fill(deck.text.ahead, { minutes: ahead }) : "";
    }

    var discussion = root.querySelector(".study-discussion");
    if (discussion) {
      discussion.open = false;
      root.querySelector("[data-discussion-toggle]").textContent =
        fill(deck.text.discussion, { count: card.comments });
      var body = root.querySelector("[data-discussion-body]");
      body.innerHTML = "";
      body.setAttribute("data-loaded", "");
    }

    renderProgress();
    renderUndo();
    var p = panel();
    p.focus({ preventScroll: true });
    if (p.getBoundingClientRect().top < 0) { p.scrollIntoView({ block: "start" }); }
  }

  // Cùng công thức với views._progress_numbers.
  function renderProgress() {
    var ids = {};
    deck.queue.forEach(function (id) { ids[id] = true; });
    Object.keys(deck.learning).forEach(function (id) { ids[id] = true; });
    var remaining = Object.keys(ids).length;
    var total = Math.max(deck.total || 0, remaining, 1);
    var done = total - remaining;
    var seen = Math.min(Math.max(Object.keys(deck.seen).length, done), total);
    var text = q(".study-head-text");
    if (text) { text.textContent = fill(deck.text.progress, { seen: seen, total: total, done: done }); }
    var bar = q(".study-progress");
    if (bar) {
      bar.querySelector(".seen").style.width = Math.round(seen * 100 / total) + "%";
      bar.querySelector(".done").style.width = Math.round(done * 100 / total) + "%";
    }
  }

  function renderUndo() {
    var form = q("[data-undo-form]");
    if (!form) { return; }
    var top = deck.undoStack.length ? deck.undoStack[deck.undoStack.length - 1] : deck.serverUndo;
    form.hidden = !top;
    form.querySelector("[data-undo-text]").textContent = top ? fill(deck.text.undo, { word: top.word }) : "";
  }

  function setBusy(busy) {
    var p = panel();
    if (p) { p.classList.toggle("is-busy", busy); }
  }

  function setOffline(offline) {
    var note = q("[data-sync-offline]");
    if (note) { note.hidden = !offline; }
  }

  // -------------------------------------------------------------------------
  // Chấm / hoàn tác tại chỗ
  // -------------------------------------------------------------------------
  // Ảnh chụp CHỈ của thẻ sắp chấm — giống mục hoàn tác của server
  // (views._grade: in_queue / in_learning / first). Thẻ khác không đụng tới,
  // để kết quả server đã trả cho chúng không bị ảnh chụp cũ đè mất.
  function snapshot(id) {
    var card = deck.cards[id];
    return {
      vocab: id,
      word: card ? card.word : "",
      state: card ? card.state : null,
      inQueue: deck.queue.indexOf(id) !== -1,
      inLearning: Object.prototype.hasOwnProperty.call(deck.learning, id),
      due: deck.learning[id],
      seen: !!deck.seen[id]
    };
  }

  function grade(code) {
    var id = deck.current;
    deck.undoStack.push(snapshot(id));
    if (deck.undoStack.length > UNDO_MAX) { deck.undoStack.shift(); }

    // = views._grade_word
    remove(deck.queue, id);
    if (deck.touch) {
      deck.learning[id] = null;        // server sẽ báo còn ở bước học không
    } else if (deck.qualities[code] < 3) {
      deck.queue.push(id);             // ôn thêm: Quên -> xuống cuối hàng đợi
    }
    deck.seen[id] = true;
    deck.forced = null;
    enqueue({ op: "grade", vocab: id, quality: code });
    advance();
  }

  function undo(form) {
    var entry = deck.undoStack.pop();
    if (!entry) {
      // Lần chấm cần hoàn tác xảy ra trước khi tải trang (không có ảnh chụp)
      // -> để server làm như cũ: gửi form hoàn tác rồi nhận lại cả panel.
      if (!deck.serverUndo) { return; }
      setBusy(true);
      whenFlushed(function () {
        deck = null;
        setBusy(false);   // main.js bỏ qua form khi panel đang bận
        if (form.requestSubmit) { form.requestSubmit(); } else { form.submit(); }
      });
      return;
    }
    // = views._restore_study_state
    var id = entry.vocab;
    remove(deck.queue, id);
    if (entry.inQueue) { deck.queue.unshift(id); }
    if (entry.inLearning) { deck.learning[id] = entry.due; } else { delete deck.learning[id]; }
    if (entry.seen) { deck.seen[id] = true; } else { delete deck.seen[id]; }
    if (deck.cards[id] && entry.state) { deck.cards[id].state = entry.state; }
    deck.forced = id;
    deck.serverUndo = null;   // server trả mục mới khi xử lý xong lệnh này
    enqueue({ op: "undo", vocab: id });
    advance();
  }

  // -------------------------------------------------------------------------
  // Hàng chờ gửi lên server
  // -------------------------------------------------------------------------
  function bump(id, delta) {
    deck.pendingByCard[id] = (deck.pendingByCard[id] || 0) + delta;
    if (deck.pendingByCard[id] <= 0) { delete deck.pendingByCard[id]; }
  }

  function enqueue(op) {
    deck.seq += 1;
    op.seq = deck.seq;
    deck.outbox.push(op);
    bump(op.vocab, 1);
    saveOutbox();
    flush();
  }

  function payload(ops) {
    var body = new FormData();
    body.append("csrfmiddlewaretoken", deck.csrf);
    body.append("payload", JSON.stringify({ session: deck.session, ops: ops }));
    return body;
  }

  function flush() {
    if (!deck || deck.inflight || deck.retryTimer) { return; }
    if (!deck.outbox.length) { runAfterFlush(); return; }
    var batch = deck.outbox.slice();
    var mine = deck;
    deck.inflight = batch;
    fetch(deck.urls.sync, {
      method: "POST", body: payload(batch), credentials: "same-origin",
      headers: { "X-Requested-With": "fetch" }
    })
      .then(function (response) {
        if (response.status === 401) {
          return response.json().then(function (data) { window.location.href = data.login; return null; });
        }
        if (response.status === 409) { clearOutbox(mine); window.location.reload(); return null; }
        if (!response.ok) { throw new Error("HTTP " + response.status); }
        return response.json();
      })
      .then(function (data) {
        if (!data || deck !== mine) { return; }
        acknowledge(batch, data);
      })
      .catch(function () {
        if (deck !== mine) { return; }
        deck.inflight = null;
        deck.failures += 1;
        if (deck.failures >= OFFLINE_AFTER) { setOffline(true); }
        var delay = RETRY_DELAYS[Math.min(deck.failures - 1, RETRY_DELAYS.length - 1)];
        deck.retryTimer = setTimeout(function () {
          if (deck !== mine) { return; }
          deck.retryTimer = null;
          flush();
        }, delay);
      });
  }

  function acknowledge(batch, data) {
    deck.inflight = null;
    deck.failures = 0;
    setOffline(false);
    deck.outbox = deck.outbox.slice(batch.length);
    batch.forEach(function (op) { bump(op.vocab, -1); });
    deck.acked = data.seq;
    deck.clockSkew = parseTime(data.now) - Date.now();
    deck.serverUndo = data.undo;
    saveOutbox();

    if (data.resync) {
      // Server và trang lệch nhau (vd hoàn tác ở tab khác) -> nghe server.
      clearOutbox(deck);
      deck.outbox = [];
      setBusy(true);
      reloadPanel();
      return;
    }
    (data.missing || []).forEach(dropCard);
    Object.keys(data.cards || {}).forEach(function (key) {
      var id = Number(key);
      var status = data.cards[key];
      // Thẻ còn lệnh mới hơn đang chờ (chấm lại / hoàn tác) -> kết quả này đã cũ.
      if (deck.pendingByCard[id]) { return; }
      var card = deck.cards[id];
      if (card) {
        card.state = status.state;
        if (status.previews) { card.previews = status.previews; }
      }
      if (status.learning) {
        deck.learning[id] = status.due ? parseTime(status.due) : 0;
      } else {
        delete deck.learning[id];
      }
    });
    if (!deck.waiting && !deck.finishing) { renderProgress(); renderUndo(); }

    if (deck.outbox.length) { flush(); } else { runAfterFlush(); }
    if (deck && deck.waiting) { advance(); }
  }

  function whenFlushed(callback) {
    deck.afterFlush.push(callback);
    flush();
  }

  function runAfterFlush() {
    if (!deck || deck.outbox.length || deck.inflight) { return; }
    var callbacks = deck.afterFlush;
    deck.afterFlush = [];
    callbacks.forEach(function (callback) { callback(); });
  }

  function dropCard(id) {
    remove(deck.queue, id);
    delete deck.learning[id];
    delete deck.cards[id];
    deck.missing[id] = true;
    if (deck.forced === id) { deck.forced = null; }
  }

  // localStorage: chỉ là lưới an toàn khi mất mạng / đóng tab.
  function storageKey(session) { return STORAGE_PREFIX + session; }
  function saveOutbox() {
    var store = storage();
    if (!store || !deck) { return; }
    try {
      if (deck.outbox.length) {
        store.setItem(storageKey(deck.session), JSON.stringify(deck.outbox));
      } else {
        store.removeItem(storageKey(deck.session));
      }
    } catch (e) { /* bỏ qua */ }
  }
  function loadOutbox() {
    var store = storage();
    if (!store) { return []; }
    try {
      var ops = JSON.parse(store.getItem(storageKey(deck.session)) || "[]");
      return Array.isArray(ops) ? ops : [];
    } catch (e) { return []; }
  }
  function clearOutbox(state) {
    var store = storage();
    if (!store) { return; }
    try { store.removeItem(storageKey(state.session)); } catch (e) { /* bỏ qua */ }
  }

  // -------------------------------------------------------------------------
  // Tải thêm thẻ / khu thảo luận / cả panel
  // -------------------------------------------------------------------------
  function prefetch(urgent) {
    if (!deck || deck.loadingCards) { return; }
    var wanted = [];
    if (deck.forced !== null) { wanted.push(deck.forced); }
    var ahead = 0;
    deck.queue.forEach(function (id) {
      if (deck.cards[id]) { ahead += 1; } else if (!deck.missing[id]) { wanted.push(id); }
    });
    Object.keys(deck.learning).forEach(function (key) { wanted.push(Number(key)); });
    wanted = wanted.filter(function (id, i) {
      return !deck.cards[id] && !deck.missing[id] && wanted.indexOf(id) === i;
    });
    if (!wanted.length || (!urgent && ahead > PREFETCH_AHEAD)) { return; }
    wanted = wanted.slice(0, CARDS_PER_FETCH);
    var mine = deck;
    deck.loadingCards = true;
    fetch(deck.urls.cards + "?ids=" + wanted.join(","), {
      credentials: "same-origin", headers: { "X-Requested-With": "fetch" }
    })
      .then(function (response) {
        if (!response.ok) { throw new Error("HTTP " + response.status); }
        return response.json();
      })
      .then(function (data) {
        if (deck !== mine) { return; }
        deck.loadingCards = false;
        wanted.forEach(function (id) {
          if (data.cards[id]) { deck.cards[id] = data.cards[id]; } else { dropCard(id); }
        });
        if (deck.waiting) { advance(); }
      })
      .catch(function () {
        if (deck !== mine) { return; }
        deck.loadingCards = false;
        if (deck.waiting) { setTimeout(function () { if (deck === mine) { prefetch(true); } }, 3000); }
      });
  }

  function loadDiscussion(details) {
    var body = details.querySelector("[data-discussion-body]");
    if (!deck || !body || body.getAttribute("data-loaded") === String(deck.current)) { return; }
    var id = deck.current;
    body.setAttribute("data-loaded", String(id));
    fetch(deck.urls.discussion.replace(/\/0\/discussion\/$/, "/" + id + "/discussion/"), {
      credentials: "same-origin", headers: { "X-Requested-With": "fetch" }
    })
      .then(function (response) {
        if (!response.ok) { throw new Error("HTTP " + response.status); }
        return response.text();
      })
      .then(function (html) {
        if (deck && deck.current === id) { body.innerHTML = html; }
      })
      .catch(function () { body.setAttribute("data-loaded", ""); });
  }

  // Xin server vẽ lại cả panel (tổng kết cuối phiên / lệch trạng thái).
  function reloadPanel() {
    var headers = {};
    headers[PARTIAL_HEADER] = "1";
    var url = deck ? deck.urls.panel : window.location.pathname;
    fetch(url, { credentials: "same-origin", headers: headers })
      .then(function (response) {
        if (!response.ok || response.headers.get(PARTIAL_HEADER) !== "1") {
          window.location.href = response.url || url;
          return;
        }
        return response.text().then(function (html) {
          var p = panel();
          p.innerHTML = html;      // MutationObserver dưới đây gọi start()
          p.classList.remove("is-busy");
          p.focus({ preventScroll: true });
        });
      })
      .catch(function () { window.location.href = url; });
  }

  // -------------------------------------------------------------------------
  // Nối với trang
  // -------------------------------------------------------------------------
  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("button");
    if (button && button.type === "submit") { lastSubmitter = button; }
  }, true);

  // Pha capture: chạy TRƯỚC listener submit của main.js (gắn ở #card-panel).
  document.addEventListener("submit", function (event) {
    if (!deck) { return; }
    var form = event.target;
    var p = panel();
    if (!p || !p.contains(form)) { return; }

    if (form.classList.contains("grade-form")) {
      event.preventDefault();
      event.stopPropagation();
      if (p.classList.contains("is-busy")) { return; }
      var submitter = event.submitter ||
        (lastSubmitter && form.contains(lastSubmitter) ? lastSubmitter : null);
      grade(submitter && submitter.value ? submitter.value : "nho");
      return;
    }
    if (form.hasAttribute("data-undo-form")) {
      event.preventDefault();
      event.stopPropagation();
      if (!p.classList.contains("is-busy")) { undo(form); }
      return;
    }
    // Form khác (kết thúc phiên, bình luận...): gửi hết lệnh đang chờ trước,
    // không thì server chưa biết các lần chấm cuối.
    if (deck.outbox.length || deck.inflight) {
      event.preventDefault();
      event.stopPropagation();
      setBusy(true);
      whenFlushed(function () { form.submit(); });
    }
  }, true);

  // Khu thảo luận: tải bình luận khi mở (sự kiện toggle không nổi bọt).
  document.addEventListener("toggle", function (event) {
    var details = event.target;
    if (deck && details.classList && details.classList.contains("study-discussion") && details.open) {
      loadDiscussion(details);
    }
  }, true);

  window.addEventListener("online", function () {
    if (deck && deck.retryTimer) {
      clearTimeout(deck.retryTimer);
      deck.retryTimer = null;
      flush();
    }
  });

  // Đóng tab / sang trang khác khi còn lệnh chưa gửi: sendBeacon gửi nốt.
  // Lô đang bay thì để nó chạy (gửi song song sẽ ghi đè session) — nếu nó
  // không tới được, localStorage còn giữ và lần mở sau sẽ gửi lại.
  window.addEventListener("pagehide", function () {
    if (!deck || deck.inflight || !deck.outbox.length || !navigator.sendBeacon) { return; }
    try { navigator.sendBeacon(deck.urls.sync, payload(deck.outbox)); } catch (e) { /* bỏ qua */ }
  });

  function boot() {
    var p = panel();
    if (!p) { return; }
    start();
    // main.js thay nội dung panel (tổng kết -> "Ôn thêm"...) -> bộ thẻ mới.
    new MutationObserver(function () { start(); }).observe(p, { childList: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
}());
