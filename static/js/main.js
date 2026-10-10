// Hành vi front-end dùng chung cho mọi template.
// Không framework, không build step: file này được base.html nạp ở cuối <body>.

// ---------------------------------------------------------------------------
// 1. Màn học (SC04 — templates/learning/_card_panel.html), spec.md Phase 1.
//
//    a) Hiện thẻ 2 bước: bấm thẻ / nút "Hiện đáp án" / phím Space -> thêm
//       .is-revealed vào [data-study-card] (lộ nghĩa, ví dụ, 4 nút chấm).
//    b) Chấm không tải lại trang: form [data-card-ajax] gửi bằng fetch() kèm
//       header X-Card-Partial: 1; server trả riêng phần thẻ (views._render_card)
//       và ta thay bên trong #card-panel. Lỗi mạng -> gửi form kiểu thường.
//    c) Phím tắt: Space lật · 1-4 chấm · Z hoàn tác · E ví dụ · ? bảng phím tắt.
//    d) Vuốt trên điện thoại: trái = Quên rồi, phải = Nhớ, lên = Dễ (khi đã lật thẻ).
//    e) Chế độ tập trung: nút ☰ mở/ẩn sidebar, nhớ trong localStorage.
//    f) Câu báo sau mỗi lần chấm (T6.4) — từ data-toast của nút vừa bấm.
//       ĐANG TẠM TẮT (10/10/2026) — xem initStudyScreen().
//    g) Hướng dẫn cử chỉ ← → ↑ ở 3 lần mở màn học đầu trên điện thoại (T6.6).
//
//    Mọi listener gắn ở document / #card-panel (event delegation) vì nội dung
//    thẻ bị thay mới sau mỗi lần chấm. Tắt JS: form gửi thường, mọi thứ hiện
//    sẵn (CSS chỉ ẩn mặt sau khi <html> có class "js").
// ---------------------------------------------------------------------------
var CARD_PARTIAL_HEADER = "X-Card-Partial";
var SWIPE_THRESHOLD = 80;          // px — vuốt ngắn hơn coi như chạm nhầm
var SIDEBAR_STORAGE_KEY = "bjt.focus.sidebar";
var suppressCardClick = false;     // vừa vuốt xong thì bỏ qua click "lật thẻ"

function studyScreen() { return document.querySelector("[data-study-card]"); }
function cardPanel() { return document.querySelector("[data-card-panel]"); }
function isRevealed(screen) { return !!(screen && screen.classList.contains("is-revealed")); }
function isPanelBusy() {
  var panel = cardPanel();
  return !!(panel && panel.classList.contains("is-busy"));
}

function revealCard() {
  var screen = studyScreen();
  if (!screen || isRevealed(screen)) { return false; }
  screen.classList.add("is-revealed");
  var card = screen.querySelector("[data-flashcard]");
  if (card) { card.classList.add("is-flipped"); }
  maybeShowSwipeCoach();
  return true;
}

// Hướng dẫn cử chỉ lần đầu (spec.md T6.6): sau lần LẬT THẺ đầu tiên của mỗi
// lần mở màn học, chỉ trên thiết bị cảm ứng, chỉ ở 3 lần mở đầu (đếm bằng
// localStorage). Không đọc được localStorage (riêng tư / bị chặn) thì coi như
// lần đầu — hiện mỗi lần mở màn học một lần, chấp nhận được. Không lưu DB.
var COACH_STORAGE_KEY = "bjt.swipeCoach.count";
var COACH_TIMES = 3;
var coachShown = false;

function isTouchDevice() {
  return !!(window.matchMedia && window.matchMedia("(hover: none) and (pointer: coarse)").matches);
}

function coachCount() {
  try { return parseInt(window.localStorage.getItem(COACH_STORAGE_KEY) || "0", 10) || 0; }
  catch (e) { return 0; }
}

function maybeShowSwipeCoach() {
  var coach = document.querySelector("[data-swipe-coach]");
  if (coachShown || !coach || !isTouchDevice()) { return; }
  coachShown = true;   // mỗi lần mở trang chỉ một lần
  var count = coachCount();
  if (count >= COACH_TIMES) { return; }
  try { window.localStorage.setItem(COACH_STORAGE_KEY, String(count + 1)); } catch (e) { /* bỏ qua */ }
  coach.hidden = false;
}

