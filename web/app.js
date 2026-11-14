let project;
let lastArrangement = null;
let buildReady = false;
let editingColumn = null;
let addingBoxesToColumn = null;
const $ = id => document.getElementById(id);
function setBusy(message, busy=true){$('busyMessage').textContent=message;$('busyOverlay').hidden=!busy;}
function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));}
async function loadExample(){ project = await (await fetch('/api/example')).json(); render(); }
function emptyProject(){ return {version:1,drawer:{width:580,depth:580},defaults:{height:40,wall:2,r:4,cover_width:32,cover_width_short:28,short_depth_below:45},columns:[]}; }
function render(){
  const d=project.drawer, defs=project.defaults;
  $('drawerWidth').value=d.width;$('drawerDepth').value=d.depth;$('height').value=defs.height;$('wall').value=defs.wall;$('radius').value=defs.r;
  const scale=Math.min(1.35, Math.max(0.5, (innerWidth-340)/d.width));
  const canvas=$('canvas');canvas.style.width=`${d.width*scale}px`;canvas.style.height=`${d.depth*scale}px`;canvas.innerHTML='';
  const topAdd=document.createElement('button');topAdd.className='edge-add top';topAdd.textContent='+';topAdd.setAttribute('aria-label','Add column at top edge');topAdd.onclick=openColumnDialog;
  const bottomAdd=document.createElement('button');bottomAdd.className='edge-add bottom';bottomAdd.textContent='+';bottomAdd.setAttribute('aria-label','Add column at bottom edge');bottomAdd.onclick=openColumnDialog;canvas.append(topAdd,bottomAdd);
  renderRulers(d,scale);
  canvas.onmousemove=event=>{const rect=canvas.getBoundingClientRect();const x=Math.max(0,Math.min(d.width,(event.clientX-rect.left)/scale));const y=Math.max(0,Math.min(d.depth,(rect.bottom-event.clientY)/scale));$('cursorPosition').textContent=`Cursor: (${x.toFixed(1)}, ${y.toFixed(1)}) mm`;};
  canvas.onmouseleave=()=>{$('cursorPosition').textContent='Cursor: (0, 0) mm';};
  let x=0,total=0,unique=new Set();
  project.columns.forEach((c, columnIndex)=>{let y=0;let boxIndex=0;const col=document.createElement('div');col.className='column';col.style.left=`${x*scale}px`;col.style.width=`${c.width*scale}px`;const h=document.createElement('button');h.className='column-title';h.textContent=`${c.name} (${c.width} mm)`;h.title='Edit column';h.onclick=()=>openColumnEditor(columnIndex);col.append(h);const remove=document.createElement('button');remove.className='column-delete';remove.textContent='×';remove.title=`Delete ${c.name}`;remove.setAttribute('aria-label',`Delete ${c.name}`);remove.onclick=()=>deleteColumn(columnIndex);col.append(remove);const addBox=document.createElement('button');addBox.className='column-add';addBox.textContent='+';addBox.title=`Add boxes to ${c.name}`;addBox.setAttribute('aria-label',`Add boxes to ${c.name}`);addBox.onclick=()=>openBoxDialog(columnIndex);col.append(addBox);
    c.boxes.forEach(r=>{for(let q=0;q<r.qty;q++){const index=boxIndex++;const b=document.createElement('div');b.className='box'+(y+r.depth>d.depth?' overflow':'');b.draggable=true;b.dataset.column=columnIndex;b.dataset.index=index;b.style.top=`${(d.depth-y-r.depth)*scale}px`;b.style.height=`${Math.max(14,r.depth*scale-2)}px`;b.title=`${r.depth} X ${c.width} mm`;const cover=document.createElement('i');cover.className='cover';const coverWidth=r.depth<project.defaults.short_depth_below?project.defaults.cover_width_short:project.defaults.cover_width;cover.style.height=`${Math.min(r.depth,coverWidth)*scale}px`;const label=document.createElement('span');label.textContent=`${r.depth} X ${c.width}`;const remove=document.createElement('button');remove.className='box-delete';remove.setAttribute('aria-label','Delete box');remove.textContent='×';b.append(cover,label,remove);remove.onclick=event=>{event.stopPropagation();removeBox(columnIndex,index)};b.addEventListener('dragstart',event=>{event.dataTransfer.setData('text/plain',`${columnIndex}:${index}`);b.classList.add('dragging')});b.addEventListener('dragend',()=>b.classList.remove('dragging'));b.addEventListener('dragover',event=>{event.preventDefault();b.classList.add('drop-target')});b.addEventListener('dragleave',()=>b.classList.remove('drop-target'));b.addEventListener('drop',event=>{event.preventDefault();b.classList.remove('drop-target');const [fromColumn,fromIndex]=event.dataTransfer.getData('text/plain').split(':').map(Number);if(fromColumn===columnIndex)moveBox(fromColumn,fromIndex,index)});col.append(b);y+=r.depth;total++;unique.add(`${r.depth}X${c.width}`)}});canvas.append(col);x+=c.width});
  $('summary').textContent=`${total} boxes · ${unique.size} unique sizes · ${x} / ${d.width} mm used`;
}
function renderRulers(d,scale){
  const xRuler=$('xRuler'),yRuler=$('yRuler');xRuler.innerHTML='';yRuler.innerHTML='';
  const step=d.width>700?100:50;
  for(let value=0;value<=d.width;value+=step){const tick=document.createElement('span');tick.className='ruler-tick';tick.style.left=`${value*scale}px`;tick.textContent=value;xRuler.append(tick);}
  const yStep=d.depth>700?100:50;
  for(let value=0;value<=d.depth;value+=yStep){const tick=document.createElement('span');tick.className='ruler-tick';tick.style.bottom=`${value*scale}px`;tick.textContent=value;yRuler.append(tick);}
}
async function validate(){
  const response=await fetch('/api/validate',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(project)});
  const data=await response.json();$('issues').innerHTML=data.issues.map(i=>`<div class="issue ${i.level}">${i.level}: ${i.msg}</div>`).join('');
  $('build').disabled=data.issues.some(i=>i.level==='error'); return data;
}
async function build(){
  if((await validate()).issues?.some(i=>i.level==='error'))return;
  $('build').disabled=true;setBusy('Generating STL files');$('results').textContent='Building...';
  const response=await fetch('/api/build',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({project,options:{workers:+$('workers').value,include_scad:$('includeScad').checked}})});
  if(!response.ok){$('results').textContent=(await response.text());$('build').disabled=false;setBusy('',false);return}
  const poll=async()=>{const data=await (await fetch('/api/build')).json();$('results').innerHTML=(data.items||[]).map(i=>`<div class="job"><span>${i.filename} · ${i.status}</span>${i.status==='done'||i.status==='cached'?`<a href="/api/build/files/${i.filename}">STL</a>`:''}</div>`).join('')||'Waiting...';if(data.state==='running')setTimeout(poll,700);else{$('build').disabled=false;$('zip').hidden=false;$('zip').href='/api/build/zip?include_scad='+$('includeScad').checked;buildReady=data.state==='done';$('slice').disabled=!buildReady||!lastArrangement||lastArrangement.failed.length>0;setBusy('',false)}};poll();
}
async function arrangeBeds(){
  setBusy('Arranging print beds');
  const response=await fetch('/api/arrange',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({project,options:{bed_width:+$('bedWidth').value,bed_depth:+$('bedDepth').value,margin:+$('bedMargin').value,gap:+$('bedGap').value,allow_rotation:$('allowRotation').checked}})});
  const data=await response.json();
  if(!response.ok){$('arrangementSummary').textContent=typeof data.detail==='string'?data.detail:'Unable to arrange boxes';setBusy('',false);return}
  lastArrangement=data;
  $('slice').disabled=true;
  renderBeds(data);
  setBusy('',false);
}
function renderBeds(data){
  $('arrangementView').hidden=false;
  $('arrangementSummary').textContent=`${data.placed}/${data.total} boxes placed · ${data.beds.length} bed${data.beds.length===1?'':'s'}${data.failed.length?` · ${data.failed.length} could not fit`:''}${!buildReady?' · Generate STL files before slicing':''}`;
  const beds=$('beds');beds.innerHTML='';
  data.beds.forEach(bed=>{const panel=document.createElement('article');panel.className='bed-panel';const title=document.createElement('h3');title.textContent=`Bed ${bed.number}`;panel.append(title);const surface=document.createElement('div');surface.className='bed-surface';surface.style.width=`${data.bed.width}px`;surface.style.height=`${data.bed.depth}px`;bed.placements.forEach(item=>{const box=document.createElement('div');box.className='bed-box';box.style.left=`${item.x}px`;box.style.bottom=`${item.y}px`;box.style.width=`${item.width}px`;box.style.height=`${item.depth}px`;box.title=`${item.filename}${item.rotated?' (rotated)':''}`;box.textContent=item.filename.replace('.stl','');surface.append(box)});panel.append(surface);beds.append(panel)});
  if(data.failed.length){const failed=document.createElement('p');failed.className='arrangement-failed';failed.textContent=`Not placed: ${data.failed.map(item=>item.filename).join(', ')}`;beds.append(failed)}
  $('slice').disabled=!buildReady||Boolean(data.failed.length);
}
async function sliceBeds(){
  if(!lastArrangement||lastArrangement.failed.length)return;
  $('slice').disabled=true;setBusy('Slicing arranged beds');$('results').textContent='Slicing arranged beds...';
  const response=await fetch('/api/slice',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({
    arrangement:lastArrangement,
    options:{print_profile:$('printProfile').value.trim(),printer_profile:$('printerProfile').value.trim(),material_profile:$('materialProfile').value.trim(),supports:$('supports').checked,binary_gcode:$('binaryGcode').checked}
  })});
  const start=await response.json();
  if(!response.ok){$('results').textContent=typeof start.detail==='string'?start.detail:'Unable to start slicing';$('slice').disabled=false;setBusy('',false);return}
  const poll=async()=>{const data=await (await fetch('/api/slice')).json();$('results').innerHTML=(data.items||[]).map(i=>`<div class="job"><span>Bed ${i.bed} · ${i.status}</span>${i.status==='done'?`<a href="/api/slice/files/${i.filename}">${i.filename}</a>`:''}${i.status==='failed'?`<details><summary>Debug details</summary><pre>${escapeHtml(`returncode: ${i.returncode}\ncommand: ${(i.command||[]).join(' ')}\n\nstdout:\n${i.stdout||''}\n\nstderr:\n${i.stderr||''}\n\nerror:\n${i.log||''}`)}</pre></details>`:''}</div>`).join('')||'Slicing...';if(data.state==='running')setTimeout(poll,900);else{$('slice').disabled=false;$('sliceDebug').hidden=false;setBusy('',false)}};poll();
}
['drawerWidth','drawerDepth','height','wall','radius'].forEach(id=>$(id).addEventListener('change',()=>{project.drawer.width=+$('drawerWidth').value;project.drawer.depth=+$('drawerDepth').value;project.defaults.height=+$('height').value;project.defaults.wall=+$('wall').value;project.defaults.r=+$('radius').value;render();validate()}));
$('load').onclick=loadExample;$('clear').onclick=()=>{project=emptyProject();render();validate()};$('build').onclick=build;
$('arrange').onclick=arrangeBeds;
$('slice').onclick=sliceBeds;
function openColumnDialog(){ editingColumn=null;$('columnError').textContent='';$('columnDialogTitle').textContent='Add columns';$('columnCountLabel').hidden=false;$('columnDialogHint').textContent='Columns are added from left to right.';$('columnCount').value=1;$('deleteColumn').hidden=true;$('saveColumn').textContent='Add columns';$('columnDialog').showModal();$('columnWidth').focus(); }
function openColumnEditor(index){editingColumn=index;$('columnError').textContent='';$('columnDialogTitle').textContent=`Edit ${project.columns[index].name}`;$('columnWidth').value=project.columns[index].width;$('columnCountLabel').hidden=true;$('columnDialogHint').textContent='Changing width does not change the boxes in this column.';$('deleteColumn').hidden=false;$('saveColumn').textContent='Save changes';$('columnDialog').showModal();$('columnWidth').focus();}
$('addColumn').onclick=openColumnDialog;
 $('cancelColumn').onclick=()=>$('columnDialog').close();
 $('deleteColumn').onclick=()=>{deleteColumn(editingColumn);$('columnDialog').close();};
