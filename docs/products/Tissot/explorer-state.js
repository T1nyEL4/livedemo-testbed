/* Original, renderer-independent test presentation state. No product geometry. */
(function(scope){
'use strict';
function validate(data,ids){
 if(data?.schemaVersion!==1||!Array.isArray(data.groups))throw Error('Expected explorer schemaVersion 1 and groups');
 const known=new Set(ids),seen=new Set(),groupIds=new Set();
 const groups=data.groups.map(g=>{
  if(!g||typeof g.id!=='string'||!g.id||groupIds.has(g.id))throw Error('Duplicate or missing group id');
  groupIds.add(g.id);
  if(typeof g.label!=='string'||!g.label.trim()||!Array.isArray(g.parts)||!g.parts.length)throw Error('Group needs label and parts');
  for(const id of g.parts){if(!known.has(id)||seen.has(id))throw Error('Unknown or repeated part: '+id);seen.add(id);}
  if(!Array.isArray(g.offset)||g.offset.length!==3||!g.offset.every(Number.isFinite))throw Error('Offset must be three finite metres');
  if(!Number.isFinite(g.start)||!Number.isFinite(g.end)||g.start<0||g.start>=g.end||g.end>1)throw Error('Invalid reveal interval');
  if(!['observed','inferred','illustrative'].includes(g.evidence)||typeof g.note!=='string'||!g.note.trim())throw Error('Group needs evidence and an explanation');
  return {...g,parts:g.parts.slice(),offset:g.offset.slice()};
 });
 return {schemaVersion:1,notice:typeof data.notice==='string'?data.notice:'Illustrative layout; not a service procedure.',groups};
}
function offsets(groups,amount){
 if(!Number.isFinite(amount))throw Error('Separation must be finite');
 const result=new Map();
 for(const g of groups){let u=Math.max(0,Math.min(1,(amount-g.start)/(g.end-g.start)));u=u*u*(3-2*u);
  for(const id of g.parts)result.set(id,g.offset.map(v=>v*u));}
 return result;
}
const api={validate,offsets};scope.ExplorerState=api;
if(typeof module!=='undefined')module.exports=api;
})(globalThis);
