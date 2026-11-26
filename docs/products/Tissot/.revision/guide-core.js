// Shared core for the guide pages: 3D scene, model + manifest loading, directed cameras,
// guide playback (guide-player.js), part labels with leader lines and view panning.
// A page supplies the elements and renders its own step UI from the player state.
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {RoomEnvironment} from 'three/addons/environments/RoomEnvironment.js';

export const pretty = id => id.replaceAll('_', ' ').replace(/^\w/, c => c.toUpperCase());
export const fmt = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
export function shortTitle(text, max = 46) {
  const first = (text || '').split(/(?<=[.!?。！？])\s/)[0].replace(/[.。]$/, '');
  if (first.length <= max) return first;
  const cut = first.slice(0, max), sp = cut.lastIndexOf(' ');
  return cut.slice(0, sp > max / 2 ? sp : max) + '…';
}

export function startGuide({file, viewer, labelLayer, onReady, onChange, onError, onFrame, onOrientation, background = '#edf0eb', bottomInset = () => 0}) {
  const renderer = new THREE.WebGLRenderer({antialias: true, alpha: background === null});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.toneMapping = THREE.AgXToneMapping;
  viewer.prepend(renderer.domElement);
  const scene = new THREE.Scene();
  scene.background = background === null ? null : new THREE.Color(background);
  scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), .04).texture;
  const camera = new THREE.PerspectiveCamera(35, 1, .001, 100);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  const clock = new THREE.Clock();
  // Part labels start hidden; the page's Show labels button turns them on (?labels=1 starts with them on).
  const state = {player: null, director: null, guides: [], clips: [], manifest: {}, labelsOn: new URLSearchParams(location.search).get('labels') === '1'};
  const partObjects = new Map(), partNames = {};

  function resize() {
    const w = viewer.clientWidth, h = viewer.clientHeight;
    if (w <= 0 || h <= 0) return;
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
    state.director?.resize(state.player?.time || 0);
  }
  new ResizeObserver(resize).observe(viewer);

  // Part labels: the parts named by the current step's camera, max 4, never overlapping.
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'label-leaders'); labelLayer.append(svg);
  const labelEls = new Map(), box = new THREE.Box3(), center = new THREE.Vector3();
  function updateLabels() {
    const p = state.player, s = p?.guide.steps[p.stepIndex()];
    const parts = state.labelsOn && s?.camera?.parts ? s.camera.parts.slice(0, 4) : [];
    const w = viewer.clientWidth, h = viewer.clientHeight, placed = [];
    let lines = '';
    for (const [id, el] of labelEls) if (!parts.includes(id)) { el.remove(); labelEls.delete(id); }
    parts.forEach((id, k) => {
      const obj = partObjects.get(id); if (!obj) return;
      box.setFromObject(obj); if (box.isEmpty()) return;
      box.getCenter(center).project(camera); if (center.z > 1) return;
      const x = (center.x + 1) / 2 * w, y = (1 - center.y) / 2 * h;
      let el = labelEls.get(id);
      if (!el) { el = document.createElement('div'); el.className = 'part-label'; el.textContent = partNames[id] || pretty(id); labelLayer.append(el); labelEls.set(id, el); }
      const bw = el.offsetWidth || 110, bh = el.offsetHeight || 30;
      const lx = Math.min(w - bw / 2 - 8, Math.max(bw / 2 + 8, x + (k % 2 ? 80 : -80)));
      let ly = Math.max(bh / 2 + 56, y - 70);
      while (placed.some(r => Math.abs(r.x - lx) < (r.w + bw) / 2 + 6 && Math.abs(r.y - ly) < (r.h + bh) / 2 + 4)) ly += bh + 6;
      placed.push({x: lx, y: ly, w: bw, h: bh});
      el.style.left = lx + 'px'; el.style.top = ly + 'px';
      lines += `<line x1="${lx}" y1="${ly + bh / 2}" x2="${x}" y2="${y}"/><circle cx="${x}" cy="${y}" r="3"/>`;
    });
    svg.innerHTML = lines;
  }

  let modelRoot = null;
  function rotateView(dx, dy) {
    if (!modelRoot) return;
    state.player?.pause(); state.director?.manual?.();
    const offset = camera.position.clone().sub(controls.target);
    const spherical = new THREE.Spherical().setFromVector3(offset);
    spherical.theta -= dx * .012;
    spherical.phi = Math.max(.001, Math.min(Math.PI - .001, spherical.phi - dy * .012));
    camera.position.copy(controls.target).add(offset.setFromSpherical(spherical));
    controls.update();
  }
  function setView(view) {
    const directions={front:[0,0,1],back:[0,0,-1],right:[1,0,0],left:[-1,0,0],top:[0,1,.001],bottom:[0,-1,.001]};
    if(!directions[view] || !modelRoot) return;
    state.player?.pause();state.director?.manual?.();
    const distance=camera.position.distanceTo(controls.target);
    camera.position.copy(controls.target).add(new THREE.Vector3(...directions[view]).normalize().multiplyScalar(distance));controls.update();
  }
  function pan(dx, dy) {
    state.director?.manual?.();
    const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0);
    const up = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1);
    const step = camera.position.distanceTo(controls.target) * .08;
    const move = right.multiplyScalar(dx * step).add(up.multiplyScalar(dy * step));
    camera.position.add(move); controls.target.add(move); controls.update();
  }

  new GLTFLoader().load(file, async gltf => {
    const root = gltf.scene; modelRoot = root; scene.add(root);
    const b = new THREE.Box3().setFromObject(root), r = b.getSize(new THREE.Vector3()).length() / 2, c = b.getCenter(new THREE.Vector3());
    camera.near = r / 100; camera.far = r * 100; camera.updateProjectionMatrix();
    camera.position.copy(c).add(new THREE.Vector3(-.9, .55, 1.6).normalize().multiplyScalar(r * 3));
    controls.target.copy(c); controls.update();
    root.traverse(o => { if (o.userData?.c3d_part && !partObjects.has(o.userData.c3d_part)) partObjects.set(o.userData.c3d_part, o); });
    let views = {};
    try { state.manifest = await (await fetch(file.replace(/\.glb(?:\?.*)?$/, '.manifest.json'))).json(); } catch {}
    try { views = await (await fetch('camera-views.json')).json(); } catch {}
    for (const p of state.manifest.parts || []) partNames[p.id] = p.label || pretty(p.id);
    state.guides = state.manifest.guides || [];
    state.clips = gltf.animations;
    state.director = createCameraDirector({THREE, camera, controls, root, views, reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches});
    state.player = createGuidePlayer({THREE, mixer: new THREE.AnimationMixer(root), root, clips: gltf.animations, guides: state.guides,
      clipCameras: state.manifest.clipCameras || {}, director: state.director, ui: false, onChange});
    Object.assign(state,{root,renderer,camera,controls,scene,partObjects});
    resize();
    onReady?.(state);
    window.guideViewer = state;
  }, undefined, err => onError?.(err));

  // Shift the picture up by half of whatever covers the bottom of the view (e.g. a caption),
  // so directed shots stay visible above it. Projection-only: cameras and labels still agree.
  let inset = -1;
  function applyInset() {
    const d = Math.round(Math.max(0, bottomInset() || 0) / 2), w = viewer.clientWidth, h = viewer.clientHeight;
    if (d === inset || w <= 0 || h <= 0) return;
    inset = d;
    if (d) camera.setViewOffset(w, h, 0, d, w, h); else camera.clearViewOffset();
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(() => { inset = -1; }).observe(viewer);

  renderer.setAnimationLoop(() => {
    applyInset();
    const dt = clock.getDelta();
    state.player?.update(dt); onFrame?.(dt,state); controls.update(); renderer.render(scene, camera);
    if(onOrientation){const q=camera.quaternion.clone().invert(), length=Math.hypot(q.x,q.y,q.z);onOrientation(length?q.x/length:1,length?q.y/length:0,length?q.z/length:0,q.w);}
    if (state.player) updateLabels();
  });

  return {state, pan, setView, rotateView, auto: () => state.player && state.director?.auto(state.player.time),
    setLabels(on) { state.labelsOn = on; },
    partCount: () => (state.manifest.parts || []).length || partObjects.size};
}

// Step tick marks over a range input: one tick at the start of each step.
export function drawTicks(container, steps, duration) {
  container.replaceChildren();
  if (!duration) return;
  for (const s of steps.slice(1)) {
    const t = document.createElement('i');
    t.style.left = `${(s.startSeconds / duration) * 100}%`;
    container.append(t);
  }
}
