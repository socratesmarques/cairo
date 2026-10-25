"use strict";

// Browser-native speech boundary; callbacks keep microphone state out of chat logic.
class CairoVoice {
  constructor({ Recognition, onState, onText, onDone, onError, limitMs = 30000, maxLength = 16000 }) {
    this.Recognition = Recognition;
    this.onState = onState; this.onText = onText; this.onDone = onDone; this.onError = onError;
    this.limitMs = limitMs; this.maxLength = maxLength; this.active = false;
    this.recognition = null; this.timer = null; this.failed = false;
  }
  start(draft = "") {
    if (this.active) return;
    if (!this.Recognition) { this.onError("Este navegador não oferece ditado. Abra Cairo no Google Chrome."); return; }
    if (draft.length >= this.maxLength) { this.onError("A mensagem já atingiu o limite de caracteres."); return; }
    this.base = draft.trim(); this.finalText = ""; this.failed = false; this.errorMessage = ""; this.active = true;
    const recognition = new this.Recognition();
    this.recognition = recognition;
    recognition.lang = "pt-BR";
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    const combine = (text) => [this.base, text].filter(Boolean).join(" ").slice(0, this.maxLength);
    recognition.onstart = () => { if (this.recognition === recognition) this.onState("listening"); };
    recognition.onresult = (event) => {
      if (this.recognition !== recognition) return;
      const finals = [], interim = [];
      for (let i = 0; i < event.results.length; i++) {
        const result = event.results[i];
        (result.isFinal ? finals : interim).push(result[0].transcript);
      }
      this.finalText = finals.join(" ").trim();
      this.onText(combine([this.finalText, ...interim].join(" ").trim()));
    };
    recognition.onerror = (event) => {
      if (this.recognition !== recognition) return;
      this.failed = true; this.errorCode = event.error;
      const messages = {
        "not-allowed": "Microfone bloqueado. Permita o microfone nas configurações deste site e tente novamente.",
        "service-not-allowed": "O serviço de reconhecimento foi bloqueado pelo navegador. Tente no Google Chrome.",
        "audio-capture": "Não foi possível acessar o microfone. Confira se ele está conectado e disponível.",
        "no-speech": "Não detectei fala. Clique no microfone e tente novamente.",
        "network": "O reconhecimento de voz não conseguiu acessar o serviço. Confira a conexão e tente novamente.",
        "aborted": "Ditado interrompido.",
        "language-not-supported": "Português não está disponível neste serviço de reconhecimento."
      };
      this.errorMessage = messages[event.error] || "Não foi possível transcrever a fala. Tente novamente.";
      this.onError(this.errorMessage, event.error);
    };
    recognition.onend = () => {
      if (this.recognition !== recognition) return;
      clearTimeout(this.timer); this.timer = null; this.active = false; this.recognition = null;
      const text = combine(this.finalText);
      this.onText(text); this.onState("idle");
      if (this.finalText && !this.failed) this.onDone(text);
      else if (this.failed) this.onError(this.errorMessage, this.errorCode);
      else if (!this.failed) this.onError("Nenhuma fala foi reconhecida. Tente novamente.", "no-speech");
    };
    this.onState("starting");
    try {
      recognition.start();
      this.timer = setTimeout(() => this.stop(), this.limitMs);
    } catch (_) {
      this.cancel();
      this.onError("Não foi possível iniciar o microfone. Confira a permissão do navegador.");
    }
  }
  stop() {
    if (!this.active) return;
    this.onState("stopping");
    try { this.recognition.stop(); } catch (_) { this.cancel(); }
    // Some embedded browsers never emit end after a failed service connection.
    clearTimeout(this.timer);
    if (this.active) this.timer = setTimeout(() => { this.cancel(); this.onError("O ditado não terminou a tempo. Tente novamente."); }, 5000);
  }
  cancel() {
    const current = this.recognition;
    this.recognition = null; this.active = false; clearTimeout(this.timer); this.timer = null;
    if (current) {
      current.onstart = null; current.onresult = null; current.onerror = null; current.onend = null;
      try { current.abort(); } catch (_) { /* Already ended. */ }
      this.onText([this.base, this.finalText].filter(Boolean).join(" ").slice(0, this.maxLength));
    }
    this.onState("idle");
  }
}

if (typeof module !== "undefined" && module.exports) module.exports = { CairoVoice };


// Re-arm short utterances after each command; never run two recognizers together.
class CairoOpenMic {
  constructor({ Recognition, blocked, onText, onCommand, onState, onError, intervalMs = 600 }) {
    this.enabled = false; this.timer = null; this.blocked = blocked;
    this.onState = onState; this.intervalMs = intervalMs;
    this.voice = new CairoVoice({Recognition, onText,
      onState: (state) => { if (this.enabled) onState(state === "idle" ? "waiting" : state); },
      onError: (message, code) => {
        if (code === "no-speech") return;
        this.stop(); onError(message);
      },
      onDone: (text) => {
        if (!this.enabled) return;
        const command = text.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[.,!?]/g, "").trim();
        if (["parar escuta", "pare de ouvir", "cairo parar escuta", "cairo pare de ouvir"].includes(command)) { this.stop(); onText(""); return; }
        onState("waiting"); onCommand(text);
      }
    });
  }
  start() {
    if (this.enabled) return;
    this.enabled = true;
    this.timer = setInterval(() => this.tick(), this.intervalMs);
    this.tick();
  }
  tick() {
    if (!this.enabled || this.voice.active) return;
    if (this.blocked()) { this.onState("waiting"); return; }
    this.voice.start("");
  }
  pause() { this.voice.cancel(); }
  stop() {
    this.enabled = false;
    clearInterval(this.timer); this.timer = null;
    this.voice.cancel(); this.onState("off");
  }
}
if (typeof module !== "undefined" && module.exports) module.exports.CairoOpenMic = CairoOpenMic;