function hideSwipeCoach() {
  var coach = document.querySelector("[data-swipe-coach]");
  if (!coach || coach.hidden) { return false; }
  coach.hidden = true;
  // Tích "Không hiện lại": tắt hẳn cho tài khoản (server, bật lại ở SC08) và
  // ghi luôn bộ đếm của trình duyệt cho đủ — tải lại trang trước khi request
  // xong cũng không hiện nữa.
  var never = coach.querySelector("[data-swipe-coach-never]");
  var form = coach.querySelector("[data-swipe-coach-form]");
  if (never && never.checked && form) {
    try { window.localStorage.setItem(COACH_STORAGE_KEY, String(COACH_TIMES)); } catch (e) { /* bỏ qua */ }
    if (window.fetch && window.FormData) {
      fetch(form.action, { method: "POST", body: new FormData(form), credentials: "same-origin" })
        .catch(function () { /* mất mạng: lần sau bảng hiện lại, tích lại là được */ });
    }
    coach.parentNode.removeChild(coach);
  }
  return true;
}

function initSwipeCoach() {
  var coach = document.querySelector("[data-swipe-coach]");
  if (!coach) { return; }
  // Đóng bằng nút "Đã hiểu", chạm ra ngoài hộp, hoặc Esc. Chạm trong hộp (ô
  // "Không hiện lại") thì KHÔNG đóng.
  coach.addEventListener("click", function (event) {
    if (event.target === coach || event.target.closest("[data-swipe-coach-close]")) {
      hideSwipeCoach();
    }
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") { hideSwipeCoach(); }
  });
}

function toggleShortcutDialog() {
  var dialog = document.querySelector("[data-shortcut-dialog]");
  if (!dialog) { return; }
  if (dialog.open) {
    if (dialog.close) { dialog.close(); } else { dialog.removeAttribute("open"); }
  } else if (dialog.showModal) {
    dialog.showModal();
  } else {
    dialog.setAttribute("open", "");
  }
}

function initCardPanel() {
  var panel = cardPanel();
  if (!panel || !window.fetch || !window.FormData) { return; }
  // event.submitter chưa có ở trình duyệt cũ — nhớ nút submit vừa được bấm
  // (kể cả bấm bằng phím tắt, vì phím tắt gọi button.click()). Thiếu giá trị
  // "quality" thì server sẽ chấm mặc định, nên không được để mất.
  var lastSubmitter = null;
  panel.addEventListener("click", function (event) {
    var button = event.target.closest("button");
    if (button && button.type === "submit") { lastSubmitter = button; }
  });

  function submitNormally(form, submitter) {
    if (submitter && submitter.name) {
      var hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = submitter.name;
      hidden.value = submitter.value;
      form.appendChild(hidden);
    }
    form.submit();   // không bắn lại sự kiện submit -> không bị chặn lần nữa
  }

  panel.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form.hasAttribute("data-card-ajax")) { return; }
    event.preventDefault();
    if (isPanelBusy()) { return; }   // chống bấm 2 lần

    var submitter = event.submitter ||
      (lastSubmitter && form.contains(lastSubmitter) ? lastSubmitter : null);
    var body = new FormData(form);
    if (submitter && submitter.name) { body.append(submitter.name, submitter.value); }

    panel.classList.add("is-busy");
    form.querySelectorAll("button").forEach(function (button) { button.disabled = true; });

    var headers = {};
    headers[CARD_PARTIAL_HEADER] = "1";
    fetch(form.action, { method: "POST", body: body, credentials: "same-origin", headers: headers })
      .then(function (response) {
        if (!response.ok) { throw new Error("HTTP " + response.status); }
        // Server không trả fragment (vd hoàn tác hết lượt bị đẩy về trang
        // chủ, hoặc phiên đăng nhập hết hạn) -> sang hẳn trang đó.
        if (response.headers.get(CARD_PARTIAL_HEADER) !== "1") {
          window.location.href = response.url;
          return null;
        }
        return response.text().then(function (html) {
          if (response.url && response.url !== window.location.href) {
            history.replaceState(null, "", response.url);
          }
          // Thông báo của lần tải trang đầu (nằm ngoài panel) đã cũ — fragment
          // mới tự mang theo thông báo của chính nó.
          document.querySelectorAll(".flash").forEach(function (note) {
            if (!panel.contains(note)) { note.remove(); }
          });
          panel.innerHTML = html;
          panel.classList.remove("is-busy");
          panel.focus({ preventScroll: true });
          if (panel.getBoundingClientRect().top < 0) { panel.scrollIntoView({ block: "start" }); }
        });
      })
      .catch(function () {
        panel.classList.remove("is-busy");
        submitNormally(form, submitter);
      });
  });
}

