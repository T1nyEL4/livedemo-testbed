/* Camera math is independent of THREE/DOM. Angles: glTF Y up, front +Z.
 * Named angles are supplied from camera-views.json (also used by Blender).
 */
(function(scope){
'use strict';
const clamp=(x,a=0,b=1)=>Math.max(a,Math.min(b,x));
const ease=x=>{x=clamp(x);return x*x*(3-2*x);};
const mix=(a,b,t)=>a+(b-a)*t;
const vecMix=(a,b,t)=>a.map((v,i)=>mix(v,b[i],t));
const length=v=>Math.hypot(...v);
const sub=(a,b)=>a.map((v,i)=>v-b[i]);
function fitDistance(radius,fov,aspect,padding=1.5){
  if(![radius,fov,aspect,padding].every(Number.isFinite)||!(radius>0&&aspect>0&&fov>0&&fov<180&&padding>=1))throw Error('Invalid camera fit');
  const v=fov*Math.PI/360,h=Math.atan(Math.tan(v)*aspect);
  return radius*padding/Math.sin(Math.min(v,h));
}
function angles(shot,views){const v=views[shot.view||'isometric']||views.isometric;return [shot.azimuth??v[0],shot.elevation??v[1]];}
function blendShot(a,b,u){
  if(u<=0)return a;if(u>=1)return b;
  const k=ease(u),delta=((b.yaw-a.yaw+540)%360)-180;
  return {target:vecMix(a.target,b.target,k),radius:mix(a.radius,b.radius,k),
    padding:mix(a.padding,b.padding,k),yaw:a.yaw+delta*k,pitch:mix(a.pitch,b.pitch,k)};
}
function boxShot(box,spec,overview,views){
  const [yaw,pitch]=angles(spec,views);
  return {target:vecMix(box.min,box.max,.5),radius:Math.max(length(sub(box.max,box.min))/2,
    length(sub(overview.max,overview.min))/2*(spec.minContext??.15),1e-5),padding:spec.padding??1.5,yaw,pitch};
}
function stepIndex(steps,time){let i=steps.findIndex(s=>time<s.endSeconds-1e-8);return i<0?steps.length-1:i;}
function shotAt({steps,time,boundsAt,overview,views,reducedMotion=false}){
  const intro=boxShot(overview,{},overview,views);
  if(time<=0||!steps.length)return intro;
  const i=stepIndex(steps,time),step=steps[i],spec=step.camera||{};
  // Fixed causal samples make seek/replay independent of frame rate and playback history.
  function tracked(s,t){
    const spec=s.camera||{},start=s.motionStartSeconds??s.startSeconds;
    t=Math.min(t,s.actionEndSeconds);
    const current=boxShot(boundsAt(t,spec.parts),spec,overview,views);
    let result=current;
    for(const lag of [.06,.12,.18]){
      const old=boxShot(boundsAt(Math.max(start,t-lag),spec.parts),spec,overview,views);
      result={...result,target:vecMix(result.target,old.target,.18),radius:mix(result.radius,old.radius,.18)};
    }
    // Keep current moving bounds inside the shot even while the target eases.
    result.radius=Math.max(result.radius,current.radius+length(sub(current.target,result.target)));
    return result;
  }
  const destination=tracked(step,Math.max(time,step.motionStartSeconds??step.startSeconds));
  const duration=spec.transitionSeconds??(step.camera ? .8 : 0);
  if(reducedMotion||!duration||time>=step.startSeconds+duration)return destination;
  const previous=i?tracked(steps[i-1],step.startSeconds):intro;
  return blendShot(previous,destination,(time-step.startSeconds)/duration);
}
function positionFor(shot,fov,aspect,overview){
  const yaw=shot.yaw*Math.PI/180,pitch=shot.pitch*Math.PI/180;
  const direction=[Math.sin(yaw)*Math.cos(pitch),Math.sin(pitch),Math.cos(yaw)*Math.cos(pitch)];
  let distance=fitDistance(shot.radius,fov,aspect,shot.padding);
  // Keep the camera outside the conservative product sphere during an orbit.
  // The model stays fixed; this also prevents a close focus flying through housing.
  const c=vecMix(overview.min,overview.max,.5),r=length(sub(overview.max,overview.min))/2;
  const offset=sub(shot.target,c),dot=offset.reduce((s,x,i)=>s+x*direction[i],0);
  distance=Math.max(distance,-dot+Math.sqrt(Math.max(0,dot*dot+r*r-length(offset)**2))+r*.02);
  return {target:shot.target.slice(),position:shot.target.map((v,i)=>v+direction[i]*distance),distance};
}
function createShotController({evaluate,write,read,reducedMotion=false}){
  let enabled=true,lastTime=null,resume=null;
  return {
    get enabled(){return enabled;},
    manual(){enabled=false;resume=null;},
    reset(time=0){enabled=true;resume=null;lastTime=time;write(evaluate(time));},
    auto(time){enabled=true;resume=reducedMotion?null:{from:read(),elapsed:0};lastTime=null;if(reducedMotion)write(evaluate(time));},
    update(time,dt=0,force=false){
      if(!enabled)return;
      if(time===lastTime&&!resume&&!force)return; // Pause freezes automatic movement.
      let pose=evaluate(time);
      if(resume){resume.elapsed+=Math.max(0,dt);const k=ease(resume.elapsed/.6);
        pose=blendShot(resume.from,pose,k);if(k===1)resume=null;}
      write(pose);lastTime=time;
    }
  };
}
function createCameraDirector({THREE,camera,controls,root,views,reducedMotion=false}){
  let plan=[],boundsAt=null,overview=null,current=null;
  const box=new THREE.Box3();
  const getBounds=parts=>{
    root.updateMatrixWorld(true);box.makeEmpty();
    root.traverse(o=>{if(o.isMesh&&(!parts?.length||parts.includes(o.userData?.c3d_part||o.name)))box.expandByObject(o);});
    if(box.isEmpty())box.setFromObject(root);
    return {min:box.min.toArray(),max:box.max.toArray()};
  };
  overview=getBounds();
  const evaluate=time=>shotAt({steps:plan,time,boundsAt,overview,views,reducedMotion});
  const write=shot=>{
    current=shot;const p=positionFor(shot,camera.fov,camera.aspect,overview);
    controls.target.fromArray(p.target);camera.position.fromArray(p.position);camera.lookAt(controls.target);
    camera.near=Math.max(1e-5,Math.min(shot.radius/100,p.distance/1000));
    camera.far=Math.max(p.distance*10,shot.radius*100);camera.updateProjectionMatrix();
    controls.update();
  };
  const read=()=>{
    const v=camera.position.clone().sub(controls.target),d=v.length();
    return {...current,target:controls.target.toArray(),yaw:Math.atan2(v.x,v.z)*180/Math.PI,
      pitch:Math.asin(clamp(v.y/d,-1,1))*180/Math.PI,
      radius:d/fitDistance(1,camera.fov,camera.aspect,current.padding)};
  };
  const controller=createShotController({evaluate,write,read,reducedMotion});
  const manual=()=>controller.manual();controls.addEventListener('start',manual);
  // Damping retains manual angular velocity and would fight deterministic automatic shots.
  controls.enableDamping=false;
  return {...controller,get enabled(){return controller.enabled;},getBounds,
    select(steps,sample){overview=getBounds();plan=steps;boundsAt=sample;controller.reset();},
    resize(time){controller.update(time,0,true);},
    dispose(){controls.removeEventListener('start',manual);},
  };
}
const api={ease,fitDistance,blendShot,boxShot,stepIndex,shotAt,positionFor,createShotController,createCameraDirector};
Object.assign(scope,api);if(typeof module!=='undefined')module.exports=api;
})(globalThis);
