/* Màn làm bài khu Kiểm tra — templates/exam/play_vocab.html (T7.5), play_exam.html (T7.6).
 *
 * Chỉ là lớp tăng cường: tắt JS thì form POST + redirect vẫn chạy y như cũ.
 *   - Bài từ vựng ([data-exam-form]): bấm phương án là chấm luôn; gửi bằng fetch kèm
 *     header X-Exam-Partial, thay khối #exam-play — không tải lại trang.
 *   - Đề thi ([data-exam-autosubmit]): bấm phương án là gửi form thường (server quyết
 *     câu tiếp theo, khoá câu, đồng hồ).
 *   - Phím 1-9 chọn và gửi, Enter sang câu tiếp / xem kết quả.
 *   - Đồng hồ ([data-seconds-left]): đếm lùi từ số giây server trả; hết giờ gửi #exam-timeout.
 *   - Audio phát 1 lần (audio[data-audio-once]) ở chế độ Thi: ẩn thanh tua, khoá nút sau lần
 *     phát đầu, nhớ trong sessionStorage nên F5 không phát lại. File vẫn là URL công khai —
 *     đây là luật luyện tập, không phải chống gian lận (spec mục 4).
 *   - Ghi thời gian làm câu (ms) vào ô ẩn t.
 */
(function () {
  "use strict";
  var ROOT_ID = "exam-play";
  var busy = false;
  var shownAt = performance.now();

  function root() { return document.getElementById(ROOT_ID); }

  function stampTime(form) {
    var timer = form.querySelector("[data-exam-timer]");
    if (timer) timer.value = Math.round(performance.now() - shownAt);
  }

  // ---------------------------------------------------------------- bài từ vựng (fetch)
  function swapFrom(html, url) {
    var doc = new DOMParser().parseFromString(html, "text/html");
    var next = doc.getElementById(ROOT_ID);
    if (!next) return false;
    root().replaceWith(next);
    if (doc.title) document.title = doc.title;
    if (url) history.pushState(null, "", url);
    shownAt = performance.now();
    bind();
    var first = next.querySelector('input[name="option"], [data-enter]');
    if (first) first.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
    return true;
  }

  function submitPartial(form) {
    if (busy) return;
    if (!form.querySelector('input[name="option"]:checked')) return;
    busy = true;
    stampTime(form);
    var order = form.querySelector('input[name="order"]').value;
    fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Exam-Partial": "1" },
      credentials: "same-origin",
    })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        busy = false;
        if (!swapFrom(html, form.action + "?da=" + encodeURIComponent(order))) form.submit();
      })
      .catch(function () { busy = false; form.submit(); });
  }

  function follow(link) {
    if (busy) return;
    busy = true;
    fetch(link.href, { credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        busy = false;
        if (!swapFrom(html, link.href)) window.location.href = link.href;
      })
      .catch(function () { busy = false; window.location.href = link.href; });
  }

  // ---------------------------------------------------------------- đề thi (form thường)
  function submitPlain(form) {
    if (busy || !form.querySelector('input[name="option"]:checked')) return;
    busy = true;
    stampTime(form);
    form.submit();
  }

  function submit(form) {
    if (form.hasAttribute("data-exam-form")) submitPartial(form);
    else submitPlain(form);
  }

  function pad(n) { return (n < 10 ? "0" : "") + n; }

  function startTimer() {
    var box = document.querySelector("[data-seconds-left]");
    if (!box) return;
    var left = parseInt(box.getAttribute("data-seconds-left"), 10);
    var text = box.querySelector("[data-timer-text]");
    var deadline = Date.now() + left * 1000;  // đếm theo đồng hồ máy từ mốc server, không cộng dồn lệch
    function tick() {
      var s = Math.max(0, Math.round((deadline - Date.now()) / 1000));
      var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
      text.textContent = (h ? h + ":" + pad(m) : m) + ":" + pad(s % 60);
      box.classList.toggle("is-low", s <= 300);
      if (s === 0) {
        var form = document.getElementById("exam-timeout");
        if (form && !busy) { busy = true; form.submit(); }
        return;
      }
      setTimeout(tick, 1000);
    }
    tick();
  }

  function audioOnce() {
    var audio = document.querySelector("audio[data-audio-once]");
    if (!audio) return;
    var key = "exam-audio-played:" + audio.getAttribute("data-audio-once");
    var note = document.querySelector("[data-audio-note]");
    var played = false;
    try { played = sessionStorage.getItem(key) === "1"; } catch (e) { /* bộ nhớ bị chặn: vẫn cho phát */ }
    audio.controls = false;
    var wrap = document.createElement("div");
    wrap.className = "ex-player";
    wrap.innerHTML = '<button type="button" class="ex-play-btn">▶</button>' +
      '<div class="bar flex-1"><i class="s-mid"></i></div><span class="muted text-sm" data-audio-time></span>';
    audio.after(wrap);
    var btn = wrap.querySelector("button");
    btn.setAttribute("aria-label", audio.getAttribute("data-play-label") || "▶");
    var fill = wrap.querySelector("i"), time = wrap.querySelector("[data-audio-time]");
    function lock(msgKey) {
      btn.disabled = true;
      if (note && note.getAttribute(msgKey)) note.textContent = note.getAttribute(msgKey);
    }
    if (played) { lock("data-done"); fill.style.width = "100%"; return; }
    btn.addEventListener("click", function () {
      try { sessionStorage.setItem(key, "1"); } catch (e) { /* bỏ qua */ }
      btn.disabled = true;
      audio.play();
    });
    audio.addEventListener("timeupdate", function () {
      if (!audio.duration) return;
      fill.style.width = (audio.currentTime / audio.duration * 100) + "%";
      time.textContent = Math.floor(audio.currentTime) + "s / " + Math.floor(audio.duration) + "s";
    });
    audio.addEventListener("ended", function () { lock("data-done"); });
  }

  function bind() {
    var form = document.querySelector("[data-exam-form], [data-exam-autosubmit]");
    if (form) {
      var check = form.querySelector("[data-exam-check]");
      if (check) check.hidden = true;  // có JS: bấm phương án là gửi luôn
      form.addEventListener("change", function (e) {
        if (e.target.name === "option") submit(form);
      });
      form.addEventListener("submit", function (e) { e.preventDefault(); submit(form); });
    }
    var swap = document.querySelector("[data-exam-swap]");
    if (swap) {
      swap.addEventListener("click", function (e) { e.preventDefault(); follow(swap); });
    }
  }

  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute && e.target.getAttribute("data-confirm");
    if (msg && !busy && !window.confirm(msg)) e.preventDefault();
  }, true);

  document.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    var tag = e.target && e.target.tagName;
    if (tag === "TEXTAREA" || (tag === "INPUT" && e.target.type !== "radio")) return;
    var radios = document.querySelectorAll('[data-exam-form] input[name="option"], [data-exam-autosubmit] input[name="option"]');
    if (radios.length && /^[1-9]$/.test(e.key)) {
      var r = radios[parseInt(e.key, 10) - 1];
      if (r) { r.checked = true; e.preventDefault(); submit(r.form); }
      return;
    }
    if (e.key === "Enter" && !radios.length) {
      var go = document.querySelector("[data-enter]");
      if (go) { e.preventDefault(); go.click(); }
    }
  });

  // Nút Back của trình duyệt sau khi đã pushState: tải lại đúng URL đó.
  window.addEventListener("popstate", function () { window.location.reload(); });

  bind();
  startTimer();
  audioOnce();
})();
