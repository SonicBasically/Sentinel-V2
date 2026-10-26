// Click-through test for spoken requests handed to the chat window (sentinel_v2.html): mock Ollama, /exec, /tts and the backend voice routes.
// Needs jsdom:  mkdir -p ~/.cache/sentinel-jsdom && cd ~/.cache/sentinel-jsdom && npm i jsdom@22
// Run:  JSDOM_PATH=~/.cache/sentinel-jsdom/node_modules/jsdom node tools/test_voice_handoff.js
const path = require('path');
const fs = require('fs');
const {JSDOM} = require(process.env.JSDOM_PATH || 'jsdom');
const html = fs.readFileSync(path.join(__dirname, '..', 'sentinel_v2.html'), 'utf8');
const chatReqs = [], execCmds = [], ttsTexts = [], questions = [], urls = [];
let replies = [], polled = [], chatStatus = 200;
function ndjson(text) {
  const enc = new TextEncoder();
  const line = JSON.stringify({message: {content: text}, done: false}) + '\n';
  let sent = false;
  return {ok: true, status: 200, body: {getReader() {
    return {read: async () => sent ? {done: true} : (sent = true, {done: false, value: enc.encode(line)})};
  }}};
}
async function mockFetch(url, opts) {
  url = String(url); urls.push(url);
  if (url.includes('/api/chat')) {
    chatReqs.push(JSON.parse(opts.body));
    if (chatStatus !== 200) return {ok: false, status: chatStatus, body: null};
    return ndjson(replies.shift() || '(no more replies)');
  }
  if (url.includes('/exec')) {
    const b = JSON.parse(opts.body); execCmds.push(b.command);
    return {ok: true, status: 200, json: async () => ({stdout: 'OUTPUT-OF:' + b.command, stderr: '', returncode: 0})};
  }
  if (url.includes('/tts')) { ttsTexts.push(JSON.parse(opts.body).text); return {ok: true, status: 200, json: async () => ({})}; }
  if (url.includes('/api/voice/question')) { questions.push(JSON.parse(opts.body)); return {ok: true, status: 200, json: async () => ({followup: true})}; }
  if (url.includes('/modes/')) return {ok: true, status: 200, json: async () => ({text: 'MODE-DOC-TEXT'})};
  if (url.includes('/api/voice/last_response')) {
    const next = polled.shift();
    return {ok: true, status: 200, json: async () => next
      ? Object.assign({status: 'new', listening: true, processing: false, wake: {enabled: true, state: 'idle'}}, next)
      : {status: 'empty', listening: true, processing: false, wake: {enabled: true, state: 'idle'}}};
  }
  return {ok: false, status: 404, json: async () => ({}), text: async () => '', blob: async () => null};
}
const dom = new JSDOM(html, {runScripts: 'dangerously', url: 'http://localhost:8766/', pretendToBeVisual: true,
  beforeParse(w) {
    w.fetch = mockFetch; w.TextDecoder = TextDecoder; w.localStorage.setItem('sentinel_api_key', 'test');
    w.HTMLElement.prototype.scrollTo = function () {}; w.Element.prototype.scrollIntoView = function () {};
    w.speechSynthesis = undefined;
  }});
