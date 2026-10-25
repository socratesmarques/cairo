"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { CairoVoice } = require("../cairo/web/voice.js");

function fixture(overrides = {}) {
  let current;
  class Recognition {
    constructor() { current = this; }
    start() { this.onstart(); }
    stop() { this.onend(); }
    abort() {}
  }
  const states = [], texts = [], done = [], errors = [];
  const voice = new CairoVoice({ Recognition, onState: x => states.push(x), onText: x => texts.push(x), onDone: x => done.push(x), onError: x => errors.push(x), ...overrides });
  return { voice, states, texts, done, errors, current: () => current };
}
function result(text, final) { const r = [{ transcript: text }]; r.isFinal = final; return r; }

test("Portuguese dictation appends to draft and sends only final text", () => {
  const f = fixture(); f.voice.start("Cairo,");
  assert.equal(f.current().lang, "pt-BR");
  f.current().onresult({results:[result("abra", false)]});
  assert.equal(f.done.length, 0);
  f.current().onresult({results:[result("abra o Chrome", true)]});
  f.voice.stop();
  assert.deepEqual(f.done, ["Cairo, abra o Chrome"]);
  assert.equal(f.voice.active, false);
});
test("recognition errors never auto-send a command", () => {
  const f = fixture(); f.voice.start();
  f.current().onresult({results:[result("abra o Chrome", true)]});
  f.current().onerror({error:"not-allowed"}); f.current().onend();
  assert.equal(f.done.length, 0); assert.match(f.errors[0], /Microfone bloqueado/);
});
test("cancel prevents late results from crossing conversations", () => {
  const f = fixture(); f.voice.start(); const callback=f.current().onresult;
  f.voice.cancel(); callback({results:[result("late", true)]});
  assert.equal(f.done.length, 0); assert.equal(f.voice.active, false);
});
test("unsupported browsers expose a useful error", () => {
  const f = fixture({Recognition:null}); f.voice.start();
  assert.match(f.errors[0], /Google Chrome/); assert.equal(f.voice.active, false);
});
test("transcription is bounded and interim-only input is not sent", () => {
  const f = fixture({maxLength:10}); f.voice.start("oi");
  f.current().onresult({results:[result("muito longo texto", false)]});
  assert.equal(f.texts.at(-1).length, 10);
  f.voice.stop(); assert.equal(f.done.length, 0); assert.equal(f.texts.at(-1), "oi");
});
const { CairoOpenMic } = require('../cairo/web/voice.js');
function openFixture() {
  const instances = [], commands = [], errors = [], states = [];
  let blocked = false;
  class Recognition {
    constructor() { instances.push(this); }
    start() { this.onstart(); }
    stop() { this.onend(); }
    abort() {}
  }
  const mic = new CairoOpenMic({Recognition, intervalMs:60000, blocked:()=>blocked,
    onState:x=>states.push(x), onText:()=>{}, onError:x=>errors.push(x),
    onCommand:x=>{ commands.push(x); blocked=true; }});
  return {mic, instances, commands, errors, states, unblock:()=>{blocked=false;}, block:()=>{blocked=true;},
    say(text) {const r=instances.at(-1); r.onresult({results:[result(text,true)]}); r.onend();}};
}
test('open listening sends commands once, waits for work, then rearms', () => {
  const f=openFixture();
  try {
    f.mic.start(); f.say('abra Google');
    assert.deepEqual(f.commands,['abra Google']);
    f.mic.tick(); assert.equal(f.instances.length,1);
    f.unblock(); f.mic.tick(); f.say('abra YouTube Music');
    assert.deepEqual(f.commands,['abra Google','abra YouTube Music']);
  } finally { f.mic.stop(); }
});
test('silence is recoverable, permission denial disables open listening', () => {
  const f=openFixture();
  try {
    f.mic.start(); let r=f.instances.at(-1);
    r.onerror({error:'no-speech'}); r.onend(); f.mic.tick();
    assert.equal(f.instances.length,2); assert.equal(f.errors.length,0);
    f.instances.at(-1).onerror({error:'not-allowed'});
    assert.equal(f.mic.enabled,false); f.mic.tick(); assert.equal(f.instances.length,2);
    assert.equal(f.errors.length,1); assert.equal(f.commands.length,0);
  } finally { f.mic.stop(); }
});
test('spoken stop never becomes an agent command', () => {
  const f=openFixture();
  try { f.mic.start(); f.say('Cairo, parar escuta.'); assert.equal(f.mic.enabled,false); assert.equal(f.commands.length,0); }
  finally {f.mic.stop();}
});
test('stopping rejects late transcripts and cancels restart timer', () => {
  const f=openFixture();
  f.mic.start(); const r=f.instances.at(-1), resultCallback=r.onresult, endCallback=r.onend;
  f.mic.stop(); resultCallback({results:[result('abra Google',true)]}); endCallback(); f.mic.tick();
  assert.equal(f.commands.length,0); assert.equal(f.instances.length,1); assert.equal(f.mic.timer,null);
});
test('speaking pauses capture and blocks restart until playback ends', () => {
  const f=openFixture();
  try {f.mic.start(); f.block(); f.mic.pause(); f.mic.tick(); assert.equal(f.instances.length,1);
    f.unblock(); f.mic.tick(); assert.equal(f.instances.length,2);}
  finally {f.mic.stop();}
});
