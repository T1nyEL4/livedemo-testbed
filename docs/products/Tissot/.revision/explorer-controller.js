// Original display-only controls. GLB animation and source geometry stay authoritative.
import * as THREE from 'three';
function automaticLayout(root, byId, reason) {
 const bounds = new THREE.Box3().setFromObject(root);
 const center = bounds.getCenter(new THREE.Vector3());
 const distance = bounds.getSize(new THREE.Vector3()).length() * .35 || .01;
 const groups = [...byId].map(([id, records], index) => {
  const partBounds = new THREE.Box3();
  for (const {obj} of records) partBounds.expandByObject(obj);
  const direction = partBounds.getCenter(new THREE.Vector3()).sub(center);
  if (direction.lengthSq() < distance * distance * 1e-10) {
   const angle = index * Math.PI * (3 - Math.sqrt(5));
   direction.set(Math.cos(angle), Math.sin(angle), .5);
  }
  return {
   id, label: id.replaceAll('_', ' '), parts: [id],
   offset: direction.normalize().multiplyScalar(distance).toArray(),
   start: 0, end: 1, evidence: 'illustrative',
   note: 'Automatically separated from the loaded model. The offset is a display aid.'
  };
 });
 return {schemaVersion: 1, notice: reason + ' Showing automatic, illustrative separation.', groups};
}

