// Click-through test for the action follow-up loop in sentinel_v2.html (mock Ollama + mock /exec).
// Needs jsdom (not in the repo):  mkdir -p ~/.cache/sentinel-jsdom && cd ~/.cache/sentinel-jsdom && npm i jsdom@22
// Run:  JSDOM_PATH=~/.cache/sentinel-jsdom/node_modules/jsdom node tools/test_followup_loop.js
const path = require('path');
const fs = require('fs');
const {JSDOM} = require(process.env.JSDOM_PATH || 'jsdom');
const html = fs.readFileSync(path.join(__dirname, '..', 'sentinel_v2.html'), 'utf8');
const chatReqs = [], execCmds = [];
let replies = [];
function ndjson(text) {
  const enc = new TextEncoder();
  const line = JSON.stringify({message: {content: text}, done: false}) + '\n';
  let sent = false;
  return {ok: true, status: 200, body: {getReader() {
    return {read: async () => sent ? {done: true} : (sent = true, {done: false, value: enc.encode(line)})};
  }}};
}
async function mockFetch(url, opts) {
  url = String(url);
  if (url.includes('/api/chat')) { chatReqs.push(JSON.parse(opts.body)); return ndjson(replies.shift() || '(no more replies)'); }
  if (url.includes('/exec')) {
    const b = JSON.parse(opts.body); execCmds.push(b.command);
    return {ok: true, status: 200, json: async () => ({stdout: 'OUTPUT-OF:' + b.command, stderr: '', returncode: 0})};
  }
  return {ok: false, status: 404, json: async () => ({}), text: async () => '', blob: async () => null};
}
const dom = new JSDOM(html, {runScripts: 'dangerously', url: 'http://localhost:8766/', pretendToBeVisual: true,
  beforeParse(w) {
    w.fetch = mockFetch; w.TextDecoder = TextDecoder; w.localStorage.setItem('sentinel_api_key', 'test');
    w.HTMLElement.prototype.scrollTo = function () {}; w.Element.prototype.scrollIntoView = function () {};
  }});
const w = dom.window;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const act = cmd => '<ACTION>' + JSON.stringify({type: 'run_command', command: cmd, description: 'x'}) + '</ACTION>';
let fails = 0;
function check(name, ok) { console.log((ok ? 'PASS ' : 'FAIL ') + name); if (!ok) fails++; }
const lastMsg = i => chatReqs[i].messages[chatReqs[i].messages.length - 1];
(async () => {
  await sleep(500);
  const first = [{action: {type: 'run_command', command: 'df -h', description: 'disk'}, result: {ok: true, output: '/dev/sda1 50%'}}];
  w.chatHistory.length = 0;
  w.chatHistory.push({role: 'user', content: 'check my disk'}, {role: 'assistant', content: 'ok'},
    {role: 'user', content: w.ACTION_RESULT_TAG + '\nAction "disk" → success: /dev/sda1 50%'});
  // 1) chain: read-only follow-up runs, output goes back, final answer
  replies = ['Checking inodes. ' + act('df -i'), 'All good.'];
  await w.followUpLoop('mistral:latest', 'brief', first);
  check('chain made 2 model calls', chatReqs.length === 2);
  check('read-only follow-up ran without a prompt', execCmds.length === 1 && execCmds[0] === 'df -i');
  check('second call carries the output back as a user message',
    lastMsg(1).role === 'user' && lastMsg(1).content.startsWith('[Action results') && lastMsg(1).content.includes('OUTPUT-OF:df -i'));
  check('results message ends with the answer-from-output instruction', lastMsg(1).content.includes('Answer my last question'));
  // 2) command that changes things must ask; No ends the chain
  chatReqs.length = 0; execCmds.length = 0;
  replies = ['Cleaning up. ' + act('rm -rf /tmp/x'), 'SHOULD-NOT-BE-REQUESTED'];
  const p = w.followUpLoop('mistral:latest', 'brief', first);
  await sleep(400);
  check('confirm dialog shown for rm', w.document.getElementById('confirm-modal').classList.contains('show'));
  w.document.getElementById('cm-no').click();
  await p;
  check('rm never executed', execCmds.length === 0);
  check('chain stopped after cancel (no extra model call)', chatReqs.length === 1);
  // 3) model repeats a command that already ran: not run again, but it gets nudged to answer
  chatReqs.length = 0; execCmds.length = 0;
  replies = ['Again. ' + act('df -h'), 'Root is at 98 percent.'];
  await w.followUpLoop('mistral:latest', 'brief', first);
  check('repeat of an already-run action is not run again', execCmds.length === 0);
  check('blocked repeat triggers a nudge and a second model call',
    chatReqs.length === 2 && lastMsg(1).role === 'user' && lastMsg(1).content.includes('already ran') && lastMsg(1).content.includes('Answer my last question'));
  // 4) step limit
  chatReqs.length = 0; execCmds.length = 0;
  replies = [act('ls /a'), act('ls /b'), act('ls /c'), 'extra'];
  await w.followUpLoop('mistral:latest', 'brief', first);
  check('limit: 3 model calls, 2 extra command rounds', chatReqs.length === 3 && execCmds.length === 2);
  check('limit message shown', w.document.body.textContent.includes('Stopped after 3 follow-up steps'));
  console.log(fails ? '\n' + fails + ' FAILED' : '\nALL PASSED');
  process.exit(fails ? 1 : 0);
})().catch(e => { console.error('ERR', e); process.exit(2); });
