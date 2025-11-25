document.addEventListener("DOMContentLoaded", () => {
  if (window.AOS) {
    AOS.init({ duration: 1000 });
  }

  const yearSpan = document.getElementById("year");
  if (yearSpan) {
    yearSpan.textContent = new Date().getFullYear();
  }

  const startBtn = document.getElementById("startBtn");
  if (startBtn) {
    startBtn.addEventListener("click", () => {
      window.location.href = "/login";
    });
  }
});