// "?" — một số bàn phím/IME báo key rỗng, nên nhận cả Shift + phím "/".
function isHelpKey(event) {
  return event.key === "?" || (event.shiftKey && event.code === "Slash");
}

function isTypingTarget(el) {
  return !!(el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)));
}

function initStudyShortcuts() {
  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-shortcut-open]")) {
      toggleShortcutDialog();
      return;
    }
    if (event.target.closest("[data-reveal]") || event.target.closest("[data-flashcard]")) {
      if (suppressCardClick) { suppressCardClick = false; return; }
      revealCard();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (!cardPanel()) { return; }
    if (event.ctrlKey || event.metaKey || event.altKey) { return; }
    if (isTypingTarget(event.target)) { return; }   // đang gõ bình luận

    var key = event.key;
    var dialog = document.querySelector("[data-shortcut-dialog]");
    if (dialog && dialog.open) {
      if (isHelpKey(event)) { event.preventDefault(); toggleShortcutDialog(); }
      return;   // Esc do <dialog> tự xử lý
    }
    if (isHelpKey(event)) { event.preventDefault(); toggleShortcutDialog(); return; }

    var busy = isPanelBusy();
    var screen = studyScreen();

    if (key === " " || key === "Spacebar" ||
        (key === "Enter" && event.target.closest && event.target.closest("[data-flashcard]"))) {
      if (!screen) { return; }
      // Space luôn để lật thẻ — không để nó "bấm" nút đang được focus.
      event.preventDefault();
      if (!busy) { revealCard(); }
      return;
    }
    if (/^[1-4]$/.test(key)) {
      if (!screen) { return; }
      event.preventDefault();
      if (busy || !isRevealed(screen)) { return; }   // phải lật thẻ rồi mới chấm
      var grade = screen.querySelector('[data-grade-key="' + key + '"]');
      if (grade) { grade.click(); }
      return;
    }
    if (key === "z" || key === "Z") {
      var undo = cardPanel().querySelector("[data-undo]");
      if (undo && !busy) { event.preventDefault(); undo.click(); }
      return;
    }
    if ((key === "e" || key === "E") && isRevealed(screen)) {
      var examples = screen.querySelector("[data-examples]");
      if (examples) { event.preventDefault(); examples.open = !examples.open; }
    }
  });
}

// Vuốt thẻ đã lật để chấm (T1.6 + spec.md T6.3): phải = Nhớ (phím 3),
// trái = Quên rồi (phím 1), LÊN = Dễ (phím 4). Hướng chốt một lần ở ~10px đầu.
// Trên thiết bị cảm ứng thẻ đã lật có `touch-action:none` (base.css) để trình
// duyệt không cuộn trang khi kéo trên thẻ — vì vậy kéo XUỐNG tự cuộn trang
// bằng tay ở đây (iOS Safari không hỗ trợ touch-action:pan-down).
var SWIPE_KEYS = { right: "3", left: "1", up: "4" };

