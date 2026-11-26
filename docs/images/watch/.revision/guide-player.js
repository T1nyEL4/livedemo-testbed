/* Shared mechanics, timeline UI and camera orchestration for both viewers.
   Pass ui:false to drive it from your own page (index.html does): no panel is created and the
   returned object exposes the guide, step index, play/pause, chapters, step-only playback,
   speed and change notifications. */
(function(scope){
'use strict';
function createGuidePlayer({THREE,mixer,root,clips,guides=[],clipCameras={},container,director,ui=true,onChange}) {
  const baseline=[];
  // Exported rest is authoritative, including non-joint animation channels.
  root.traverse(o=>baseline.push([o,o.position.clone(),o.quaternion.clone(),o.scale.clone()]));
  const restore=()=>{mixer.stopAllAction();for(const [o,p,q,s] of baseline){o.position.copy(p);o.quaternion.copy(q);o.scale.copy(s);}root.updateMatrixWorld(true);};
  let guide=null,clip=null,time=0,playing=false,active=true,direction=1,speed=1,stopAt=null,ignoreStepPauses=false;
  const listeners=onChange?[onChange]:[];
  const el=tag=>ui?document.createElement(tag):null;
  const panel=el('section'),selector=el('select'),caption=el('p'),progress=el('input'),controls=el('div');
  if(ui){
    panel.setAttribute('aria-label','Product walkthrough');selector.setAttribute('aria-label','Walkthrough or independent clip');
    for(const c of clips){const g=guides.find(g=>g.clip===c.name),option=document.createElement('option');option.value=c.name;option.textContent=g?.title||c.name;selector.append(option);}
    caption.setAttribute('aria-live','polite');
    progress.type='range';progress.min=0;progress.step=.01;progress.setAttribute('aria-label','Animation progress');progress.style.width='100%';
    controls.style.cssText='display:flex;gap:4px;flex-wrap:wrap;margin-bottom:12px';
  }
  const button=(label,fn)=>{if(!ui)return {};const b=document.createElement('button');b.textContent=label;b.onclick=fn;controls.append(b);return b;};
  const index=()=>stepIndex(guide.steps,time);
  const show=()=>{
    if(ui){const i=index();caption.textContent=`Step ${i+1} of ${guide.steps.length}: ${guide.steps[i].instruction}`;progress.value=time;play.textContent=playing?'Pause':'Play';}
    for(const fn of listeners)fn(api);
  };
  function pose(t){restore();const a=mixer.clipAction(clip);a.reset();a.setLoop(THREE.LoopOnce);a.clampWhenFinished=true;a.play();a.time=t;a.paused=true;mixer.update(0);root.updateMatrixWorld(true);}
  function seek(t,{camera=true}={}){active=true;time=Math.max(0,Math.min(t,clip.duration));pose(time);if(camera&&director){director.update(time,0,true);pose(time);}show();}
  function toggle(){active=true;direction=1;stopAt=null;if(time>=clip.duration){director?.reset();seek(0);}playing=!playing;show();}
  function reverse(){active=true;direction=-1;stopAt=null;if(time<=0)seek(clip.duration);playing=true;show();}
  const chapter=i=>{playing=false;stopAt=null;const s=guide.steps[i];seek(s.motionStartSeconds??s.startSeconds);};
  function playStep(i){
    ignoreStepPauses=false;
    // Play exactly one chapter from its start (camera lead-in included) and stop at its end.
    i=Math.max(0,Math.min(guide.steps.length-1,i));const s=guide.steps[i];
    direction=1;seek(s.startSeconds);stopAt=Math.max(s.startSeconds,s.endSeconds-1e-3);playing=true;show();  // stop just inside the step so it stays current
  }
  function replayStep(){direction=1;stopAt=null;seek(guide.steps[index()].startSeconds);playing=true;show();}
  function restart(){ignoreStepPauses=false;playing=false;direction=1;stopAt=null;director?.reset();seek(0);}
  const play=button('Play',toggle);
  button('Reverse',reverse);
  button('Previous',()=>chapter(Math.max(0,index()-1)));
  button('Next',()=>chapter(Math.min(guide.steps.length-1,index()+1)));
  button('Replay step',replayStep);
  button('Restart',restart);
  button('Auto view',()=>director?.auto(time));
  function select(id){
    restore();clip=clips.find(c=>c.name===id);if(!clip)throw Error('Animation missing');
    const record=clipCameras[id]||{};
    guide=guides.find(g=>g.clip===id)||{clip:id,title:null,steps:[{id, instruction:id.replaceAll('_',' '),startSeconds:0,
      motionStartSeconds:record.motionStartSeconds??0,actionEndSeconds:record.actionEndSeconds??clip.duration,
      endSeconds:clip.duration,camera:record.camera}]};
    playing=false;direction=1;active=true;time=0;stopAt=null;if(ui){selector.value=id;progress.max=clip.duration;}pose(0);
    if(director){director.select(guide.steps,(t,parts)=>{pose(t);return director.getBounds(parts);});}
    seek(0);
  }
  if(ui){selector.onchange=()=>select(selector.value);progress.oninput=()=>{playing=false;seek(Number(progress.value));};
    panel.append(selector,caption,progress,controls);container.prepend(panel);}
  const api={get active(){return active;},get time(){return time;},get playing(){return playing;},
    get guide(){return guide;},get clipName(){return clip?.name;},get duration(){return clip?clip.duration:0;},
    playAll(){restart();ignoreStepPauses=true;playing=true;show();},
    get speed(){return speed;},set speed(v){speed=Math.max(.1,Math.min(4,Number(v)||1));show();},
    stepIndex:()=>guide?index():0,seek,select,toggle,reverse,chapter,playStep,replayStep,restart,
    pause(){playing=false;stopAt=null;show();},
    auto(){director?.auto(time);},
    onChange(fn){listeners.push(fn);},
    release(){playing=false;active=false;restore();show();},
    update(dt){
      if(active&&playing){let next=Math.max(0,Math.min(time+dt*speed*direction,clip.duration));
        const pause=!ignoreStepPauses&&direction>0&&guide.steps.find(s=>s.pauseAfter&&s.endSeconds>time+1e-7&&s.endSeconds<=next);
        if(pause){next=pause.endSeconds;playing=false;}
        if(direction>0&&stopAt!=null&&next>=stopAt-1e-7){next=stopAt;playing=false;stopAt=null;}
        if(next>=clip.duration||next<=0)playing=false;
        seek(next,{camera:false});}
      director?.update(time,dt);if(active)pose(time);
    },
    dispose(){playing=false;active=false;restore();director?.dispose();if(ui)panel.remove();}};
  if(clips.length)select(guides[0]?.clip||clips[0].name);else{if(ui)panel.remove();director?.select([],()=>director.getBounds());return null;}
  return api;
}
scope.createGuidePlayer=createGuidePlayer;
if(typeof module!=='undefined')module.exports={createGuidePlayer};
})(globalThis);
