// Conexión WebSocket estable al servidor
const socket = io({
    transports: ["websocket"],
    reconnection: true,
    reconnectionAttempts: 10,
    reconnectionDelay: 1000
});

// =======================
//     EVENTOS BÁSICOS
// =======================

// Al conectar
socket.on("connect", () => {
    console.log("🟢 WebSocket conectado:", socket.id);
});

// Al desconectar
socket.on("disconnect", (reason) => {
    console.log("🔴 WebSocket desconectado:", reason);
});

// Mensajes del servidor
socket.on("server_message", (data) => {
    console.log("📩 Mensaje del servidor:", data.msg);
});

// =======================
//   EVENTOS DE SampleTrack
// =======================

// Para mostrar eventos en la caja inferior de SampleTrack
const eventosDiv = document.getElementById("eventos");

// Recibe un evento en tiempo real (al agregar/editar/eliminar una muestra)
socket.on("sample_event", (msg) => {
    if (!eventosDiv) return; // si no estamos en samples.html
    
    const p = document.createElement("p");
    p.textContent = "🔔 " + msg;
    p.classList.add("fade");
    eventosDiv.prepend(p);

    if (eventosDiv.childElementCount > 15) {
        eventosDiv.removeChild(eventosDiv.lastChild);
    }
});