function initCardSwipe() {
  var card = null;
  var start = null;

  function reset() {
    if (card) {
      card.style.transform = "";
      card.classList.remove("is-swiping", "swipe-left", "swipe-right", "swipe-up");
    }
    card = null;
    start = null;
  }

  document.addEventListener("touchstart", function (event) {
    var target = event.target.closest && event.target.closest("[data-flashcard]");
    if (!target || event.touches.length !== 1 || !isRevealed(studyScreen()) || isPanelBusy()) { return; }
    card = target;
    var t = event.touches[0];
    start = { x: t.clientX, y: t.clientY, lastY: t.clientY, dx: 0, dy: 0, dir: null };
  }, { passive: true });

  document.addEventListener("touchmove", function (event) {
    if (!card || !start) { return; }
    var t = event.touches[0];
    var dx = t.clientX - start.x;
    var dy = t.clientY - start.y;
    if (start.dir === null && (Math.abs(dx) > 10 || Math.abs(dy) > 10)) {
      start.dir = Math.abs(dx) > Math.abs(dy) ? "h" : (dy < 0 ? "up" : "down");
    }
    if (start.dir === "down") {
      window.scrollBy(0, start.lastY - t.clientY);
      start.lastY = t.clientY;
      return;
    }
    if (start.dir === null) { return; }
    card.classList.add("is-swiping");
    if (start.dir === "h") {
      start.dx = dx;
      card.style.transform = "translateX(" + dx + "px) rotate(" + (dx / 25) + "deg)";
      card.classList.toggle("swipe-left", dx <= -SWIPE_THRESHOLD);
      card.classList.toggle("swipe-right", dx >= SWIPE_THRESHOLD);
    } else {
      start.dy = Math.min(0, dy);   // đã chốt "lên" thì kéo ngược xuống chỉ về 0
      card.style.transform = "translateY(" + start.dy + "px)";
      card.classList.toggle("swipe-up", start.dy <= -SWIPE_THRESHOLD);
    }
  }, { passive: true });

  document.addEventListener("touchend", function () {
    if (!card || !start) { return; }
    var dir = null;
    if (start.dir === "h" && Math.abs(start.dx) >= SWIPE_THRESHOLD) {
      dir = start.dx > 0 ? "right" : "left";
    } else if (start.dir === "up" && start.dy <= -SWIPE_THRESHOLD) {
      dir = "up";
    }
    reset();
    if (!dir) { return; }
    suppressCardClick = true;
    setTimeout(function () { suppressCardClick = false; }, 400);
    var button = document.querySelector('[data-study-card] [data-grade-key="' + SWIPE_KEYS[dir] + '"]');
    if (button) { button.click(); }
  });
  document.addEventListener("touchcancel", reset);
}

// Nút ☰ hiện ở 2 nơi (CSS quyết định): trang có chế độ tập trung (SC04) và
// mọi trang trên màn ≤900px (T2.4 — sidebar thành menu mở bằng nút). Chỉ chế
// độ tập trung mới NHỚ lựa chọn: trên điện thoại menu luôn đóng khi sang
// trang mới, mở sẵn sẽ che nội dung.
function initSidebarToggle() {
  var shell = document.querySelector("[data-app-shell]");
  var button = document.querySelector("[data-sidebar-toggle]");
  if (!shell || !button) { return; }
  var remember = shell.classList.contains("is-focus");
  // localStorage có thể ném lỗi (trình duyệt chặn lưu trữ) — khi đó chỉ mất
  // phần "nhớ lựa chọn", nút vẫn chạy.
  if (remember) {
    try {
      if (window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "1") { shell.classList.add("show-sidebar"); }
    } catch (e) { /* bỏ qua */ }
  }
  button.setAttribute("aria-expanded", shell.classList.contains("show-sidebar") ? "true" : "false");
  button.addEventListener("click", function () {
    var shown = shell.classList.toggle("show-sidebar");
    button.setAttribute("aria-expanded", shown ? "true" : "false");
    if (remember) {
      try { window.localStorage.setItem(SIDEBAR_STORAGE_KEY, shown ? "1" : "0"); } catch (e) { /* bỏ qua */ }
    }
  });
}

// Vừa gửi bình luận (views.flashcard_comment redirect kèm #study-discussion)
// -> lật thẻ và mở sẵn khu thảo luận để thấy ngay bình luận của mình.
function openDiscussionFromHash() {
  if (window.location.hash !== "#study-discussion") { return; }
  var discussion = document.getElementById("study-discussion");
  if (!discussion) { return; }
  revealCard();
  discussion.open = true;
  discussion.scrollIntoView({ block: "start" });
}

// Câu báo sau mỗi lần chấm (spec.md T6.4): "✓ Nhớ · gặp lại sau 1 ngày".
// Bắt `click` ở pha CAPTURE — trước khi study_deck.js (chặn submit) hay
// fetch của initCardPanel đổi sang thẻ kế — nên đọc đúng `data-toast` của thẻ
// vừa chấm. Phím 1-4 và vuốt đều đi qua button.click() nên cũng có câu báo.
// Chữ do server dựng (views._grade_toasts); tắt JS thì không có câu báo.
var TOAST_MS = 1600;
var toastTimer = null;

function showGradeToast(text) {
  var toast = document.querySelector("[data-grade-toast]");
  if (!toast || !text) { return; }
  toast.textContent = text;
  toast.hidden = false;
  toast.classList.remove("is-shown");
  void toast.offsetWidth;   // chấm liên tiếp: chạy lại hiệu ứng hiện
  toast.classList.add("is-shown");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(function () {
    toast.classList.remove("is-shown");
    toastTimer = setTimeout(function () { toast.hidden = true; }, 200);
  }, TOAST_MS);
}

