/* ── SAVED CHATS: the backend stores them in Chats/ (git-ignored), so every device sees the same list ── */
var chatId=null, chatList=[], chatQuery='', chatSearchT=null;
var chatSavedSig='', chatSavedLen=0, chatSaving=false, chatRetryAt=0;

function chatApi(path,opts){
  opts=opts||{};
  if(opts.body&&!opts.headers) opts.headers={'Content-Type':'application/json'};
  return bfetch(backend()+path,opts).then(function(r){
    return r.json().catch(function(){return {};}).then(function(j){
      if(!r.ok) throw new Error(j.detail||('HTTP '+r.status));
      return j;
    });
  });
}
function chatNewId(){return Date.now().toString(36)+Math.random().toString(36).slice(2,8);}
function chatSig(){
  var l=chatHistory[chatHistory.length-1];
  return chatHistory.length+':'+(l&&typeof l.content==='string'?l.content.length:0);
}
function chatPayload(){
  return chatHistory.filter(function(m){return m&&(m.role==='user'||m.role==='assistant')&&typeof m.content==='string';})
    .map(function(m){return {role:m.role,content:m.content};});
}
function chatBusy(){
  if(sendBtn.disabled){stL.textContent='wait for the reply to finish first';return true;}
  return false;
}

async function saveChatNow(){
  if(chatSaving||!API_KEY) return;
  if(!chatHistory.length){chatId=null;chatSavedLen=0;chatSavedSig='';return;}
  var sig=chatSig();
  if(sig===chatSavedSig) return;
  var msgs=chatPayload();
  if(!msgs.length) return;
  // History got cut (personality switch): start a new chat so the saved one is never overwritten.
  if(chatId&&chatHistory.length<chatSavedLen) chatId=null;
  var id=chatId||chatNewId();
  chatSaving=true;
  try{
    var r=await chatApi('/chats/'+encodeURIComponent(id),{method:'PUT',body:JSON.stringify({messages:msgs})});
    chatId=id;chatSavedSig=sig;chatSavedLen=chatHistory.length;
    if(chatQuery){loadChatList();}
    else{
      chatList=chatList.filter(function(c){return c.id!==r.id;});
      chatList.unshift({id:r.id,title:r.title,updated:r.updated,count:r.count});
      renderChatList();
    }
  }catch(e){chatRetryAt=Date.now()+10000;console.warn('chat save failed:',e.message);}
  chatSaving=false;
}
async function chatFlush(){
  for(var i=0;i<40&&chatSaving;i++) await new Promise(function(r){setTimeout(r,50);});
  await saveChatNow();
}
setInterval(function(){if(Date.now()>=chatRetryAt) saveChatNow();},2000);

async function loadChatList(){
  if(!API_KEY) return;
  var q=chatQuery;
  try{
    var j=await chatApi('/chats'+(q?'?q='+encodeURIComponent(q):''));
    if(q!==chatQuery) return;   // a newer search is already running
    chatList=j.chats||[];renderChatList();
  }catch(e){console.warn('chat list failed:',e.message);}
}

function renderChatList(){
  var el=document.getElementById('ch-list');
  if(!el) return;
  if(!chatList.length){el.innerHTML='<div class="sb-nores">'+(chatQuery?'No chats match':'No saved chats yet')+'</div>';return;}
  el.innerHTML=chatList.map(function(c){
    return '<div class="ch-item'+(c.id===chatId?' active':'')+'" role="listitem" tabindex="0" data-id="'+escHtml(c.id)+'">'+
      '<div class="ch-main"><div class="ch-title">'+escHtml(c.title)+'</div>'+(c.snippet?'<div class="ch-snip">'+escHtml(c.snippet)+'</div>':'')+'</div>'+
      '<span class="ch-act"><button type="button" class="ch-ib" data-act="rename" aria-label="Rename chat" title="Rename">✎</button>'+
      '<button type="button" class="ch-ib" data-act="del" aria-label="Delete chat" title="Delete">×</button></span></div>';
  }).join('');
}

function chatReset(msg){
  chatId=null;chatHistory=[];chatSavedLen=0;chatSavedSig='';
  msgsEl.innerHTML='';
  if(msg) addMsg('ai',msg);
  stL.textContent='ready';stR.textContent='';
  renderChatList();
}
async function newChat(){
  if(chatBusy()) return;
  await chatFlush();
  chatReset('New chat started.');
  closeDrawers();
  textarea.focus();
}
async function openChat(id){
  if(id===chatId){closeDrawers();return;}
  if(chatBusy()) return;
  await chatFlush();
  try{
    var c=await chatApi('/chats/'+encodeURIComponent(id));
    chatId=c.id;
    chatHistory=(c.messages||[]).map(function(m){return {role:m.role,content:m.content};});
    chatSavedLen=chatHistory.length;chatSavedSig=chatSig();
    msgsEl.innerHTML='';
    var when=c.updated?new Date(c.updated).toLocaleString('en-US',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}):'saved';
    chatHistory.forEach(function(m){
      var txt=m.content;
      if(m.role==='user'){if(txt.indexOf(ACTION_RESULT_TAG)===0) return;}
      else{if(txt.indexOf('[Results]')===0) return;txt=stripActions(txt);}
      if(!txt.trim()) return;
      var d=addMsg(m.role==='user'?'user':'ai',txt);
      var meta=d.querySelector('.msg-meta');
      if(meta) meta.textContent=(m.role==='user'?'YOU':'SENTINEL')+' · '+when;
    });
    autoScroll();
    stL.textContent='ready';stR.textContent='';
    renderChatList();closeDrawers();
  }catch(e){stL.textContent='could not open chat: '+e.message;}
}

