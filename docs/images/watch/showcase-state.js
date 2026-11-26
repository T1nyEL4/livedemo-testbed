/* Readouts are derived from actual player state, never decorative telemetry. */
(function(scope){
  'use strict';
  function primary(clips, guides, requested){
    const names=clips.map(c=>c.name);
    if(names.includes(requested))return requested;
    if(names.includes('how_to_use'))return 'how_to_use';
    return guides[0]?.clip || names[0];
  }
  function readout(player, manifest){
    const speed=Number(player.speed),duration=Number(player.duration),time=Number(player.time);
    const result={speed:Number.isFinite(speed)?speed:1,
      progress:Number.isFinite(time)&&duration>0?Math.max(0,Math.min(1,time/duration)):0,
      components:(manifest.parts||[]).filter(p=>!p.glow).length,metric:null,angle:null};
    // Explicit metrics override legacy engine metadata, including an empty list.
    const m=manifest.mechanism,c=manifest.clipCameras?.[player.clipName]||{};
    let definitions=manifest.metrics;
    if(definitions===undefined && m?.cycleClip===player.clipName && Number.isFinite(m.cycleDegrees) && m.cycleDegrees>0){
      definitions=[{label:'Crank angle',unit:'°',clip:m.cycleClip,samples:[
        [c.motionStartSeconds??0,0],[c.actionEndSeconds??duration,m.cycleDegrees]]}];
    }
    if(Array.isArray(definitions) && Number.isFinite(time)){
      for(const metric of definitions){
        if(!metric || metric.clip!==player.clipName || typeof metric.label!=='string' || !metric.label.trim() ||
           typeof metric.unit!=='string' || !Array.isArray(metric.samples) || metric.samples.length<2)continue;
        const samples=metric.samples;
        if(!samples.every((s,i)=>Array.isArray(s)&&s.length===2&&s.every(Number.isFinite)&&s[0]>=0&&
          (i===0||s[0]>samples[i-1][0])))continue;
        let value=samples[0][1];
        for(let i=1;i<samples.length;i++){
          const [t0,v0]=samples[i-1],[t1,v1]=samples[i];
          const fraction=Math.max(0,Math.min(1,(time-t0)/(t1-t0)));
          value=v0+(v1-v0)*fraction;
          if(time<=t1)break;
        }
        const precision=Number.isInteger(metric.precision)?Math.max(0,Math.min(3,metric.precision)):0;
        result.metric={label:metric.label,unit:metric.unit,value,precision};
        if(definitions!==manifest.metrics)result.angle=value;
        break;
      }
    }
    return result;
  }
  scope.ShowcaseState={primary,readout};
  if(typeof module!=='undefined')module.exports=scope.ShowcaseState;
})(globalThis);