function initGradeToast() {
  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("[data-study-card] [data-grade-key]");
    if (!button || button.disabled || isPanelBusy()) { return; }
    showGradeToast(button.getAttribute("data-toast"));
  }, true);
}

function initStudyScreen() {
  openDiscussionFromHash();
  initCardPanel();
  initStudyShortcuts();
  initCardSwipe();
  // TẠM TẮT (10/10/2026, Dat): câu báo sau mỗi lần chấm làm chậm nhịp vuốt trên
  // điện thoại. Server vẫn dựng data-toast (views._grade_toasts) — bật lại chỉ
  // cần bỏ comment dòng dưới.
  // initGradeToast();
  initSwipeCoach();
  initSidebarToggle();
}

// ---------------------------------------------------------------------------
// 2. Dropdown nhiều-lựa-chọn có ô tìm nhanh
//    Dùng ở: SC05 (lọc chủ đề), SC10 (chọn chủ đề cho phiếu PDF).
//
//    Khung HTML tối thiểu — xem templates/vocabulary/list.html làm mẫu:
//      <details class="dropdown">
//        <summary class="dropdown-toggle">
//          <span data-dropdown-summary data-all="..." data-suffix="..."></span>
//        </summary>
//        <div class="dropdown-panel">
//          <input data-dropdown-search>                  <- ô tìm nhanh (không có name!)
//          <button type="button" data-dropdown-check="1">   <- chọn tất cả
//          <button type="button" data-dropdown-check="0">   <- bỏ chọn hết
//          <div class="dropdown-list">
//            <label class="checkbox-row" data-search="tên việt tên nhật slug">
//              <input type="checkbox" name="..." value="...">
//          </div>
//          <p data-dropdown-empty hidden>Không có mục nào khớp</p>
//        </div>
//      </details>
//
//    Dựng trên <details> nên tắt JavaScript vẫn mở/đóng và tích chọn được —
//    chỉ mất ô tìm nhanh, và template có <noscript> ẩn ô đó đi.
// ---------------------------------------------------------------------------

// Bỏ dấu để gõ "hop hanh" vẫn ra "Họp hành" — người dùng hiếm khi gõ đủ dấu khi
// đang tìm nhanh. Kana/kanji không có dấu tổ hợp nên không bị ảnh hưởng.
function normalizeSearchText(text) {
  return (text || "").toLowerCase()
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/đ/g, "d");
}

