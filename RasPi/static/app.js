// ----------------- DOM refs -----------------
const list       = document.getElementById('song-list');
const playBtn    = document.getElementById('play-btn');
const stopBtn    = document.getElementById('stop-btn');
const statusTxt  = document.getElementById('status-text');
const progBar    = document.getElementById('progress-bar');
const ringFg     = document.getElementById('ring-fg');
const playingSec = document.getElementById('playing-view');
const nowTitle   = document.getElementById('now-title');

// state
let selectedSong = null;
let progTimer    = null;

// --------------- song-card factory  (old tap logic) ---------------
function makeCard(name) {
  const card = document.createElement('div');
  card.className  = 'song-card';
  card.textContent = name;

  /* OLD BEHAVIOUR - a simple tap on finger-up selects the card.
     No pointer-capture, no drag detection exactly as before.   */
  card.addEventListener('pointerup', () => select(card, name));

  return card;
}

// ----------------- apply visual selection -----------------
function select(card, name) {
  selectedSong = name;

  /* Remove highlight from any card that still has it */
  document.querySelectorAll('.song-card.selected')
          .forEach(el => el.classList.remove('selected'));

  card.classList.add('selected');
  playBtn.disabled = false;
  statusTxt.textContent = `Selected: ${name}`;
}

// ----------------- view switching -----------------
function showPlaying(show){
  playingSec.classList.toggle('active',show);
}

// ----------------- network calls -----------------
async function fetchJSON(url,opts){
  const r = await fetch(url,opts); return r.json();
}

// ----------------- event handlers -----------------
playBtn.addEventListener('pointerup',()=>safeRun(playBtn,async()=>{
  if(!selectedSong) return;
  await fetchJSON('/play',{method:'POST',headers:{'Content-Type':'application/json'},
                            body:JSON.stringify({song:selectedSong})});
}));

stopBtn.addEventListener('pointerup',()=>safeRun(stopBtn,async()=>{
  await fetchJSON('/stop',{method:'POST'});
}));

// disable rapid double-taps
async function safeRun(btn,fn){
  btn.style.pointerEvents='none';
  try{await fn();}finally{btn.style.pointerEvents='';}
}

// ----------------- polling -----------------
async function pollStatus(){
  try{
    const d=await fetchJSON('/status');
    statusTxt.textContent = d.state==='playing' ? `Playing: ${d.song}` : 'Idle';

    if(d.state==='playing'){            // enter playing view
      nowTitle.textContent = `Now Playing: ${d.song}`;
      showPlaying(true);
      if(!progTimer) progTimer=setInterval(pollProgress,120);
      playBtn.disabled=true;
    }else{                              // back to library
      showPlaying(false);
      clearInterval(progTimer); progTimer=null;
      playBtn.disabled=!selectedSong;
    }
  }catch{statusTxt.textContent='Status error';}
}

async function pollProgress(){
  try{
    const {pct} = await fetchJSON('/progress');
    const clamped = Math.min(1,Math.max(0,pct));
    ringFg.style.strokeDashoffset = 339 * (1-clamped);
  }catch{/* ignore */}
}

// ----------------- init -----------------
async function init(){
  // load songs
  try{
    const songs = await fetchJSON('/songs');
    songs.sort((a,b)=>a.localeCompare(b,undefined,{sensitivity:'base'}))
         .forEach(n=>list.appendChild(makeCard(n)));
  }catch{statusTxt.textContent='Error loading songs';}

  pollStatus();
  setInterval(pollStatus,1000);
}

window.addEventListener('DOMContentLoaded',init);
