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
//    d) Vuốt trên điện thoại: trái = Quên rồi, phải = Nhớ (khi đã lật thẻ).
//    e) Chế độ tập trung: nút ☰ mở/ẩn sidebar, nhớ trong localStorage.
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
  return true;
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

function initCardSwipe() {
  var card = null;
  var start = null;

  function reset() {
    if (card) {
      card.style.transform = "";
      card.classList.remove("is-swiping", "swipe-left", "swipe-right");
    }
    card = null;
    start = null;
  }

  document.addEventListener("touchstart", function (event) {
    var target = event.target.closest && event.target.closest("[data-flashcard]");
    if (!target || event.touches.length !== 1 || !isRevealed(studyScreen()) || isPanelBusy()) { return; }
    card = target;
    start = { x: event.touches[0].clientX, y: event.touches[0].clientY, dx: 0, horizontal: null };
  }, { passive: true });

  document.addEventListener("touchmove", function (event) {
    if (!card || !start) { return; }
    var dx = event.touches[0].clientX - start.x;
    var dy = event.touches[0].clientY - start.y;
    // Quyết định hướng một lần: vuốt dọc là cuộn trang, không đụng tới thẻ.
    if (start.horizontal === null && (Math.abs(dx) > 10 || Math.abs(dy) > 10)) {
      start.horizontal = Math.abs(dx) > Math.abs(dy);
    }
    if (!start.horizontal) { return; }
    start.dx = dx;
    card.classList.add("is-swiping");
    card.style.transform = "translateX(" + dx + "px) rotate(" + (dx / 25) + "deg)";
    card.classList.toggle("swipe-left", dx <= -SWIPE_THRESHOLD);
    card.classList.toggle("swipe-right", dx >= SWIPE_THRESHOLD);
  }, { passive: true });

  document.addEventListener("touchend", function () {
    if (!card || !start) { return; }
    var dx = start.dx;
    reset();
    if (Math.abs(dx) < SWIPE_THRESHOLD) { return; }
    suppressCardClick = true;
    setTimeout(function () { suppressCardClick = false; }, 400);
    // Phải = "Nhớ" (phím 3), trái = "Quên rồi" (phím 1).
    var button = document.querySelector('[data-study-card] [data-grade-key="' + (dx > 0 ? "3" : "1") + '"]');
    if (button) { button.click(); }
  });
  document.addEventListener("touchcancel", reset);
}

function initSidebarToggle() {
  var shell = document.querySelector("[data-app-shell]");
  var button = document.querySelector("[data-sidebar-toggle]");
  if (!shell || !button || !shell.classList.contains("is-focus")) { return; }
  // localStorage có thể ném lỗi (trình duyệt chặn lưu trữ) — khi đó chỉ mất
  // phần "nhớ lựa chọn", nút vẫn chạy.
  try {
    if (window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "1") { shell.classList.add("show-sidebar"); }
  } catch (e) { /* bỏ qua */ }
  button.setAttribute("aria-expanded", shell.classList.contains("show-sidebar") ? "true" : "false");
  button.addEventListener("click", function () {
    var shown = shell.classList.toggle("show-sidebar");
    button.setAttribute("aria-expanded", shown ? "true" : "false");
    try { window.localStorage.setItem(SIDEBAR_STORAGE_KEY, shown ? "1" : "0"); } catch (e) { /* bỏ qua */ }
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

function initStudyScreen() {
  openDiscussionFromHash();
  initCardPanel();
  initStudyShortcuts();
  initCardSwipe();
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
});

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