function initDropdown(dropdown) {
  var search = dropdown.querySelector("[data-dropdown-search]");
  var summary = dropdown.querySelector("[data-dropdown-summary]");
  var empty = dropdown.querySelector("[data-dropdown-empty]");
  var rows = Array.prototype.slice.call(dropdown.querySelectorAll("[data-search]"));

  function applySearch() {
    var needle = normalizeSearchText(search ? search.value : "").trim();
    var shown = 0;
    rows.forEach(function (row) {
      var hit = !needle ||
        normalizeSearchText(row.getAttribute("data-search")).indexOf(needle) !== -1;
      row.hidden = !hit;
      if (hit) { shown += 1; }
    });
    if (empty) { empty.hidden = shown !== 0; }
  }

  // Phần mở rộng tuỳ chọn (SC05, 01/10/2026) — template nào không khai báo thì
  // dropdown chạy y như cũ (SC10 vẫn hiện "N chủ đề đã chọn"):
  //   data-names="3" trên [data-dropdown-summary] -> hiện TÊN tối đa 3 mục + "+k"
  //   data-label trên từng dòng                    -> tên ngắn dùng cho chip
  //   [data-dropdown-count][data-for=<id>]          -> "Đã chọn x/y"
  //   [data-dropdown-chips][data-for=<id>]          -> hàng chip có nút ✕ bỏ nhanh
  //   [data-dropdown-close]                         -> nút "Xong" đóng panel
  var id = dropdown.id;
  var counter = id ? document.querySelector('[data-dropdown-count][data-for="' + id + '"]') : null;
  var chips = id ? document.querySelector('[data-dropdown-chips][data-for="' + id + '"]') : null;

  function boxOf(row) { return row.querySelector("input[type=checkbox]"); }
  function checkedRows() {
    return rows.filter(function (row) { var box = boxOf(row); return box && box.checked; });
  }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }

  function refreshSummary() {
    var picked = checkedRows();
    rows.forEach(function (row) {
      var box = boxOf(row);
      row.classList.toggle("is-checked", !!(box && box.checked));
    });

    if (summary) {
      var maxNames = parseInt(summary.getAttribute("data-names"), 10);
      if (maxNames > 0) {
        summary.textContent = "";
        if (!picked.length) {
          summary.appendChild(el("span", "summary-placeholder", summary.getAttribute("data-all")));
        } else {
          picked.slice(0, maxNames).forEach(function (row) {
            summary.appendChild(el("span", "summary-chip", row.getAttribute("data-label")));
          });
          if (picked.length > maxNames) {
            summary.appendChild(el("span", "summary-more", "+" + (picked.length - maxNames)));
          }
        }
      } else {
        summary.textContent = picked.length
          ? picked.length + " " + summary.getAttribute("data-suffix")
          : summary.getAttribute("data-all");
      }
    }

    if (counter) {
      counter.textContent = counter.getAttribute("data-label") + " " +
        picked.length + "/" + counter.getAttribute("data-total");
    }

    if (chips) {
      chips.textContent = "";
      picked.forEach(function (row) {
        var chip = el("span", "filter-chip", row.getAttribute("data-label"));
        var remove = el("button", "filter-chip-remove", "\u2715");
        remove.type = "button";
        remove.setAttribute("data-value", boxOf(row).value);
        remove.setAttribute("aria-label", chips.getAttribute("data-remove-label") || "");
        chip.appendChild(remove);
        chips.appendChild(chip);
      });
    }
  }

  if (chips) {
    chips.addEventListener("click", function (event) {
      var button = event.target.closest(".filter-chip-remove");
      if (!button) { return; }
      rows.forEach(function (row) {
        var box = boxOf(row);
        if (box && box.value === button.getAttribute("data-value")) { box.checked = false; }
      });
      refreshSummary();
    });
  }
  dropdown.querySelectorAll("[data-dropdown-close]").forEach(function (button) {
    button.addEventListener("click", function () {
      dropdown.open = false;
      var toggle = dropdown.querySelector("summary");
      if (toggle) { toggle.focus(); }
    });
  });

  // "Chọn tất cả / Bỏ chọn hết" chỉ áp cho các mục ĐANG HIỆN — khi đang gõ tìm
  // kiếm thì đó mới là ý người dùng muốn.
  dropdown.querySelectorAll("[data-dropdown-check]").forEach(function (button) {
    button.addEventListener("click", function () {
      var state = button.getAttribute("data-dropdown-check") === "1";
      rows.forEach(function (row) {
        if (row.hidden) { return; }
        var box = row.querySelector("input[type=checkbox]");
        if (box) { box.checked = state; }
      });
      refreshSummary();
    });
  });

  if (search) {
    search.addEventListener("input", applySearch);
    // Enter trong ô tìm nhanh KHÔNG được submit cả form đang bọc dropdown.
    search.addEventListener("keydown", function (event) {
      if (event.key === "Enter") { event.preventDefault(); }
    });
  }
  dropdown.addEventListener("change", refreshSummary);
  dropdown.addEventListener("toggle", function () {
    if (dropdown.open && search) { search.focus(); }
  });
  document.addEventListener("click", function (event) {
    if (dropdown.open && !dropdown.contains(event.target)) { dropdown.open = false; }
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && dropdown.open) { dropdown.open = false; }
  });

  refreshSummary();
}

function initDropdowns() {
  document.querySelectorAll("details.dropdown").forEach(initDropdown);
}

// ---------------------------------------------------------------------------
// 6. <select data-autosubmit>: đổi giá trị là gửi luôn form chứa nó.
//    Dùng ở SC05 (số dòng mỗi trang). Tắt JS thì template có nút "Áp dụng".
// ---------------------------------------------------------------------------
function initAutoSubmit() {
  document.querySelectorAll("select[data-autosubmit]").forEach(function (select) {
    select.addEventListener("change", function () {
      if (select.form) { select.form.submit(); }
    });
  });
}

