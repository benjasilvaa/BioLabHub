
const socket = io({
    transports: ["websocket"],
    reconnection: true,
    reconnectionAttempts: 10,
    reconnectionDelay: 1000
});






socket.on("connect", () => {
    console.log(" WebSocket conectado:", socket.id);
});


socket.on("disconnect", (reason) => {
    console.log(" WebSocket desconectado:", reason);
});


socket.on("server_message", (data) => {
    console.log(" Mensaje del servidor:", data.msg);
});






const eventosDiv = document.getElementById("eventos");


socket.on("sample_event", (msg) => {
    if (!eventosDiv) return; 
    
    const p = document.createElement("p");
    p.textContent = " " + msg;
    p.classList.add("fade");
    eventosDiv.prepend(p);

    if (eventosDiv.childElementCount > 15) {
        eventosDiv.removeChild(eventosDiv.lastChild);
    }
});
