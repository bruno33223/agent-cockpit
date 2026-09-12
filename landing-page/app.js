document.addEventListener("DOMContentLoaded", () => initLandingApp());

const simState = { isRunning: false, step: 0 };

function initLandingApp() {
    bindControls();
    appendLogEntry("Cockpit Core online. Aguardando comando de simulação da frota...", "info");
}

function appendLogEntry(message, type = "info") {
    const logStream = document.getElementById("logStream");
    if (!logStream) return;

    const entry = document.createElement("div");
    entry.className = "log-entry " + type;

    const timestamp = new Date().toLocaleTimeString();
    entry.textContent = timestamp + " " + message;

    logStream.appendChild(entry);
    logStream.scrollTop = logStream.scrollHeight;
}

function startFleetSimulation() {
    if (simState.isRunning) return;
    simState.isRunning = true;

    setTimeout(() => {
        appendLogEntry("🚀 Despacho Concorrente: 3 Builders inicializados em Worktrees isoladas.", "info");
    }, 0);

    setTimeout(() => {
        appendLogEntry("🧪 TDD Iron Law: Builder 1, 2 e 3 executando verify_red (Fase Vermelha)...", "info");
    }, 800);

    setTimeout(() => {
        appendLogEntry("⚡ Local Worker: GPU Ollama (Qwen 7B) processando patches atômicos em fila FIFO...", "info");
    }, 1600);

    setTimeout(() => {
        appendLogEntry("🛡️ Harsh Critics: 3 Revisores auditando git diff adversariamente...", "info");
    }, 2400);

    setTimeout(() => {
        appendLogEntry("✅ Gauntlet Verdict: Fatias 1, 2 e 3 APROVADAS com 0 não-conformidades!", "success");
    }, 3200);

    setTimeout(() => {
        appendLogEntry("📦 Handoff consolidado com sucesso em HANDOFF.md. Telemetria salva.", "success");
        simState.isRunning = false;
    }, 3600);
}

function resetSimulation() {
    if (simState.isRunning) return;
    const logStream = document.getElementById("logStream");
    if (logStream) logStream.innerHTML = "";
    simState.isRunning = false;
    appendLogEntry("Sistema reinicializado. Pronto para novo ciclo.", "info");
}

function bindControls() {
    const btnStart = document.querySelector("#btnStartSim");
    if (btnStart) btnStart.addEventListener("click", startFleetSimulation);
    const btnReset = document.querySelector("#btnResetSim");
    if (btnReset) btnReset.addEventListener("click", resetSimulation);
}
