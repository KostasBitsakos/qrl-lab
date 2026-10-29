"""Right-click / middle-click on a dashboard tab opens ?tab=<label> in a new browser tab (R-20261028-002 item 7).
The script runs in a same-origin component iframe and attaches listeners to the parent page's tab buttons.
Left click is untouched (no listener on 'click'; contextmenu/auxclick only)."""

SCRIPT = """<script>(function(){
var doc;try{doc=window.parent.document;}catch(e){return;}
function url(label){var u=new URL(window.parent.location.href);u.search='';u.hash='';u.searchParams.set('tab',label);return u.toString();}
function bind(){doc.querySelectorAll('button[role="tab"]').forEach(function(b){
  if(b.dataset.qrlTabLink)return;b.dataset.qrlTabLink='1';b.title=(b.title||'')+'Δεξί κλικ: άνοιγμα σε νέο tab';
  function open(ev){ev.preventDefault();ev.stopPropagation();
    var label=(b.innerText||b.textContent||'').trim();window.parent.open(url(label),'_blank');}
  b.addEventListener('contextmenu',open);
  b.addEventListener('auxclick',function(ev){if(ev.button===1)open(ev);});
});}
bind();
if(!doc.body.dataset.qrlTabObs){doc.body.dataset.qrlTabObs='1';new MutationObserver(bind).observe(doc.body,{childList:true,subtree:true});}
})();</script>"""
