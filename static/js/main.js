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

document.addEventListener("DOMContentLoaded", function () {
  initFlashcards();
  initDropdowns();
});
