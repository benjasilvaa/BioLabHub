
const socket = io({
    transports: ["websocket"],
    reconnection: true,
    reconnectionAttempts: 10,
    reconnectionDelay: 1000
});


window.BioLabHubLog = window.BioLabHubLog || {
    events: [],
    add(type, message, extra) {
        const entry = {
            ts: new Date().toISOString(),
            type,
            message,
            extra: extra || null,
        };
        this.events.unshift(entry);
        if (this.events.length > 100) {
            this.events.pop();
        }
        console.log("[BioLabHub]", type, message, extra || "");
    }
};


socket.on("connect", () => {
    window.BioLabHubLog.add("socket", "WebSocket conectado", { id: socket.id });
});


socket.on("disconnect", (reason) => {
    window.BioLabHubLog.add("socket", "WebSocket desconectado", { reason });
});


socket.on("server_message", (data) => {
    window.BioLabHubLog.add("server_message", data.msg || "Mensaje del servidor", data);
});


const eventosDiv = document.getElementById("eventos");


socket.on("sample_event", (msg) => {
    window.BioLabHubLog.add("sample_event", msg);
    if (!eventosDiv) return; 
    
    const p = document.createElement("p");
    p.textContent = " " + msg;
    p.classList.add("fade");
    eventosDiv.prepend(p);

    if (eventosDiv.childElementCount > 15) {
        eventosDiv.removeChild(eventosDiv.lastChild);
    }
});


socket.on("critical_event", (payload) => {
    const msg = `ALERTA CRTICA: ${payload.tipo || "evento"} desde IP ${payload.ip || "desconocida"} (intentos: ${payload.cantidad || "?"})`;
    window.BioLabHubLog.add("critical_event", msg, payload);

    if (!eventosDiv) return;

    const p = document.createElement("p");
    p.textContent = " " + msg;
    p.classList.add("fade");
    p.style.color = "#b71c1c";
    p.style.fontWeight = "bold";
    eventosDiv.prepend(p);

    if (eventosDiv.childElementCount > 20) {
        eventosDiv.removeChild(eventosDiv.lastChild);
    }
});
