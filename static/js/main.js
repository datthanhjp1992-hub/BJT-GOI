// Shared front-end behaviour across all templates (flashcard flip, quiz select, etc.)
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".flashcard").forEach((card) => {
    card.addEventListener("click", () => card.classList.toggle("is-flipped"));
  });
});