function expandedBoxes(column){return column.boxes.flatMap(row=>Array.from({length:row.qty},()=>row.depth));}
function regroupBoxes(depths){return depths.reduce((rows,depth)=>{const last=rows[rows.length-1];if(last&&last.depth===depth)last.qty++;else rows.push({depth,qty:1});return rows},[]);}
function removeBox(columnIndex,index){const depths=expandedBoxes(project.columns[columnIndex]);depths.splice(index,1);project.columns[columnIndex].boxes=regroupBoxes(depths);render();validate();}
function deleteColumn(index){project.columns.splice(index,1);project.columns.forEach((column,columnIndex)=>column.name=`Col ${columnIndex+1}`);render();validate();}
function moveBox(columnIndex,fromIndex,toIndex){const depths=expandedBoxes(project.columns[columnIndex]);const [item]=depths.splice(fromIndex,1);depths.splice(toIndex,0,item);project.columns[columnIndex].boxes=regroupBoxes(depths);render();validate();}
$('columnForm').addEventListener('submit',event=>{event.preventDefault();const width=+$('columnWidth').value;if(!(width>0))return;const existing=project.columns.reduce((sum,column)=>sum+column.width,0)-(editingColumn===null?0:project.columns[editingColumn].width);const count=editingColumn===null?+$('columnCount').value:1;if(existing+width*count>project.drawer.width){$('columnError').textContent=`That would exceed the drawer width. ${project.drawer.width-existing} mm remains.`;return}if(editingColumn!==null){project.columns[editingColumn].width=width}else{const start=project.columns.length;for(let i=0;i<count;i++)project.columns.push({name:`Col ${start+i+1}`,width,boxes:[]})}$('columnDialog').close();render();validate()});
function openBoxDialog(columnIndex){addingBoxesToColumn=columnIndex;$('boxDepth').value=50;$('boxCount').value=1;$('boxDialog').showModal();$('boxDepth').focus();}
$('cancelBox').onclick=()=>$('boxDialog').close();
$('boxForm').addEventListener('submit',event=>{event.preventDefault();const depth=+$('boxDepth').value;const count=+$('boxCount').value;if(!(depth>0&&count>0))return;const column=project.columns[addingBoxesToColumn];const used=column.boxes.reduce((sum,row)=>sum+row.depth*row.qty,0);if(used+depth*count>project.drawer.depth){$('boxError').textContent=`That would exceed the drawer depth. ${project.drawer.depth-used} mm remains.`;return}const boxes=column.boxes;const last=boxes[boxes.length-1];if(last&&last.depth===depth)last.qty+=count;else boxes.push({depth,qty:count});$('boxDialog').close();render();validate()});
(async()=>{const s=await (await fetch('/api/status')).json();const buildStatus=await (await fetch('/api/build')).json();buildReady=buildStatus.state==='done';$('status').innerHTML=(s.openscad.found?`<span class="ok">OpenSCAD found</span>`:'<span class="bad">OpenSCAD not found</span>')+' '+(s.prusaslicer.found?`<span class="ok">PrusaSlicer found</span>`:'<span class="bad">PrusaSlicer not found</span>');project=emptyProject();render();await validate()})();
