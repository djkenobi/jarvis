/* Jarvis frontend logic */
(() => {
  "use strict";

  const els = {
    messages: document.getElementById("messages"),
    micBtn: document.getElementById("mic-btn"),
    txtBtn: document.getElementById("txt-btn"),
    textInput: document.getElementById("text-input"),
    sendBtn: document.getElementById("send-btn"),
    listenState: document.getElementById("listen-state"),
    pulseDot: document.getElementById("pulse-dot"),
    statBrain: document.getElementById("stat-brain"),
    statVoice: document.getElementById("stat-voice"),
    statPhone: document.getElementById("stat-phone"),
    statControl: document.getElementById("stat-control"),
    btnStatus: document.getElementById("btn-status"),
    btnLogout: document.getElementById("btn-logout"),
    ttsAudio: document.getElementById("tts-audio"),
    // modal
    modal: document.getElementById("modal"),
    modalTitle: document.getElementById("modal-title"),
    modalText: document.getElementById("modal-text"),
    modalPinRow: document.getElementById("modal-pin-row"),
    modalPin: document.getElementById("modal-pin"),
    modalOk: document.getElementById("modal-ok"),
    modalCancel: document.getElementById("modal-cancel"),
    // login
    loginScreen: document.getElementById("login-screen"),
    loginForm: document.getElementById("login-form"),
    loginUser: document.getElementById("login-user"),
    loginPass: document.getElementById("login-pass"),
    loginError: document.getElementById("login-error"),
  };

  const cfg = { adminPinRequired: false };
  let history = [];
  let recognition = null;
  let pendingAction = null;

  // -------------------------------------------------------------- //
  // Utilities
  // -------------------------------------------------------------- //
  function esc(s) {
    return (s || "").replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  function addMsg(role, text, action) {
    const wrap = document.createElement("div");
    wrap.className = `msg ${role}`;
    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.textContent = role === "user" ? "U" : "J";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    if (action) {
      const tag = document.createElement("div");
      tag.className = "action-tag";
      tag.textContent = `⚡ Action: ${action}`;
      bubble.appendChild(tag);
    }
    bubble.appendChild(document.createTextNode(text));
    wrap.appendChild(avatar);
    wrap.appendChild(bubble);
    els.messages.appendChild(wrap);
    els.messages.scrollTop = els.messages.scrollHeight;
    return bubble;
  }

  function setListen(active, label) {
    els.pulseDot.classList.toggle("active", active);
    els.listenState.textContent = label || (active ? "Listening" : "Idle");
  }

  function playAudio(url) {
    if (!url) return;
    els.ttsAudio.src = url;
    els.ttsAudio.play().catch(() => {});
  }

  // -------------------------------------------------------------- //
  // Auth
  // -------------------------------------------------------------- //
  function showApp() { els.loginScreen.hidden = true; }

  function showLogin() {
    els.loginScreen.hidden = false;
    els.loginError.hidden = true;
    els.loginUser.focus();
  }

  async function checkAuth() {
    try {
      const res = await fetch("/api/auth/status");
      const data = await res.json();
      if (data.enabled && !data.authed) {
        showLogin();
        return false;
      }
      showApp();
      return true;
    } catch (e) {
      // Server unreachable — assume auth not required so UI is usable offline.
      showApp();
      return true;
    }
  }

  els.btnLogout.addEventListener("click", async () => {
    try { await fetch("/api/auth/logout", { method: "POST" }); } catch (e) {}
    showLogin();
  });

  async function doLogin(username, password) {
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (res.ok) {
        showApp();
        await initApp();
        return true;
      }
      els.loginError.hidden = false;
      return false;
    } catch (e) {
      els.loginError.textContent = "Could not reach the server.";
      els.loginError.hidden = false;
      return false;
    }
  }

  els.loginForm.addEventListener("submit", (e) => {
    e.preventDefault();
    doLogin(els.loginUser.value, els.loginPass.value);
  });

  // -------------------------------------------------------------- //
  // Load config
  // -------------------------------------------------------------- //
  async function loadConfig() {
    try {
      const res = await fetch("/api/config");
      const data = await res.json();
      cfg.name = data.name;
      cfg.adminPinRequired = !!data.admin_pin_required;
      els.statBrain.textContent = data.name;
      els.statVoice.textContent = "en-GB · Male";
      els.statPhone.textContent = data.phone_enabled ? "ON" : "OFF";
      els.statPhone.className = data.phone_enabled ? "on" : "off";
      els.statControl.textContent = data.control_enabled ? "ON" : "OFF";
      els.statControl.className = data.control_enabled ? "on" : "off";
    } catch (e) {
      els.statBrain.textContent = "offline";
    }
  }

  // -------------------------------------------------------------- //
  // Chat
  // -------------------------------------------------------------- //
  async function send(text) {
    const trimmed = (text || "").trim();
    if (!trimmed) return;
    addMsg("user", trimmed);
    els.textInput.value = "";

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed, history }),
      });
      const data = await res.json();
      if (!res.ok) {
        addMsg("jarvis", "⚠️ " + (data.error || data.detail || "Error") +
          (data.hint ? "\n" + data.hint : ""));
        return;
      }
      addMsg("jarvis", data.reply, data.action);
      history.push({ role: "user", content: trimmed });
      history.push({ role: "assistant", content: data.reply });
      if (history.length > 20) history = history.slice(-20);

      if (data.action) {
        pendingAction = { action: data.action, userMessage: trimmed };
        showConfirm(data.action, trimmed, data.reply);
      }
      playAudio(data.audio);
    } catch (e) {
      addMsg("jarvis", "⚠️ Could not reach the server.");
    }
  }

  // -------------------------------------------------------------- //
  // Voice input (Web Speech API)
  // -------------------------------------------------------------- //
  function initSpeech() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      els.micBtn.title = "Speech not supported in this browser";
      els.micBtn.style.opacity = 0.4;
      return;
    }
    recognition = new SR();
    recognition.lang = "en-GB";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => { setListen(true, "Listening…"); els.micBtn.classList.add("recording"); };
    recognition.onend = () => { setListen(false, "Idle"); els.micBtn.classList.remove("recording"); };
    recognition.onerror = (e) => { setListen(false, e.error === "not-allowed" ? "Mic blocked" : "Idle"); };
    recognition.onresult = (e) => {
      const t = e.results[0][0].transcript;
      if (t) send(t);
    };

    els.micBtn.addEventListener("click", () => {
      if (recognition) {
        recognition.stop();
        recognition.start();
      }
    });
  }

  // -------------------------------------------------------------- //
  // Action confirmation modal
  // -------------------------------------------------------------- //
  function showConfirm(action, userMessage, reply) {
    const labels = { call: "Call Phone", status: "Check System", run: "Run Command" };
    els.modalTitle.textContent = "Confirm Action — " + (labels[action] || action);
    els.modalText.textContent = reply || `Jarvis wants to perform: ${action}`;
    els.modalPinRow.hidden = !cfg.adminPinRequired;
    els.modalPin.value = "";
    els.modal.hidden = false;
    els.modalOk.onclick = () => doAction(action, userMessage);
    els.modalCancel.onclick = () => { els.modal.hidden = true; pendingAction = null; };
    if (!cfg.adminPinRequired) els.modalPin.focus();
  }

  async function doAction(action, userMessage) {
    const payload = {
      action,
      user_message: userMessage || "",
    };
    if (cfg.adminPinRequired) payload.pin = els.modalPin.value;
    try {
      const res = await fetch("/api/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.ok && data.result) {
        const r = data.result;
        const out = ["✅ " + (r.label || "Action completed") + ":"];
        if (r.call_sid) out.push("Call SID: " + r.call_sid);
        if (r.stdout) out.push("\n" + r.stdout);
        if (r.stderr) out.push("\n[stderr] " + r.stderr);
        if (r.error) out.push("\n" + r.error);
        addMsg("jarvis", out.join("\n"));
      } else {
        addMsg("jarvis", "⚠️ " + (data.error || "Action failed."));
      }
    } catch (e) {
      addMsg("jarvis", "⚠️ Could not run the action.");
    }
    els.modal.hidden = true;
    pendingAction = null;
  }

  // -------------------------------------------------------------- //
  // Events
  // -------------------------------------------------------------- //
  els.sendBtn.addEventListener("click", () => send(els.textInput.value));
  els.textInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") send(els.textInput.value);
  });
  els.btnStatus.addEventListener("click", () => {
    // One-click system status (safe, read-only built-in).
    fetch("/api/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "status" }),
    }).then((r) => r.json()).then((data) => {
      if (data.ok && data.result && data.result.stdout) addMsg("jarvis", data.result.stdout);
      else addMsg("jarvis", "⚠️ " + (data.error || "Status unavailable. Enable CONTROL_ENABLED."));
    });
  });

  // -------------------------------------------------------------- //
  async function initApp() {
    await loadConfig();
    initSpeech();
  }

  (async () => {
    const authed = await checkAuth();
    if (authed) await initApp();
  })();
})();
