/* ===== Recorder Pages — Shared Functions ===== */

// ---- Time utilities ----
function parseTime(v){
    v=(v||'').trim();
    if(!v)return 0;
    if(v.includes(':')){
        var p=v.split(':');
        if(p.length===2)return parseFloat(p[0])*60+parseFloat(p[1]);
        if(p.length===3)return parseFloat(p[0])*3600+parseFloat(p[1])*60+parseFloat(p[2]);
        return 0;
    }
    return parseFloat(v)||0;
}

function fmtTime(s){
    if(isNaN(s)||s<0)return'0:00.000';
    var ms=Math.round(s*1000),m=Math.floor(ms/60000);
    ms%=60000;
    var sec=Math.floor(ms/1000);
    ms%=1000;
    return m+':'+(sec<10?'0':'')+sec+'.'+(ms<100?(ms<10?'00':'0'):'')+ms;
}

function getTime(minId, inputId, parsedId){
    var el1=document.getElementById(minId||'timeMin');
    var el2=document.getElementById(inputId||'timeInput');
    var el3=document.getElementById(parsedId||'parsedTime');
    var min=parseInt(el1?el1.value:0)||0;
    var t=min*60+parseTime(el2?el2.value:'0');
    if(el3)el3.textContent=fmtTime(t);
    return t;
}

// ---- Calc preview ----
var _recorderLastProjectKey=null;
function setRecorderProjectKey(key){_recorderLastProjectKey=key;}

function calcPreview(){
    var sel=document.getElementById('projectId');
    var raw=getTime('timeMin','timeInput','parsedTime');
    var vio=parseInt(document.getElementById('violations')?document.getElementById('violations').value:0)||0;
    var opt=sel.options[sel.selectedIndex]||sel.querySelector('option[value="'+sel.value+'"]');
    var pen=opt?parseFloat(opt.dataset.penalty):0;
    var p=vio*pen,fin=raw+p;
    var rawEl=document.getElementById('calcRaw');
    var penEl=document.getElementById('calcPenalty');
    var finEl=document.getElementById('calcFinal');
    if(rawEl)rawEl.textContent=fmtTime(raw);
    if(penEl)penEl.textContent=fmtTime(p);
    if(finEl)finEl.textContent=fmtTime(fin);
}

function adjViolation(delta){
    var el=document.getElementById('violations');
    if(!el)return;
    var v=parseInt(el.value)||0;
    el.value=Math.max(0,v+delta);
    calcPreview();
}

function quickTime(sec, minId, inputId){
    var min=Math.floor(sec/60);
    var s=sec-min*60;
    var el1=document.getElementById(minId||'timeMin');
    var el2=document.getElementById(inputId||'timeInput');
    if(el1)el1.value=min;
    if(el2)el2.value=s;
    getTime(minId,inputId,'parsedTime');
    calcPreview();
    if(el2){el2.focus();el2.select();}
}

// ---- Stopwatch ----
var stopwatchInterval=null;
var stopwatchRunning=false;
var stopwatchStartTime=0;
var stopwatchElapsed=0;

function startStopwatch(){
    if(stopwatchRunning)return;
    var btn=document.getElementById('startBtn');
    if(btn&&btn.disabled)return;
    stopwatchRunning=true;
    stopwatchStartTime=Date.now()-stopwatchElapsed;
    if(btn)btn.disabled=true;
    var stopBtn=document.getElementById('stopBtn');
    if(stopBtn)stopBtn.disabled=false;
    stopwatchInterval=setInterval(function(){
        document.getElementById('stopwatchDisplay').textContent=fmtTime((Date.now()-stopwatchStartTime)/1000);
    },10);
}

function stopStopwatch(){
    if(!stopwatchRunning)return;
    stopwatchRunning=false;
    clearInterval(stopwatchInterval);
    stopwatchInterval=null;
    stopwatchElapsed=Date.now()-stopwatchStartTime;
    var sec=stopwatchElapsed/1000;
    document.getElementById('stopwatchDisplay').textContent=fmtTime(sec);
    var startBtn=document.getElementById('startBtn');
    if(startBtn)startBtn.disabled=false;
    var stopBtn=document.getElementById('stopBtn');
    if(stopBtn)stopBtn.disabled=true;
    var intSec=Math.floor(sec);
    var min=Math.floor(intSec/60);
    var s=intSec%60;
    var ms=Math.round((sec-intSec)*1000);
    var el1=document.getElementById('timeMin');
    var el2=document.getElementById('timeInput');
    if(el1)el1.value=min;
    if(el2)el2.value=s+'.'+(ms<100?(ms<10?'00':'0'):'')+ms;
    getTime('timeMin','timeInput','parsedTime');
    calcPreview();
}

function resetStopwatch(){
    if(stopwatchRunning){
        clearInterval(stopwatchInterval);
        stopwatchInterval=null;
        stopwatchRunning=false;
    }
    stopwatchElapsed=0;
    document.getElementById('stopwatchDisplay').textContent='0:00.000';
    var startBtn=document.getElementById('startBtn');
    if(startBtn)startBtn.disabled=false;
    var stopBtn=document.getElementById('stopBtn');
    if(stopBtn)stopBtn.disabled=true;
}

// ---- Success overlay ----
function showSuccessOverlay(finalTime, mode, recorderId){
    var pName=document.getElementById('participantName')?document.getElementById('participantName').textContent:'';
    var sel=document.getElementById('projectId');
    var pProject=sel.options[sel.selectedIndex].text;
    var label=mode==='score'?'成绩: ':'用时: ';
    var display=mode==='score'?finalTime:fmtTime(finalTime);
    var overlay=document.createElement('div');
    overlay.id='successOverlay';
    overlay.innerHTML='<div class="box"><div class="icon">🎉</div><h2>提交成功!</h2><p>'+pName+'</p><p>'+pProject+'</p><div class="time-result">'+label+display+'</div><div class="actions"><button class="btn btn-secondary" onclick="window.close()">关闭网页</button><a href="/recorder/'+recorderId+'/scan" class="btn btn-primary">录入员首页</a></div><div class="auto-hint">3秒后自动跳转...</div></div>';
    document.body.appendChild(overlay);
    setTimeout(function(){window.location.href='/recorder/'+recorderId+'/scan';},3000);
}
