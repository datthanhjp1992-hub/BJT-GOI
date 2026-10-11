/* Màn làm bài khu Kiểm tra (templates/exam/play_vocab.html) — spec T7.5.
 *
 * Chỉ là lớp tăng cường: tắt JS thì form POST + redirect vẫn chạy y như cũ.
 *   - Bấm một phương án = gửi luôn (không cần nút "Kiểm tra").
 *   - Phím 1-9 chọn và gửi, Enter sang câu tiếp / xem kết quả.
 *   - Gửi bằng fetch kèm header X-Exam-Partial: server trả trang phản hồi,
 *     JS thay khối #exam-play — không tải lại cả trang. Lỗi mạng -> gửi form thường.
 *   - Ghi thời gian làm câu (ms) vào ô ẩn t.
 */
(function () {
  "use strict";
  var ROOT_ID = "exam-play";
  var busy = false;
  var shownAt = performance.now();

  function root() { return document.getElementById(ROOT_ID); }

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

  function submitForm(form) {
    if (busy) return;
    var choice = form.querySelector('input[name="option"]:checked');
    if (!choice) return;
    busy = true;
    var timer = form.querySelector("[data-exam-timer]");
    if (timer) timer.value = Math.round(performance.now() - shownAt);
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

  function bind() {
    var form = document.querySelector("[data-exam-form]");
    if (form) {
      var check = form.querySelector("[data-exam-check]");
      if (check) check.hidden = true;  // có JS: bấm phương án là chấm luôn
      form.addEventListener("change", function (e) {
        if (e.target.name === "option") submitForm(form);
      });
      form.addEventListener("submit", function (e) { e.preventDefault(); submitForm(form); });
    }
    var swap = document.querySelector("[data-exam-swap]");
    if (swap) {
      swap.addEventListener("click", function (e) { e.preventDefault(); follow(swap); });
    }
  }

  document.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    var tag = e.target && e.target.tagName;
    if (tag === "TEXTAREA" || (tag === "INPUT" && e.target.type !== "radio")) return;
    var radios = document.querySelectorAll('[data-exam-form] input[name="option"]');
    if (radios.length && /^[1-9]$/.test(e.key)) {
      var r = radios[parseInt(e.key, 10) - 1];
      if (r) { r.checked = true; e.preventDefault(); submitForm(r.form); }
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
})();