// ---------------------------------------------------------------------------
// 5. Bảng xem trước khi nhập file (SC07b): tab lọc theo trạng thái + phân trang.
//
//    Server đã in SẴN mọi dòng của file vào HTML (tối đa 2000), hàm này chỉ
//    ẩn/hiện. Làm phía client vì phân trang phía server nghĩa là mỗi lần lật
//    trang phải phân tích lại cả file — full_clean() từng dòng — chỉ để lấy 30
//    dòng kế tiếp.
//
//    Khung HTML tối thiểu — xem templates/admin_panel/data_import.html:
//      <div data-preview data-preview-page-size="30" data-preview-default="error">
//        <button data-preview-filter="all|new|update|skipped|error">
//        <tbody data-preview-body>
//          <tr data-preview-row="new">                <- nhóm trạng thái của dòng
//        <p data-preview-empty style="display:none">   <- không dòng nào khớp
//        <div data-preview-pager style="display:none">
//          <button data-preview-prev> <span data-preview-info> <button data-preview-next>
//
//    Tắt JavaScript thì mọi dòng vẫn hiện, chỉ mất lọc và phân trang.
// ---------------------------------------------------------------------------
function initPreviewTable(root) {
  var body = root.querySelector("[data-preview-body]");
  if (!body) { return; }

  var rows = Array.prototype.slice.call(body.querySelectorAll("[data-preview-row]"));
  var buttons = Array.prototype.slice.call(root.querySelectorAll("[data-preview-filter]"));
  var pager = root.querySelector("[data-preview-pager]");
  var info = root.querySelector("[data-preview-info]");
  var prevButton = root.querySelector("[data-preview-prev]");
  var nextButton = root.querySelector("[data-preview-next]");
  var emptyNote = root.querySelector("[data-preview-empty]");
  var pageSize = parseInt(root.getAttribute("data-preview-page-size"), 10) || 30;
  var filter = root.getAttribute("data-preview-default") || "all";
  var page = 1;

  function matches(row) {
    return filter === "all" || row.getAttribute("data-preview-row") === filter;
  }

  function render() {
    var total = 0;
    rows.forEach(function (row) { if (matches(row)) { total += 1; } });

    var pageCount = Math.max(1, Math.ceil(total / pageSize));
    if (page > pageCount) { page = pageCount; }
    var from = (page - 1) * pageSize;

    var seen = 0;
    rows.forEach(function (row) {
      if (!matches(row)) {
        row.style.display = "none";
        return;
      }
      row.style.display = (seen >= from && seen < from + pageSize) ? "" : "none";
      seen += 1;
    });

    buttons.forEach(function (button) {
      var isActive = button.getAttribute("data-preview-filter") === filter;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
    // Ẩn bằng style chứ không bằng thuộc tính hidden: .pagination có
    // display:flex trong CSS, mà display:flex thắng display:none mặc định của
    // [hidden] nên thanh phân trang vẫn hiện ra dù đã set hidden.
    if (emptyNote) { emptyNote.style.display = total === 0 ? "" : "none"; }
    if (pager) { pager.style.display = pageCount < 2 ? "none" : ""; }
    if (info) { info.textContent = page + " / " + pageCount; }
    if (prevButton) { prevButton.disabled = page <= 1; }
    if (nextButton) { nextButton.disabled = page >= pageCount; }
  }

  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      filter = button.getAttribute("data-preview-filter");
      page = 1;   // đổi tab mà giữ nguyên số trang thì dễ rơi vào trang trống
      render();
    });
  });
  if (prevButton) {
    prevButton.addEventListener("click", function () {
      if (page > 1) { page -= 1; render(); }
    });
  }
  if (nextButton) {
    nextButton.addEventListener("click", function () {
      page += 1;
      render();
    });
  }

  render();
}

function initPreviewTables() {
  document.querySelectorAll("[data-preview]").forEach(initPreviewTable);
}

document.addEventListener("DOMContentLoaded", function () {
  initStudyScreen();
  initRequiredBeforeSubmit();
  initDropdowns();
  initPreviewTables();
  initAutoSubmit();
  initLoadingButtons();
});