function chatRename(item,id){
  var c=chatList.find(function(x){return x.id===id;});
  var main=item.querySelector('.ch-main');
  if(!c||!main) return;
  var inp=document.createElement('input');
  inp.className='ch-edit';inp.value=c.title;inp.maxLength=80;inp.setAttribute('aria-label','Chat title');
  var done=false;
  function finish(save){
    if(done) return;done=true;
    var t=inp.value.trim();
    if(save&&t&&t!==c.title){
      chatApi('/chats/'+encodeURIComponent(id)+'/rename',{method:'POST',body:JSON.stringify({title:t})})
        .then(function(r){c.title=r.title;renderChatList();})
        .catch(function(e){stL.textContent='rename failed: '+e.message;renderChatList();});
    }else renderChatList();
  }
  inp.addEventListener('keydown',function(e){
    if(e.key==='Enter'){e.preventDefault();finish(true);}
    else if(e.key==='Escape'){finish(false);}
  });
  inp.addEventListener('blur',function(){finish(true);});
  item.classList.add('editing');
  item.replaceChild(inp,main);
  inp.focus();inp.select();
}
function chatDelete(btn,id){
  if(!btn.classList.contains('confirm')){
    btn.classList.add('confirm');btn.textContent='Delete?';btn.setAttribute('aria-label','Confirm delete');
    setTimeout(function(){
      if(btn.isConnected&&btn.classList.contains('confirm')){btn.classList.remove('confirm');btn.textContent='×';btn.setAttribute('aria-label','Delete chat');}
    },3000);
    return;
  }
  if(id===chatId&&chatBusy()) return;
  chatApi('/chats/'+encodeURIComponent(id),{method:'DELETE'}).then(function(){
    chatList=chatList.filter(function(x){return x.id!==id;});
    if(id===chatId) chatReset('Chat deleted.');
    else renderChatList();
  }).catch(function(e){stL.textContent='delete failed: '+e.message;});
}

(function(){
  var list=document.getElementById('ch-list');
  list.addEventListener('click',function(e){
    if(e.target.closest('.ch-edit')) return;
    var item=e.target.closest('.ch-item');
    if(!item) return;
    var id=item.getAttribute('data-id'),b=e.target.closest('.ch-ib');
    if(b){e.stopPropagation();if(b.getAttribute('data-act')==='rename') chatRename(item,id);else chatDelete(b,id);return;}
    openChat(id);
  });
  list.addEventListener('keydown',function(e){
    if((e.key==='Enter'||e.key===' ')&&e.target.classList&&e.target.classList.contains('ch-item')){
      e.preventDefault();openChat(e.target.getAttribute('data-id'));
    }
  });
  var inp=document.getElementById('chatSearch'),clr=document.getElementById('chatSearchClear');
  function setQ(v){inp.value=v;chatQuery=v.trim();loadChatList();}
  inp.addEventListener('input',function(){
    clearTimeout(chatSearchT);
    chatSearchT=setTimeout(function(){chatQuery=inp.value.trim();loadChatList();},250);
  });
  inp.addEventListener('keydown',function(e){if(e.key==='Escape'&&inp.value) setQ('');});
  clr.addEventListener('click',function(){setQ('');inp.focus();});
  setInterval(function(){if(!document.hidden&&!chatQuery&&!document.querySelector('.ch-edit')) loadChatList();},20000);
  document.addEventListener('visibilitychange',function(){
    if(document.hidden) saveChatNow();
    else if(!chatQuery) loadChatList();
  });
})();

// One-time import of the old per-browser history (localStorage) into the server's Chats/ folder.
async function chatMigrateOld(){
  if(!API_KEY||!sessions.length) return;
  try{
    var old=sessions.slice().reverse();
    for(var i=0;i<old.length;i++){
      var s=old[i];
      var msgs=(s.history||[]).filter(function(m){return m&&(m.role==='user'||m.role==='assistant')&&typeof m.content==='string';})
        .map(function(m){return {role:m.role,content:m.content};});
      if(!msgs.length) continue;
      var t=+s.id||Date.parse(s.time)||Date.now();
      await chatApi('/chats/old'+String(s.id).replace(/[^A-Za-z0-9_-]/g,''),{method:'PUT',body:JSON.stringify({messages:msgs,title:String(s.preview||'').slice(0,60),created:t,updated:t,keep_time:true})});
    }
    sessions=[];
    try{localStorage.removeItem('sentinel_sessions');}catch(e){}
  }catch(e){console.warn('old session import failed:',e.message);}
}