const w = dom.window;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const act = cmd => '<ACTION>' + JSON.stringify({type: 'run_command', command: cmd, description: 'x'}) + '</ACTION>';
let fails = 0;
function check(name, ok) { console.log((ok ? 'PASS ' : 'FAIL ') + name); if (!ok) fails++; }
const sys = i => chatReqs[i].messages[0].content;
async function until(fn, ms) { const t = Date.now(); while (!fn() && Date.now() - t < ms) await sleep(50); return fn(); }
(async () => {
  await sleep(500);
  w.ttsEnabled = true;
  w.chatHistory.length = 0;
  const draft = 'half-typed message';
  const ta = w.textarea; ta.value = draft;

  // 1) a handoff arrives through the poll, runs a read-only command, answers with a question
  replies = ['Let me look. ' + act('df -h'), 'The root drive is at 98 percent. Want me to look for big folders?'];
  polled = [{transcript: 'why is my disk full', reply: '', handoff: true}];
  check('turn finished and reported to the backend', await until(() => questions.length === 1, 6000));
  check('model got the spoken words as the user message', chatReqs[0].messages.some(m => m.role === 'user' && m.content === 'why is my disk full'));
  check('first request carries the mode document context', /=== CONTEXT:/.test(sys(0)) && sys(0).includes('MODE-DOC-TEXT'));
  check('first request carries the spoken-style instruction', sys(0).includes('=== VOICE ==='));
  check('follow-up request keeps the spoken-style instruction', chatReqs.length === 2 && sys(1).includes('=== VOICE ==='));
  check('the command ran', execCmds.length === 1 && execCmds[0] === 'df -h');
  check('output went back to the model', chatReqs[1].messages[chatReqs[1].messages.length - 1].content.includes('OUTPUT-OF:df -h'));
  check('both replies were spoken', ttsTexts.length === 2 && ttsTexts[1].startsWith('The root drive is at 98 percent'));
  check('backend told the final reply and that it was spoken',
    questions[0].reply === 'The root drive is at 98 percent. Want me to look for big folders?' && questions[0].spoken === true);
  check('typed draft untouched', ta.value === draft);
  check('simple-command routes were not tried for a spoken request', !urls.some(u => /\/command\b|\/games\/(resolve|launch)/.test(u)));
  check('send button free again', w.document.getElementById('sendBtn').disabled === false);

  // 2) a typed message right after is a normal one (no spoken-style instruction)
  chatReqs.length = 0; ttsTexts.length = 0; questions.length = 0;
  replies = ['Hello there.'];
  ta.value = 'hello';
  await w.send();
  check('typed request has no spoken-style instruction', chatReqs.length === 1 && !sys(0).includes('=== VOICE ==='));
  check('typed request does not report to the voice backend', questions.length === 0);

  // 3) two spoken requests in a row run one after the other, in order
  chatReqs.length = 0; ttsTexts.length = 0; questions.length = 0;
  replies = ['First answer.', 'Second answer.'];
  polled = [{transcript: 'first thing', reply: '', handoff: true}, {transcript: 'second thing', reply: '', handoff: true}];
  check('both reported', await until(() => questions.length === 2, 6000));
  const userMsgs = chatReqs.map(r => r.messages[r.messages.length - 1].content);
  check('answered in order', userMsgs[0] === 'first thing' && userMsgs[1] === 'second thing');
  check('second request saw the first answer in history', chatReqs[1].messages.some(m => m.role === 'assistant' && m.content === 'First answer.'));

  // 4) with the voice turned off nothing is spoken and the backend is told so
  chatReqs.length = 0; ttsTexts.length = 0; questions.length = 0;
  w.ttsEnabled = false;
  replies = ['Silent answer?'];
  polled = [{transcript: 'say something', reply: '', handoff: true}];
  check('reported without speech', await until(() => questions.length === 1, 6000) && questions[0].spoken === false && ttsTexts.length === 0);
  w.ttsEnabled = true;

  // 5) the model is unreachable: a short spoken apology, no crash, button freed
  chatReqs.length = 0; ttsTexts.length = 0; questions.length = 0;
  chatStatus = 500;
  polled = [{transcript: 'anything', reply: '', handoff: true}];
  check('apology spoken', await until(() => ttsTexts.length === 1, 6000) && ttsTexts[0].startsWith('Sorry'));
  await sleep(300);
  check('send button free after the error', w.document.getElementById('sendBtn').disabled === false);
  chatStatus = 200;

  // 6) an ordinary (non-handoff) spoken reply still shows and speaks as before
  ttsTexts.length = 0;
  polled = [{transcript: 'pause', reply: 'Paused.', handoff: false}];
  check('plain command reply is spoken', await until(() => ttsTexts.length === 1, 6000) && ttsTexts[0] === 'Paused.');
  console.log(fails ? '\n' + fails + ' FAILED' : '\nALL PASSED');
  process.exit(fails ? 1 : 0);
})().catch(e => { console.error('ERR', e); process.exit(2); });
