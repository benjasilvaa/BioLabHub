document.addEventListener("DOMContentLoaded", () => {
    AOS.init({ duration: 1000 });
  
    document.getElementById("year").textContent = new Date().getFullYear();
  
    document.getElementById("startBtn").addEventListener("click", () => {
      const user = localStorage.getItem("user");
      if (user) {
        alert("Redirigiendo a Home...");
        // window.location.href = "home.html";
      } else {
        alert("Redirigiendo a Login...");
        // window.location.href = "login.html";
      }
    });
  });