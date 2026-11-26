const root = document.documentElement;

if (root.classList.contains('intro-playing')) {
  playIntro().catch(() => {
    root.classList.remove('intro-playing');
    document.querySelector('.intro').hidden = true;
  });
}

async function playIntro() {
  const stage = document.querySelector('.intro');
  const lockup = stage.querySelector('.intro-lockup');
  const symbol = stage.querySelector('.intro-symbol');
  const wordmark = stage.querySelector('.intro-wordmark');
  const cursor = stage.querySelector('.intro-cursor');
  const box = stage.querySelector('.selection-box');
  const skip = stage.querySelector('.intro-skip');
  const dots = document.querySelector('.page-dots');
  const brand = document.querySelector('.brand');
  const title = document.querySelector('#page-title');
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const controller = new AbortController();
  const signal = controller.signal;
  const settle = 'cubic-bezier(0.2, 0.78, 0.26, 1)';
  let cursorPosition;

  function finish() {
    if (signal.aborted) return;
    controller.abort();
    [...stage.getAnimations({ subtree: true }), ...title.getAnimations(), ...dots.getAnimations()]
      .forEach(animation => animation.cancel());
    stage.hidden = true;
    root.classList.remove('intro-playing');
  }

  function skipIntro() {
    finish();
    title.focus({ preventScroll: true });
  }

  function animate(element, frames, duration, options = {}) {
    signal.throwIfAborted();
    return element.animate(frames, { duration, fill: 'forwards', ...options }).finished;
  }

  function at(point) {
    return 'translate(' + point.x + 'px, ' + point.y + 'px)';
  }

  function selection(layer, bounds) {
    const element = stage.querySelector('[data-layer="' + layer + '"]');
    if (!bounds) return { element, rect: element.getBoundingClientRect() };

    // The four SVG layers share the 169 × 149 Affinity artboard.
    const area = symbol.getBoundingClientRect();
    return {
      element,
      rect: {
        left: area.left + bounds.x / 169 * area.width,
        top: area.top + bounds.y / 149 * area.height,
        width: bounds.width / 169 * area.width,
        height: bounds.height / 149 * area.height,
      },
    };
  }

  async function drawBox({ element, rect }) {
    const padding = 5;
    const start = { x: rect.left - padding, y: rect.top - padding };
    const width = rect.width + 2 * padding;
    const height = rect.height + 2 * padding;
    const end = { x: start.x + width, y: start.y + height };

    await animate(cursor, [
      { transform: at(cursorPosition), opacity: cursorPosition.opacity ?? 1 },
      { transform: at(start), opacity: 1 },
    ], 235, { easing: settle });

    Object.assign(box.style, {
      left: start.x + 'px',
      top: start.y + 'px',
      width: width + 'px',
      height: height + 'px',
    });

    await Promise.all([
      animate(box, [
        { transform: 'scale(0.02)', opacity: 0.75 },
        { transform: 'scale(1)', opacity: 1 },
      ], 420, { easing: settle }),
      animate(cursor, [{ transform: at(start) }, { transform: at(end) }], 420, { easing: settle }),
    ]);

    await Promise.all([
      animate(element, [{ opacity: 0 }, { opacity: 1 }], 185, { easing: 'ease-out' }),
      animate(box, [{ opacity: 1 }, { opacity: 0 }], 205, { delay: 85 }),
    ]);
    cursorPosition = end;
  }

  skip.addEventListener('click', skipIntro, { signal });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') skipIntro();
  }, { signal });
  motion.addEventListener('change', finish, { signal });
  stage.hidden = false;

  try {
    await Promise.all(Array.from(lockup.querySelectorAll('img'), image => image.decode()));
    signal.throwIfAborted();

    const icon = symbol.getBoundingClientRect();
    const centeredBase = at({
      x: innerWidth / 2 - (icon.left + icon.width * 63.6 / 169),
      y: innerHeight / 2 - (icon.top + icon.height * 65.1 / 149),
    });

    lockup.style.transform = centeredBase;
    await animate(stage.querySelector('[data-layer="base"]'), [
      { opacity: 0, transform: 'scale(0.92)' },
      { opacity: 1, transform: 'scale(1)' },
    ], 420, { easing: settle });

    await animate(lockup, [
      { transform: centeredBase },
      { transform: 'translate(0, 0)' },
    ], 500, { delay: 110, easing: settle });

    cursorPosition = { x: innerWidth / 2 + icon.width * 0.53, y: icon.top - 22, opacity: 0 };
    for (const [layer, bounds] of [
      ['top', { x: 43, y: 21, width: 126, height: 53 }],
      ['middle', { x: 41, y: 65, width: 128, height: 42 }],
      ['bottom', { x: 42, y: 96, width: 127, height: 53 }],
      ['wordmark'],
    ]) {
      await drawBox(selection(layer, bounds));
    }

    await animate(cursor, [{ opacity: 1 }, { opacity: 0 }], 150);
    const from = lockup.getBoundingClientRect();
    const to = brand.getBoundingClientRect();
    const destination = at({ x: to.left - from.left, y: to.top - from.top });
    const scale = to.width / from.width;
    const landingDuration = 900;
    const landingOptions = { easing: 'cubic-bezier(0.25, 0.88, 0.25, 1)' };

    await Promise.all([
      animate(lockup, [
        { transform: 'translate(0, 0) scale(1)' },
        { transform: destination + ' scale(' + scale + ')' },
      ], landingDuration, landingOptions),
      animate(dots, [
        { height: '100dvh', maskSize: '100% 400%' },
        { height: 'var(--dots-height)', maskSize: '100% 100%' },
      ], landingDuration, landingOptions),
      animate(title, [
        { opacity: 0, transform: 'translateY(1.4rem)' },
        { opacity: 1, transform: 'translateY(0)' },
      ], 650, { delay: 540, easing: settle }),
    ]);
  } finally {
    finish();
  }
}
