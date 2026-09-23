/* ui.h - the phone page served at http://hs300relay.local/ui (or by IP).
 * Four toggle buttons, ALL OFF, live status every 2 s, and the round-trip
 * time of every command measured in the browser (fetch start to reply). */
#pragma once
static const char UI_HTML[] PROGMEM = R"HTML(<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HS300 relay box</title>
<style>
body{font-family:system-ui,sans-serif;background:#111;color:#eee;margin:0;padding:16px}
h1{font-size:18px;margin:0 0 12px}
.b{display:block;width:100%;padding:18px;margin:8px 0;font-size:20px;border:0;border-radius:10px;color:#fff;background:#333}
.on{background:#c62828}.off{background:#2e7d32}.all{background:#555}
#s{font-family:monospace;white-space:pre;margin-top:12px;color:#9cf}
#l{font-family:monospace;font-size:14px;color:#aaa;white-space:pre;margin-top:8px;max-height:40vh;overflow:auto}
</style></head><body>
<h1>HS300 relay box</h1>
<button class="b" id="r1" onclick="tog(1)">LOAD</button>
<button class="b" id="r2" onclick="tog(2)">STRING</button>
<button class="b" id="r3" onclick="tog(3)">SPARE 3</button>
<button class="b" id="r4" onclick="tog(4)">SPARE 4</button>
<button class="b all" onclick="cmd('ALL OFF')">ALL OFF</button>
<div id="s">...</div><div id="l"></div>
<script>
var st=[0,0,0,0];
var names=['LOAD','STRING','SPARE 3','SPARE 4'];
function paint(t){var m=t.match(/R1=(\d) R2=(\d) R3=(\d) R4=(\d)/);if(!m)return;
 for(var i=0;i<4;i++){st[i]=+m[i+1];var b=document.getElementById('r'+(i+1));
  b.className='b '+(st[i]?'on':'off');b.textContent=names[i]+(st[i]?(i==1?'  OUT':'  ON'):(i==1?'  IN':'  OFF'));}
 document.getElementById('s').textContent=t;}
function cmd(c){var t0=performance.now();
 fetch('/cmd?c='+encodeURIComponent(c)).then(function(r){return r.text()}).then(function(t){
  var ms=(performance.now()-t0).toFixed(0);paint(t);
  var l=document.getElementById('l');l.textContent=new Date().toLocaleTimeString()+'  '+c+'  '+ms+' ms\n'+l.textContent;
 }).catch(function(e){document.getElementById('s').textContent='no reply: '+e;});}
function tog(i){cmd('R'+i+(st[i-1]?' OFF':' ON'));}
function poll(){fetch('/status').then(function(r){return r.text()}).then(paint).catch(function(){});}
poll();setInterval(poll,2000);
</script></body></html>)HTML";