export async function installExplorer(state, panel, modelFile = 'model.glb'){
 const {root,renderer,camera,controls,player,director}=state;
 const records=[],byId=new Map();
 root.traverse(obj=>{
  if(!obj.isMesh)return;
  let node=obj,id;
  while(node&&!id){id=node.userData?.c3d_part;node=node.parent;}
  id=id||obj.name;
  if(!id)return;
  const materials=(Array.isArray(obj.material)?obj.material:[obj.material]).map(m=>m.clone());
  const r={obj,id,original:obj.material,materials,position:obj.position.clone()};records.push(r);
  if(!byId.has(id))byId.set(id,[]);byId.get(id).push(r);
 });
 let data;
 try {
  const url = new URL(modelFile, document.baseURI);
  url.pathname = url.pathname.replace(/\.glb$/i, '') + '.explorer.json';
  url.search = '';
  url.hash = '';
  // Preserve the standard export pairing: model.glb + explorer.json.
  if (url.pathname.endsWith('/model.explorer.json')) {
   url.pathname = url.pathname.replace(/model\.explorer\.json$/, 'explorer.json');
  }
  const response = await fetch(url, {cache: 'no-cache'});
  if (!response.ok) throw Error('Layout unavailable');
  data = ExplorerState.validate(await response.json(), byId.keys());
 } catch (error) {
  console.warn('Using automatic take-apart layout:', error.message);
  data = automaticLayout(root, byId, 'A matching authored layout could not be loaded.');
 }
 panel.innerHTML='<button type="button" data-action="apart" aria-pressed="false">Take apart</button><label>Part separation<input aria-label="Illustrative separation" type="range" min="0" max="1" step="0.01" value="0"></label><label>Inspect assembly<select aria-label="Assembly to inspect"></select></label><div class="explorer-actions"><button type="button" data-mode="context" aria-pressed="true">Transparent context</button><button type="button" data-mode="isolate" aria-pressed="false">Isolate</button><button type="button" data-mode="section" aria-pressed="false">Section preview</button></div><details><summary>About this view</summary><p class="explorer-evidence"></p><p class="explorer-notice"></p></details>';

 const select=panel.querySelector('select'),slider=panel.querySelector('input'),evidence=panel.querySelector('.explorer-evidence');
 const option=(value,text)=>{const o=document.createElement('option');o.value=value;o.textContent=text;select.append(o);};
 option('','Whole machine');data.groups.forEach(g=>option(g.id,g.label));
 panel.querySelector('.explorer-notice').textContent=data.notice;
 let active=false,amount=0,target=0,selected='',mode='context',focus=null,assembling=false;
 const apart=panel.querySelector('[data-action="apart"]');
 function syncButton(){apart.textContent=!assembling&&(amount>0||target>0)?'Assemble':'Take apart';apart.setAttribute('aria-pressed',String(amount>0||target>0));}
 const viewerPanel = panel.closest('.stage')?.querySelector('.viewer-panel');
 function updateDotOpacity(separation) {
  viewerPanel?.style.setProperty('--dot-opacity', String(Math.max(0, 1 - 2 * separation)));
 }
 const normal=new THREE.Vector3(0,0,-1),plane=new THREE.Plane();
 const bounds=new THREE.Box3(),v=new THREE.Vector3(),world=new THREE.Vector3();
 const hadClipping=renderer.localClippingEnabled;
 function begin(){
  if(active)return;
  player?.release();director?.manual();
  root.updateMatrixWorld(true);
  for(const r of records){r.position.copy(r.obj.position);r.world=r.obj.getWorldPosition(new THREE.Vector3());}
  active=true;
 }
 function restore(){
  if(!active)return;
  for(const r of records){r.obj.position.copy(r.position);r.obj.material=r.original;}
  renderer.localClippingEnabled=hadClipping;root.updateMatrixWorld(true);
  active=false;assembling=false;amount=target=0;slider.value='0';syncButton();focus=null;selected='';mode='context';select.value='';
  updateDotOpacity(0);
  panel.querySelectorAll('[data-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mode==='context')));
  evidence.textContent='Whole machine assembled. Use the guide controls to resume playback.';
 }
 function apply(){
  if(!active)return;
  syncButton();
  updateDotOpacity(amount);
  const offsets=ExplorerState.offsets(data.groups,amount),group=data.groups.find(g=>g.id===selected);
  const chosen=new Set(group?.parts||byId.keys());
  root.updateMatrixWorld(true);
  for(const r of records){
   world.copy(r.world).add(v.fromArray(offsets.get(r.id)||[0,0,0]));
   r.obj.parent.updateWorldMatrix(true,false);
   r.obj.position.copy(r.obj.parent.worldToLocal(world));
  }
  root.updateMatrixWorld(true);bounds.makeEmpty();
  for(const r of records)if(chosen.has(r.id))bounds.expandByObject(r.obj);
  if(bounds.isEmpty())bounds.setFromObject(root);
  const center=bounds.getCenter(new THREE.Vector3());plane.setFromNormalAndCoplanarPoint(normal,center);
  renderer.localClippingEnabled=true;
  for(const r of records){
   const isChosen=chosen.has(r.id);
   r.obj.material=Array.isArray(r.original)?r.materials:r.materials[0];
   r.materials.forEach((m,i)=>{
    const original=Array.isArray(r.original)?r.original[i]:r.original;
    const ghost=Boolean(group)&&!isChosen;
    const changed=m.transparent!==(ghost||original.transparent)||Boolean(m.clippingPlanes?.length)!==(mode==='section')||m.side!==(mode==='section'?THREE.DoubleSide:original.side);
    m.opacity=ghost?(mode==='isolate'?0:.12):original.opacity;
    m.transparent=ghost||original.transparent;m.depthWrite=ghost?false:original.depthWrite;
    m.clippingPlanes=mode==='section'?[plane]:null;m.side=mode==='section'?THREE.DoubleSide:original.side;
    if(m.emissive){m.emissive.copy(original.emissive);if(group&&isChosen)m.emissive.setHex(0x153947);}
    if(changed)m.needsUpdate=true;
   });
  }
  evidence.textContent=group?`${group.label} · ${group.evidence}. ${group.note}`:'Whole machine · choose an assembly to inspect.';
  if(mode==='section')evidence.textContent+=' Section preview is uncapped and display-only.';
 }
 function fit(){
  apply();const b=bounds.clone(),c=b.getCenter(new THREE.Vector3()),radius=Math.max(b.getSize(v).length()/2,.001);
  const angle=Math.min(camera.fov*Math.PI/360,Math.atan(Math.tan(camera.fov*Math.PI/360)*camera.aspect));
  const direction=camera.position.clone().sub(controls.target).normalize();
  focus={from:camera.position.clone(),to:c.clone().addScaledVector(direction,radius*1.25/Math.sin(angle)),fromTarget:controls.target.clone(),toTarget:c,t:0};
 }
 function stopFocus(){focus=null;}
 controls.addEventListener('start',stopFocus);
 select.onchange=()=>{begin();selected=select.value;fit();};
 slider.oninput=()=>{begin();assembling=false;amount=target=Number(slider.value);apply();fit();};
 apart.onclick=()=>{begin();assembling=!assembling&&(amount>0||target>0);target=assembling?0:1;syncButton();fit();};
 panel.querySelectorAll('[data-mode]').forEach(button=>button.onclick=()=>{
  begin();mode=button.dataset.mode;
  panel.querySelectorAll('[data-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));apply();fit();
 });
 return {restore,data,get active(){return active;},
  update(dt){
   if(!active)return;
   const before=amount;amount+=Math.sign(target-amount)*Math.min(Math.abs(target-amount),Math.max(0,dt)/2.2);
   if(before!==amount){slider.value=String(amount);apply();if(!selected)fit();}
   if(assembling&&amount===0){restore();player?.restart?.();player?.auto?.();return;}
   if(focus){focus.t+=Math.max(0,dt);const t=Math.min(1,focus.t/.65),k=t*t*(3-2*t);
    camera.position.lerpVectors(focus.from,focus.to,k);controls.target.lerpVectors(focus.fromTarget,focus.toTarget,k);controls.update();if(t===1)focus=null;}
  },
  dispose(){restore();controls.removeEventListener('start',stopFocus);for(const r of records)r.materials.forEach(m=>m.dispose());}
 };
}