// ---------------------------------------------------------------------------
// 7. Nút submit chạy lâu (spec.md T3.3): <button data-loading-text="Đang tải...">
//    Bấm là đổi chữ + khoá nút, chặn lần submit thứ hai của cùng form (tạo PDF
//    SC10, xuất PDF kính ngữ, nhập dữ liệu SC07b, "Học hôm nay"...).
//
//    - Khoá ở setTimeout(0): khoá ngay trong sự kiện submit thì trình duyệt
//      có thể bỏ name/value của nút khỏi dữ liệu gửi đi.
//    - Form trả về FILE tải xuống (PDF) thì trang không đổi -> tự mở khoá
//      sau LOADING_RESET_MS. Quay lại bằng nút Back (bfcache) cũng mở khoá.
//    - Form đã bị JS khác chặn (defaultPrevented, vd màn học gửi bằng fetch)
//      thì bỏ qua. Tắt JavaScript: nút giữ nguyên, form gửi như thường.
//    - Link TẢI FILE <a download data-loading-text> (PDF kính ngữ SC17/SC20):
//      trang không đổi nên cũng đổi chữ + chặn bấm lặp, mở lại sau
//      LINK_LOADING_RESET_MS (không biết chính xác lúc file tải xong).
// ---------------------------------------------------------------------------
var LOADING_RESET_MS = 15000;
var LINK_LOADING_RESET_MS = 4000;

function resetLoadingButton(button) {
  if (!button.classList.contains("is-loading")) { return; }
  button.classList.remove("is-loading");
  button.disabled = false;
  button.removeAttribute("aria-busy");
  if (button.tagName === "A") { button.removeAttribute("aria-disabled"); }
  if (button.dataset.loadingOriginal !== undefined) {
    button.textContent = button.dataset.loadingOriginal;
  }
  if (button.form) { delete button.form.dataset.submitting; }
}

function initLoadingButtons() {
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (event.defaultPrevented || !(form instanceof HTMLFormElement)) { return; }
    var button = event.submitter;
    if (!button || !button.hasAttribute("data-loading-text")) {
      button = form.querySelector("[data-loading-text]");
    }
    if (!button) { return; }
    if (form.dataset.submitting) { event.preventDefault(); return; }
    form.dataset.submitting = "1";
    window.setTimeout(function () {
      button.dataset.loadingOriginal = button.textContent;
      button.textContent = button.getAttribute("data-loading-text");
      button.classList.add("is-loading");
      button.setAttribute("aria-busy", "true");
      button.disabled = true;
      window.setTimeout(function () { resetLoadingButton(button); }, LOADING_RESET_MS);
    }, 0);
  });
  document.addEventListener("click", function (event) {
    var link = event.target.closest && event.target.closest("a[data-loading-text]");
    if (!link) { return; }
    if (link.classList.contains("is-loading")) { event.preventDefault(); return; }
    // Đổi chữ SAU khi trình duyệt đã nhận cú bấm (giống nút submit ở trên).
    window.setTimeout(function () {
      link.dataset.loadingOriginal = link.textContent;
      link.textContent = link.getAttribute("data-loading-text");
      link.classList.add("is-loading");
      link.setAttribute("aria-busy", "true");
      link.setAttribute("aria-disabled", "true");
      window.setTimeout(function () { resetLoadingButton(link); }, LINK_LOADING_RESET_MS);
    }, 0);
  });
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) { return; }
    document.querySelectorAll("[data-loading-text].is-loading").forEach(resetLoadingButton);
  });
}

// ---------------------------------------------------------------------------
// 4. Nút cần một ô bắt buộc mới bấm được (SC12: "Từ chối" phải có lý do).
//
//    Ô lý do KHÔNG đặt required sẵn, vì nút "Duyệt" cùng nằm trong form đó và
//    duyệt thì lý do là tuỳ chọn. Nên required chỉ được bật đúng lúc bấm nút
//    từ chối, rồi gỡ ra ngay để lần bấm "Duyệt" sau đó không bị chặn oan.
//
//    Đây chỉ là lớp phủ cho nhanh: tắt JavaScript thì view vẫn kiểm tra và
//    báo lỗi ngay dưới ô nhập như cũ.
// ---------------------------------------------------------------------------
function initRequiredBeforeSubmit() {
  document.querySelectorAll("[data-reject-requires]").forEach(function (button) {
    button.addEventListener("click", function (event) {
      var field = document.getElementById(button.getAttribute("data-reject-requires"));
      if (!field || field.value.trim()) { return; }
      event.preventDefault();
      field.setCustomValidity(button.getAttribute("data-reject-message") || "");
      field.reportValidity();
      field.focus();
      field.addEventListener("input", function clear() {
        field.setCustomValidity("");
        field.removeEventListener("input", clear);
      });
    });
  });
}
