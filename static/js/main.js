// Hành vi front-end dùng chung cho mọi template.
// Không framework, không build step: file này được base.html nạp ở cuối <body>.

// ---------------------------------------------------------------------------
// 1. Flashcard (SC04): bấm vào thẻ để lật ra nghĩa.
// ---------------------------------------------------------------------------
function initFlashcards() {
  document.querySelectorAll(".flashcard").forEach(function (card) {
    card.addEventListener("click", function () { card.classList.toggle("is-flipped"); });
  });
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

  function refreshSummary() {
    if (!summary) { return; }
    var checked = rows.filter(function (row) {
      var box = row.querySelector("input[type=checkbox]");
      return box && box.checked;
    }).length;
    summary.textContent = checked
      ? checked + " " + summary.getAttribute("data-suffix")
      : summary.getAttribute("data-all");
  }

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
  initFlashcards();
  initRequiredBeforeSubmit();
  initDropdowns();
  initPreviewTables();
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
