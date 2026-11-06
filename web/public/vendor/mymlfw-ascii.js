// node_modules/ascii.rest/dist/mount.js
function mount(el, piece2, options = {}) {
  const make = typeof piece2 === "function" ? piece2 : piece2.default;
  const meta = typeof piece2 === "function" ? {} : piece2.meta;
  const { fps = meta.fps ?? 30, motion = false, ...rest } = { ...meta.options, ...options };
  const frame = make(rest);
  const { cols = 80, rows = 24, palette, ground, cell = 2 } = meta;
  const canvas = el instanceof HTMLCanvasElement ? el : null;
  const color = palette && canvas ? new Uint8Array(cols * rows) : void 0;
  const rgb2 = (css) => css[0] === "#" ? [1, 3, 5].map((i) => parseInt(css.slice(i, i + 2), 16)) : (css.match(/[\d.]+/g) || []).map(Number);
  const dark = (css) => {
    const c = rgb2(css);
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2] < 128;
  };
  const env = () => ({ paper: canvas && ground ? !dark(ground) : dark(getComputedStyle(el).color), color });
  const reduced = !motion && typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  let t = reduced ? meta.still ?? 0 : 0;
  let draw = () => {
    el.textContent = frame(t, env());
  };
  let ro;
  if (canvas) {
    const font = (px) => `${px}px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`;
    const ctx = canvas.getContext("2d");
    const atlas = document.createElement("canvas");
    const actx = atlas.getContext("2d");
    const slots = /* @__PURE__ */ new Map();
    let w = 0, h = 0, sw = 0, sh = 0, pw = 0, ph = 0, width = -1, ink = "";
    let xs = new Int32Array(0), ys = new Int32Array(0), gx = new Int32Array(0), gy = new Int32Array(0);
    let last2 = "", full = true;
    const lastColor = color && new Uint8Array(cols * rows);
    canvas.style.display ||= "block";
    canvas.style.width ||= "100%";
    canvas.style.aspectRatio = `${cols} / ${rows * cell}`;
    const size2 = () => {
      width = canvas.clientWidth;
      w = width * (devicePixelRatio || 1) / cols;
      h = w * cell;
      sw = Math.ceil(w);
      sh = Math.ceil(h);
      pw = sw + 2;
      ph = sh + 2;
      canvas.width = Math.round(w * cols);
      canvas.height = Math.round(h * rows);
      atlas.width = pw * 32;
      atlas.height = ph * 32;
      xs = Int32Array.from({ length: cols + 1 }, (_, x) => Math.round(x * w));
      ys = Int32Array.from({ length: rows + 1 }, (_, y) => Math.round(y * h));
      gx = Int32Array.from({ length: cols }, (_, x) => Math.round(x * w + (w - sw) / 2));
      gy = Int32Array.from({ length: rows }, (_, y) => Math.round(y * h + (h - sh) / 2));
      slots.clear();
      full = true;
    };
    const glyph2 = (code3, i) => {
      const key = code3 * 256 + i;
      let s = slots.get(key);
      if (s !== void 0)
        return s;
      if (slots.size === 1024) {
        actx.clearRect(0, 0, atlas.width, atlas.height);
        slots.clear();
      }
      s = slots.size;
      const x = s % 32 * pw + 1, y = Math.floor(s / 32) * ph + 1;
      actx.font = font(w / 0.6);
      actx.textAlign = "center";
      actx.textBaseline = "middle";
      actx.fillStyle = palette ? palette[i] || palette[0] : ink;
      actx.save();
      actx.beginPath();
      actx.rect(x - 1, y - 1, pw, ph);
      actx.clip();
      actx.fillText(String.fromCharCode(code3), x + sw / 2, y + sh / 2);
      actx.restore();
      slots.set(key, s);
      return s;
    };
    draw = () => {
      if (!palette && getComputedStyle(canvas).color !== ink) {
        ink = getComputedStyle(canvas).color;
        slots.clear();
        actx.clearRect(0, 0, atlas.width, atlas.height);
        full = true;
      }
      const text2 = frame(t, env());
      if (ground)
        ctx.fillStyle = ground;
      if (full) {
        if (ground)
          ctx.fillRect(0, 0, canvas.width, canvas.height);
        else
          ctx.clearRect(0, 0, canvas.width, canvas.height);
      }
      for (let k = 0, x = 0, y = 0; k < text2.length; k++) {
        const c = text2.charCodeAt(k);
        if (c === 10) {
          x = 0;
          y++;
          continue;
        }
        const i = y * cols + x;
        if (full || c !== last2.charCodeAt(k) || color && color[i] !== lastColor[i]) {
          const x0 = xs[x], y0 = ys[y], cw = xs[x + 1] - x0, ch = ys[y + 1] - y0;
          if (!full) {
            if (ground)
              ctx.fillRect(x0, y0, cw, ch);
            else
              ctx.clearRect(x0, y0, cw, ch);
          }
          if (c !== 32) {
            const s = glyph2(c, color ? color[i] : 0);
            ctx.drawImage(atlas, s % 32 * pw + 1 + x0 - gx[x], Math.floor(s / 32) * ph + 1 + y0 - gy[y], cw, ch, x0, y0, cw, ch);
          }
        }
        x++;
      }
      last2 = text2;
      if (color)
        lastColor.set(color);
      full = false;
    };
    size2();
    ro = new ResizeObserver(() => {
      if (canvas.clientWidth !== width) {
        size2();
        draw();
      }
    });
    ro.observe(canvas);
  }
  draw();
  if (!fps)
    return () => ro?.disconnect();
  const still = matchMedia("(prefers-reduced-motion: reduce)");
  let raf = 0;
  let last = 0;
  let seen = false;
  const tick = (now) => {
    raf = requestAnimationFrame(tick);
    const dt = now - last;
    if (dt < 1e3 / fps - 2)
      return;
    last = now;
    t += Math.min(dt, 100) / 1e3;
    draw();
  };
  const run = () => {
    const go = seen && !document.hidden && (motion || !still.matches);
    if (go && !raf) {
      last = performance.now();
      raf = requestAnimationFrame(tick);
    } else if (!go && raf) {
      cancelAnimationFrame(raf);
      raf = 0;
    }
  };
  const io = new IntersectionObserver((entries) => {
    seen = entries[entries.length - 1].isIntersecting;
    run();
  });
  io.observe(el);
  document.addEventListener("visibilitychange", run);
  still.addEventListener("change", run);
  return () => {
    io.disconnect();
    ro?.disconnect();
    cancelAnimationFrame(raf);
    raf = 0;
    document.removeEventListener("visibilitychange", run);
    still.removeEventListener("change", run);
  };
}

// node_modules/ascii.rest/dist/banner.js
var fonts = {
  block: {
    height: 5,
    glyphs: {
      A: ".##.|#..#|####|#..#|#..#",
      B: "###.|#..#|###.|#..#|###.",
      C: ".###|#...|#...|#...|.###",
      D: "###.|#..#|#..#|#..#|###.",
      E: "####|#...|###.|#...|####",
      F: "####|#...|###.|#...|#...",
      G: ".###|#...|#.##|#..#|.###",
      H: "#..#|#..#|####|#..#|#..#",
      I: "#|#|#|#|#",
      J: "...#|...#|...#|#..#|.##.",
      K: "#..#|#.#.|##..|#.#.|#..#",
      L: "#...|#...|#...|#...|####",
      M: "#...#|##.##|#.#.#|#...#|#...#",
      N: "#...#|##..#|#.#.#|#..##|#...#",
      O: ".##.|#..#|#..#|#..#|.##.",
      P: "###.|#..#|###.|#...|#...",
      Q: ".##.|#..#|#..#|#.#.|.#.#",
      R: "###.|#..#|###.|#.#.|#..#",
      S: ".###|#...|.##.|...#|###.",
      T: "#####|..#..|..#..|..#..|..#..",
      U: "#..#|#..#|#..#|#..#|.##.",
      V: "#...#|#...#|#...#|.#.#.|..#..",
      W: "#...#|#...#|#.#.#|##.##|#...#",
      X: "#...#|.#.#.|..#..|.#.#.|#...#",
      Y: "#...#|.#.#.|..#..|..#..|..#..",
      Z: "####|...#|..#.|.#..|####",
      0: "###|#.#|#.#|#.#|###",
      1: ".#.|##.|.#.|.#.|###",
      2: "###|..#|###|#..|###",
      3: "###|..#|.##|..#|###",
      4: "#.#|#.#|###|..#|..#",
      5: "###|#..|###|..#|###",
      6: "###|#..|###|#.#|###",
      7: "###|..#|..#|..#|..#",
      8: "###|#.#|###|#.#|###",
      9: "###|#.#|###|..#|###",
      ".": ".|.|.|.|#",
      ",": ".|.|.|#|#",
      "!": "#|#|#|.|#",
      "?": "###|..#|.##|...|.#.",
      "'": "#|#|.|.|.",
      ":": ".|#|.|#|.",
      "-": "...|...|###|...|...",
      "+": "...|.#.|###|.#.|...",
      "=": "...|###|...|###|...",
      "/": "..#|..#|.#.|#..|#..",
      _: "...|...|...|...|###",
      " ": ".."
    }
  },
  slim: {
    height: 5,
    glyphs: {
      A: ".#.|#.#|###|#.#|#.#",
      B: "##.|#.#|##.|#.#|##.",
      C: ".##|#..|#..|#..|.##",
      D: "##.|#.#|#.#|#.#|##.",
      E: "###|#..|##.|#..|###",
      F: "###|#..|##.|#..|#..",
      G: ".##|#..|#.#|#.#|.##",
      H: "#.#|#.#|###|#.#|#.#",
      I: "###|.#.|.#.|.#.|###",
      J: "..#|..#|..#|#.#|.#.",
      K: "#.#|#.#|##.|#.#|#.#",
      L: "#..|#..|#..|#..|###",
      M: "#.#|###|#.#|#.#|#.#",
      N: "##.|#.#|#.#|#.#|#.#",
      O: ".#.|#.#|#.#|#.#|.#.",
      P: "##.|#.#|##.|#..|#..",
      Q: ".#.|#.#|#.#|##.|.##",
      R: "##.|#.#|##.|#.#|#.#",
      S: ".##|#..|.#.|..#|##.",
      T: "###|.#.|.#.|.#.|.#.",
      U: "#.#|#.#|#.#|#.#|###",
      V: "#.#|#.#|#.#|.#.|.#.",
      W: "#.#|#.#|#.#|###|#.#",
      X: "#.#|#.#|.#.|#.#|#.#",
      Y: "#.#|#.#|.#.|.#.|.#.",
      Z: "###|..#|.#.|#..|###",
      0: "###|#.#|#.#|#.#|###",
      1: ".#.|##.|.#.|.#.|###",
      2: "##.|..#|.#.|#..|###",
      3: "##.|..#|.#.|..#|##.",
      4: "#.#|#.#|###|..#|..#",
      5: "###|#..|##.|..#|##.",
      6: ".##|#..|###|#.#|###",
      7: "###|..#|.#.|.#.|.#.",
      8: "###|#.#|###|#.#|###",
      9: "###|#.#|###|..#|##.",
      ".": ".|.|.|.|#",
      ",": ".|.|.|#|#",
      "!": "#|#|#|.|#",
      "?": "##.|..#|.#.|...|.#.",
      "'": "#|#|.|.|.",
      ":": ".|#|.|#|.",
      "-": "...|...|###|...|...",
      "+": "...|.#.|###|.#.|...",
      "=": "...|###|...|###|...",
      "/": "..#|..#|.#.|#..|#..",
      _: "...|...|...|...|###",
      " ": ".."
    }
  },
  tall: {
    height: 7,
    glyphs: {
      A: ".###.|#...#|#...#|#####|#...#|#...#|#...#",
      B: "####.|#...#|#...#|####.|#...#|#...#|####.",
      C: ".###.|#...#|#....|#....|#....|#...#|.###.",
      D: "###..|#..#.|#...#|#...#|#...#|#..#.|###..",
      E: "#####|#....|#....|####.|#....|#....|#####",
      F: "#####|#....|#....|####.|#....|#....|#....",
      G: ".###.|#...#|#....|#.###|#...#|#...#|.###.",
      H: "#...#|#...#|#...#|#####|#...#|#...#|#...#",
      I: "###|.#.|.#.|.#.|.#.|.#.|###",
      J: "....#|....#|....#|....#|....#|#...#|.###.",
      K: "#...#|#..#.|#.#..|##...|#.#..|#..#.|#...#",
      L: "#....|#....|#....|#....|#....|#....|#####",
      M: "#...#|##.##|#.#.#|#.#.#|#...#|#...#|#...#",
      N: "#...#|#...#|##..#|#.#.#|#..##|#...#|#...#",
      O: ".###.|#...#|#...#|#...#|#...#|#...#|.###.",
      P: "####.|#...#|#...#|####.|#....|#....|#....",
      Q: ".###.|#...#|#...#|#...#|#.#.#|#..#.|.##.#",
      R: "####.|#...#|#...#|####.|#.#..|#..#.|#...#",
      S: ".###.|#...#|#....|.###.|....#|#...#|.###.",
      T: "#####|..#..|..#..|..#..|..#..|..#..|..#..",
      U: "#...#|#...#|#...#|#...#|#...#|#...#|.###.",
      V: "#...#|#...#|#...#|#...#|#...#|.#.#.|..#..",
      W: "#...#|#...#|#...#|#.#.#|#.#.#|##.##|#...#",
      X: "#...#|#...#|.#.#.|..#..|.#.#.|#...#|#...#",
      Y: "#...#|#...#|.#.#.|..#..|..#..|..#..|..#..",
      Z: "#####|....#|...#.|..#..|.#...|#....|#####",
      0: ".###.|#...#|#..##|#.#.#|##..#|#...#|.###.",
      1: "..#|.##|#.#|..#|..#|..#|..#",
      2: ".###.|#...#|....#|...#.|..#..|.#...|#####",
      3: ".###.|#...#|....#|..##.|....#|#...#|.###.",
      4: "...#.|..##.|.#.#.|#..#.|#####|...#.|...#.",
      5: "#####|#....|####.|....#|....#|#...#|.###.",
      6: "..##.|.#...|#....|####.|#...#|#...#|.###.",
      7: "#####|....#|...#.|..#..|..#..|..#..|..#..",
      8: ".###.|#...#|#...#|.###.|#...#|#...#|.###.",
      9: ".###.|#...#|#...#|.####|....#|...#.|.##..",
      ".": ".|.|.|.|.|.|#",
      ",": "..|..|..|..|..|.#|#.",
      "!": "#|#|#|#|#|.|#",
      "?": ".###.|#...#|....#|...#.|..#..|.....|..#..",
      "'": "#|#|.|.|.|.|.",
      ":": ".|.|#|.|.|.|#",
      "-": "....|....|....|####|....|....|....",
      "+": ".....|..#..|..#..|#####|..#..|..#..|.....",
      "=": ".....|.....|#####|.....|#####|.....|.....",
      "/": "....#|....#|...#.|..#..|.#...|#....|#....",
      _: ".....|.....|.....|.....|.....|.....|#####",
      " ": "...|...|...|...|...|...|..."
    }
  },
  bold: {
    height: 7,
    glyphs: {
      A: ".####.|##..##|##..##|######|##..##|##..##|##..##",
      B: "#####.|##..##|##..##|#####.|##..##|##..##|#####.",
      C: ".####.|##..##|##....|##....|##....|##..##|.####.",
      D: "####..|##.##.|##..##|##..##|##..##|##.##.|####..",
      E: "######|##....|##....|#####.|##....|##....|######",
      F: "######|##....|##....|#####.|##....|##....|##....",
      G: ".####.|##..##|##....|##.###|##..##|##..##|.#####",
      H: "##..##|##..##|##..##|######|##..##|##..##|##..##",
      I: "####|.##.|.##.|.##.|.##.|.##.|####",
      J: "....##|....##|....##|....##|##..##|##..##|.####.",
      K: "##..##|##.##.|####..|###...|####..|##.##.|##..##",
      L: "##....|##....|##....|##....|##....|##....|######",
      M: "##....##|###..###|########|##.##.##|##....##|##....##|##....##",
      N: "##...##|###..##|####.##|##.####|##..###|##...##|##...##",
      O: ".####.|##..##|##..##|##..##|##..##|##..##|.####.",
      P: "#####.|##..##|##..##|#####.|##....|##....|##....",
      Q: ".####.|##..##|##..##|##..##|##.###|##.##.|.##.##",
      R: "#####.|##..##|##..##|#####.|##.##.|##..##|##..##",
      S: ".####.|##..##|##....|.####.|....##|##..##|.####.",
      T: "######|..##..|..##..|..##..|..##..|..##..|..##..",
      U: "##..##|##..##|##..##|##..##|##..##|##..##|.####.",
      V: "##..##|##..##|##..##|##..##|##..##|.####.|..##..",
      W: "##....##|##....##|##....##|##.##.##|########|###..###|##....##",
      X: "##..##|##..##|.####.|..##..|.####.|##..##|##..##",
      Y: "##..##|##..##|.####.|..##..|..##..|..##..|..##..",
      Z: "######|....##|...##.|..##..|.##...|##....|######",
      0: ".####.|##..##|##..##|##.###|###.##|##..##|.####.",
      1: "..##|.###|####|..##|..##|..##|..##",
      2: ".####.|##..##|....##|...##.|..##..|.##...|######",
      3: ".####.|##..##|....##|..###.|....##|##..##|.####.",
      4: "...###|..####|.##.##|##..##|######|....##|....##",
      5: "######|##....|#####.|....##|....##|##..##|.####.",
      6: "..###.|.##...|##....|#####.|##..##|##..##|.####.",
      7: "######|....##|...##.|..##..|..##..|..##..|..##..",
      8: ".####.|##..##|##..##|.####.|##..##|##..##|.####.",
      9: ".####.|##..##|##..##|.#####|....##|...##.|.###..",
      ".": "..|..|..|..|..|##|##",
      ",": "..|..|..|..|##|##|#.",
      "!": "##|##|##|##|..|##|##",
      "?": ".####.|##..##|...##.|..##..|......|..##..|..##..",
      "'": "##|##|..|..|..|..|..",
      ":": "..|##|##|..|..|##|##",
      "-": "....|....|....|####|....|....|....",
      "+": "......|..##..|..##..|######|..##..|..##..|......",
      "=": "......|......|######|......|######|......|......",
      "/": "....##|....##|...##.|..##..|.##...|##....|##....",
      _: "......|......|......|......|......|......|######",
      " ": "...|...|...|...|...|...|..."
    }
  },
  round: {
    height: 6,
    glyphs: {
      0: ".###.|#...#|#.#.#|#.#.#|#...#|.###.",
      1: ".#.|##.|.#.|.#.|.#.|###",
      2: ".###.|#...#|...#.|..#..|.#...|#####",
      3: ".###.|#...#|..##.|....#|#...#|.###.",
      4: "...#.|..##.|.#.#.|#..#.|#####|...#.",
      5: "#####|#....|####.|....#|#...#|.###.",
      6: "..##.|.#...|#....|####.|#...#|.###.",
      7: "####.|....#|...#.|..#..|..#..|..#..",
      8: ".###.|#...#|.###.|#...#|#...#|.###.",
      9: ".###.|#...#|.####|....#|...#.|.##..",
      A: ".###.|#...#|#...#|#####|#...#|#...#",
      B: "###..|#..#.|###..|#..#.|#...#|####.",
      C: ".####|#....|#....|#....|#....|.####",
      D: "###..|#..#.|#...#|#...#|#..#.|###..",
      E: ".####|#....|####.|#....|#....|.####",
      F: ".####|#....|####.|#....|#....|#....",
      G: ".####|#....|#....|#.##.|#...#|.###.",
      H: "#...#|#...#|#####|#...#|#...#|#...#",
      I: "###|.#.|.#.|.#.|.#.|###",
      J: "....#|....#|....#|....#|#...#|.###.",
      K: "#...#|#..#.|###..|#..#.|#...#|#...#",
      L: "#....|#....|#....|#....|#....|.####",
      M: "#...#|##.##|#.#.#|#...#|#...#|#...#",
      N: "#...#|##..#|#.#.#|#.#.#|#..##|#...#",
      O: ".###.|#...#|#...#|#...#|#...#|.###.",
      P: ".###.|#...#|#...#|####.|#....|#....",
      Q: ".###.|#...#|#...#|#.#.#|#..#.|.##.#",
      R: ".###.|#...#|#..#.|###..|#..#.|#...#",
      S: ".###.|#....|.##..|...#.|....#|####.",
      T: "#####|..#..|..#..|..#..|..#..|..#..",
      U: "#...#|#...#|#...#|#...#|#...#|.###.",
      V: "#...#|#...#|#...#|.#.#.|.#.#.|..#..",
      W: "#...#|#...#|#...#|#.#.#|#.#.#|.#.#.",
      X: "#...#|.#.#.|..#..|..#..|.#.#.|#...#",
      Y: "#...#|#...#|.#.#.|..#..|..#..|..#..",
      Z: "#####|...#.|..#..|..#..|.#...|#####",
      ".": ".|.|.|.|.|#",
      ",": ".|.|.|.|#|#",
      "!": "#|#|#|#|.|#",
      "?": ".###.|#...#|...#.|..#..|.....|..#..",
      "'": "#|#|.|.|.|.",
      ":": ".|#|.|.|#|.",
      "-": "...|...|###|...|...|...",
      "+": "...|.#.|###|.#.|...|...",
      "=": "...|###|...|###|...|...",
      "/": "..#|..#|.#.|.#.|#..|#..",
      _: "....|....|....|....|....|####",
      " ": "...|...|...|...|...|..."
    }
  },
  wide: {
    height: 5,
    glyphs: {
      0: ".####.|#...##|#.##.#|##...#|.####.",
      1: "..#|.##|..#|..#|..#",
      2: "#####.|.....#|.####.|#.....|######",
      3: "#####.|.....#|.####.|.....#|#####.",
      4: "#...#.|#...#.|######|....#.|....#.",
      5: "######|#.....|#####.|.....#|#####.",
      6: ".####.|#.....|#####.|#....#|.####.",
      7: "######|.....#|....#.|...#..|..#...",
      8: ".####.|#....#|.####.|#....#|.####.",
      9: ".####.|#....#|.#####|.....#|.####.",
      A: ".####.|#....#|######|#....#|#....#",
      B: "#####.|#....#|######|#....#|#####.",
      C: ".#####|#.....|#.....|#.....|.#####",
      D: "#####.|#....#|#....#|#....#|#####.",
      E: "######|#.....|#####.|#.....|######",
      F: "######|#.....|#####.|#.....|#.....",
      G: ".#####|#.....|#..###|#....#|.####.",
      H: "#....#|#....#|######|#....#|#....#",
      I: "###|.#.|.#.|.#.|###",
      J: ".....#|.....#|.....#|#....#|.####.",
      K: "#....#|#...#.|#####.|#...#.|#....#",
      L: "#.....|#.....|#.....|#.....|######",
      M: "#.....#|##...##|#.#.#.#|#..#..#|#.....#",
      N: "#....#|##...#|#.#..#|#..#.#|#...##",
      O: ".####.|#....#|#....#|#....#|.####.",
      P: "#####.|#....#|#####.|#.....|#.....",
      Q: ".####.|#....#|#....#|#...#.|.###.#",
      R: "#####.|#....#|#####.|#...#.|#....#",
      S: ".####.|#.....|.####.|.....#|.####.",
      T: "#######|...#...|...#...|...#...|...#...",
      U: "#....#|#....#|#....#|#....#|.####.",
      V: "#.....#|#.....#|.#...#.|..#.#..|...#...",
      W: "#.....#|#..#..#|#.#.#.#|##...##|#.....#",
      X: "#....#|.#..#.|..##..|.#..#.|#....#",
      Y: "#.....#|.#...#.|..#.#..|...#...|...#...",
      Z: "######|....#.|..##..|.#....|######",
      ".": ".|.|.|.|#",
      ",": ".|.|.|#|#",
      "!": "#|#|#|.|#",
      "?": "#####.|.....#|..###.|......|..#...",
      "'": "#|#|.|.|.",
      ":": ".|#|.|#|.",
      "-": "....|....|####|....|....",
      "+": ".....|..#..|#####|..#..|.....",
      "=": "....|####|....|####|....",
      "/": "....#|...#.|..#..|.#...|#....",
      _: "......|......|......|......|######",
      " ": "....|....|....|....|...."
    }
  },
  mixed: {
    height: 9,
    cased: true,
    glyphs: {
      A: ".###.|#...#|#...#|#####|#...#|#...#|#...#|.....|.....",
      B: "####.|#...#|#...#|####.|#...#|#...#|####.|.....|.....",
      C: ".###.|#...#|#....|#....|#....|#...#|.###.|.....|.....",
      D: "####.|#...#|#...#|#...#|#...#|#...#|####.|.....|.....",
      E: "#####|#....|#....|####.|#....|#....|#####|.....|.....",
      F: "#####|#....|#....|####.|#....|#....|#....|.....|.....",
      G: ".###.|#...#|#....|#.###|#...#|#...#|.####|.....|.....",
      H: "#...#|#...#|#...#|#####|#...#|#...#|#...#|.....|.....",
      I: "###|.#.|.#.|.#.|.#.|.#.|###|...|...",
      J: "....#|....#|....#|....#|....#|#...#|.###.|.....|.....",
      K: "#...#|#..#.|#.#..|##...|#.#..|#..#.|#...#|.....|.....",
      L: "#....|#....|#....|#....|#....|#....|#####|.....|.....",
      M: "#...#|##.##|#.#.#|#.#.#|#...#|#...#|#...#|.....|.....",
      N: "#...#|#...#|##..#|#.#.#|#..##|#...#|#...#|.....|.....",
      O: ".###.|#...#|#...#|#...#|#...#|#...#|.###.|.....|.....",
      P: "####.|#...#|#...#|####.|#....|#....|#....|.....|.....",
      Q: ".###.|#...#|#...#|#...#|#.#.#|#..#.|.##.#|.....|.....",
      R: "####.|#...#|#...#|####.|#.#..|#..#.|#...#|.....|.....",
      S: ".###.|#...#|#....|.###.|....#|#...#|.###.|.....|.....",
      T: "#####|..#..|..#..|..#..|..#..|..#..|..#..|.....|.....",
      U: "#...#|#...#|#...#|#...#|#...#|#...#|.###.|.....|.....",
      V: "#...#|#...#|#...#|#...#|#...#|.#.#.|..#..|.....|.....",
      W: "#...#|#...#|#...#|#.#.#|#.#.#|#.#.#|.#.#.|.....|.....",
      X: "#...#|#...#|.#.#.|..#..|.#.#.|#...#|#...#|.....|.....",
      Y: "#...#|#...#|.#.#.|..#..|..#..|..#..|..#..|.....|.....",
      Z: "#####|....#|...#.|..#..|.#...|#....|#####|.....|.....",
      a: ".....|.....|.###.|....#|.####|#...#|.####|.....|.....",
      b: "#....|#....|####.|#...#|#...#|#...#|####.|.....|.....",
      c: "....|....|.###|#...|#...|#...|.###|....|....",
      d: "....#|....#|.####|#...#|#...#|#...#|.####|.....|.....",
      e: ".....|.....|.###.|#...#|#####|#....|.####|.....|.....",
      f: "..##|.#..|###.|.#..|.#..|.#..|.#..|....|....",
      g: ".....|.....|.####|#...#|#...#|#...#|.####|....#|.###.",
      h: "#....|#....|#.##.|##..#|#...#|#...#|#...#|.....|.....",
      i: "#|.|#|#|#|#|#|.|.",
      j: "..#|...|..#|..#|..#|..#|..#|..#|##.",
      k: "#...|#...|#..#|#.#.|##..|#.#.|#..#|....|....",
      l: "#.|#.|#.|#.|#.|#.|.#|..|..",
      m: ".....|.....|##.#.|#.#.#|#.#.#|#.#.#|#.#.#|.....|.....",
      n: ".....|.....|#.##.|##..#|#...#|#...#|#...#|.....|.....",
      o: ".....|.....|.###.|#...#|#...#|#...#|.###.|.....|.....",
      p: ".....|.....|####.|#...#|#...#|#...#|####.|#....|#....",
      q: ".....|.....|.####|#...#|#...#|#...#|.####|....#|....#",
      r: "....|....|#.##|##..|#...|#...|#...|....|....",
      s: ".....|.....|.####|#....|.###.|....#|####.|.....|.....",
      t: ".#..|.#..|###.|.#..|.#..|.#..|..##|....|....",
      u: ".....|.....|#...#|#...#|#...#|#...#|.####|.....|.....",
      v: ".....|.....|#...#|#...#|#...#|.#.#.|..#..|.....|.....",
      w: ".....|.....|#...#|#...#|#.#.#|#.#.#|.#.#.|.....|.....",
      x: ".....|.....|#...#|.#.#.|..#..|.#.#.|#...#|.....|.....",
      y: ".....|.....|#...#|#...#|#...#|#...#|.####|....#|.###.",
      z: ".....|.....|#####|...#.|..#..|.#...|#####|.....|.....",
      0: ".###.|#...#|#..##|#.#.#|##..#|#...#|.###.|.....|.....",
      1: ".#.|##.|.#.|.#.|.#.|.#.|###|...|...",
      2: ".###.|#...#|....#|...#.|..#..|.#...|#####|.....|.....",
      3: ".###.|#...#|....#|..##.|....#|#...#|.###.|.....|.....",
      4: "...#.|..##.|.#.#.|#..#.|#####|...#.|...#.|.....|.....",
      5: "#####|#....|####.|....#|....#|#...#|.###.|.....|.....",
      6: "..##.|.#...|#....|####.|#...#|#...#|.###.|.....|.....",
      7: "#####|....#|...#.|..#..|.#...|.#...|.#...|.....|.....",
      8: ".###.|#...#|#...#|.###.|#...#|#...#|.###.|.....|.....",
      9: ".###.|#...#|#...#|.####|....#|...#.|.##..|.....|.....",
      ".": ".|.|.|.|.|.|#|.|.",
      ",": "..|..|..|..|..|..|.#|#.|..",
      "!": "#|#|#|#|#|.|#|.|.",
      "?": ".###.|#...#|....#|...#.|..#..|.....|..#..|.....|.....",
      "'": "#|#|.|.|.|.|.|.|.",
      ":": ".|.|.|#|.|.|#|.|.",
      "-": "....|....|....|....|####|....|....|....|....",
      "+": ".....|.....|..#..|..#..|#####|..#..|..#..|.....|.....",
      "=": ".....|.....|.....|#####|.....|#####|.....|.....|.....",
      "/": "....#|....#|...#.|..#..|.#...|#....|#....|.....|.....",
      _: ".....|.....|.....|.....|.....|.....|#####|.....|.....",
      " ": "...|...|...|...|...|...|...|...|..."
    }
  },
  italic: {
    height: 5,
    glyphs: {
      0: "..##.|.#..#|.#.##|##.#.|.##..",
      1: "...#|.##.|..#.|.#..|###.",
      2: "..###|....#|..##.|.#...|####.",
      3: "..###|....#|..##.|...#.|###..",
      4: ".#..#|#..#.|####.|..#..|..#..",
      5: "..####|.#....|.###..|...#..|###...",
      6: "..##.|.#...|.###.|#..#.|.##..",
      7: ".####|...#.|..#..|.#...|#....",
      8: "..##.|.#..#|..##.|#..#.|.##..",
      9: "..##.|.#..#|..###|...#.|.##..",
      A: "..##.|.#..#|.####|#..#.|#..#.",
      B: "..###|.#..#|.###.|#..#.|###..",
      C: "..###|.#...|.#...|#....|.###.",
      D: "..###|.#..#|.#..#|#..#.|###..",
      E: "..####|.#....|.###..|#.....|####..",
      F: "..####|.#....|.###..|#.....|#.....",
      G: "..###|.#...|.#.##|#..#.|.###.",
      H: "..#..#|.#..#.|.####.|#..#..|#..#..",
      I: ".###.|..#..|..#..|.#...|###..",
      J: ".....#|....#.|....#.|#..#..|.##...",
      K: "..#.#|.#.#.|.##..|#.#..|#..#.",
      L: "..#.|.#..|.#..|#...|####",
      M: "..#...#|.##.##.|.#.#.#.|#...#..|#...#..",
      N: "..#..#|.##.#.|.#.##.|#..#..|#..#..",
      O: "..##.|.#..#|.#..#|#..#.|.##..",
      P: "..###|.#..#|.###.|#....|#....",
      Q: "..##.|.#..#|.#..#|#.##.|.##.#",
      R: "..###|.#..#|.###.|#.#..|#..#.",
      S: "..###|.#...|..##.|...#.|###..",
      T: "#####|..#..|..#..|.#...|.#...",
      U: "..#..#|.#..#.|.#..#.|#..#..|.##...",
      V: "..#..#|.#..#.|.#.#..|#.#...|.#....",
      W: "..#...#|.#...#.|.#.#.#.|#.#.#..|.#.#...",
      X: "..#...#|..#.#..|...#...|.#.#...|#...#..",
      Y: "#...#|.#.#.|..#..|.#...|.#...",
      Z: "..####|....#.|..##..|.#....|####..",
      ".": ".|.|.|.|#",
      ",": "..|..|..|.#|#.",
      "!": "..#|.#.|.#.|...|#..",
      "?": "###|..#|.#.|...|#..",
      "'": ".#|#.|..|..|..",
      ":": "..|.#|..|..|#.",
      "-": "...|...|###|...|...",
      "+": "...|.#.|###|.#.|...",
      "=": "....|.###|....|###.|....",
      "/": "....#|...#.|..#..|.#...|#....",
      _: "....|....|....|....|####",
      " ": "...|...|...|...|..."
    }
  }
};
var shadows = {
  double: " \u2551\u2551\u2551\u2550\u255D\u2557\u2563\u2550\u255A\u2554\u2560\u2550\u2569\u2566\u256C",
  single: " \u2502\u2502\u2502\u2500\u2518\u2510\u2524\u2500\u2514\u250C\u251C\u2500\u2534\u252C\u253C",
  heavy: " \u2503\u2503\u2503\u2501\u251B\u2513\u252B\u2501\u2517\u250F\u2523\u2501\u253B\u2533\u254B",
  rounded: " \u2502\u2502\u2502\u2500\u256F\u256E\u2524\u2500\u2570\u256D\u251C\u2500\u2534\u252C\u253C",
  ascii: " |||-+++-+++-+++"
};
var INK = { light: "#1f2328", dark: "#f0f6fc" };
var QUIET = { light: "#59636e", dark: "#9198a1" };
var HEX = /^#[0-9a-f]{6}$/i;
var and = (words2) => words2.length > 1 ? `${words2.slice(0, -1).join(", ")} and ${words2.at(-1)}` : words2[0] ?? "";
function resolve(font) {
  if (font !== void 0 && font !== null && typeof font === "object")
    return font;
  const name = font ?? "block";
  if (!Object.hasOwn(fonts, name))
    throw new Error(`ascii.rest: there is no font named "${name}": there are ${and(Object.keys(fonts))}, or pass one of your own`);
  return fonts[name];
}
var fail = (what) => {
  throw new Error(`ascii.rest: ${what}`);
};
var whole = (v, name, least) => v === void 0 || Number.isInteger(v) && v >= least ? v : fail(`${name} takes a whole number of ${least} or more, not ${String(v)}`);
var positive = (v, name) => v === void 0 || typeof v === "number" && Number.isFinite(v) && v > 0 ? v : fail(`${name} takes a number above 0, not ${String(v)}`);
var chars = (v, name, most) => {
  const check = (s) => typeof s === "string" && [...s].length >= 1 && [...s].length <= most && !/[\u0000-\u001f\u007f-\u009f]/.test(s) ? s : fail(`${name} takes ${most === 1 ? "one character" : "one or two characters"}, not ${JSON.stringify(s)}`);
  if (v === void 0)
    return void 0;
  if (typeof v === "object" && v !== null) {
    const g = v;
    return { dark: g.dark === void 0 ? void 0 : check(g.dark), light: g.light === void 0 ? void 0 : check(g.light) };
  }
  return check(v);
};
function drawable(text2, font = "block") {
  const f = resolve(font);
  return [...String(text2)].filter((ch) => [...f.cased ? ch : ch.toUpperCase()].some((c) => Object.hasOwn(f.glyphs, c))).join("");
}
var shapes = (text2, f) => [...String(text2)].flatMap((ch) => [...f.cased ? ch : ch.toUpperCase()]).map((c) => Object.hasOwn(f.glyphs, c) ? f.glyphs[c] : void 0).filter((g) => Boolean(g)).map((g) => g.split("|"));
function fade(stops, n) {
  const rgb2 = stops.map((s) => [1, 3, 5].map((i) => parseInt(s.slice(i, i + 2), 16)));
  return Array.from({ length: n }, (_, i) => {
    const k = n > 1 ? i / (n - 1) * (rgb2.length - 1) : 0;
    const a = Math.min(rgb2.length - 2, Math.floor(k)), f = k - a;
    const c = rgb2.length === 1 ? rgb2[0] : rgb2[a].map((v, j) => Math.round(v + (rgb2[a + 1][j] - v) * f));
    return `#${c.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
  });
}
var pick = (themed3, theme) => themed3 !== null && typeof themed3 === "object" && !Array.isArray(themed3) ? themed3[theme] : themed3;
function banner(text2, options = {}) {
  const font = resolve(options.font);
  if (!drawable(text2, font).trim())
    fail(`the font draws none of "${text2}"`);
  const glyphs = shapes(text2, font);
  const effect = options.effect ?? "glint";
  if (!["glint", "type", "still"].includes(effect))
    fail(`effect takes "glint", "type" or "still", not ${JSON.stringify(effect)}`);
  const gap = whole(options.gap, "gap", 0) ?? 2;
  let shade = shadows.double;
  if (options.shadow === "none")
    shade = null;
  else if (options.shadow !== void 0) {
    shade = Object.hasOwn(shadows, options.shadow) ? shadows[options.shadow] : options.shadow;
    if (typeof shade !== "string" || [...shade].length !== 16 || /[\u0000-\u001f\u007f-\u009f]/.test(shade))
      fail(`shadow takes ${[...Object.keys(shadows), "none"].join(", ")}, or 16 characters of your own, not ${JSON.stringify(options.shadow)}`);
  }
  const joins = shade === null ? [] : [...shade];
  const h = font.height;
  const span2 = (s2) => glyphs.reduce((w, g) => w + g[0].length * s2, 0) + gap * (glyphs.length - 1) + (shade ? 1 : 0);
  const pad2 = options.pad;
  const pads = pad2 === void 0 || typeof pad2 === "number" ? [pad2 ?? 0, pad2 ?? 0] : Array.isArray(pad2) && pad2.length === 2 ? pad2 : fail(`pad takes a number, or [rows, columns], not ${JSON.stringify(pad2)}`);
  const [padY, padX] = pads.map((p, i) => whole(p, i ? "pad's columns" : "pad", 0) ?? 0);
  const tall = h + (shade ? 1 : 0);
  let s = whole(options.pixel, "pixel", 1) ?? 2;
  const max = positive(options.max, "max");
  let cols, rows, x0, y0;
  if (options.size) {
    if (options.size.cols === void 0 || options.size.rows === void 0)
      fail("size takes { cols, rows }, both of them");
    cols = whole(options.size.cols, "size.cols", 1);
    rows = whole(options.size.rows, "size.rows", 1);
    while (s > 1 && span2(s) > cols - 2)
      s--;
    x0 = Math.max(0, Math.floor((cols - span2(s)) / 2));
    y0 = Math.floor((rows - tall) / 2);
  } else {
    if (max !== void 0)
      while (s > 1 && span2(s) + 2 * padX > max)
        s--;
    cols = span2(s) + 2 * padX;
    rows = tall + 2 * padY;
    x0 = padX;
    y0 = padY;
  }
  const ink = new Uint8Array(cols * rows);
  let x = x0;
  for (const g of glyphs) {
    g.forEach((line2, y) => {
      for (let i = 0; i < line2.length; i++)
        if (line2[i] === "#") {
          for (let k = 0; k < s; k++)
            if (x + i * s + k < cols && y0 + y < rows)
              ink[(y0 + y) * cols + x + i * s + k] = 1;
        }
    });
    x += g[0].length * s + gap;
  }
  const at3 = (c, r) => c >= 0 && c < cols && r >= 0 && r < rows ? ink[r * cols + c] : 0;
  const grid3 = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (at3(c, r)) {
        grid3.push(null);
        continue;
      }
      if (!shade) {
        grid3.push(" ");
        continue;
      }
      const a = at3(c - 1, r - 1), b = at3(c, r - 1), d = at3(c - 1, r);
      const edges = (a !== b ? 1 : 0) | (d ? 2 : 0) | (a !== d ? 4 : 0) | (b ? 8 : 0);
      grid3.push(joins[edges === 15 ? 2 | 8 : edges]);
    }
  }
  const both = (v, dark, light) => typeof v === "string" ? { dark: v, light: v } : { dark: v?.dark ?? dark, light: v?.light ?? light };
  const fill = both(chars(options.fill, "fill", 1), "\u2593", "\u2588");
  const gl = options.glint ?? {};
  const shine = both(chars(gl.chars, "glint.chars", 2), "\u2588\u2588", "\u2592\u2593");
  const speed3 = positive(options.speed, "speed") ?? 1;
  const firstAt = gl.first ?? 0.5;
  if (typeof firstAt !== "number" || !Number.isFinite(firstAt))
    fail(`glint.first takes a number of seconds, not ${String(firstAt)}`);
  const first = firstAt / speed3, sweep = (positive(gl.sweep, "glint.sweep") ?? 2.4) / speed3, every = (positive(gl.every, "glint.every") ?? 3.2) / speed3;
  const width = positive(gl.width, "glint.width") ?? 2.4;
  const slant = gl.slant ?? 1.2;
  if (typeof slant !== "number" || !Number.isFinite(slant))
    fail(`glint.slant takes a number, not ${String(slant)}`);
  const step = (positive(options.type?.step, "type.step") ?? 2 / 15) / speed3;
  const rest = every <= sweep ? first : (-first % every + every) % every >= sweep ? 0 : (first + sweep + (every - sweep) / 2) % every;
  const ends = [];
  for (let i = 0, e = x0; i < glyphs.length; i++)
    ends.push((e += glyphs[i][0].length * s + (i ? gap : 0)) + (shade ? 1 : 0));
  const colored = options.color !== void 0 && options.color !== null || options.shadowColor !== void 0 && options.shadowColor !== null;
  for (const theme of ["light", "dark"]) {
    const c = pick(options.color ?? void 0, theme);
    if (Array.isArray(c) && c.length === 0)
      fail("color takes a colour as #rrggbb, or two or more for a fade, not an empty list");
  }
  const steps = (() => {
    const c = [pick(options.color, "light"), pick(options.color, "dark")];
    return c.some((v) => Array.isArray(v) && v.length > 1) ? Math.max(2, Math.min(30, cols)) : 1;
  })();
  let palette;
  if (colored) {
    palette = [];
    for (const theme of ["light", "dark"]) {
      const c = pick(options.color ?? void 0, theme);
      const stops = c === void 0 || c === null ? [INK[theme]] : typeof c === "string" ? [c] : Array.isArray(c) ? [...c] : fail(`a colour takes #rrggbb, not ${JSON.stringify(c)}`);
      const quiet2 = pick(options.shadowColor ?? void 0, theme) ?? QUIET[theme];
      for (const v of [...stops, quiet2])
        if (typeof v !== "string" || !HEX.test(v))
          fail(`a colour takes #rrggbb, not ${JSON.stringify(v)}`);
      palette.push(quiet2, ...fade(stops, steps));
    }
  }
  const half = steps + 1;
  const lo = x0, hi = x0 + span2(s) - (shade ? 2 : 1);
  const bucket = (c) => steps === 1 ? 0 : Math.max(0, Math.min(steps - 1, Math.round((c - lo) / Math.max(1, hi - lo) * (steps - 1))));
  const left = x0 - 2, right = x0 + span2(s) + 9;
  const frame = (t, { paper = false, color } = {}) => {
    const glinting = effect === "glint";
    let p = -99;
    if (glinting) {
      const u = ((t - first) % every + every) % every / sweep;
      if (u < 1)
        p = left + (right - left) * u;
    }
    const upTo = effect === "type" ? ends[Math.min(ends.length - 1, Math.max(0, Math.floor(t / step + 1e-9)))] : cols;
    const g = paper ? "light" : "dark";
    const [core, edge] = [...shine[g]];
    const lines = [];
    for (let r = 0; r < rows; r++) {
      let line2 = "";
      for (let c = 0; c < cols; c++) {
        const k = r * cols + c;
        const cell = grid3[k];
        if (c >= upTo) {
          line2 += " ";
          continue;
        }
        if (cell !== null) {
          line2 += cell;
          if (color && palette && cell !== " ")
            color[k] = (paper ? 0 : half) + 0;
          continue;
        }
        const d = Math.abs(c + slant * r - p);
        line2 += d < width / 2 ? core : d < width ? edge ?? core : fill[g];
        if (color && palette)
          color[k] = (paper ? 0 : half) + 1 + bucket(c);
      }
      lines.push(line2);
    }
    return lines.join("\n");
  };
  const motion = effect === "glint" ? { seconds: every, from: rest, once: false, pass: [first, first + sweep] } : effect === "type" ? { seconds: step * ends.length + 4 / 15, from: 0, once: true } : { seconds: 0, from: 0, once: false };
  const name = options.name ?? drawable(text2, font).trim();
  const meta = {
    name,
    category: "type",
    note: `"${name}" in block letters`,
    cols,
    rows,
    fps: effect === "still" ? 0 : 24,
    ...palette ? { palette } : {},
    ...effect === "glint" ? { loop: every } : {},
    // Held still, a glinting banner shows its glint out of sight, and a typed one every letter, not the first.
    ...effect === "glint" && rest ? { still: rest } : effect === "type" ? { still: motion.seconds } : {}
  };
  return { meta, default: () => frame, text: drawable(text2, font), motion };
}

// node_modules/ascii.rest/dist/kit/mirror.js
var MIRROR_X = [
  "/\\",
  "()",
  "<>",
  "[]",
  "{}",
  "\u250C\u2510",
  "\u2514\u2518",
  "\u251C\u2524",
  "\u256D\u256E",
  "\u2570\u256F",
  "\u250F\u2513",
  "\u2517\u251B",
  "\u2523\u252B",
  "\u2554\u2557",
  "\u255A\u255D",
  "\u2560\u2563",
  "\u2552\u2555",
  "\u2553\u2556",
  "\u2558\u255B",
  "\u2559\u255C",
  "\u255E\u2561",
  "\u255F\u2562",
  "\u250D\u2511",
  "\u250E\u2512",
  "\u2515\u2519",
  "\u2516\u251A",
  "\u251D\u2525",
  "\u2520\u2528",
  "\u258C\u2590",
  "\u2596\u2597",
  "\u2598\u259D",
  "\u2599\u259F",
  "\u259B\u259C",
  "\u259A\u259E",
  "\u258F\u2595",
  "\u25C0\u25B6",
  "\u25C4\u25BA",
  "\u25C1\u25B7",
  "\u25E2\u25E3",
  "\u25E4\u25E5",
  "\u2571\u2572",
  "\u2310\xAC",
  "\xAB\xBB",
  "\u2039\u203A",
  "bd",
  "pq",
  "\u2196\u2197",
  "\u2199\u2198",
  "\u2190\u2192",
  "\u21D0\u21D2",
  "\u2574\u2576",
  "\u2578\u257A",
  "\u25DC\u25DD",
  "\u25DF\u25DE",
  "\u2282\u2283"
];
var MIRROR_Y = [
  "/\\",
  "\u2580\u2584",
  "\u250C\u2514",
  "\u2510\u2518",
  "\u252C\u2534",
  "\u256D\u2570",
  "\u256E\u256F",
  "\u250F\u2517",
  "\u2513\u251B",
  "\u2533\u253B",
  "\u2554\u255A",
  "\u2557\u255D",
  "\u2566\u2569",
  "\u2552\u2558",
  "\u2555\u255B",
  "\u2553\u2559",
  "\u2556\u255C",
  "\u2564\u2567",
  "\u2565\u2568",
  "\u250D\u2515",
  "\u250E\u2516",
  "\u2511\u2519",
  "\u2512\u251A",
  "\u252F\u2537",
  "\u2530\u2538",
  "\u2596\u2598",
  "\u2597\u259D",
  "\u2599\u259B",
  "\u259F\u259C",
  "\u259A\u259E",
  "\u2581\u2594",
  "\u25B2\u25BC",
  "\u25B3\u25BD",
  "\u25E2\u25E5",
  "\u25E3\u25E4",
  "\u2571\u2572",
  "^v",
  "\u203E_",
  ".'",
  ",`",
  "\u2229\u222A",
  "bp",
  "dq",
  "MW",
  "nu",
  "\u2191\u2193",
  "\u21D1\u21D3",
  "\u2196\u2199",
  "\u2197\u2198",
  "\u2227\u2228",
  "\u2575\u2577",
  "\u2579\u257B",
  "\u25E0\u25E1",
  "\u25DC\u25DF",
  "\u25DD\u25DE",
  "\u2293\u2294",
  "\u22A4\u22A5"
];
var DOTS_X = [[1, 8], [2, 16], [4, 32], [64, 128]];
var DOTS_Y = [[1, 64], [2, 4], [8, 128], [16, 32]];
var mirrors = null;
function mirror() {
  const make = (pairs, dots) => {
    const m = new Uint16Array(65536);
    for (let i = 0; i < m.length; i++)
      m[i] = i;
    for (const [a, b] of pairs)
      m[a.charCodeAt(0)] = b.charCodeAt(0), m[b.charCodeAt(0)] = a.charCodeAt(0);
    for (let k = 0; k < 256; k++)
      m[10240 + k] = 10240 + dots.reduce((v, [a, b]) => v | (k & a ? b : 0) | (k & b ? a : 0), 0);
    return m;
  };
  return mirrors ??= { x: make(MIRROR_X, DOTS_X), y: make(MIRROR_Y, DOTS_Y) };
}

// node_modules/ascii.rest/dist/kit/compose.js
var ANCHORS = ["top-left", "top", "top-right", "left", "center", "right", "bottom-left", "bottom", "bottom-right"];
var SIDES = ["left", "right", "up", "down"];
var shown = (v) => typeof v === "function" ? "a function" : typeof v === "string" ? JSON.stringify(v) : Array.isArray(v) ? `[${v.map(shown).join(", ")}]` : v !== null && typeof v === "object" ? "an object" : String(v);
var or = (words2) => words2.length > 1 ? `${words2.slice(0, -1).join(", ")} or ${words2.at(-1)}` : words2[0] ?? "";
var finite = (v) => typeof v === "number" && Number.isFinite(v);
function whole2(v, name, least, dflt) {
  if (v === void 0)
    return dflt;
  if (!Number.isInteger(v) || v < least)
    fail2(`${name} takes a whole number of ${least} or more, not ${shown(v)}`);
  return v;
}
function duration(v, name, dflt, zero = false) {
  if (v === void 0)
    return dflt;
  if (!finite(v) || (zero ? v < 0 : v <= 0))
    fail2(`${name} takes a number of seconds ${zero ? "of 0 or more" : "above 0"}, not ${shown(v)}`);
  return v;
}
function oneOf(v, name, list2, dflt) {
  if (v === void 0)
    return dflt;
  if (!list2.includes(v))
    fail2(`${name} takes ${or(list2.map((w) => JSON.stringify(w)))}, not ${shown(v)}`);
  return v;
}
function object(v, name, keys) {
  if (v === void 0)
    return {};
  if (v === null || typeof v !== "object" || Array.isArray(v))
    fail2(`${name} takes an object of options, not ${shown(v)}`);
  if (keys) {
    for (const [k, val] of Object.entries(v))
      if (val !== void 0 && !keys.includes(k))
        fail2(`${name} has no option ${JSON.stringify(k)}: it takes ${and2(keys)}`);
  }
  return v;
}
var oneLine = (v) => typeof v === "string" && !!v.trim() && !/[\u0000-\u001f\u007f-\u009f]/.test(v);
function naming(fn, o) {
  if (o.name !== void 0 && !oneLine(o.name))
    fail2(`${fn}()'s name takes one line, such as "dashboard", not ${shown(o.name)}`);
  if (o.note !== void 0 && !(oneLine(o.note) && o.note.length <= 72))
    fail2(`${fn}()'s note takes one line of 1 to 72 characters saying what you see, not ${shown(o.note)}`);
  return { ...o.name !== void 0 ? { name: o.name.trim() } : {}, ...o.note !== void 0 ? { note: o.note } : {} };
}
function loopOption(fn, v) {
  if (v === void 0)
    return void 0;
  if (!finite(v) || v < 0.05 || v > 60)
    fail2(`${fn}()'s loop takes seconds from 0.05 to 60, the loop it plays round on, not ${shown(v)}`);
  return Math.round(v * 100) / 100;
}
var CLIP = ["src", "options", "offset", "speed", "color"];
function colorOf2(v, name) {
  if (v === void 0)
    return null;
  if (isHex(v))
    return [v];
  if (v !== null && typeof v === "object" && isHex(v.light) && isHex(v.dark))
    return [v.light, v.dark];
  if (typeof v === "string") {
    const c = colorOf(v, name);
    return [c.light, c.dark];
  }
  return fail2(`${name} takes #rrggbb, { light, dark }, or a palette's name such as "ocean", not ${shown(v)}`);
}
var isPiece = (v) => v !== null && typeof v === "object" && "meta" in v && typeof v.default === "function";
var isClip = (v) => v !== null && typeof v === "object" && !(v instanceof Surface) && "src" in v && !("meta" in v);
var unwrap = (v) => v !== null && typeof v === "object" && !("meta" in v) && !("src" in v) && isPiece(v.default) ? v.default : v;
var textName = (text2) => {
  const line2 = text2.split("\n").find((l) => l.trim())?.trim() ?? "";
  return line2 ? `"${line2.slice(0, 24)}"` : "text";
};
function prepare(fn, v, keys = CLIP) {
  v = unwrap(v);
  if (isClip(v))
    object(v, `${fn}()'s part`, keys);
  const clip = isClip(v) ? v : { src: v };
  const given = unwrap(clip.src);
  const src = typeof given === "string" ? given.replace(/\r\n?/g, "\n") : given;
  if (!(typeof src === "string" || src instanceof Surface || isPiece(src)))
    fail2(`${fn}() takes pieces, text, Surfaces or { src } clips, not ${shown(src)}`);
  if (typeof src === "string" && /[\ud800-\udfff]/.test(src))
    fail2(`text takes characters from the Basic Multilingual Plane, one a cell, so not emoji: ${JSON.stringify(src.slice(0, 24))}`);
  const p = asPiece(src, typeof src === "string" ? textName(src) : "drawing");
  if (clip.options !== void 0 && (clip.options === null || typeof clip.options !== "object" || Array.isArray(clip.options)))
    fail2(`a clip's options take an object of the piece's options, not ${shown(clip.options)}`);
  const offset = clip.offset === void 0 ? 0 : finite(clip.offset) ? clip.offset : fail2(`a clip's offset takes a number of seconds, not ${shown(clip.offset)}`);
  const speed3 = clip.speed === void 0 ? 1 : finite(clip.speed) && clip.speed > 0 ? clip.speed : fail2(`a clip's speed takes a number above 0, not ${shown(clip.speed)}`);
  const tint = colorOf2(clip.color, "a clip's color");
  const frames = src.frames === true;
  return { piece: p, meta: p.meta, options: { ...clip.options }, offset, speed: speed3, tint, stretch: 0, cols: p.meta.cols, rows: p.meta.rows, frames };
}
function fit(p, cell) {
  const own = p.meta.cell ?? 2;
  p.stretch = own === cell ? 0 : own > cell ? 1 : -1;
  p.rows = p.stretch > 0 ? p.meta.rows * 2 : p.stretch < 0 ? Math.ceil(p.meta.rows / 2) : p.meta.rows;
  return p;
}
function list(fn, parts, keys = CLIP) {
  if (!Array.isArray(parts) || !parts.length)
    fail2(`${fn}() takes a list of one or more parts: pieces, text, Surfaces or { src } clips`);
  const all = parts.map((v) => prepare(fn, v, keys));
  for (const p of all)
    fit(p, all[0].meta.cell ?? 2);
  return all;
}
var apart = (a, b) => 0.3 * (a[0] - b[0]) ** 2 + 0.59 * (a[1] - b[1]) ** 2 + 0.11 * (a[2] - b[2]) ** 2;
function merge(parts, extra = [], plain = false) {
  const lists = parts.map((p) => p.tint ?? p.meta.palette);
  if (extra.length)
    lists.push(extra);
  if (plain)
    lists.push(void 0);
  try {
    return mergePalettes(lists);
  } catch {
    const all = [];
    const seen = /* @__PURE__ */ new Map();
    const add = (c) => {
      const k = c.toLowerCase();
      if (!seen.has(k))
        seen.set(k, all.push(c) - 1);
      return seen.get(k);
    };
    const idx = lists.map((p) => (p ?? []).map(add));
    const inked = lists.some((p) => !p) ? { light: add(INK2.light), dark: add(INK2.dark) } : null;
    const n = all.length;
    const values = all.map(rgb);
    const into2 = all.map((_, i) => i);
    const alive = new Uint8Array(n).fill(1);
    const near = new Int32Array(n), gap = new Float64Array(n);
    const look = (i) => {
      let best = Infinity, at4 = -1;
      for (let j = 0; j < n; j++)
        if (j !== i && alive[j]) {
          const d = apart(values[i], values[j]);
          if (d < best)
            best = d, at4 = j;
        }
      near[i] = at4;
      gap[i] = best;
    };
    for (let i = 0; i < n; i++)
      look(i);
    for (let left = n; left > 64; left--) {
      let a = -1;
      for (let i = 0; i < n; i++)
        if (alive[i] && (a < 0 || gap[i] < gap[a]))
          a = i;
      const keep = Math.min(a, near[a]), drop = Math.max(a, near[a]);
      alive[drop] = 0;
      for (let i = 0; i < n; i++)
        if (into2[i] === drop)
          into2[i] = keep;
      for (let i = 0; i < n; i++)
        if (alive[i] && near[i] === drop)
          look(i);
    }
    const kept = into2.filter((v, i) => v === i);
    const at3 = new Map(kept.map((c, i) => [c, i]));
    const to = (i) => at3.get(into2[i]);
    return {
      palette: kept.map((i) => all[i]),
      maps: idx.map((list2) => Uint8Array.from(list2, to)),
      ink: inked && { light: to(inked.light), dark: to(inked.dark) }
    };
  }
}
var LOOPS = { logos: "shine", companies: "shine", distros: "scan" };
function period(p) {
  const { meta } = p;
  if (!meta.fps)
    return 0;
  if (p.offset < 0)
    return void 0;
  let loop = meta.loop;
  if (loop === void 0 && LOOPS[meta.category]) {
    const every = { ...meta.options, ...p.options }[LOOPS[meta.category]];
    if (finite(every) && every > 0)
      loop = every;
  }
  return loop === void 0 ? void 0 : loop / p.speed;
}
var gcd = (a, b) => b ? gcd(b, a % b) : a;
function together(periods) {
  let l = 0;
  for (const p of periods) {
    if (p === 0)
      continue;
    if (p === void 0)
      return void 0;
    const h = Math.round(p * 100);
    if (h < 1 || Math.abs(h - p * 100) > 1e-6)
      return void 0;
    l = l ? l / gcd(l, h) * h : h;
    if (l > 6e3)
      return void 0;
  }
  return l ? l / 100 : void 0;
}
var playable = (loop) => loop && loop <= 60 ? loop : void 0;
function stillOf(parts) {
  let at3;
  for (const p of parts)
    if (p.meta.still !== void 0 && p.meta.fps) {
      const s = (p.meta.still - p.offset) / p.speed;
      if (s >= 0 && (at3 === void 0 || s > at3))
        at3 = s;
    }
  return at3 || void 0;
}
function groundOf(parts) {
  let g;
  for (const { meta } of parts)
    if (meta.ground) {
      if (g === void 0)
        g = meta.ground;
      else if (g.toLowerCase() !== meta.ground.toLowerCase())
        return void 0;
    }
  return g;
}
var fpsOf = (parts) => Math.max(0, ...parts.map((p) => p.meta.fps));
var categoryOf = (parts) => parts.every((p) => p.meta.category === parts[0].meta.category) ? parts[0].meta.category : "generative";
var short = (s) => s.length > 72 ? s.slice(0, 71) + "\u2026" : s;
var optionsOf = (p) => p.meta.options !== void 0 || Object.keys(p.options).length ? { ...p.meta.options, ...p.options } : void 0;
function build(fn, w, m, setup) {
  if (w.cols > MAX.cols || w.rows > MAX.rows)
    fail2(`${fn}() makes a piece ${w.cols} by ${w.rows}, past the ${MAX.cols} by ${MAX.rows} a piece can be: use fewer or smaller parts, or less room between them`);
  return piece({
    name: w.name,
    note: w.note ?? short(w.name),
    category: w.category,
    cols: w.cols,
    rows: w.rows,
    fps: w.fps,
    ...w.cell === 1 ? { cell: 1 } : {},
    ...w.ground ? { ground: w.ground } : {},
    ...w.loop ? { loop: w.loop } : {},
    ...w.still ? { still: w.still } : {},
    ...w.clock ? { clock: true } : {},
    ...w.options ? { options: w.options } : {},
    ...m.palette.length ? { palette: m.palette } : {},
    ...m.ink ? { ink: m.ink } : {}
  }, { setup });
}
function restretch(g, out, k) {
  const { cols } = g;
  for (let r = 0; r < out.rows; r++)
    for (let c = 0; c < cols; c++) {
      let i;
      if (k > 0)
        i = (r >> 1) * cols + c;
      else {
        i = 2 * r * cols + c;
        if (g.chars[i] === EMPTY && 2 * r + 1 < g.rows)
          i += cols;
      }
      out.chars[r * cols + c] = g.chars[i];
      out.colors[r * cols + c] = g.colors[i];
    }
}
function player(p, map, options = p.options) {
  const sampler = sample(p.piece, options);
  const fitted = p.stretch ? new Surface(p.cols, p.rows) : null;
  const tint = p.tint && map ? [map[0], map[p.tint.length - 1]] : null;
  return (t, paper, mono) => {
    const g = sampler.at(Math.max(0, t * p.speed + p.offset), { paper, mono: mono || !!tint });
    if (tint && !mono) {
      const k = tint[paper ? 0 : 1], { chars: chars3, colors } = g;
      for (let i = 0; i < chars3.length; i++)
        if (chars3[i] !== EMPTY)
          colors[i] = k;
    } else if (map && !mono) {
      const c = g.colors;
      for (let i = 0; i < c.length; i++)
        if (c[i] !== NONE)
          c[i] = map[c[i]] ?? NONE;
    }
    if (!fitted)
      return g;
    restretch(g, fitted, p.stretch);
    return fitted;
  };
}
function place(anchor, W, H, w, h, margin = 0) {
  const x = anchor.endsWith("left") ? margin : anchor.endsWith("right") ? W - w - margin : Math.floor((W - w) / 2);
  const y = anchor.startsWith("top") ? margin : anchor.startsWith("bottom") ? H - h - margin : Math.floor((H - h) / 2);
  return [x, y];
}
var LAYER = [...CLIP, "anchor", "margin", "move", "x", "y", "mask", "halo"];
function travel(v) {
  if (v === void 0)
    return null;
  const sides = or(SIDES.map((d) => JSON.stringify(d)));
  if (v === null || typeof v !== "object" || Array.isArray(v)) {
    if (!SIDES.includes(v))
      fail2(`a layer's move takes ${sides}, or { to, period }, not ${shown(v)}`);
    return { to: v, period: 0 };
  }
  const o = v;
  if (!SIDES.includes(o.to))
    fail2(`a layer's move.to takes ${sides}, not ${shown(o.to)}`);
  return { to: o.to, period: duration(o.period, "a layer's move period", 0) };
}
function position(v, name) {
  if (v === void 0)
    return 0;
  if (typeof v === "function") {
    const at0 = v(0);
    if (!finite(at0))
      fail2(`a layer's ${name} as a function takes t and returns a number, not ${shown(at0)} at t = 0`);
    return v;
  }
  if (!finite(v))
    fail2(`a layer's ${name} takes a number of cells, or a function of t that returns one, not ${shown(v)}`);
  return v;
}
function layerOf(fn, v, anchor) {
  const p = prepare(fn, v, LAYER);
  const l = isClip(v) ? v : {};
  if (l.halo !== void 0 && !(Number.isInteger(l.halo) && l.halo >= 0 && l.halo <= 4))
    fail2(`a layer's halo takes a whole number of cells from 0 to 4, not ${shown(l.halo)}`);
  let mask = " ";
  if (l.mask === null)
    mask = null;
  else if (l.mask !== void 0) {
    if (typeof l.mask !== "string" || l.mask.length !== 1)
      fail2(`a layer's mask takes one character, or null for none, not ${shown(l.mask)}`);
    code(l.mask);
    mask = l.mask;
  }
  return {
    ...p,
    x: position(l.x, "x"),
    y: position(l.y, "y"),
    anchor: oneOf(l.anchor, "a layer's anchor", ANCHORS, anchor),
    margin: whole2(l.margin, "a layer's margin", 0, 0),
    move: travel(l.move),
    mask,
    halo: l.halo
  };
}
function knockout(s, g, x, y, h, mask) {
  const dy = Math.max(1, Math.round(h / 2));
  const blank = 32;
  for (let r = 0; r < g.rows; r++)
    for (let c = 0; c < g.cols; c++) {
      const ch = g.chars[r * g.cols + c];
      if (ch === EMPTY || ch === mask)
        continue;
      for (let j = r - dy; j <= r + dy; j++)
        for (let i = c - h; i <= c + h; i++) {
          const k = s.index(x + i, y + j);
          if (k >= 0)
            s.put(k, blank);
        }
    }
}
var at = (v, t) => {
  const n = typeof v === "function" ? v(t) : v;
  return finite(n) ? Math.floor(n) : 0;
};
var around = (p, size2, room) => {
  const span2 = room + size2;
  return ((p + size2) % span2 + span2) % span2 - size2;
};
function spot(l, t, cols, rows) {
  const [ax, ay] = place(l.anchor, cols, rows, l.cols, l.rows, l.margin);
  let x = ax + at(l.x, t), y = ay + at(l.y, t);
  if (l.move) {
    const { to, period: period2 } = l.move;
    const across2 = to === "left" || to === "right";
    const span2 = across2 ? cols + l.cols : rows + l.rows;
    const step = Math.floor(t * span2 / period2 + 1e-9) * (to === "right" || to === "down" ? 1 : -1);
    if (across2)
      x = around(x + step, l.cols, cols);
    else
      y = around(y + step, l.rows, rows);
  }
  return [x, y];
}
function stack(fn, all, given = {}) {
  const cell = all[0].meta.cell ?? 2;
  for (const l of all)
    fit(l, cell);
  const { cols, rows } = all[0];
  for (let i = 1; i < all.length; i++) {
    const l = all[i];
    if (l.meta.category === "type" && !l.move && typeof l.x !== "function" && typeof l.y !== "function" && (l.cols > cols || l.rows > rows)) {
      const way = l.cols > cols ? `${l.cols} columns, wider than the ${cols}` : `${l.rows} rows, taller than the ${rows}`;
      fail2(`${fn}(): ${l.meta.name} is ${way} of ${all[0].meta.name} under it, so its edges would be cut off. Make it smaller (banner() takes max: ${cols}, or a narrower font), crop() it, or lay it on something bigger`);
    }
    if (l.halo === void 0)
      l.halo = l.meta.category === "type" && all.slice(0, i).some((b) => b.meta.fps > 0) ? 1 : 0;
  }
  const steered = all.some((l) => typeof l.x === "function" || typeof l.y === "function");
  const theirs = together(all.map(period).filter((p) => p !== void 0));
  const fitted = theirs && theirs <= 16 ? Math.round(Math.max(1, Math.round(8 / theirs)) * theirs * 100) / 100 : 8;
  for (const l of all)
    if (l.move && !l.move.period)
      l.move.period = fitted;
  const travels = all.flatMap((l) => l.move ? [l.move.period] : []);
  const own = travels.length ? together(travels) : 0;
  const m = merge(all);
  const whole4 = {
    name: given.name ?? all.map((l) => l.meta.name).reverse().join(" over "),
    note: given.note,
    category: all[0].meta.category,
    cols,
    rows,
    cell,
    // A layer that moves needs frames even over stills.
    fps: Math.max(fpsOf(all), steered || travels.length ? 24 : 0),
    // A scene on a blank stage keeps its ground, so it is drawn for its own dark sky on a light page too.
    ground: groundOf(all),
    // By the kit's time rule: the crossings' period with the parts' loops, a part that never repeats counting as
    // repeating on the crossings'.
    loop: steered || own === void 0 ? void 0 : together([own, ...all.map((l) => period(l) ?? (own || void 0))]),
    still: stillOf(all),
    clock: all.some((l) => l.meta.clock)
  };
  return build(fn, whole4, m, () => {
    const play = all.map((l, i) => player(l, m.maps[i]));
    return (t, s, ctx) => {
      for (let i = 0; i < all.length; i++) {
        const l = all[i];
        const g = play[i](t, ctx.paper, ctx.mono);
        const [x, y] = spot(l, t, cols, rows);
        if (l.mask === null)
          s.fill(" ", void 0, { x, y, cols: l.cols, rows: l.rows });
        else if (l.halo)
          knockout(s, g, x, y, l.halo, l.mask === null ? -1 : l.mask.charCodeAt(0));
        s.paste(g, x, y, { mask: l.mask });
      }
    };
  });
}
function layer(base, ...over2) {
  return stack("layer", [base, ...over2].map((v) => layerOf("layer", v, "top-left")));
}
function over(top, bottom, o = {}) {
  const { name, note, ...opts2 } = object(o, "over()", [...LAYER.filter((k) => k !== "src"), "name", "note"]);
  const upper = isClip(top) ? { ...opts2, ...top } : { ...opts2, src: top };
  return stack("over", [layerOf("over", bottom, "top-left"), layerOf("over", upper, "center")], naming("over", { name, note }));
}
var BOXES = { single: "\u250C\u2510\u2514\u2518\u2500\u2502", double: "\u2554\u2557\u255A\u255D\u2550\u2551", rounded: "\u256D\u256E\u2570\u256F\u2500\u2502", heavy: "\u250F\u2513\u2517\u251B\u2501\u2503", ascii: "++++-|" };
function borderOf(name, v) {
  if (v === void 0 || v === false)
    return null;
  const o = v === true ? {} : v !== null && typeof v === "object" && !Array.isArray(v) ? v : fail2(`${name} takes true, or { style, title, color, pad }, not ${shown(v)}`);
  object(o, name, ["style", "title", "color", "pad"]);
  const style = o.style ?? "rounded";
  const chars3 = typeof style === "string" && Object.hasOwn(BOXES, style) ? BOXES[style] : style;
  if (typeof chars3 !== "string" || chars3.length !== 6 || /[\ud800-\udfff]/.test(chars3))
    fail2(`a border's style takes ${or(Object.keys(BOXES).map((k) => JSON.stringify(k)))}, or 6 characters of your own: top left, top right, bottom left, bottom right, across, down; not ${shown(style)}`);
  for (const ch of chars3)
    code(ch);
  const title = o.title ?? false;
  if (typeof title !== "boolean" && typeof title !== "string")
    fail2(`a border's title takes words, or true for the piece's name, not ${shown(title)}`);
  if (typeof title === "string")
    for (const ch of title)
      code(ch);
  const color = colorOf2(o.color, "a border's color");
  const p = o.pad;
  const pad2 = p === void 0 ? [0, 1] : typeof p === "number" ? [whole2(p, "a border's pad", 0, 0), whole2(p, "a border's pad", 0, 0)] : Array.isArray(p) && p.length === 2 ? [whole2(p[0], "a border's pad rows", 0, 0), whole2(p[1], "a border's pad columns", 0, 0)] : fail2(`a border's pad takes a number, or [rows, columns], not ${shown(p)}`);
  return { chars: chars3, title, color, pad: pad2 };
}
function box(s, { x, y, cols: w, rows: h }, chars3, title, color) {
  const [tl, tr, bl, br, across2, down2] = Array.from(chars3, (ch) => ch.charCodeAt(0));
  const set = (cx, cy, ch) => {
    const i = s.index(cx, cy);
    if (i >= 0)
      s.put(i, ch, color);
  };
  for (let c = 1; c < w - 1; c++)
    set(x + c, y, across2), set(x + c, y + h - 1, across2);
  for (let r = 1; r < h - 1; r++)
    set(x, y + r, down2), set(x + w - 1, y + r, down2);
  set(x, y, tl), set(x + w - 1, y, tr), set(x, y + h - 1, bl), set(x + w - 1, y + h - 1, br);
  if (title && w >= 7) {
    const room = w - 6;
    const words2 = ` ${title.length > room ? title.slice(0, room - 1).trimEnd() + "\u2026" : title} `;
    for (let k = 0; k < words2.length; k++)
      set(x + 2 + k, y, words2.charCodeAt(k));
  }
}
var titleOf = (b, name) => b.title === true ? name.replace(/[\u0000-\u001f\u007f-\u009f\ud800-\udfff]+/g, " ").replace(/\s+/g, " ").trim().replace(/^"(.+)"$/, "$1") : b.title || "";
var borderInk = (m, at3, b) => b?.color ? [m.maps[at3][0], m.maps[at3][b.color.length - 1]] : null;
function border(src, o = {}) {
  const fn = "border";
  const p = prepare(fn, src);
  const b = borderOf("border()", object(o, "border()"));
  const [py, px] = b.pad;
  const cols = p.cols + 2 * px + 2, rows = p.rows + 2 * py + 2;
  const m = merge([p], b.color ?? [], !b.color);
  const title = titleOf(b, p.meta.name);
  const boxed = build(fn, { ...single(p), cols, rows }, m, (options) => {
    const play = player(p, m.maps[0], options);
    const ink = borderInk(m, 1, b);
    return (t, s, ctx) => {
      box(s, { x: 0, y: 0, cols, rows }, b.chars, title, ctx.mono || !ink ? NONE : ink[ctx.paper ? 0 : 1]);
      s.paste(play(t, ctx.paper, ctx.mono), px + 1, py + 1);
    };
  });
  return withMotion(boxed, playedOnce(p));
}
function arrange(fn, all, cols, rows, spots, name, own, boxes2 = [], b = null) {
  const m = merge(all, b?.color ?? [], boxes2.length > 0 && !b?.color);
  const { name: given, note } = naming(fn, own);
  const loop = loopOption(fn, own.loop);
  const fps = fpsOf(all);
  const whole4 = {
    name: given ?? name,
    note,
    category: categoryOf(all),
    cols,
    rows,
    cell: all[0].meta.cell ?? 2,
    fps,
    ground: groundOf(all),
    // A loop of the whole's own wins: its time wraps round on it, so parts that would only meet past a minute repeat.
    loop: loop !== void 0 ? fps ? loop : void 0 : together(all.map(period)),
    still: stillOf(all),
    clock: all.some((p) => p.meta.clock)
  };
  return build(fn, whole4, m, () => {
    const play = all.map((p, i) => player(p, m.maps[i]));
    const ink = borderInk(m, all.length, b);
    return (t, s, ctx) => {
      if (loop !== void 0)
        t -= loop * Math.floor(t / loop);
      const k = ctx.mono || !ink ? NONE : ink[ctx.paper ? 0 : 1];
      for (const bx of boxes2)
        box(s, bx.region, b.chars, bx.title, k);
      for (let i = 0; i < all.length; i++)
        s.paste(play[i](t, ctx.paper, ctx.mono), spots[i][0], spots[i][1]);
    };
  });
}
function grid(parts, o = {}) {
  const fn = "grid";
  const opts2 = object(o, "grid()", ["columns", "gap", "align", "border", "loop", "name", "note"]);
  const all = list(fn, parts);
  const columns = whole2(opts2.columns, "grid's columns", 1, Math.ceil(Math.sqrt(all.length)));
  const g = opts2.gap;
  const [gx, gy] = g === void 0 ? [2, 1] : typeof g === "number" ? [whole2(g, "grid's gap", 0, 0), whole2(g, "grid's gap", 0, 0)] : Array.isArray(g) && g.length === 2 ? [whole2(g[0], "grid's gap columns", 0, 0), whole2(g[1], "grid's gap rows", 0, 0)] : fail2(`grid's gap takes a number, or [columns, rows], not ${shown(g)}`);
  const align = oneOf(opts2.align, "grid's align", ANCHORS, "center");
  const b = borderOf("grid's border", opts2.border);
  const n = Math.min(columns, all.length), lines = Math.ceil(all.length / n);
  const widths = Array.from({ length: n }, (_, j) => Math.max(...all.filter((_2, i) => i % n === j).map((p) => p.cols)));
  const heights = Array.from({ length: lines }, (_, r) => Math.max(...all.slice(r * n, r * n + n).map((p) => p.rows)));
  const [py, px] = b ? b.pad : [0, 0];
  const e = b ? 1 : 0;
  const cw = widths.map((w) => w + 2 * (px + e)), ch = heights.map((h) => h + 2 * (py + e));
  const xs = cw.map((_, j) => cw.slice(0, j).reduce((a, v) => a + v + gx, 0));
  const ys = ch.map((_, r) => ch.slice(0, r).reduce((a, v) => a + v + gy, 0));
  const spots = all.map((p, i) => {
    const j = i % n, r = Math.floor(i / n);
    if (b && p.frames) {
      const [dx2, dy2] = place(align, cw[j], ch[r], p.cols, p.rows);
      return [xs[j] + dx2, ys[r] + dy2];
    }
    const [dx, dy] = place(align, widths[j], heights[r], p.cols, p.rows);
    return [xs[j] + e + px + dx, ys[r] + e + py + dy];
  });
  const boxes2 = b ? all.flatMap((p, i) => {
    const j = i % n, r = Math.floor(i / n);
    return p.frames ? [] : [{ region: { x: xs[j], y: ys[r], cols: cw[j], rows: ch[r] }, title: titleOf(b, p.meta.name) }];
  }) : [];
  const cols = xs[n - 1] + cw[n - 1], rows = ys[lines - 1] + ch[lines - 1];
  return arrange(fn, all, cols, rows, spots, and2(all.map((p) => p.meta.name)), opts2, boxes2, b);
}
var single = (p) => ({
  name: p.meta.name,
  note: p.meta.note,
  category: p.meta.category,
  cols: p.cols,
  rows: p.rows,
  cell: p.meta.cell ?? 2,
  fps: p.meta.fps,
  ground: p.meta.ground,
  loop: playable(period(p)),
  still: p.meta.still !== void 0 ? Math.max(0, (p.meta.still - p.offset) / p.speed) : void 0,
  clock: p.meta.clock,
  options: optionsOf(p)
});
function playedOnce(p, lag = 0, rate2 = 1) {
  const m = p.piece.motion;
  if (!m?.once || !finite(m.seconds) || !finite(m.from))
    return void 0;
  const end = lag + (m.from + m.seconds - p.offset) / (rate2 * p.speed);
  return end <= 60 ? { seconds: Math.max(0, end), from: 0, once: true } : void 0;
}
var withMotion = (whole4, motion) => motion ? Object.assign(whole4, { motion }) : whole4;
function reshape(fn, p, cols, rows, draw) {
  const m = merge([p]);
  const whole4 = build(fn, { ...single(p), cols, rows }, m, (options) => {
    const play = player(p, m.maps[0], options);
    return (t, s, ctx) => draw(play(t, ctx.paper, ctx.mono), s);
  });
  return withMotion(whole4, playedOnce(p));
}
function crop(src, region) {
  const p = prepare("crop", src);
  if (region === null || typeof region !== "object")
    fail2(`crop() takes a region, { x, y, cols, rows }, not ${shown(region)}`);
  const { x, y, cols, rows } = region;
  for (const [k, v] of [["x", x], ["y", y]])
    if (!Number.isInteger(v))
      fail2(`crop's region.${k} takes a whole number, not ${shown(v)}`);
  for (const [k, v] of [["cols", cols], ["rows", rows]])
    if (!Number.isInteger(v) || v < 1)
      fail2(`crop's region.${k} takes a whole number of 1 or more, not ${shown(v)}`);
  const x0 = Math.max(0, x), y0 = Math.max(0, y), x1 = Math.min(p.cols, x + cols), y1 = Math.min(p.rows, y + rows);
  if (x1 <= x0 || y1 <= y0)
    fail2(`crop's region, ${cols} by ${rows} at ${x}, ${y}, misses ${p.meta.name}, which is ${p.cols} by ${p.rows}`);
  return reshape("crop", p, x1 - x0, y1 - y0, (g, s) => s.paste(g, -x0, -y0));
}
function pad(src, n) {
  const p = prepare("pad", src);
  let sides;
  if (typeof n === "number")
    sides = Array(4).fill(whole2(n, "pad", 0, 0));
  else if (Array.isArray(n) && n.length === 2) {
    const [r, c] = [whole2(n[0], "pad's rows", 0, 0), whole2(n[1], "pad's columns", 0, 0)];
    sides = [r, c, r, c];
  } else if (n !== null && typeof n === "object" && !Array.isArray(n)) {
    const o = n;
    sides = ["top", "right", "bottom", "left"].map((k) => whole2(o[k], `pad's ${k}`, 0, 0));
  } else
    return fail2(`pad takes a number, [rows, columns] or { top, right, bottom, left }, not ${shown(n)}`);
  const [top, right, bottom, left] = sides;
  return reshape("pad", p, p.cols + left + right, p.rows + top + bottom, (g, s) => s.paste(g, left, top));
}
function scale(src, factor) {
  const p = prepare("scale", src);
  const [fx, fy] = typeof factor === "number" ? [whole2(factor, "scale's factor", 1, 1), whole2(factor, "scale's factor", 1, 1)] : Array.isArray(factor) && factor.length === 2 ? [whole2(factor[0], "scale's factor across", 1, 1), whole2(factor[1], "scale's factor down", 1, 1)] : fail2(`scale takes a whole number of 1 or more, or [across, down], not ${shown(factor)}`);
  const cols = p.cols * fx, rows = p.rows * fy;
  return reshape("scale", p, cols, rows, (g, s) => {
    for (let y = 0; y < rows; y++) {
      const from = Math.floor(y / fy) * g.cols;
      for (let x = 0, i = y * cols; x < cols; x++, i++) {
        const k = from + Math.floor(x / fx);
        s.put(i, g.chars[k], g.colors[k]);
      }
    }
  });
}
function flip(src, axis) {
  const p = prepare("flip", src);
  if (axis === void 0)
    fail2(`flip() takes an axis: "x" mirrors it left to right, "y" turns it upside down, "both" does both`);
  const ax = oneOf(axis, "flip's axis", ["x", "y", "both"], "x");
  const fx = ax !== "y", fy = ax !== "x";
  const { cols, rows } = p;
  return reshape("flip", p, cols, rows, (g, s) => {
    const m = mirror();
    for (let y = 0; y < rows; y++)
      for (let x = 0; x < cols; x++) {
        const k = (fy ? rows - 1 - y : y) * cols + (fx ? cols - 1 - x : x);
        let ch = g.chars[k];
        if (fx)
          ch = m.x[ch];
        if (fy)
          ch = m.y[ch];
        s.put(y * cols + x, ch, g.colors[k]);
      }
  });
}
function retime(fn, p, time, timing, motion) {
  const given = Object.fromEntries(Object.entries(timing).filter(([, v]) => v !== void 0));
  if (p.tint) {
    const m = merge([p]);
    const painted = build(fn, { ...single(p), loop: void 0, still: void 0, ...given }, m, (options2) => {
      const play = player(p, m.maps[0], options2);
      return (t, s, ctx) => s.paste(play(time(t), ctx.paper, ctx.mono), 0, 0);
    });
    return withMotion(painted, motion);
  }
  const { loop: _loop, still: _still, ...rest } = p.meta;
  const options = optionsOf(p);
  const meta = checkMeta({ ...rest, ...options ? { options } : {}, ...given });
  const retimed = chained({
    meta,
    default(o) {
      const frame = p.piece.default({ ...meta.options, ...o });
      return (t, env) => frame(Math.max(0, time(Number.isFinite(t) ? t : 0) * p.speed + p.offset), env);
    }
  });
  return withMotion(retimed, motion);
}
var stillAt = (p) => p.meta.still !== void 0 ? Math.max(0, (p.meta.still - p.offset) / p.speed) : void 0;
function speed(src, factor) {
  if (!finite(factor) || factor <= 0)
    fail2(`speed takes a number above 0, 2 for twice as fast, not ${shown(factor)}`);
  const p = prepare("speed", src);
  const loop = period(p), still = stillAt(p);
  return retime("speed", p, (t) => t * factor, { loop: playable(loop ? loop / factor : void 0), still: still && still / factor }, playedOnce(p, 0, factor));
}
function delay(src, seconds) {
  const wait = duration(seconds, "delay", 0, true);
  const p = prepare("delay", src);
  const still = stillAt(p);
  return retime("delay", p, (t) => t - wait, { still: still !== void 0 ? still + wait : void 0 }, playedOnce(p, wait));
}
function repeat(src, seconds) {
  const every = duration(seconds, "repeat", 1);
  const p = prepare("repeat", src);
  const still = stillAt(p);
  return retime("repeat", p, (t) => t - every * Math.floor(t / every), { loop: p.meta.fps ? every : void 0, still: still !== void 0 && still < every ? still : void 0 });
}
function freeze(src, at3) {
  const moment = duration(at3, "freeze", 0, true);
  return retime("freeze", prepare("freeze", src), () => moment, { fps: 0 });
}
function named(src, name, o = {}) {
  const opts2 = object(o, "named()", ["note", "category"]);
  const line2 = (v) => typeof v === "string" && !!v.trim() && !/[\u0000-\u001f\u007f-\u009f]/.test(v);
  if (!line2(name))
    fail2(`named() takes a name, one line such as "hello", not ${shown(name)}`);
  if (opts2.note !== void 0 && !line2(opts2.note))
    fail2(`named()'s note takes one line saying what you see, not ${shown(opts2.note)}`);
  const p = prepare("named", src);
  const asItWas = p.speed === 1 && !p.offset && !p.tint && !Object.keys(p.options).length;
  const renamed = retime("named", p, (t) => t, {
    fps: p.meta.fps,
    loop: asItWas ? p.meta.loop : playable(period(p)),
    still: stillAt(p),
    name: name.trim(),
    note: opts2.note ?? short(name.trim()),
    category: opts2.category ?? p.meta.category
  }, playedOnce(p));
  return asItWas ? chained({ ...p.piece, meta: renamed.meta, default: renamed.default }) : renamed;
}

// node_modules/ascii.rest/dist/kit/fx.js
var show = (v) => typeof v === "string" ? JSON.stringify(v) : v !== null && typeof v === "object" ? Array.isArray(v) ? "a list" : "an object" : String(v);
var or2 = (words2) => words2.length > 1 ? `${words2.slice(0, -1).join(", ")} or ${words2.at(-1)}` : words2[0] ?? "";
var RULES = {
  seconds: [(v) => v > 0, "a number of seconds above 0"],
  time: [(v) => v >= 0, "a number of seconds, 0 or more"],
  positive: [(v) => v > 0, "a number above 0"],
  atLeast1: [(v) => v >= 1, "a number of cells, 1 or more"],
  zeroUp: [(v) => v >= 0, "a number, 0 or more"],
  number: [() => true, "a number"],
  share: [(v) => v >= 0 && v <= 1, "a number from 0 to 1"],
  cells: [(v) => Number.isInteger(v) && v >= 1, "a whole number of cells, 1 or more"],
  shift: [(v) => Number.isInteger(v), "a whole number of cells"],
  room: [(v) => Number.isInteger(v) && v >= 0, "a whole number of cells, 0 or more"],
  whole: [(v) => Number.isInteger(v), "a whole number"],
  steps: [(v) => Number.isInteger(v) && v >= 1 && v <= 32, "a whole number from 1 to 32"]
};
function num(v, name, fallback, rule) {
  if (v === void 0)
    return fallback;
  const [ok, words2] = RULES[rule];
  if (typeof v !== "number" || !Number.isFinite(v) || !ok(v))
    fail2(`${name} takes ${words2}, not ${show(v)}`);
  return v;
}
function wordy(v, name, words2, fallback, rule) {
  if (typeof v !== "string")
    return num(v, name, fallback, rule);
  if (Object.hasOwn(words2, v))
    return words2[v];
  return fail2(`${name} takes ${or2(Object.keys(words2).map((w) => JSON.stringify(w)))}, or ${RULES[rule][1]}, not ${show(v)}${suggest(v, Object.keys(words2))}`);
}
var often = (every) => ({ often: every / 2, sometimes: every, rarely: every * 2 });
var SPEED = { slow: 0.5, normal: 1, fast: 2 };
function choice(v, name, choices, fallback) {
  if (v === void 0)
    return fallback;
  if (!choices.includes(v))
    fail2(`${name} takes ${or2(choices.map((c) => JSON.stringify(c)))}, not ${show(v)}`);
  return v;
}
var printable = (c) => {
  const k = c.charCodeAt(0);
  return c.length === 1 && k >= 32 && !(k >= 127 && k <= 159) && !(k >= 55296 && k <= 57343);
};
function chars2(v, name, fallback, least = 1, most = Infinity) {
  if (v === void 0)
    return fallback;
  if (typeof v !== "string" || v.length < least || v.length > most || ![...v].every(printable)) {
    const many = most === 1 ? "one character" : least === most ? `${least} characters` : most === 2 ? "one or two characters" : least === 1 ? "one or more characters" : `${least} or more characters`;
    fail2(`${name} takes ${many}, each a printable one from the Basic Multilingual Plane, not ${show(v)}`);
  }
  return v;
}
function colour(v, name) {
  if (v === void 0)
    return void 0;
  if (isHex(v))
    return v;
  if (typeof v === "string")
    return colorOf(v, name).dark;
  return fail2(`${name} takes a colour as #rrggbb or a palette's name such as "gold", not ${show(v)}`);
}
var COMMON = ["name", "note", "options"];
var RENAMED = {
  "dissolve.scale": "write blob, the patches' size in cells across, which is 1 / scale: 7 for 0.15",
  "rainbow.spread": "write cycles, the times the colours fit across the piece, which is spread times its width",
  "hueCycle.spread": "write cycles, the times the colours fit across the piece, which is spread times its width"
};
function optionsOf2(o, fx, keys) {
  if (o === void 0)
    return {};
  if (typeof o === "number")
    fail2(`${fx}() takes its options as an object, not ${o}: over a list, write list.map((p) => ${fx}(p))`);
  if (o === null || typeof o !== "object" || Array.isArray(o))
    fail2(`${fx}() takes its options as an object, such as { period: 4 }, not ${show(o)}`);
  const known2 = [...keys, ...COMMON];
  for (const [k, v] of Object.entries(o))
    if (v !== void 0 && !known2.includes(k))
      fail2(`${fx}() has no option ${JSON.stringify(k)}${RENAMED[`${fx}.${k}`] ? "" : suggest(k, known2)}: ${RENAMED[`${fx}.${k}`] ?? `it takes ${or2(known2)}`}`);
  return o;
}
var mod = (a, n) => (a % n + n) % n;
var gcd2 = (a, b) => b ? gcd2(b, a % b) : a;
function lcm(a, b) {
  const x = Math.round(a * 100), y = Math.round(b * 100);
  if (x < 1 || y < 1)
    return void 0;
  const k = x / gcd2(x, y);
  return k * y <= 6e3 ? +(k * b).toFixed(6) : void 0;
}
function quiet(t, busy, span2) {
  const n = 480;
  let from = -1;
  for (let k = 0; k <= n; k++) {
    const u = t + span2 * k / n;
    if (from < 0 && !busy(u))
      from = u;
    else if (from >= 0 && busy(u))
      return +((from + u) / 2 - span2 / n / 2).toFixed(3);
  }
  return from < 0 ? t : +((from + t + span2) / 2).toFixed(3);
}
var Inks = class {
  list = [];
  #at = /* @__PURE__ */ new Map();
  /** From the source's palette index to the index here. */
  map;
  /** How many of the colours are the source's own. */
  own;
  constructor(src) {
    this.map = Uint8Array.from(src ?? [], (c) => this.add(c));
    this.own = this.list.length;
  }
  /** The index of a colour, added if it is new. */
  add(c) {
    const k = c.toLowerCase();
    let i = this.#at.get(k);
    if (i === void 0) {
      i = this.list.length < 64 ? this.list.push(c) - 1 : nearest(this.list, c);
      this.#at.set(k, i);
    }
    return i;
  }
  /** The index of a colour if it is here or there is room to add it; else `fallback`, rather than the nearest. */
  fit(c, fallback) {
    const i = this.#at.get(c.toLowerCase());
    if (i !== void 0 && this.list[i].toLowerCase() === c.toLowerCase())
      return i;
    return this.list.length < 64 ? this.add(c) : fallback;
  }
};
var QUIET2 = { light: "#59636e", dark: "#9198a1" };
var LOOPS2 = { logos: "shine", companies: "shine", distros: "scan" };
var ours = /* @__PURE__ */ new WeakSet();
function periodOf(p, options) {
  const m = p.meta;
  if (!m.fps)
    return void 0;
  if (m.loop)
    return m.loop;
  if (ours.has(p))
    return void 0;
  const v = Object.hasOwn(LOOPS2, m.category) ? options[LOOPS2[m.category]] : void 0;
  return typeof v === "number" && Number.isFinite(v) && v > 0 ? v : void 0;
}
var isMotion = (v) => !!v && typeof v === "object" && typeof v.seconds === "number" && typeof v.from === "number";
var textOf = (s) => s.replace(/\r\n?/g, "\n").split("\n").map((l) => l.replace(/[^\t]*\t/g, (run) => run.slice(0, -1).padEnd(Math.floor((run.length - 1) / 8) * 8 + 8))).join("\n");
function sourceOf(src, fx) {
  if (typeof src === "string") {
    const text2 = textOf(src);
    if (/[\ud800-\udfff]/.test(text2))
      fail2(`${fx}() takes text of characters from the Basic Multilingual Plane, one a cell, not emoji: ${JSON.stringify(src.slice(0, 40))}`);
    return asPiece(text2, text2.split("\n").map((l) => l.trim()).find(Boolean)?.slice(0, 40) ?? "text");
  }
  if (src instanceof Surface)
    return asPiece(src, "grid");
  if (!src || typeof src !== "object" || !src.meta || typeof src.default !== "function")
    fail2(`${fx}() takes a piece, a block of text or a Surface, not ${src === null ? "null" : typeof src}`);
  return src;
}
function mainInk(p, at3, options, map) {
  const most = (paper) => {
    const { text: text2, color } = snapshot(p, at3, { paper, options });
    const count = /* @__PURE__ */ new Map();
    let best = 0, n = 0;
    for (let k = 0, i = 0; k < text2.length; k++) {
      const c = text2.charCodeAt(k);
      if (c === 10)
        continue;
      if (c !== 32 && color && i < color.length) {
        const v = (count.get(color[i]) ?? 0) + 1;
        count.set(color[i], v);
        if (v > n)
          n = v, best = color[i];
      }
      i++;
    }
    return map[best] ?? 0;
  };
  return { light: most(true), dark: most(false) };
}
function build2(fx, src, o, make, keep = true) {
  const p = sourceOf(src, fx);
  const m = p.meta;
  if (o.options !== void 0 && (o.options === null || typeof o.options !== "object" || Array.isArray(o.options)))
    fail2(`${fx}.options takes the source's options as an object, such as { shine: 0 }, not ${show(o.options)}`);
  const options = m.options || o.options ? { ...m.options, ...o.options } : void 0;
  const inks = new Inks(keep ? m.palette ?? null : null);
  const e = make({ meta: m, inks, piece: p, options: options ?? {} });
  const ink = keep && m.palette ? mainInk(p, m.still ?? 0, options ?? {}, inks.map) : inks.list.length ? { light: inks.add(INK2.light), dark: inks.add(INK2.dark) } : null;
  const cols = e.cols ?? m.cols, rows = e.rows ?? m.rows;
  if (cols > MAX.cols || rows > MAX.rows)
    fail2(`${fx}() makes a piece ${cols} by ${rows} from one ${m.cols} by ${m.rows}, past the ${MAX.cols} by ${MAX.rows} a piece can be: use a smaller source, or a smaller reach`);
  const own = periodOf(p, options ?? {});
  const loop = !e.moves ? own : e.period ? lcm(own ?? e.period, e.period) : void 0;
  const name = o.name === void 0 ? m.name : typeof o.name === "string" ? o.name : fail2(`${fx}.name takes a string, not ${show(o.name)}`);
  const note = o.note ?? `${name}, ${e.what}`.slice(0, 72);
  const still = e.still ?? m.still;
  const out = piece({
    name,
    note,
    category: m.category,
    cols,
    rows,
    fps: e.moves ? m.fps || 24 : m.fps,
    ...inks.list.length ? { palette: inks.list, ink: ink ?? 0 } : {},
    ground: m.ground,
    cell: m.cell,
    loop,
    still: still ? +still.toFixed(3) : void 0,
    clock: m.clock,
    options
  }, {
    setup: (opts2) => {
      const play = sample(p, opts2);
      const palette = inks.list.length ? new Palette(inks.list, ink ?? 0) : null;
      const grid3 = new Surface(m.cols, m.rows, { palette, aspect: m.cell ?? 2 });
      const other = new Surface(m.cols, m.rows, { palette, aspect: m.cell ?? 2 });
      const { map } = inks;
      const read = (into2, t, paper, mono) => {
        const g = play.at(t, { paper, mono });
        const none = palette ? palette.ink(paper) : NONE;
        into2.chars.set(g.chars);
        for (let i = 0; i < g.colors.length; i++) {
          const c = g.colors[i];
          into2.colors[i] = c === NONE ? none : map[c] ?? none;
        }
        into2.paper = paper;
        into2.mono = mono;
        return into2;
      };
      const draw = e.setup();
      let fctx = null;
      return (t, s, ctx) => {
        fctx ??= Object.assign(ctx, { x: e.x ?? 0, y: e.y ?? 0, at: (u) => read(other, Number.isFinite(u) ? u : 0, ctx.paper, ctx.mono) });
        draw(t, s, read(grid3, t, ctx.paper, ctx.mono), fctx);
      };
    }
  });
  ours.add(out);
  const theirs = p.motion;
  const from = out.meta.still ?? 0;
  const motion = !e.moves ? isMotion(theirs) ? { seconds: theirs.seconds, from: theirs.from, once: !!theirs.once } : void 0 : loop ? { seconds: loop, from, once: false } : e.once !== void 0 && e.once <= 60 ? { seconds: +e.once.toFixed(3), from: 0, once: true } : { seconds: 4, from, once: false };
  return motion ? Object.assign(out, { motion }) : out;
}
var copy = (s, g) => {
  s.chars.set(g.chars);
  s.colors.set(g.colors);
};
function density(c) {
  const dense = ramps.detailed;
  const k = dense.indexOf(String.fromCharCode(c));
  if (k > 0)
    return k / (dense.length - 1);
  if (c === 9608)
    return 1;
  if (c === 9619)
    return 0.8;
  if (c === 9618)
    return 0.55;
  if (c === 9617)
    return 0.3;
  if (isBlock(c))
    return 0.5;
  if (c >= 10240 && c <= 10495) {
    let dots = 0;
    for (let b = c - 10240; b; b >>= 1)
      dots += b & 1;
    return 0.1 + dots / 10;
  }
  if (c >= 9472 && c <= 9599)
    return 0.35;
  if (c === 9679)
    return 0.7;
  if (c === 8226)
    return 0.4;
  if (c === 183)
    return 0.15;
  return 0.5;
}
var isBlock = (c) => c >= 9600 && c <= 9631;
var isSolid = (c) => !(c >= 9472 && c <= 9599) && !(c >= 10240 && c <= 10495) && density(c) >= 0.45;
function glint(src, options) {
  const o = optionsOf2(options, "glint", ["every", "sweep", "speed", "first", "width", "slant", "chars", "color"]);
  const every = wordy(o.every, "glint.every", often(4), 4, "seconds");
  const asked = o.sweep === void 0 ? void 0 : num(o.sweep, "glint.sweep", 1.2, "seconds");
  if (o.sweep !== void 0 && o.speed !== void 0)
    fail2("glint takes sweep or speed, which both set how fast the band crosses, not both");
  const pace = wordy(o.speed, "glint.speed", SPEED, 1, "positive");
  const first = num(o.first, "glint.first", 0.5, "number");
  const width = num(o.width, "glint.width", 3, "positive");
  const slant = num(o.slant, "glint.slant", 1, "number");
  const keep = o.chars === null;
  const given = keep ? "" : chars2(o.chars, "glint.chars", "", 1, 2);
  const color = colour(o.color, "glint.color");
  return build2("glint", src, o, ({ meta: m, inks }) => {
    const core = new Uint8Array(256).fill(NONE), edge = new Uint8Array(256).fill(NONE);
    if (color) {
      core.fill(inks.add(color));
      edge.fill(inks.add(color));
    } else {
      const own = inks.list.slice(0, inks.own);
      own.forEach((c, i) => core[i] = inks.fit(mix(c, "#ffffff", 0.6), i));
      own.forEach((c, i) => edge[i] = inks.fit(mix(c, "#ffffff", 0.3), core[i]));
    }
    const reach = width / 2 + 1;
    const lo = Math.min(0, slant * (m.rows - 1)) - reach, hi = m.cols - 1 + Math.max(0, slant * (m.rows - 1)) + reach;
    const sweep = asked ?? Math.min(Math.min(Math.max(1.2, (hi - lo) / 40), 3) / pace, 0.75 * every);
    const busy = (t) => mod(t - first, every) < sweep;
    return {
      moves: true,
      period: every,
      still: quiet(m.still ?? 0, busy, every),
      what: "glinting now and then",
      setup: () => {
        const kinds = /* @__PURE__ */ new Map();
        const kind = (c) => {
          let k = kinds.get(c);
          if (k === void 0)
            kinds.set(c, k = isBlock(c) ? 1 : isSolid(c) ? 2 : 0);
          return k;
        };
        const SLASH = 47;
        return (t, s, g, ctx) => {
          copy(s, g);
          const u = mod(t - first, every) / sweep;
          if (u >= 1)
            return;
          const at3 = lo + (hi - lo) * u;
          const pair = given || (ctx.paper ? "\u2592\u2593" : "\u2588\u2593");
          const c0 = pair.charCodeAt(0), c1 = pair.charCodeAt(pair.length - 1);
          for (let y = 0, i = 0; y < g.rows; y++)
            for (let x = 0; x < g.cols; x++, i++) {
              const ch = g.chars[i];
              if (ch === EMPTY)
                continue;
              const d = Math.abs(x + slant * y - at3);
              if (d >= reach)
                continue;
              const inCore = d < width / 2;
              const k = given || keep ? -1 : kind(ch);
              if (given || k === 1)
                s.chars[i] = inCore ? c0 : c1;
              else if (k === 2 && inCore)
                s.chars[i] = SLASH;
              if (!ctx.mono && !(k === 1 && ctx.paper))
                s.colors[i] = (inCore ? core : edge)[g.colors[i]];
            }
        };
      }
    };
  });
}
function typeIn(src, options) {
  const o = optionsOf2(options, "typeIn", ["speed", "start", "cursor", "order", "hold", "seed"]);
  const start = num(o.start, "typeIn.start", 0, "time");
  const order = choice(o.order, "typeIn.order", ["reading", "random", "columns"], "reading");
  const cursor = o.cursor === false ? "" : chars2(o.cursor, "typeIn.cursor", order === "random" ? "" : "\u258C", 1, 1);
  const hold = o.hold === void 0 ? void 0 : num(o.hold, "typeIn.hold", 0, "time");
  const seed = num(o.seed, "typeIn.seed", 1, "whole");
  const pace = typeof o.speed === "string" ? wordy(o.speed, "typeIn.speed", SPEED, 1, "positive") : 1;
  const own = typeof o.speed === "number" || o.speed === void 0 ? o.speed === void 0 ? void 0 : num(o.speed, "typeIn.speed", 40, "positive") : void 0;
  if (o.speed !== void 0 && typeof o.speed !== "string" && typeof o.speed !== "number")
    num(o.speed, "typeIn.speed", 40, "positive");
  const text2 = typeof src === "string" && cursor ? textOf(src).split("\n").map((l) => l + " ").join("\n") : src;
  return build2("typeIn", text2, o, ({ meta: m, piece: p, options: opts2 }) => {
    const { cols, rows } = m;
    const total = snapshot(p, m.still ?? 0, { options: opts2 }).text.replace(/\s/g, "").length;
    const speed3 = own ?? Math.max(40, total / 3) * pace;
    const typing = total / speed3;
    const cycle2 = hold === void 0 ? 0 : start + typing + hold;
    let seq = null;
    if (order === "columns") {
      seq = new Int32Array(cols * rows);
      for (let x = 0, k = 0; x < cols; x++)
        for (let y = 0; y < rows; y++)
          seq[k++] = y * cols + x;
    } else if (order === "random") {
      const key = Float64Array.from({ length: cols * rows }, (_, i) => hash(seed, i, 7));
      seq = Int32Array.from({ length: cols * rows }, (_, i) => i).sort((a, b) => key[a] - key[b]);
    }
    const code3 = cursor ? cursor.charCodeAt(0) : 0;
    const blink = (u) => mod(u, 1.06) < 0.53;
    const still = hold === void 0 ? start + typing + 0.5 : hold > 0 ? start + typing + Math.min(hold, 1) / 2 : Math.max(0, start + typing - 1e-3);
    return {
      moves: true,
      period: cycle2 || void 0,
      still,
      once: hold === void 0 ? start + typing + 0.5 : void 0,
      what: "typed in",
      setup: () => (t, s, g) => {
        const local = cycle2 ? mod(t, cycle2) : t;
        const n = Math.floor((local - start) * speed3 + 1e-6);
        const all = g.chars.length;
        let shown3 = 0, next = -1, last = -1;
        for (let k = 0; k < all; k++) {
          const i = seq ? seq[k] : k;
          if (g.chars[i] === EMPTY)
            continue;
          if (shown3 >= n) {
            next = i;
            break;
          }
          s.chars[i] = g.chars[i];
          s.colors[i] = g.colors[i];
          shown3++;
          last = i;
        }
        if (!code3)
          return;
        if (next >= 0) {
          if (local >= start || blink(local - start))
            s.put(next, code3, g.colors[next]);
          return;
        }
        if (seq || last < 0 || !blink(local - start - typing))
          return;
        if (last % cols + 1 < cols && g.chars[last + 1] === EMPTY)
          s.put(last + 1, code3, g.colors[last]);
      }
    };
  });
}
function level(t, period2, mode) {
  const u = mod(t, period2) / period2;
  const ease2 = (k) => smoothstep(0, 1, k);
  if (mode === "in")
    return u < 0.4 ? ease2(u / 0.4) : 1;
  if (mode === "out")
    return u < 0.6 ? 1 : 1 - ease2((u - 0.6) / 0.4);
  return u < 0.3 ? ease2(u / 0.3) : u < 0.6 ? 1 : u < 0.9 ? 1 - ease2((u - 0.6) / 0.3) : 0;
}
var HELD = { in: 0.7, out: 0.3, inout: 0.45 };
var MODES = ["in", "out", "inout"];
var MODE_WHAT = { in: "in", out: "out", inout: "in and out" };
function dissolve(src, options) {
  const o = optionsOf2(options, "dissolve", ["period", "mode", "blob", "edge", "seed"]);
  const period2 = num(o.period, "dissolve.period", 6, "seconds");
  const mode = choice(o.mode, "dissolve.mode", MODES, "inout");
  const scale2 = 1 / num(o.blob, "dissolve.blob", 7, "atLeast1");
  const auto = o.edge === void 0;
  const edge = o.edge === "" ? "" : chars2(o.edge, "dissolve.edge", ".:", 1);
  const seed = num(o.seed, "dissolve.seed", 1, "whole");
  return build2("dissolve", src, o, ({ meta: m }) => {
    const n = m.cols * m.rows, aspect = m.cell ?? 2;
    const v = new Float64Array(n);
    for (let y = 0, i = 0; y < m.rows; y++)
      for (let x = 0; x < m.cols; x++, i++)
        v[i] = 0.8 * valueNoise(x * scale2, y * scale2 * aspect, seed) + 0.2 * hash(x, y, seed, 3);
    const at3 = new Float32Array(n);
    Int32Array.from({ length: n }, (_, i) => i).sort((a, b) => v[a] - v[b]).forEach((i, rank) => at3[i] = (rank + 0.5) / n);
    const band = edge ? 0.12 : 0;
    const codes = [...edge].map((c) => c.charCodeAt(0)), blocks = auto ? [9617, 9618] : codes;
    return {
      moves: true,
      period: period2,
      still: HELD[mode] * period2,
      what: `dissolving ${MODE_WHAT[mode]}`,
      setup: () => (t, s, g) => {
        const k = level(t, period2, mode);
        if (k >= 1)
          return copy(s, g);
        const front = k * (1 + band);
        for (let i = 0; i < n; i++) {
          const ch = g.chars[i];
          if (ch === EMPTY)
            continue;
          const d = front - at3[i];
          if (d <= 0)
            continue;
          const set = isBlock(ch) ? blocks : codes;
          s.put(i, d >= band ? ch : set[Math.min(set.length - 1, Math.floor(d / band * set.length))], g.colors[i]);
        }
      }
    };
  });
}
function fade2(src, options) {
  const o = optionsOf2(options, "fade", ["period", "mode", "ramp"]);
  const period2 = num(o.period, "fade.period", 6, "seconds");
  const mode = choice(o.mode, "fade.mode", MODES, "inout");
  const auto = o.ramp === void 0 || o.ramp === "auto";
  const chars3 = ramp(auto ? "standard" : o.ramp);
  if (chars3[0] !== " ")
    fail2(`fade.ramp starts with a space, the place every character fades to, not ${JSON.stringify(chars3)}`);
  const given = [...chars3].map((c) => c.charCodeAt(0));
  const blocks = [...ramps.blocks].map((c) => c.charCodeAt(0));
  const ascii = (c) => c > 32 && c < 127;
  return build2("fade", src, o, () => ({
    moves: true,
    period: period2,
    still: HELD[mode] * period2,
    what: `fading ${MODE_WHAT[mode]}`,
    setup: () => {
      const steps = /* @__PURE__ */ new Map();
      const stepsOf = (c) => {
        let v = steps.get(c);
        if (v === void 0) {
          const codes = !auto || ascii(c) ? given : isBlock(c) ? blocks : [32, c];
          const own = codes.indexOf(c);
          steps.set(c, v = { codes, top: own > 0 ? own : Math.max(1, Math.round(density(c) * (codes.length - 1))) });
        }
        return v;
      };
      return (t, s, g) => {
        const k = level(t, period2, mode);
        if (k >= 1)
          return copy(s, g);
        for (let y = 0, i = 0; y < g.rows; y++)
          for (let x = 0; x < g.cols; x++, i++) {
            const ch = g.chars[i];
            if (ch === EMPTY)
              continue;
            const { codes, top } = stepsOf(ch);
            const step = Math.max(0, Math.min(top, Math.floor(top * k + 0.5 + bayer(x, y))));
            if (step)
              s.put(i, step === top ? ch : codes[step], g.colors[i]);
          }
      };
    }
  }));
}
function scan(src, options) {
  const o = optionsOf2(options, "scan", ["period", "direction", "char", "color", "reveal"]);
  const period2 = num(o.period, "scan.period", 3, "seconds");
  const direction = choice(o.direction, "scan.direction", ["down", "up", "right", "left"], "down");
  const across2 = direction === "down" || direction === "up";
  const char = chars2(o.char, "scan.char", across2 ? "\u2500" : "\u2502", 1, 1).charCodeAt(0);
  const color = colour(o.color, "scan.color");
  if (o.reveal !== void 0 && typeof o.reveal !== "boolean")
    fail2(`scan.reveal takes true or false, not ${show(o.reveal)}`);
  const reveal = o.reveal ?? false;
  const forward = direction === "down" || direction === "right";
  return build2("scan", src, o, ({ meta: m, inks }) => {
    const ink = color ? inks.add(color) : -1;
    const along = across2 ? m.rows : m.cols;
    const lineAt = (t) => {
      const u = mod(t, period2) / period2;
      if (reveal)
        return u >= 0.6 ? null : Math.floor(-1 + u / 0.6 * (along + 1));
      return Math.floor(-1 + u * (along + 2));
    };
    const busy = (t) => {
      const p = lineAt(t);
      return p !== null && (reveal || p >= 0 && p < along);
    };
    return {
      moves: true,
      period: period2,
      still: quiet(0, busy, period2),
      what: reveal ? "revealed by a scan line" : "with a scan line passing",
      setup: () => (t, s, g) => {
        const pos = lineAt(t);
        if (pos === null)
          return copy(s, g);
        const line2 = forward ? pos : along - 1 - pos;
        for (let y = 0, i = 0; y < g.rows; y++)
          for (let x = 0; x < g.cols; x++, i++) {
            const q = across2 ? y : x;
            if (q === line2)
              s.put(i, char, ink >= 0 ? ink : g.chars[i] === EMPTY ? NONE : g.colors[i]);
            else if (!reveal || (forward ? q < line2 : q > line2)) {
              s.chars[i] = g.chars[i];
              s.colors[i] = g.colors[i];
            }
          }
      }
    };
  });
}
function glitch(src, options) {
  const o = optionsOf2(options, "glitch", ["every", "length", "first", "amount", "chars", "seed"]);
  const every = wordy(o.every, "glitch.every", often(2.5), 2.5, "seconds");
  const length = num(o.length, "glitch.length", 0.35, "seconds");
  const first = num(o.first, "glitch.first", 0.5, "number");
  const amount = wordy(o.amount, "glitch.amount", { subtle: 0.25, medium: 0.5, strong: 0.85 }, 0.5, "share");
  const junk = [...chars2(o.chars, "glitch.chars", "#%&@$/\\|<>", 1)].map((c) => c.charCodeAt(0));
  const seed = num(o.seed, "glitch.seed", 1, "whole");
  return build2("glitch", src, o, ({ meta: m }) => {
    const busy = (t) => mod(t - first, every) < length;
    const reach = 1 + Math.round(amount * 10);
    return {
      moves: true,
      period: every,
      still: quiet(m.still ?? 0, busy, every),
      what: "glitching now and then",
      setup: () => (t, s, g) => {
        const u = mod(t - first, every);
        if (u >= length)
          return copy(s, g);
        const k = Math.floor(u * 16 + 1e-6);
        const shift = Math.floor(hash(seed, k, 1) * 3);
        const { cols } = g;
        for (let y = 0; y < g.rows; y++) {
          const band = y + shift >> 1;
          const dx = hash(seed, k, 2, band) < amount * 0.7 ? Math.round((hash(seed, k, 3, band) * 2 - 1) * reach) : 0;
          for (let x = 0; x < cols; x++) {
            const from = x - dx;
            if (from < 0 || from >= cols)
              continue;
            const j = y * cols + from;
            if (g.chars[j] === EMPTY)
              continue;
            const i = y * cols + x;
            const swap = hash(seed, k, i, 4) < amount * 0.12;
            s.put(i, swap ? junk[Math.floor(hash(seed, k, i, 5) * junk.length)] : g.chars[j], g.colors[j]);
          }
        }
      }
    };
  });
}
function wave(src, options) {
  const o = optionsOf2(options, "wave", ["amplitude", "amount", "wavelength", "period", "speed", "axis"]);
  const axis = choice(o.axis, "wave.axis", ["rows", "columns"], "rows");
  const rows = axis === "rows";
  if (o.amplitude !== void 0 && o.amount !== void 0)
    fail2("wave takes amplitude or amount, which both say how far it sways, not both");
  if (o.period !== void 0 && o.speed !== void 0)
    fail2("wave takes period or speed, which both say how fast it runs, not both");
  const much = o.amount === void 0 ? 1 : choice(o.amount, "wave.amount", ["subtle", "medium", "strong"], "medium") === "subtle" ? 0.5 : o.amount === "strong" ? 2 : 1;
  const pace = o.speed === void 0 ? 1 : SPEED[choice(o.speed, "wave.speed", ["slow", "normal", "fast"], "normal")];
  const amplitude = num(o.amplitude, "wave.amplitude", (rows ? 2 : 1) * much, "positive");
  const wavelength = num(o.wavelength, "wave.wavelength", rows ? 12 : 16, "positive");
  const period2 = num(o.period, "wave.period", 2 / pace, "seconds");
  const room = Math.ceil(amplitude);
  return build2("wave", src, o, ({ meta: m }) => ({
    cols: m.cols + (rows ? 2 * room : 0),
    rows: m.rows + (rows ? 0 : 2 * room),
    moves: true,
    period: period2,
    what: "swaying in a wave",
    setup: () => (t, s, g) => {
      const { cols: w, rows: h } = g;
      const lines = rows ? h : w;
      for (let k = 0; k < lines; k++) {
        const off = room + Math.round(amplitude * Math.sin(TAU * (k / wavelength - t / period2)));
        for (let j = 0, n = rows ? w : h; j < n; j++) {
          const i = rows ? k * w + j : j * w + k;
          if (g.chars[i] === EMPTY)
            continue;
          s.put(rows ? k * s.cols + off + j : (off + j) * s.cols + k, g.chars[i], g.colors[i]);
        }
      }
    }
  }));
}
function hsl(h, s, l) {
  const a = s * Math.min(l, 1 - l);
  const f = (n) => {
    const k = (n + h / 30) % 12;
    return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))));
  };
  return "#" + [f(0), f(8), f(4)].map((v) => v.toString(16).padStart(2, "0")).join("");
}
var hues = {
  light: Array.from({ length: 12 }, (_, i) => hsl(i * 30, 0.8, 0.4)),
  dark: Array.from({ length: 12 }, (_, i) => hsl(i * 30, 0.9, 0.66))
};
var cycle = (stops, n) => stops.length === 1 ? Array(n).fill(stops[0]) : gradient([...stops, stops[0]], n + 1).slice(0, n);
function rainbowOf(fx, src, options, cyclesBy) {
  const o = optionsOf2(options, fx, ["colors", "steps", "period", "cycles", "direction"]);
  const steps = num(o.steps, `${fx}.steps`, 12, "steps");
  const period2 = num(o.period, `${fx}.period`, 3, "seconds");
  const cycles = num(o.cycles, `${fx}.cycles`, cyclesBy, "zeroUp");
  const direction = choice(o.direction, `${fx}.direction`, ["x", "y", "diagonal"], "x");
  const spec = typeof o.colors === "string" ? colorsOf(o.colors, `${fx}.colors`) : o.colors ?? hues;
  const list2 = (v, name) => Array.isArray(v) && v.length && v.every(isHex) ? v : fail2(`${name} takes a list of colours as #rrggbb, or { light, dark }, not ${show(v)}`);
  const [light, dark] = Array.isArray(spec) ? [list2(spec, `${fx}.colors`), list2(spec, `${fx}.colors`)] : spec && typeof spec === "object" ? [list2(spec.light, `${fx}.colors.light`), list2(spec.dark, `${fx}.colors.dark`)] : fail2(`${fx}.colors takes a list of colours as #rrggbb, or { light, dark }, not ${show(spec)}`);
  return build2(fx, src, o, ({ meta: m, inks }) => {
    const at3 = [cycle(dark, steps).map((c) => inks.add(c)), cycle(light, steps).map((c) => inks.add(c))];
    const aspect = m.cell ?? 2;
    const spread2 = cycles / (direction === "x" ? m.cols : direction === "y" ? m.rows : m.cols + aspect * m.rows);
    return {
      moves: true,
      period: period2,
      what: cycles ? "in rainbow colours" : "cycling through colours",
      setup: () => (t, s, g, ctx) => {
        copy(s, g);
        if (ctx.mono)
          return;
        const idx = at3[ctx.paper ? 1 : 0], ph = t / period2;
        for (let y = 0, i = 0; y < g.rows; y++)
          for (let x = 0; x < g.cols; x++, i++) {
            if (g.chars[i] === EMPTY)
              continue;
            const pos = direction === "x" ? x : direction === "y" ? y : x + g.aspect * y;
            s.colors[i] = idx[Math.min(steps - 1, Math.floor(mod(pos * spread2 - ph, 1) * steps + 1e-7))];
          }
      }
    };
  }, false);
}
function rainbow(src, options) {
  return rainbowOf("rainbow", src, options, 1);
}
var hueCycle = (src, options) => rainbowOf("hueCycle", src, options, 0);
function shake(src, options) {
  const o = optionsOf2(options, "shake", ["amount", "every", "length", "first", "seed"]);
  const amount = wordy(o.amount, "shake.amount", { subtle: 1, medium: 2, strong: 3 }, 1, "cells");
  const every = wordy(o.every, "shake.every", often(2), 2, "seconds");
  const length = num(o.length, "shake.length", 0.3, "seconds");
  const first = num(o.first, "shake.first", 0.5, "number");
  const seed = num(o.seed, "shake.seed", 1, "whole");
  return build2("shake", src, o, ({ meta: m }) => ({
    cols: m.cols + 2 * amount,
    rows: m.rows + 2 * amount,
    moves: true,
    period: every,
    still: quiet(m.still ?? 0, (t) => mod(t - first, every) < length, every),
    what: "shaking now and then",
    setup: () => (t, s, g) => {
      const u = mod(t - first, every);
      let dx = 0, dy = 0;
      if (u < length) {
        const k = Math.floor(u * 20 + 1e-6);
        dx = Math.round((hash(seed, k, 1) * 2 - 1) * amount);
        dy = Math.round((hash(seed, k, 2) * 2 - 1) * amount);
        if (!dx && !dy)
          dx = hash(seed, k, 3) < 0.5 ? -amount : amount;
      }
      s.paste(g, amount + dx, amount + dy, { mask: null });
    }
  }));
}
var outlines = {
  single: " \u2502\u2502\u2502\u2500\u2518\u2510\u2524\u2500\u2514\u250C\u251C\u2500\u2534\u252C\u253C",
  double: " \u2551\u2551\u2551\u2550\u255D\u2557\u2563\u2550\u255A\u2554\u2560\u2550\u2569\u2566\u256C",
  rounded: " \u2502\u2502\u2502\u2500\u256F\u256E\u2524\u2500\u2570\u256D\u251C\u2500\u2534\u252C\u253C",
  heavy: " \u2503\u2503\u2503\u2501\u251B\u2513\u252B\u2501\u2517\u250F\u2523\u2501\u253B\u2533\u254B",
  ascii: " |||-+++-+++-+++"
};
var NX = [0, 0, 1, -1, 1, -1, 1, -1];
var NY = [1, -1, 0, 0, 1, 1, -1, -1];
function flood(solid2, out, queue, cols, rows) {
  out.fill(0);
  let head = 0, tail = 0;
  for (let i = 0; i < cols * rows; i++) {
    const x = i % cols, y = i / cols | 0;
    if ((x === 0 || y === 0 || x === cols - 1 || y === rows - 1) && !solid2[i])
      out[i] = 1, queue[tail++] = i;
  }
  while (head < tail) {
    const i = queue[head++], x = i % cols, y = i / cols | 0;
    for (let k = 0; k < 4; k++) {
      const nx = x + NX[k], ny = y + NY[k];
      if (nx < 0 || nx >= cols || ny < 0 || ny >= rows)
        continue;
      const j = ny * cols + nx;
      if (!out[j] && !solid2[j])
        out[j] = 1, queue[tail++] = j;
    }
  }
}
function outline(src, options) {
  const o = optionsOf2(options, "outline", ["style", "color", "gap"]);
  const style = o.style === void 0 ? outlines.single : Object.hasOwn(outlines, o.style) ? outlines[o.style] : o.style;
  if (typeof style !== "string" || style.length !== 16 || ![...style].every(printable))
    fail2(`outline.style takes ${or2(Object.keys(outlines).map((k) => JSON.stringify(k)))}, or 16 characters of your own, not ${show(o.style)}`);
  const joins = [...style].map((c) => c.charCodeAt(0));
  const color = colour(o.color, "outline.color");
  const gap = num(o.gap, "outline.gap", 1, "whole");
  if (gap < 0)
    fail2(`outline.gap takes a whole number of cells, 0 or more, not ${gap}`);
  return build2("outline", src, o, ({ meta: m, inks }) => {
    const ink = color ? inks.add(color) : -1;
    const cols = m.cols + 2, rows = m.rows + 2;
    return {
      cols,
      rows,
      moves: false,
      what: "outlined",
      setup: () => {
        const solid2 = new Uint8Array(cols * rows), out = new Uint8Array(cols * rows), queue = new Int32Array(cols * rows);
        const is = (a, x, y) => x >= 0 && x < cols && y >= 0 && y < rows && a[y * cols + x] === 1;
        const line2 = (x, y) => is(out, x, y) && (is(solid2, x - 1, y - 1) || is(solid2, x, y - 1) || is(solid2, x + 1, y - 1) || is(solid2, x - 1, y) || is(solid2, x + 1, y) || is(solid2, x - 1, y + 1) || is(solid2, x, y + 1) || is(solid2, x + 1, y + 1));
        const over2 = { mask: null };
        return (t, s, g) => {
          solid2.fill(0);
          for (let y = 0; y < g.rows; y++)
            for (let x = 0; x < g.cols; x++)
              if (g.chars[y * g.cols + x] !== EMPTY)
                solid2[(y + 1) * cols + x + 1] = 1;
          if (gap)
            for (let y = 1; y < rows - 1; y++)
              for (let x = 1, last = -1; x < cols - 1; x++) {
                if (!solid2[y * cols + x])
                  continue;
                if (last >= 0 && x - last - 1 <= gap)
                  solid2.fill(1, y * cols + last + 1, y * cols + x);
                last = x;
              }
          flood(solid2, out, queue, cols, rows);
          for (let y = 0; y < rows; y++)
            for (let x = 0; x < cols; x++) {
              if (!line2(x, y))
                continue;
              const up = line2(x, y - 1) && (is(solid2, x - 1, y) || is(solid2, x - 1, y - 1) || is(solid2, x + 1, y) || is(solid2, x + 1, y - 1));
              const down2 = line2(x, y + 1) && (is(solid2, x - 1, y) || is(solid2, x - 1, y + 1) || is(solid2, x + 1, y) || is(solid2, x + 1, y + 1));
              const left = line2(x - 1, y) && (is(solid2, x, y - 1) || is(solid2, x - 1, y - 1) || is(solid2, x, y + 1) || is(solid2, x - 1, y + 1));
              const right = line2(x + 1, y) && (is(solid2, x, y - 1) || is(solid2, x + 1, y - 1) || is(solid2, x, y + 1) || is(solid2, x + 1, y + 1));
              const bits = (up ? 1 : 0) | (down2 ? 2 : 0) | (left ? 4 : 0) | (right ? 8 : 0);
              if (!bits)
                continue;
              let c = ink;
              for (let k = 0; c < 0 && k < 8; k++) {
                const sx = x + NX[k] - 1, sy = y + NY[k] - 1;
                if (sx >= 0 && sx < g.cols && sy >= 0 && sy < g.rows && g.chars[sy * g.cols + sx] !== EMPTY)
                  c = g.colors[sy * g.cols + sx];
              }
              s.put(y * cols + x, joins[bits], c < 0 ? NONE : c);
            }
          s.paste(g, 1, 1, over2);
        };
      }
    };
  });
}
function shadow(src, options) {
  const o = optionsOf2(options, "shadow", ["dx", "dy", "char", "color", "solid"]);
  const dx = num(o.dx, "shadow.dx", 1, "shift");
  const dy = num(o.dy, "shadow.dy", 1, "shift");
  const char = chars2(o.char, "shadow.char", "\u2591", 1, 1).charCodeAt(0);
  const color = colour(o.color, "shadow.color");
  if (o.solid !== void 0 && typeof o.solid !== "boolean")
    fail2(`shadow.solid takes true or false, not ${show(o.solid)}`);
  const solid2 = o.solid ?? true;
  return build2("shadow", src, o, ({ meta: m, inks }) => {
    const tone = color ? [inks.add(color), inks.add(color)] : m.palette ? [inks.add(QUIET2.dark), inks.add(QUIET2.light)] : [NONE, NONE];
    const cols = m.cols + Math.abs(dx), rows = m.rows + Math.abs(dy);
    const x0 = dx < 0 ? -dx : 0, y0 = dy < 0 ? -dy : 0;
    return {
      cols,
      rows,
      moves: false,
      what: "with a drop shadow",
      setup: () => {
        const ink = new Uint8Array(cols * rows), out = new Uint8Array(cols * rows).fill(1), queue = new Int32Array(cols * rows);
        const over2 = { mask: null };
        return (t, s, g, ctx) => {
          const c = tone[ctx.paper ? 1 : 0];
          if (solid2) {
            ink.fill(0);
            for (let y = 0, i = 0; y < g.rows; y++)
              for (let x = 0; x < g.cols; x++, i++)
                if (g.chars[i] !== EMPTY)
                  ink[(y + y0) * cols + x + x0] = 1;
            flood(ink, out, queue, cols, rows);
          }
          for (let y = 0, i = 0; y < g.rows; y++)
            for (let x = 0; x < g.cols; x++, i++) {
              const k = (y + y0 + dy) * cols + x + x0 + dx;
              if (g.chars[i] !== EMPTY && out[k])
                s.put(k, char, c);
            }
          s.paste(g, x0, y0, over2);
        };
      }
    };
  });
}

// node_modules/ascii.rest/dist/kit/core.js
function fail2(what) {
  throw new Error(`ascii.rest: ${what}`);
}
var and2 = (words2) => words2.length > 1 ? `${words2.slice(0, -1).join(", ")} and ${words2.at(-1)}` : words2[0] ?? "";
var TAU = Math.PI * 2;
var clamp = (v, lo = 0, hi = 1) => v < lo ? lo : v > hi ? hi : v;
var lerp = (a, b, k) => a + (b - a) * k;
var smoothstep = (e0, e1, v) => {
  const k = clamp((v - e0) / (e1 - e0));
  return k * k * (3 - 2 * k);
};
var fract = (v) => v - Math.floor(v);
function hash(a, b = 0, c = 0, d = 0) {
  let h = Math.imul(a | 0, 374761393) + Math.imul(b | 0, 668265263) + Math.imul(c | 0, 2246822519) + Math.imul(d | 0, 3266489917);
  h = Math.imul(h ^ h >>> 13, 1274126177);
  return ((h ^ h >>> 16) >>> 0) / 4294967296;
}
function valueNoise(x, y, seed = 0) {
  const xi = Math.floor(x), yi = Math.floor(y);
  const fx = x - xi, fy = y - yi;
  const u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy);
  const a = hash(xi, yi, seed), b = hash(xi + 1, yi, seed), c = hash(xi, yi + 1, seed), d = hash(xi + 1, yi + 1, seed);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}
var BAYER4 = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5].map((v) => (v + 0.5) / 16 - 0.5);
var bayer = (x, y) => BAYER4[(y & 3) * 4 + (x & 3)];
var ramps = {
  standard: " .:-=+*#%@",
  detailed: " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$",
  donut: " .,-~:;=!*#$@",
  blocks: " \u2591\u2592\u2593\u2588",
  eighths: " \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588",
  dots: " .\xB7\u2022\u25CF",
  lines: " .-=\u2261",
  stars: " .\xB7+*",
  binary: " #"
};
var CONTROL = /[\u0000-\u001f\u007f-\u009f]/;
function ramp(r = "standard") {
  if (typeof r !== "string")
    fail2(`a ramp takes a name, ${and2(Object.keys(ramps))}, or a string of characters, not ${String(r)}`);
  if (Object.hasOwn(ramps, r))
    return ramps[r];
  if (r.length < 2 || CONTROL.test(r) || /[\ud800-\udfff]/.test(r))
    fail2(`a ramp takes a name, ${and2(Object.keys(ramps))}, or two or more characters of your own, not ${JSON.stringify(r)}`);
  return r;
}
var INK2 = { light: "#1f2328", dark: "#f0f6fc" };
var HEX2 = /^#[0-9a-f]{6}$/i;
var isHex = (v) => typeof v === "string" && HEX2.test(v);
function rgb(hex2) {
  if (!isHex(hex2))
    fail2(`a colour takes #rrggbb, not ${JSON.stringify(hex2)}`);
  return [parseInt(hex2.slice(1, 3), 16), parseInt(hex2.slice(3, 5), 16), parseInt(hex2.slice(5, 7), 16)];
}
var hex = ([r, g, b]) => "#" + [r, g, b].map((v) => Math.round(clamp(v, 0, 255)).toString(16).padStart(2, "0")).join("");
var mix = (a, b, k) => {
  const x = rgb(a), y = rgb(b);
  return hex(x.map((v, i) => lerp(v, y[i], clamp(k))));
};
function gradient(stops, n) {
  if (!Array.isArray(stops) || !stops.length)
    fail2("a gradient takes one or more colours as #rrggbb");
  if (!Number.isInteger(n) || n < 1)
    fail2(`a gradient takes a whole number of colours of 1 or more, not ${String(n)}`);
  const c = stops.map(rgb);
  return Array.from({ length: n }, (_, i) => {
    const k = n > 1 ? i / (n - 1) * (c.length - 1) : 0;
    const a = Math.min(c.length - 2, Math.floor(k));
    return c.length === 1 ? hex(c[0]) : hex(c[a].map((v, j) => lerp(v, c[a + 1][j], k - a)));
  });
}
var distance = (a, b) => 0.3 * (a[0] - b[0]) ** 2 + 0.59 * (a[1] - b[1]) ** 2 + 0.11 * (a[2] - b[2]) ** 2;
function nearest(colors, color, from = 0, to = colors.length) {
  const want = rgb(color);
  let best = from, bd = Infinity;
  for (let i = from; i < to; i++) {
    const d = distance(rgb(colors[i]), want);
    if (d < bd)
      bd = d, best = i;
  }
  return best;
}
var themed = (v) => v !== null && typeof v === "object" && !Array.isArray(v) && "light" in v && "dark" in v;
var Palette = class {
  /** As meta.palette: the light colours then the dark ones when themed. At least two: one colour is listed twice. */
  colors;
  themed;
  /** Colours a theme. */
  size;
  #cache = [/* @__PURE__ */ new Map(), /* @__PURE__ */ new Map()];
  #ink;
  constructor(spec, ink = 0) {
    if (Array.isArray(spec)) {
      if (!spec.length)
        fail2("a palette takes one or more colours as #rrggbb, not an empty list");
      this.themed = false;
      this.size = spec.length;
      this.colors = spec.length === 1 ? [spec[0], spec[0]] : [...spec];
    } else if (spec && typeof spec === "object" && Array.isArray(spec.light) && Array.isArray(spec.dark)) {
      const { light, dark } = spec;
      if (!light.length || light.length !== dark.length)
        fail2(`a palette's light and dark lists take the same number of colours, one or more, not ${light.length} and ${dark.length}`);
      this.themed = true;
      this.size = light.length;
      this.colors = [...light, ...dark];
    } else
      fail2(`a palette takes a list of colours as #rrggbb, or { light, dark }, not ${JSON.stringify(spec)}`);
    for (const c of this.colors)
      if (!isHex(c))
        fail2(`a palette takes colours as #rrggbb, not ${JSON.stringify(c)}`);
    if (this.colors.length > 64)
      fail2(`a palette takes up to 64 colours, light and dark together, not ${this.colors.length}`);
    this.#ink = ink;
  }
  /** The index into meta.palette, for env.color, of a colour on paper or on a dark page. */
  index(c, paper = false) {
    const base = this.themed && !paper ? this.size : 0;
    if (typeof c === "number") {
      if (!Number.isInteger(c) || c < 0 || c >= this.size)
        fail2(`colour ${c} is not one of the palette's ${this.size}: a colour index takes a whole number from 0 to ${this.size - 1}`);
      return base + c;
    }
    const cache = this.#cache[paper ? 0 : 1];
    let i = cache.get(c);
    if (i === void 0) {
      if (!isHex(c))
        fail2(`a colour takes #rrggbb or an index into the palette, not ${JSON.stringify(c)}`);
      const lc = c.toLowerCase();
      i = -1;
      for (let k = base; k < base + this.size; k++)
        if (this.colors[k].toLowerCase() === lc)
          i = k, k = Infinity;
      if (i < 0)
        i = nearest(this.colors, c, base, base + this.size);
      cache.set(c, i);
    }
    return i;
  }
  /** The index of the ink a cell with no colour of its own takes. */
  ink(paper = false) {
    const ink = this.#ink;
    return this.index(themed(ink) ? paper ? ink.light : ink.dark : ink, paper);
  }
};
var schemes = {
  ocean: {
    light: ["#7fb8d6", "#3a8fc4", "#0077b6", "#025a8c", "#023e6b", "#03045e"],
    dark: ["#0a1f5c", "#0353a4", "#0077b6", "#00b4d8", "#90e0ef", "#e0fbfc"]
  },
  sunset: {
    light: ["#f4a261", "#e76f51", "#c9184a", "#9d0b4a", "#6a0d6b", "#3b0f5c"],
    dark: ["#3b0f5c", "#7b2cbf", "#c9184a", "#ff6b35", "#ffb627", "#ffe8a3"]
  },
  neon: {
    light: ["#c77dff", "#9d4edd", "#e0218a", "#b5179e", "#7209b7", "#3a0ca3"],
    dark: ["#3c096c", "#7b2ff7", "#f107a3", "#ff5edf", "#00e5ff", "#e0ffff"]
  },
  fire: {
    light: ["#fbbf24", "#f59e0b", "#ea580c", "#c2410c", "#991b1b", "#5b0f0f"],
    dark: ["#4a0d02", "#991b1b", "#dc2626", "#f97316", "#facc15", "#fef9c3"]
  },
  aurora: {
    light: ["#a78bfa", "#7c3aed", "#0d9488", "#047857", "#065f46", "#064e3b"],
    dark: ["#312e81", "#0e7490", "#059669", "#22c55e", "#86efac", "#ecfdf5"]
  },
  forest: {
    light: ["#a3d9a5", "#4ade80", "#16a34a", "#15803d", "#166534", "#14532d"],
    dark: ["#052e16", "#14532d", "#15803d", "#22c55e", "#86efac", "#dcfce7"]
  },
  candy: {
    light: ["#f9a8d4", "#f472b6", "#db2777", "#a21caf", "#7e22ce", "#0e7490"],
    dark: ["#831843", "#db2777", "#f472b6", "#c084fc", "#67e8f9", "#fef08a"]
  },
  mono: {
    light: ["#d4d4d8", "#a1a1aa", "#71717a", "#3f3f46", "#18181b"],
    dark: ["#3f3f46", "#71717a", "#a1a1aa", "#d4d4d8", "#fafafa"]
  },
  ink: { light: [INK2.light], dark: [INK2.dark] },
  paper: {
    light: ["#d6c4a8", "#b08d62", "#8b6a43", "#5c4630", "#3b2a1d"],
    dark: ["#3f2d20", "#6b4f3a", "#a07850", "#d4b483", "#f3e3c3"]
  },
  github: {
    light: ["#9be9a8", "#40c463", "#30a14e", "#216e39"],
    dark: ["#0e4429", "#006d32", "#26a641", "#39d353"]
  },
  ice: {
    light: ["#7dd3fc", "#38bdf8", "#0284c7", "#075985", "#0c4a6e"],
    dark: ["#0c4a6e", "#0369a1", "#38bdf8", "#bae6fd", "#f0f9ff"]
  },
  gold: {
    light: ["#facc15", "#eab308", "#ca8a04", "#a16207", "#713f12"],
    dark: ["#713f12", "#ca8a04", "#facc15", "#fef08a", "#fffbeb"]
  },
  lava: {
    light: ["#fdba74", "#f97316", "#dc2626", "#991b1b", "#450a0a"],
    dark: ["#450a0a", "#991b1b", "#ef4444", "#f97316", "#fde047"]
  },
  matrix: {
    light: ["#86efac", "#4ade80", "#16a34a", "#15803d", "#14532d"],
    dark: ["#022c0f", "#15803d", "#22c55e", "#86efac", "#f0fdf4"]
  },
  night: {
    light: ["#93c5fd", "#60a5fa", "#2563eb", "#1e40af", "#172554"],
    dark: ["#1e293b", "#1e40af", "#3b82f6", "#93c5fd", "#f8fafc"]
  },
  space: {
    light: ["#ddd6fe", "#c4b5fd", "#8b5cf6", "#6d28d9", "#4338ca", "#1e1b4b"],
    dark: ["#2e1065", "#5b21b6", "#7c3aed", "#60a5fa", "#e0e7ff", "#fff7ed"]
  }
};
var materialColors = {
  water: { light: ["#1e3a8a", "#1d4ed8", "#60a5fa", "#0369a1"], dark: ["#2563eb", "#60a5fa", "#a5d8ff", "#e0f2fe"] },
  sea: { light: ["#134e4a", "#115e59", "#0f766e", "#0d9488"], dark: ["#0f766e", "#14b8a6", "#2dd4bf", "#ccfbf1"] },
  cola: { light: ["#2b1408", "#431d0b", "#7c3a12", "#92400e"], dark: ["#5a250c", "#74351a", "#94532a", "#ead0a8"] },
  lemonade: { light: ["#854d0e", "#a16207", "#ca8a04", "#a16207"], dark: ["#ca8a04", "#eab308", "#fde047", "#fef9c3"] },
  coffee: { light: ["#3b2314", "#4a2c18", "#5b3a24", "#7c4a2a"], dark: ["#7b5135", "#946446", "#b8875e", "#e2c9a6"] },
  tea: { light: ["#713f12", "#854d0e", "#a16207", "#b45309"], dark: ["#b45309", "#d97706", "#f59e0b", "#fde68a"] },
  juice: { light: ["#9a3412", "#c2410c", "#ea580c", "#c2410c"], dark: ["#c2410c", "#ea580c", "#fb923c", "#fed7aa"] },
  wine: { light: ["#4c0519", "#881337", "#9f1239", "#be123c"], dark: ["#9f1239", "#be123c", "#e11d48", "#fda4af"] },
  milk: { light: ["#64748b", "#94a3b8", "#94a3b8", "#64748b"], dark: ["#cbd5e1", "#e2e8f0", "#f1f5f9", "#ffffff"] },
  glass: { light: ["#475569", "#94a3b8", "#64748b"], dark: ["#94a3b8", "#f8fafc", "#cbd5e1"] },
  fire: { light: ["#7f1d1d", "#b91c1c", "#c2410c", "#d97706", "#a16207"], dark: ["#7f1d1d", "#dc2626", "#f97316", "#facc15", "#fef9c3"] },
  candle: { light: ["#9a3412", "#c2410c", "#d97706", "#b45309", "#92400e"], dark: ["#c2410c", "#f97316", "#fbbf24", "#fde68a", "#fffbeb"] },
  lava: { light: ["#7f1d1d", "#b91c1c", "#ea580c", "#ca8a04"], dark: ["#991b1b", "#ef4444", "#f97316", "#fde047"] },
  smoke: { light: ["#9ca3af", "#6b7280", "#4b5563"], dark: ["#4b5563", "#9ca3af", "#d1d5db"] },
  steam: { light: ["#94a3b8", "#64748b"], dark: ["#94a3b8", "#e2e8f0"] },
  cloud: { light: ["#6b7280", "#9ca3af", "#4b5563"], dark: ["#e5e7eb", "#6b7280", "#9ca3af"] },
  storm: { light: ["#374151", "#6b7280", "#1f2937"], dark: ["#9ca3af", "#374151", "#4b5563"] },
  steel: { light: ["#1e293b", "#475569", "#64748b", "#94a3b8"], dark: ["#475569", "#94a3b8", "#cbd5e1", "#ffffff"] },
  gold: { light: ["#713f12", "#854d0e", "#a16207", "#ca8a04"], dark: ["#a16207", "#eab308", "#fde047", "#fffbeb"] },
  copper: { light: ["#7c2d12", "#9a3412", "#c2410c", "#ea580c"], dark: ["#9a3412", "#c2410c", "#fb923c", "#ffedd5"] },
  wood: { light: ["#3f2a14", "#6b4423", "#8b5a2b"], dark: ["#6b4423", "#a0682f", "#d29b5c"] },
  grass: { light: ["#14532d", "#15803d", "#16a34a"], dark: ["#166534", "#22c55e", "#86efac"] },
  seaweed: { light: ["#064e3b", "#047857", "#059669"], dark: ["#065f46", "#10b981", "#6ee7b7"] },
  sand: { light: ["#713f12", "#92400e", "#a16207"], dark: ["#a16207", "#d4a24c", "#f5deb3"] },
  ice: { light: ["#0369a1", "#0284c7", "#0c4a6e"], dark: ["#7dd3fc", "#bae6fd", "#ffffff"] },
  neon: { light: ["#f9a8d4", "#db2777", "#831843"], dark: ["#9d174d", "#ec4899", "#fce7f3"] },
  cyan: { light: ["#67e8f9", "#0891b2", "#164e63"], dark: ["#155e75", "#22d3ee", "#ecfeff"] },
  lamp: { light: ["#fcd34d", "#d97706", "#92400e"], dark: ["#92400e", "#f59e0b", "#fef3c7"] },
  ceramic: { light: ["#374151", "#9ca3af", "#6b7280"], dark: ["#e5e7eb", "#6b7280", "#ffffff"] },
  wax: { light: ["#92400e", "#d6b98c", "#78350f"], dark: ["#fef3c7", "#a8a29e", "#ffffff"] },
  moon: { light: ["#a16207", "#ca8a04", "#ca8a04"], dark: ["#fef9c3", "#fde68a", "#ffffff"] },
  night: { light: ["#334155", "#94a3b8", "#475569"], dark: ["#cbd5e1", "#475569", "#f1f5f9"] },
  stars: { light: ["#94a3b8", "#334155"], dark: ["#64748b", "#f8fafc"] },
  rose: { light: ["#be123c", "#e11d48", "#9f1239"], dark: ["#e11d48", "#fb7185", "#ffe4e6"] },
  goldfish: { light: ["#c2410c", "#ea580c", "#9a3412"], dark: ["#ea580c", "#fb923c", "#ffedd5"] },
  brick: { light: ["#7f1d1d", "#9a3412"], dark: ["#b91c1c", "#f97316"] },
  bubbles: { light: ["#0284c7", "#0369a1"], dark: ["#7dd3fc", "#f0f9ff"] },
  fizz: { light: ["#92400e", "#b45309"], dark: ["#e0b98a", "#fef3c7"] },
  sparks: { light: ["#ca8a04", "#ea580c", "#b91c1c"], dark: ["#fde047", "#f97316", "#dc2626"] },
  rain: { light: ["#1d4ed8", "#2563eb"], dark: ["#60a5fa", "#bfdbfe"] },
  snow: { light: ["#64748b", "#94a3b8"], dark: ["#e2e8f0", "#ffffff"] },
  ink: { light: [INK2.light], dark: [INK2.dark] },
  sunset: { light: ["#1e1b4b", "#6d28d9", "#c2410c", "#ca8a04"], dark: ["#1e1b4b", "#7c3aed", "#f97316", "#fde047"] },
  sky: { light: ["#1e3a8a", "#2563eb", "#0ea5e9"], dark: ["#0f172a", "#1e3a8a", "#38bdf8"] }
};
var named2 = (name, prefer) => {
  const [a, b] = prefer === "materials" ? [materialColors, schemes] : [schemes, materialColors];
  return Object.hasOwn(a, name) ? a[name] : Object.hasOwn(b, name) ? b[name] : void 0;
};
var NAMES = () => `a palette's name such as "ocean", "fire" or "cola" (see schemes and materialColors)`;
function colorsOf(v, what = "colors", prefer = "looks") {
  if (typeof v === "string") {
    if (isHex(v))
      return [v];
    const s = named2(v, prefer);
    if (s)
      return { light: [...s.light], dark: [...s.dark] };
    return fail2(`${what} takes ${NAMES()}, colours as #rrggbb, or { light, dark }, not ${JSON.stringify(v)}: ${didYouMean(v)}`);
  }
  if (Array.isArray(v)) {
    if (!v.length || !v.every(isHex))
      fail2(`${what} takes colours as #rrggbb, one or more, not ${JSON.stringify(v)}`);
    return [...v];
  }
  if (v !== null && typeof v === "object" && Array.isArray(v.light) && Array.isArray(v.dark)) {
    const { light, dark } = v;
    if (!light.length || !dark.length || !light.every(isHex) || !dark.every(isHex))
      fail2(`${what} takes { light, dark }, each one or more colours as #rrggbb, not ${JSON.stringify(v)}`);
    return { light: [...light], dark: [...dark] };
  }
  return fail2(`${what} takes ${NAMES()}, colours as #rrggbb, or { light, dark }, not ${typeof v === "object" ? JSON.stringify(v) ?? String(v) : String(v)}`);
}
function colorOf(v, what = "color") {
  if (isHex(v))
    return { light: v, dark: v };
  if (typeof v === "string") {
    const s = named2(v, "looks");
    if (!s)
      return fail2(`${what} takes a colour as #rrggbb, { light, dark }, or ${NAMES()}, not ${JSON.stringify(v)}: ${didYouMean(v)}`);
    const strong = (list2) => list2[Math.min(list2.length - 1, Math.floor(list2.length * 0.6))];
    return { light: strong(s.light), dark: strong(s.dark) };
  }
  const o = v;
  if (v !== null && typeof v === "object" && !Array.isArray(v) && isHex(o.light) && isHex(o.dark))
    return { light: o.light, dark: o.dark };
  return fail2(`${what} takes a colour as #rrggbb, { light, dark }, or ${NAMES()}, not ${typeof v === "object" ? JSON.stringify(v) ?? String(v) : String(v)}`);
}
function didYouMean(word) {
  const all = [.../* @__PURE__ */ new Set([...Object.keys(schemes), ...Object.keys(materialColors)])];
  const near = nearWords(word, all);
  return near.length ? `did you mean ${near.map((n) => JSON.stringify(n)).join(" or ")}?` : `a colour of your own is #rrggbb, and the names are ${and2(all)}`;
}
function lettersApart(a, b) {
  const d = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let prev = d[0];
    d[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const keep = d[j];
      d[j] = Math.min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = keep;
    }
  }
  return d[b.length];
}
var SYNONYMS = {
  middle: ["center", "middle"],
  centre: ["center"],
  centred: ["center"],
  mid: ["center", "middle"],
  colour: ["color", "colors", "palette"],
  colours: ["colors", "palette", "color"],
  palette: ["colors", "color"],
  colors: ["palette", "color"],
  color: ["colors", "palette"],
  size: ["scale", "size"],
  scale: ["size", "scale"],
  dir: ["to", "toward", "way"],
  direction: ["to", "toward", "way", "direction"],
  heading: ["to"],
  towards: ["toward", "to"],
  big: ["large", "strong", "big"],
  large: ["huge", "large", "strong"],
  little: ["small", "subtle"],
  tiny: ["small", "subtle", "tiny"],
  huge: ["huge", "large"],
  quick: ["fast"],
  quickly: ["fast"],
  rapid: ["fast"],
  slowly: ["slow"],
  medium: ["normal", "medium"],
  normal: ["medium", "normal"],
  light: ["subtle", "light"],
  heavy: ["strong", "heavy"],
  weak: ["subtle"],
  soft: ["subtle", "soft"],
  hard: ["strong"],
  duration: ["period", "seconds"],
  time: ["period", "seconds"],
  length: ["period", "seconds", "length"],
  loop: ["period", "loop"],
  delay: ["first", "start", "delay"],
  text: ["label", "title", "text"],
  title: ["label", "title"],
  label: ["title", "label"],
  caption: ["label", "title"],
  width: ["cols", "width"],
  height: ["rows", "height"],
  columns: ["cols", "columns"],
  speed: ["speed", "period"],
  rate: ["speed", "rate"],
  amount: ["amount", "size"],
  strength: ["amount"],
  intensity: ["amount"]
};
function nearWords(word, words2) {
  const w = word.toLowerCase().slice(0, 40);
  const same = (SYNONYMS[w] ?? []).filter((s) => words2.includes(s) && s !== word);
  const close = words2.filter((n) => !same.includes(n) && lettersApart(w, n.toLowerCase()) <= (w.length <= 4 ? 1 : 2));
  return [...same, ...close].slice(0, 3);
}
function suggest(word, words2) {
  if (typeof word !== "string")
    return "";
  const near = nearWords(word, words2);
  return near.length ? ` (did you mean ${near.map((n) => JSON.stringify(n)).join(" or ")}?)` : "";
}
function mergePalettes(parts) {
  const palette = [];
  const at3 = /* @__PURE__ */ new Map();
  const add = (c) => {
    const k = c.toLowerCase();
    let i = at3.get(k);
    if (i === void 0)
      at3.set(k, i = palette.push(c) - 1);
    return i;
  };
  const maps = parts.map((p) => Uint8Array.from(p ?? [], (c) => add(c)));
  let ink = null;
  if (palette.length && parts.some((p) => !p))
    ink = { light: add(INK2.light), dark: add(INK2.dark) };
  if (palette.length > 64)
    fail2(`these pieces have ${palette.length} colours between them, past the 64 a piece can have: use fewer, or a piece in fewer colours`);
  if (palette.length === 1)
    palette.push(palette[0]);
  return { palette, maps, ink };
}
var EMPTY = 0;
var NONE = 255;
function code(ch) {
  if (typeof ch !== "string")
    fail2(`a cell takes a character as a string, not ${String(ch)}`);
  const c = ch.length ? ch.charCodeAt(0) : EMPTY;
  if (c && (c < 32 || c >= 127 && c <= 159 || c >= 55296 && c <= 57343))
    fail2(`a cell takes one printable character from the Basic Multilingual Plane, not ${JSON.stringify(ch)}`);
  return c;
}
var Surface = class _Surface {
  cols;
  rows;
  chars;
  colors;
  /** A cell's height in cell widths: 2, the shape of a character, or 1 for a square grid (meta.cell). */
  aspect;
  /** The piece's colours, which a colour given by #rrggbb or index is found in; null for a piece in one ink. */
  palette;
  /** True when the frame is drawn dark on a light page (env.paper). */
  paper = false;
  /** True when the frame is drawn as text in one ink, so colours are not shown (no env.color). */
  mono = true;
  #line;
  constructor(cols, rows, { palette = null, aspect = 2 } = {}) {
    if (!Number.isInteger(cols) || cols < 1 || !Number.isInteger(rows) || rows < 1)
      fail2(`a surface takes whole numbers of columns and rows of 1 or more, not ${cols} by ${rows}`);
    this.cols = cols;
    this.rows = rows;
    this.chars = new Uint16Array(cols * rows);
    this.colors = new Uint8Array(cols * rows).fill(NONE);
    this.aspect = aspect;
    this.palette = palette;
    this.#line = new Uint16Array(cols);
  }
  /** The cell's index into chars and colors, or -1 outside the grid. */
  index(x, y) {
    x = Math.floor(x);
    y = Math.floor(y);
    return x >= 0 && x < this.cols && y >= 0 && y < this.rows ? y * this.cols + x : -1;
  }
  /** The palette index of a colour for this frame's theme; NONE for no colour, or on a piece with no palette. */
  resolve(color) {
    if (color === void 0 || color === null || !this.palette)
      return NONE;
    return this.palette.index(color, this.paper);
  }
  /**
   * Draws one character at a cell, in a colour if given: an index into the piece's colours or #rrggbb. "" clears the
   * cell; " " is a blank that still covers what is under it. Throws for a control character or one outside the BMP,
   * which a frame can't hold a cell of.
   */
  set(x, y, ch, color) {
    const i = this.index(x, y);
    if (i < 0)
      return;
    const c = code(ch);
    this.chars[i] = c;
    this.colors[i] = c === EMPTY ? NONE : this.resolve(color);
  }
  /** Draws by index with a char code and a palette index as they are, for drawing loops that have them already. */
  put(i, code3, color = NONE) {
    this.chars[i] = code3;
    this.colors[i] = color;
  }
  /** The character at a cell: "" where nothing is drawn or outside the grid. */
  get(x, y) {
    const i = this.index(x, y);
    return i < 0 || this.chars[i] === EMPTY ? "" : String.fromCharCode(this.chars[i]);
  }
  /** The palette index at a cell, NONE where it has no colour or outside the grid. */
  colorAt(x, y) {
    const i = this.index(x, y);
    return i < 0 ? NONE : this.colors[i];
  }
  /** Empties every cell, or every cell of a region. */
  clear(region) {
    if (!region) {
      this.chars.fill(EMPTY);
      this.colors.fill(NONE);
      return;
    }
    this.fill("", void 0, region);
  }
  /** Fills every cell, or a region's, with one character in one colour. */
  fill(ch, color, region) {
    const { x, y, cols, rows } = this.clip(region);
    const c = code(ch), k = c === EMPTY ? NONE : this.resolve(color);
    for (let r = y; r < y + rows; r++) {
      this.chars.fill(c, r * this.cols + x, r * this.cols + x + cols);
      this.colors.fill(k, r * this.cols + x, r * this.cols + x + cols);
    }
  }
  /** A region cut down to the grid, whole cells; the whole grid when none is given. */
  clip(region) {
    if (!region)
      return { x: 0, y: 0, cols: this.cols, rows: this.rows };
    const x0 = Math.max(0, Math.floor(region.x)), y0 = Math.max(0, Math.floor(region.y));
    const x1 = Math.min(this.cols, Math.floor(region.x) + Math.floor(region.cols)), y1 = Math.min(this.rows, Math.floor(region.y) + Math.floor(region.rows));
    return { x: x0, y: y0, cols: Math.max(0, x1 - x0), rows: Math.max(0, y1 - y0) };
  }
  /**
   * Writes text from a cell, left to right, a newline starting the next row back at x. Spaces cover what is under
   * them. ascii.rest/kit's draw has text() with alignment and wrapping.
   */
  write(x, y, text2, color) {
    let cx = Math.floor(x), cy = Math.floor(y);
    for (const ch of String(text2)) {
      if (ch === "\n")
        cx = Math.floor(x), cy++;
      else
        this.set(cx++, cy, ch, color);
    }
  }
  /**
   * Lays another grid over this one with its top left at x, y. Its EMPTY cells, and its `mask` character (a space by
   * default; null for none), let this one show through. Its colours are copied as they are, or through `map`, from its
   * palette's indices to this one's (mergePalettes() makes these).
   */
  paste(src, x, y, { mask = " ", map } = {}) {
    const m = mask === null || mask === "" ? -1 : mask.charCodeAt(0);
    x = Math.floor(x);
    y = Math.floor(y);
    for (let r = Math.max(0, -y); r < src.rows && r + y < this.rows; r++)
      for (let c = Math.max(0, -x); c < src.cols && c + x < this.cols; c++) {
        const i = r * src.cols + c;
        const ch = src.chars[i];
        if (ch === EMPTY || ch === m)
          continue;
        const k = (r + y) * this.cols + c + x;
        const col = src.colors[i];
        this.chars[k] = ch;
        this.colors[k] = col === NONE || !map ? col : map[col] ?? NONE;
      }
  }
  /**
   * Reads a frame back into the grid: the string a piece returned and, for a coloured one, the env.color it wrote.
   * Spaces become EMPTY, so the frame can be laid over another; lines are cut or padded to the grid.
   */
  load(text2, color) {
    this.clear();
    let x = 0, y = 0;
    for (let k = 0; k < text2.length && y < this.rows; k++) {
      const c = text2.charCodeAt(k);
      if (c === 10) {
        x = 0;
        y++;
        continue;
      }
      if (x < this.cols && c !== 32) {
        const i = y * this.cols + x;
        this.chars[i] = c;
        this.colors[i] = color ? color[i] : NONE;
      }
      x++;
    }
    return this;
  }
  /**
   * The frame: `rows` lines of `cols` characters, EMPTY as a space. Given env.color (a coloured piece drawn in colour),
   * it writes every cell's palette index into it, the ink where a cell has no colour.
   */
  frame(env = {}) {
    const { cols, rows, chars: chars3, colors } = this;
    const color = env.color;
    if (color && this.palette) {
      const ink = this.palette.ink(this.paper);
      const n = Math.min(color.length, chars3.length);
      for (let i = 0; i < n; i++)
        color[i] = colors[i] === NONE ? ink : colors[i];
    }
    const line2 = this.#line;
    let out = "";
    for (let r = 0; r < rows; r++) {
      for (let c = 0, i = r * cols; c < cols; c++, i++)
        line2[c] = chars3[i] || 32;
      out += (r ? "\n" : "") + String.fromCharCode.apply(null, line2);
    }
    return out;
  }
  /** The frame as text in one ink. */
  toString() {
    return this.frame();
  }
  /** A copy, with the same palette and theme. */
  clone() {
    const s = new _Surface(this.cols, this.rows, { palette: this.palette, aspect: this.aspect });
    s.chars.set(this.chars);
    s.colors.set(this.colors);
    s.paper = this.paper;
    s.mono = this.mono;
    return s;
  }
  /** A grid of a frame's text, as wide as its longest line, and its colours if given. */
  static from(text2, color, palette = null) {
    const lines = String(text2).split("\n");
    const s = new _Surface(Math.max(1, ...lines.map((l) => l.length)), Math.max(1, lines.length), { palette });
    return s.load(String(text2), color);
  }
};
var CATEGORIES = ["scenes", "shapes", "space", "physics", "nature", "creatures", "objects", "generative", "effects", "ui", "data", "type", "logos", "companies", "distros"];
var MAX = { cols: 320, rows: 120 };
function checkMeta(m) {
  if (!m || typeof m !== "object")
    fail2("a piece takes a meta object");
  if (typeof m.name !== "string" || !m.name.trim())
    fail2('a piece takes a name: one line, such as "orbit"');
  if (!CATEGORIES.includes(m.category))
    fail2(`category takes one of ${and2(CATEGORIES)}, not ${JSON.stringify(m.category)}`);
  if (typeof m.note !== "string" || !m.note || m.note.length > 72)
    fail2(`note takes one line of 1 to 72 characters, not ${JSON.stringify(m.note)}`);
  if (!Number.isInteger(m.cols) || m.cols < 1 || m.cols > MAX.cols)
    fail2(`cols takes a whole number from 1 to ${MAX.cols}, not ${String(m.cols)}`);
  if (!Number.isInteger(m.rows) || m.rows < 1 || m.rows > MAX.rows)
    fail2(`rows takes a whole number from 1 to ${MAX.rows}, not ${String(m.rows)}`);
  if (!Number.isInteger(m.fps) || m.fps < 0 || m.fps > 60)
    fail2(`fps takes a whole number from 0 (a still) to 60, not ${String(m.fps)}`);
  if (m.options !== void 0 && (typeof m.options !== "object" || m.options === null))
    fail2("options takes an object of the piece's options and their defaults");
  if (m.palette !== void 0 && !(Array.isArray(m.palette) && m.palette.length >= 2 && m.palette.length <= 64 && m.palette.every(isHex)))
    fail2("a palette takes 2 to 64 colours as #rrggbb");
  if (m.ground !== void 0 && !isHex(m.ground))
    fail2(`ground takes a colour as #rrggbb, not ${JSON.stringify(m.ground)}`);
  if (m.cell !== void 0 && m.cell !== 1 && m.cell !== 2)
    fail2(`cell takes 1 (square) or 2, not ${String(m.cell)}`);
  if (m.loop !== void 0 && !(typeof m.loop === "number" && Number.isFinite(m.loop) && m.loop > 0))
    fail2(`loop takes a number of seconds above 0, not ${String(m.loop)}`);
  if (m.still !== void 0 && !(typeof m.still === "number" && Number.isFinite(m.still) && m.still >= 0))
    fail2(`still takes a number of seconds of 0 or more, not ${String(m.still)}`);
  return m;
}
var Chainable = class {
  named(name, note) {
    return named(this, name, note === void 0 ? {} : { note });
  }
  note(note) {
    return named(this, this.meta.name, { note });
  }
  over(bottom, o) {
    return over(this, bottom, o);
  }
  behind(top, o) {
    return over(top, this, o);
  }
  speed(factor) {
    return speed(this, factor);
  }
  delay(seconds) {
    return delay(this, seconds);
  }
  repeat(seconds) {
    return repeat(this, seconds);
  }
  freeze(at3) {
    return freeze(this, at3);
  }
  pad(n) {
    return pad(this, n);
  }
  border(o) {
    return border(this, o);
  }
  crop(region) {
    return crop(this, region);
  }
  flip(axis) {
    return flip(this, axis);
  }
  scale(factor) {
    return scale(this, factor);
  }
  glint(o) {
    return glint(this, o);
  }
  shake(o) {
    return shake(this, o);
  }
  glitch(o) {
    return glitch(this, o);
  }
  wave(o) {
    return wave(this, o);
  }
  fade(o) {
    return fade2(this, o);
  }
  dissolve(o) {
    return dissolve(this, o);
  }
  rainbow(o) {
    return rainbow(this, o);
  }
  hueCycle(o) {
    return hueCycle(this, o);
  }
  outline(o) {
    return outline(this, o);
  }
  shadow(o) {
    return shadow(this, o);
  }
  scan(o) {
    return scan(this, o);
  }
  typeIn(o) {
    return typeIn(this, o);
  }
};
function chained(p) {
  if (p instanceof Chainable)
    return p;
  if (!p || typeof p !== "object" || !p.meta || typeof p.default !== "function")
    fail2(`chained() takes a piece, meta and a default function, not ${String(p)}`);
  return Object.assign(Object.create(Chainable.prototype), p);
}
function specOf(spec, name, size2 = { cols: 64, rows: 24 }) {
  if (spec !== void 0 && (spec === null || typeof spec !== "object"))
    fail2(`${name}() takes a spec object, such as { cols: 64, rows: 24 }`);
  const { palette: given, ...rest } = spec ?? {};
  const palette = given === void 0 ? void 0 : colorsOf(given, `${name}()'s palette`);
  return { ...rest, name: spec?.name ?? name, cols: spec?.cols ?? size2.cols, rows: spec?.rows ?? size2.rows, ...palette !== void 0 ? { palette } : {} };
}
function spread(stops, n) {
  if (Array.isArray(stops))
    return gradient(stops, n);
  const { light, dark } = stops;
  if (!Array.isArray(light) || !Array.isArray(dark))
    fail2(`colours take a list of #rrggbb, or { light, dark }, not ${JSON.stringify(stops)}`);
  return { light: gradient(light, n), dark: gradient(dark, n) };
}
function metaOf(spec) {
  if (!spec || typeof spec !== "object")
    fail2("piece() takes a spec: { name, cols, rows } at least");
  const palette = spec.palette === void 0 ? null : new Palette(typeof spec.palette === "string" ? colorsOf(spec.palette, "palette") : spec.palette, spec.ink ?? 0);
  if (palette) {
    palette.ink(true);
    palette.ink(false);
  }
  const name = typeof spec.name === "string" ? spec.name.trim() : spec.name;
  const meta = {
    name,
    category: spec.category ?? "generative",
    note: spec.note ?? (typeof name === "string" ? name.slice(0, 72) : name),
    cols: spec.cols,
    rows: spec.rows,
    fps: spec.fps ?? 30,
    ...spec.options !== void 0 ? { options: spec.options } : {},
    ...spec.clock ? { clock: true } : {},
    ...palette ? { palette: palette.colors } : {},
    ...spec.ground !== void 0 ? { ground: spec.ground } : {},
    ...spec.cell !== void 0 ? { cell: spec.cell } : {},
    ...spec.loop !== void 0 ? { loop: spec.loop } : {},
    ...spec.still !== void 0 ? { still: spec.still } : {}
  };
  return { meta: checkMeta(meta), palette };
}
function piece(spec, draw) {
  const { meta, palette } = metaOf(spec);
  const setup = typeof draw === "function" ? () => draw : draw && typeof draw === "object" && typeof draw.setup === "function" ? draw.setup : fail2("piece() takes a drawing, (t, s, ctx) => { ... }, or { setup: (options) => drawing }");
  const wipe = spec.clear ?? true;
  return chained({
    meta,
    default(options) {
      const opts2 = { ...meta.options, ...options };
      const s = new Surface(meta.cols, meta.rows, { palette, aspect: meta.cell ?? 2 });
      const ctx = { options: opts2, paper: false, mono: true, cols: meta.cols, rows: meta.rows };
      const fn = setup(opts2, { cols: meta.cols, rows: meta.rows });
      if (typeof fn !== "function")
        fail2("a piece's setup returns its drawing, (t, s, ctx) => { ... }");
      return (t, env = {}) => {
        s.paper = ctx.paper = !!env.paper;
        s.mono = ctx.mono = !env.color;
        if (wipe)
          s.clear();
        fn(Number.isFinite(t) ? t : 0, s, ctx);
        return s.frame(env);
      };
    }
  });
}
function asPiece(src, name = "text") {
  if (src instanceof Surface) {
    const grid3 = src.clone();
    const palette = grid3.palette;
    const meta = checkMeta({ name, category: "type", note: name, cols: grid3.cols, rows: grid3.rows, fps: 0, ...palette ? { palette: palette.colors } : {} });
    const other = grid3.clone();
    if (palette?.themed) {
      const n = palette.size;
      for (let i = 0; i < other.colors.length; i++) {
        const c = other.colors[i];
        if (c !== NONE)
          other.colors[i] = grid3.paper ? c < n ? c + n : c : c >= n ? c - n : c;
      }
    }
    other.paper = !grid3.paper;
    return chained({
      meta,
      default: () => (t, env = {}) => (!!env.paper === grid3.paper ? grid3 : other).frame(env)
    });
  }
  if (typeof src === "string") {
    let lines = src.replace(/\r\n?/g, "\n").split("\n");
    if (lines.length > 1 && lines[0] === "") {
      while (lines.length > 1 && !lines[0].trim())
        lines.shift();
      while (lines.length > 1 && !lines[lines.length - 1].trim())
        lines.pop();
      const indent = lines.reduce((n, l) => l.trim() ? Math.min(n, l.length - l.trimStart().length) : n, Infinity);
      if (Number.isFinite(indent))
        lines = lines.map((l) => l.slice(indent));
    }
    const cols = Math.max(1, ...lines.map((l) => l.length));
    if (CONTROL.test(lines.join("")))
      fail2("text takes printable characters and newlines, not control characters");
    const text2 = lines.map((l) => l.padEnd(cols)).join("\n");
    const meta = checkMeta({ name, category: "type", note: name, cols, rows: lines.length, fps: 0 });
    return chained({ meta, default: () => () => text2 });
  }
  if (!src || typeof src !== "object" || !src.meta || typeof src.default !== "function")
    fail2("this takes a piece, a string of text or a Surface");
  return src;
}
function sample(src, options = {}) {
  const p = asPiece(src);
  const { meta } = p;
  const frame = p.default({ ...meta.options, ...options });
  const palette = meta.palette ?? null;
  const color = palette ? new Uint8Array(meta.cols * meta.rows) : void 0;
  const grid3 = new Surface(meta.cols, meta.rows, { palette: palette ? new Palette(palette) : null, aspect: meta.cell ?? 2 });
  return {
    meta,
    palette,
    at(t, { paper = false, mono = false } = {}) {
      const c = mono ? void 0 : color;
      const text2 = frame(t, { paper, color: c });
      grid3.paper = paper;
      grid3.mono = !c;
      return grid3.load(text2, c);
    }
  };
}
function snapshot(src, t = 0, { paper = false, mono = false, options = {} } = {}) {
  const p = asPiece(src);
  const color = p.meta.palette && !mono ? new Uint8Array(p.meta.cols * p.meta.rows) : void 0;
  const text2 = p.default({ ...p.meta.options, ...options })(t, { paper, color });
  return { text: text2, color: color ?? null };
}

// node_modules/ascii.rest/dist/kit/materials.js
var isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
function show2(v) {
  if (typeof v === "function")
    return v.name ? `${v.name}, a function: call it, ${v.name}()` : "a function";
  if (typeof v !== "object" || v === null)
    return typeof v === "string" ? JSON.stringify(v) : String(v);
  if (Array.isArray(v))
    return `[${v.map(show2).join(", ")}]`;
  try {
    return JSON.stringify(v) ?? String(v);
  } catch {
    return String(v);
  }
}
function optionsOf3(what, o, keys) {
  if (o === void 0)
    return {};
  if (!isObject(o))
    fail2(`${what} takes an options object, such as { ${keys[0]}: ... }, not ${show2(o)}`);
  for (const k of Object.keys(o))
    if (!keys.includes(k))
      fail2(`${what} has no option ${JSON.stringify(k)}${suggest(k, keys)}: it takes ${and2(keys.map((x) => JSON.stringify(x)))}`);
  return o;
}
var or3 = (words2) => words2.length > 1 ? `${words2.slice(0, -1).join(", ")} or ${words2.at(-1)}` : words2[0] ?? "";
function numberOf(what, v, def, lo = -Infinity, hi = Infinity, words2 = "") {
  if (v === void 0)
    return def;
  if (typeof v !== "number" || !Number.isFinite(v) || v < lo || v > hi) {
    const range = words2 || (hi === Infinity ? lo === -Infinity ? "" : ` of ${lo} or more` : ` from ${lo} to ${hi}`);
    fail2(`${what} takes a number${range}, not ${show2(v)}`);
  }
  return v;
}
function periodOf2(what, v, def) {
  const p = numberOf(what, v, def, 0, 60, " of seconds above 0, up to 60");
  if (p <= 0)
    fail2(`${what} takes a number of seconds above 0, up to 60, not ${p}`);
  return p;
}
function wordOf(what, v, words2, def) {
  if (v === void 0)
    return def;
  if (!words2.includes(v))
    fail2(`${what} takes ${or3(words2.map((w) => JSON.stringify(w)))}, not ${show2(v)}${suggest(v, words2)}`);
  return v;
}
function boolOf(what, v, def) {
  if (v === void 0)
    return def;
  if (typeof v !== "boolean")
    fail2(`${what} takes true or false, not ${show2(v)}`);
  return v;
}
function charOf(what, v, def) {
  if (v === void 0)
    return def;
  if (typeof v !== "string" || v.length !== 1 || /[\u0000-\u001f\u007f-\u009f\ud800-\udfff]/.test(v))
    fail2(`${what} takes one printable character, not ${show2(v)}`);
  return v;
}
function rampOf(what, v, def) {
  if (v === void 0)
    return def;
  if (typeof v === "string" && Object.hasOwn(ramps, v))
    return ramps[v];
  if (typeof v !== "string" || v.length < 2 || /[\u0000-\u001f\u007f-\u009f\ud800-\udfff]/.test(v))
    fail2(`${what} takes a ramp's name, ${or3(Object.keys(ramps))}, or two or more characters of your own, not ${show2(v)}`);
  return v;
}
var palettes = materialColors;
function colorsOf2(what, v, def, n) {
  const spec = v === void 0 ? palettes[def] : colorsOf(v, what, "materials");
  const s = spread(spec, n);
  return Array.isArray(s) ? { light: s, dark: s } : s;
}
var ASPECT = 2;
var isArea = (v) => isObject(v) && v.kind === "area" && typeof v.place === "function";
function areaOf(what, v) {
  if (!isArea(v))
    fail2(`${what} takes an area, such as cup(), area.rect(2, 2, 10, 4) or inside(cup()), not ${show2(v)}`);
  return v;
}
var SAMPLES = 4;
function cellsOf(a, cols, rows) {
  const p = isArea(a) ? a.place(cols, rows) : a;
  const n = cols * rows;
  const cover = new Float32Array(n);
  const W = cols + 2;
  const pad2 = new Float32Array(W * (rows + 2));
  const bx0 = clamp(Math.floor(p.x0) - 1, -1, cols + 1), bx1 = clamp(Math.ceil(p.x1) + 1, -1, cols + 1);
  const by0 = clamp(Math.floor(p.y0) - 1, -1, rows + 1), by1 = clamp(Math.ceil(p.y1) + 1, -1, rows + 1);
  const step = 1 / SAMPLES, all = SAMPLES * SAMPLES;
  for (let y = by0; y < by1; y++)
    for (let x = bx0; x < bx1; x++) {
      let k = 0;
      for (let j = 0; j < SAMPLES; j++)
        for (let i = 0; i < SAMPLES; i++)
          if (p.test(x + (i + 0.5) * step, y + (j + 0.5) * step))
            k++;
      pad2[(y + 1) * W + x + 1] = k / all;
      if (x >= 0 && x < cols && y >= 0 && y < rows)
        cover[y * cols + x] = k / all;
    }
  const inside = new Uint8Array(n);
  const list2 = [];
  let x0 = cols, y0 = rows, x1 = 0, y1 = 0;
  const top = new Int16Array(cols).fill(-1), bottom = new Int16Array(cols).fill(-1), left = new Int16Array(rows).fill(-1), right = new Int16Array(rows).fill(-1);
  for (let y = Math.max(0, by0); y < Math.min(rows, by1); y++)
    for (let x = Math.max(0, bx0); x < Math.min(cols, bx1); x++) {
      const i = y * cols + x;
      if (cover[i] < 0.5)
        continue;
      inside[i] = 1;
      list2.push(i);
      if (x < x0)
        x0 = x;
      if (x >= x1)
        x1 = x + 1;
      if (y < y0)
        y0 = y;
      if (y >= y1)
        y1 = y + 1;
      if (top[x] < 0)
        top[x] = y;
      bottom[x] = y;
      if (left[y] < 0)
        left[y] = x;
      right[y] = x;
    }
  const cv = (x, y) => pad2[(y + 1) * W + x + 1];
  const isIn = (x, y) => cv(x, y) >= 0.5 ? 1 : 0;
  const border2 = new Uint8Array(n), nx = new Float32Array(n), ny = new Float32Array(n);
  for (const i of list2) {
    const x = i % cols, y = (i - x) / cols;
    if (isIn(x - 1, y) && isIn(x + 1, y) && isIn(x, y - 1) && isIn(x, y + 1))
      continue;
    border2[i] = 1;
    const c = (dx, dy) => cv(x + dx, y + dy);
    let gx = c(1, -1) + 2 * c(1, 0) + c(1, 1) - c(-1, -1) - 2 * c(-1, 0) - c(-1, 1);
    let gy = (c(-1, 1) + 2 * c(0, 1) + c(1, 1) - c(-1, -1) - 2 * c(0, -1) - c(1, -1)) / ASPECT;
    if (Math.abs(gx) + Math.abs(gy) < 1e-6) {
      gx = isIn(x + 1, y) - isIn(x - 1, y);
      gy = (isIn(x, y + 1) - isIn(x, y - 1)) / ASPECT;
    }
    const len = Math.hypot(gx, gy) || 1;
    nx[i] = gx / len;
    ny[i] = gy / len;
  }
  const depth = new Float32Array(n);
  const D = Math.hypot(1, ASPECT), far = 4 * (cols + rows * ASPECT);
  for (const i of list2)
    depth[i] = far;
  const d = (x, y, w) => (x < 0 || x >= cols || y < 0 || y >= rows ? isIn(x, y) ? far : 0 : depth[y * cols + x]) + w;
  for (let y = y0; y < y1; y++)
    for (let x = x0; x < x1; x++) {
      const i = y * cols + x;
      if (inside[i])
        depth[i] = Math.min(depth[i], d(x - 1, y, 1), d(x, y - 1, ASPECT), d(x - 1, y - 1, D), d(x + 1, y - 1, D));
    }
  for (let y = y1 - 1; y >= y0; y--)
    for (let x = x1 - 1; x >= x0; x--) {
      const i = y * cols + x;
      if (inside[i])
        depth[i] = Math.min(depth[i], d(x + 1, y, 1), d(x, y + 1, ASPECT), d(x + 1, y + 1, D), d(x - 1, y + 1, D));
    }
  let maxDepth = 0;
  for (const i of list2) {
    depth[i] = border2[i] ? 0 : Math.max(0, Math.min(depth[i], far) - 1);
    if (depth[i] >= far - 2)
      depth[i] = cols + rows * ASPECT;
    if (depth[i] > maxDepth)
      maxDepth = depth[i];
  }
  const fringe = [];
  for (let y = Math.max(0, y0 - 1); y < Math.min(rows, y1 + 1); y++)
    for (let x = Math.max(0, x0 - 1); x < Math.min(cols, x1 + 1); x++) {
      const i = y * cols + x;
      if (inside[i] || cover[i] < 0.12 || isIn(x, y + 1) === isIn(x, y - 1) || Math.abs(cv(x - 1, y) - cv(x + 1, y)) < 0.08)
        continue;
      const gx = cv(x + 1, y - 1) + 2 * cv(x + 1, y) + cv(x + 1, y + 1) - cv(x - 1, y - 1) - 2 * cv(x - 1, y) - cv(x - 1, y + 1);
      const gy = cv(x - 1, y + 1) + 2 * cv(x, y + 1) + cv(x + 1, y + 1) - cv(x - 1, y - 1) - 2 * cv(x, y - 1) - cv(x + 1, y - 1);
      if (Math.abs(gy) / ASPECT > Math.abs(gx))
        fringe.push(i);
    }
  const isFringe = new Uint8Array(n);
  for (const i of fringe)
    isFringe[i] = 1;
  const outlines2 = /* @__PURE__ */ new Map();
  const cells = {
    cols,
    rows,
    list: Int32Array.from(list2),
    inside,
    cover,
    border: border2,
    fringe: isFringe,
    has: (x, y) => x >= -1 && x <= cols && y >= -1 && y <= rows && isIn(x, y) === 1,
    outline(style = "line") {
      let o = outlines2.get(style);
      if (!o) {
        const at3 = [...list2.filter((i) => border2[i]), ...fringe];
        o = { cells: Int32Array.from(at3), chars: Uint16Array.from(at3, (i) => (border2[i] ? edgeChar(cells, i, style) : fringeChar(cells, i)).charCodeAt(0)) };
        outlines2.set(style, o);
      }
      return o;
    },
    nx,
    ny,
    depth,
    maxDepth,
    x0: x1 > x0 ? x0 : 0,
    y0: y1 > y0 ? y0 : 0,
    x1: x1 > x0 ? x1 : 0,
    y1: y1 > y0 ? y1 : 0,
    top,
    bottom,
    left,
    right,
    level: p.level ?? null,
    room: p.room ? cellsOf(p.room, cols, rows) : null,
    cavity: p.cavity ? cellsOf(p.cavity, cols, rows) : null,
    open: !!p.open,
    char: p.char ?? null,
    placed: p
  };
  return cells;
}
function fringeChar(c, i) {
  const x = i % c.cols, y = (i - x) / c.cols;
  const k = c.cover[i];
  return c.has(x, y + 1) ? k < 0.3 ? "_" : "." : k < 0.3 ? "'" : "-";
}
function edgeChar(c, i, style = "line") {
  const { cols } = c;
  const x = i % cols, y = (i - x) / cols;
  const has = c.has;
  const L = !has(x - 1, y), R = !has(x + 1, y), U = !has(x, y - 1), D = !has(x, y + 1);
  const left = style === "round" ? "(" : "|", right = style === "round" ? ")" : "|";
  const n = +L + +R + +U + +D;
  const fringeAt = (yy) => yy >= 0 && yy < c.rows && c.fringe[yy * cols + x] === 1;
  if (n === 1) {
    if (U)
      return fringeAt(y - 1) ? " " : "-";
    if (D)
      return fringeAt(y + 1) ? " " : "_";
    const d = L ? 1 : -1;
    const out = (yy) => !has(x, yy) && has(x + d, yy);
    if (style === "line" && out(y + 1) && !out(y - 1))
      return d > 0 ? "\\" : "/";
    if (style === "line" && out(y - 1) && !out(y + 1))
      return d > 0 ? "/" : "\\";
    return d > 0 ? left : right;
  }
  if (n === 2) {
    if (L && R)
      return "|";
    if (U && D)
      return "-";
    const h = L ? 1 : -1, v = U ? 1 : -1;
    const slope = style === "round" ? h > 0 ? "(" : ")" : v > 0 === h > 0 ? "/" : "\\";
    if (x - h >= 0 && x - h < cols && c.fringe[i - h])
      return v > 0 ? "-" : "_";
    const square = has(x, y + v) && !has(x - h, y + v) && has(x + h, y) && !has(x + h, y - v);
    if (square)
      return v > 0 ? "." : !has(x + h, y + v) ? "'" : h > 0 ? left : right;
    if (has(x + h, y - v))
      return slope;
    if (c.cover[i] < 0.62)
      return v > 0 ? "." : "'";
    return slope;
  }
  if (n === 3) {
    if (!D)
      return ".";
    if (!U)
      return "'";
    const d = !R ? 1 : -1;
    if (style === "round" && (has(x + d, y - 1) || has(x + d, y + 1)))
      return d > 0 ? "(" : ")";
    return has(x + d, y - 1) ? d > 0 ? "/" : "\\" : has(x + d, y + 1) ? d > 0 ? "\\" : "/" : "-";
  }
  return ".";
}
var isMaterial = (v) => isObject(v) && typeof v.prepare === "function" && isObject(v.colors) && typeof v.name === "string";
function makeMaterial(name, colors, period2, prepare2) {
  return { name, colors, period: period2, prepare: prepare2 };
}
var code2 = (ch) => ch.charCodeAt(0);
var SPACE = 32;
function lap(t, period2) {
  if (period2 === void 0 || !Number.isFinite(period2))
    return t;
  const k = t / period2;
  const f = Math.round((k - Math.floor(k)) * 1e9) / 1e9;
  return f >= 1 ? 0 : f * period2;
}
function solid(o) {
  const p = optionsOf3("solid()", o, ["colors", "char", "ramp", "edge"]);
  const colors = colorsOf2("solid.colors", p.colors, "ink", 3);
  if (p.char !== void 0 && p.ramp !== void 0)
    fail2("solid takes a char or a ramp, not both: a char fills it flat, a ramp shades it from the edge in");
  const chars3 = p.ramp !== void 0 ? rampOf("solid.ramp", p.ramp, "\u2588") : charOf("solid.char", p.char, "\u2588");
  const edge = boolOf("solid.edge", p.edge, false);
  return makeMaterial("solid", colors, void 0, (c) => {
    const { cols } = c;
    const md = Math.max(1, c.maxDepth);
    const out = c.list.map((i) => {
      const x = i % cols, y = (i - x) / cols;
      if (edge && c.border[i])
        return SPACE;
      const t = c.char?.(x, y);
      if (t)
        return code2(t);
      return code2(chars3.length === 1 ? chars3 : chars3[Math.min(chars3.length - 1, Math.floor(c.depth[i] / md * chars3.length))]);
    });
    const role = c.list.map((i) => edge && c.border[i] ? 0 : Math.min(2, Math.floor(c.depth[i] / md * 3)));
    const line2 = edge ? c.outline() : null;
    return (_t, pt) => {
      c.list.forEach((i, k) => pt.s.put(i, out[k], pt.color(role[k])));
      line2?.cells.forEach((i, k) => pt.s.put(i, line2.chars[k], pt.color(0)));
    };
  });
}
var isEmission = (v) => isObject(v) && typeof v.emits === "function" && isObject(v.colors) && typeof v.name === "string";
var isPart = (v) => isObject(v) && v.kind === "part" && typeof v.setup === "function";
var MOVES = { bob: 4, sway: 4, swim: 12, drift: 24 };
function moved(q, ox, oy, about) {
  const mx = about === void 0 ? (x) => x : (x) => 2 * about - x;
  const char = q.char;
  return {
    test: (x, y) => q.test(mx(x + ox), y + oy),
    x0: (about === void 0 ? q.x0 : 2 * about - q.x1) - ox,
    x1: (about === void 0 ? q.x1 : 2 * about - q.x0) - ox,
    y0: q.y0 - oy,
    y1: q.y1 - oy,
    ...q.level !== void 0 ? { level: q.level - oy } : {},
    ...q.room ? { room: moved(q.room, ox, oy, about) } : {},
    ...q.cavity ? { cavity: moved(q.cavity, ox, oy, about) } : {},
    ...q.open !== void 0 ? { open: q.open } : {},
    // a cell's character moves with it; turned, the cell's centre mirrors onto the matching cell
    ...char ? { char: (x, y) => char(mx(Math.floor(x + ox) + 0.5), y + oy) } : {}
  };
}
function frameWindow(placed, parts, about, m, cols, rows, all) {
  const whole4 = moved(placed, 0, 0, about);
  const x0 = Math.max(-cols, Math.floor(whole4.x0) - 1), y0 = Math.max(-rows, Math.floor(whole4.y0) - 1);
  const w = Math.max(1, Math.min(2 * cols, Math.ceil(whole4.x1) + 1) - x0), h = Math.max(1, Math.min(2 * rows, Math.ceil(whole4.y1) + 1) - y0);
  const grid3 = new Surface(w, h);
  const draw = all(parts.map((q) => m.prepare(cellsOf(moved(q, x0, y0, about), w, h))));
  const under = { chars: new Uint16Array(w * h), colors: new Uint8Array(w * h) };
  let copied = false;
  let outer = null;
  const paint2 = {
    s: grid3,
    get paper() {
      return outer.paper;
    },
    get mono() {
      return outer.mono;
    },
    color: (i) => outer.color(i),
    get under() {
      if (!copied)
        under.chars.set(grid3.chars), under.colors.set(grid3.colors), copied = true;
      return under;
    }
  };
  return {
    lay(t, pt, dx, dy) {
      const s = pt.s, ox = x0 + dx, oy = y0 + dy;
      const c0 = Math.max(0, -ox), c1 = Math.min(w, cols - ox), r0 = Math.max(0, -oy), r1 = Math.min(h, rows - oy);
      if (c0 >= c1 || r0 >= r1)
        return;
      grid3.clear();
      for (let r = r0; r < r1; r++) {
        const j = (oy + r) * cols + ox;
        grid3.chars.set(s.chars.subarray(j + c0, j + c1), r * w + c0);
        grid3.colors.set(s.colors.subarray(j + c0, j + c1), r * w + c0);
      }
      outer = pt;
      copied = false;
      draw(t, paint2);
      for (let r = r0; r < r1; r++) {
        const j = (oy + r) * cols + ox;
        s.chars.set(grid3.chars.subarray(r * w + c0, r * w + c1), j + c0);
        s.colors.set(grid3.colors.subarray(r * w + c0, r * w + c1), j + c0);
      }
    }
  };
}
function shape(where, what, o) {
  areaOf("shape", where);
  if (isArea(what) && !isMaterial(what))
    fail2("shape takes a material second, not another area: give each area a shape() of its own, or join them with union()");
  if (isEmission(what) && !isMaterial(what))
    fail2(`shape takes a material second, and ${what.name} is an emission: send it out with emit(${what.name}(), { from: area })`);
  if (what !== void 0 && !isMaterial(what) && isObject(what) && o === void 0)
    o = what, what = void 0;
  const m = what ?? where.material?.() ?? solid();
  if (!isMaterial(m))
    fail2(`shape takes a material second, such as water(), glass() or solid(), not ${show2(what)}`);
  const p = optionsOf3("shape()'s options", o, ["move", "amount", "period"]);
  const own = typeof p.move === "function" ? p.move : null;
  const move = own ? "own" : wordOf("shape's move", p.move, ["none", "bob", "sway", "swim", "drift"], "none");
  const amount = p.amount === void 0 ? void 0 : numberOf("shape's amount", p.amount, 1, 0, 320);
  if (move === "none" && (p.amount !== void 0 || p.period !== void 0))
    fail2(`shape's ${p.amount !== void 0 ? "amount" : "period"} is for a move: give it move "bob", "sway", "swim" or "drift", or a function of your own`);
  const period2 = move === "none" ? void 0 : move === "own" ? p.period === void 0 ? Infinity : periodOf2("shape's period", p.period, 4) : periodOf2("shape's period", p.period, MOVES[move]);
  return {
    kind: "part",
    what: m,
    period: period2,
    extent: move === "none" ? where.extent : void 0,
    setup(cols, rows) {
      const placed = where.place(cols, rows);
      const parts = (where.pieces?.length ? where.pieces : [where]).map((a) => a.place(cols, rows));
      const all = (draws) => draws.length === 1 ? draws[0] : (t, pt) => draws.forEach((d) => d(t, pt));
      if (move === "none") {
        const draw = all(parts.map((q) => m.prepare(cellsOf(q, cols, rows))));
        return (t, pt) => draw(lap(t, m.period), pt);
      }
      const f = placed.frame ?? { x0: 0, y0: 0, x1: cols, y1: rows };
      const w = placed.x1 - placed.x0;
      const reach = amount ?? (move === "bob" ? 1 : move === "sway" ? 2 : move === "swim" ? Math.max(0, Math.floor((f.x1 - f.x0 - w) / 2) - 1) : cols);
      const cx = (placed.x0 + placed.x1) / 2;
      const windows = [null, null];
      const windowOf = (turned) => windows[+turned] ??= frameWindow(placed, parts, turned ? cx : void 0, m, cols, rows, all);
      return (t, pt) => {
        let dx = 0, dy = 0, turn = false;
        const mt = lap(t, period2);
        if (own) {
          const r = own(mt);
          if (!Array.isArray(r) || !Number.isFinite(r[0]) || !Number.isFinite(r[1]))
            fail2(`shape's move gave ${show2(r)} at t = ${mt}: a move of your own returns [dx, dy] in cells, or [dx, dy, true] turned round`);
          dx = Math.round(r[0]), dy = Math.round(r[1]), turn = r[2] === true;
        } else {
          const k = mt / period2;
          if (move === "bob")
            dy = Math.round(reach * Math.sin(TAU * k));
          else if (move === "sway")
            dx = Math.round(reach * Math.sin(TAU * k));
          else if (move === "swim") {
            dx = Math.round(reach * Math.sin(TAU * k)) + Math.round((f.x0 + f.x1) / 2 - cx);
            turn = Math.cos(TAU * k) < 0;
          } else
            dx = Math.round(k * reach);
        }
        const win = windowOf(turn), at3 = lap(t, m.period);
        win.lay(at3, pt, dx, dy);
        if (move === "drift" && reach > 0)
          win.lay(at3, pt, dx - reach, dy);
      };
    }
  };
}
function loopOf(periods) {
  if (!periods.length)
    return void 0;
  const gcd3 = (a, b) => b ? gcd3(b, a % b) : a;
  let l = 1;
  for (const p of periods) {
    if (!Number.isFinite(p))
      return void 0;
    const h = Math.round(p * 100);
    if (h <= 0)
      return void 0;
    l = l * h / gcd3(l, h);
    if (l > 6e3)
      return void 0;
  }
  return l / 100;
}
function partsOf(what, parts) {
  if (!Array.isArray(parts) || !parts.length)
    fail2(`${what} takes a list of one or more parts, such as [shape(cup(), glass())]`);
  parts.forEach((part, i) => {
    if (isPart(part))
      return;
    const n = `${what}'s part ${i + 1}`;
    if (typeof part === "function")
      fail2(`${n} is ${show2(part)}, and give what it makes to shape() or emit()`);
    if (isArea(part))
      fail2(`${n} is an area: draw it with shape(area), or shape(area, material)`);
    if (isEmission(part))
      fail2(`${n} is an emission: send it out with emit(${part.name}(), { from: area })`);
    if (isMaterial(part))
      fail2(`${n} is a material: fill an area with it, shape(area, ${part.name}())`);
    fail2(`${n} is not a part: make one with shape(area, material) or emit(emission)`);
  });
  return parts;
}
function colorsFor(parts) {
  const light = [INK2.light], dark = [INK2.dark];
  const seen = /* @__PURE__ */ new Map([[`${INK2.light}${INK2.dark}`, 0]]);
  const slots = parts.map((part) => {
    const { colors } = part.what;
    return colors.dark.map((d, i) => {
      const l = colors.light[i] ?? colors.light[colors.light.length - 1];
      const key = `${l.toLowerCase()}${d.toLowerCase()}`;
      const at3 = seen.get(key);
      if (at3 !== void 0)
        return at3;
      seen.set(key, light.length);
      dark.push(d);
      return light.push(l) - 1;
    });
  });
  if (light.length > 32)
    fail2(`these parts have ${light.length} colours for each page between them, past the 32 a picture can have: use fewer materials, or give some the same colors`);
  return { light, dark, slots };
}
function stage(parts, cols, rows, maps) {
  const draws = parts.map((part) => part.setup(cols, rows));
  const under = { chars: new Uint16Array(cols * rows), colors: new Uint8Array(cols * rows) };
  let copied = false;
  let map = maps(0, false);
  const paint2 = {
    s: null,
    paper: false,
    mono: true,
    color: (i) => map[i < map.length ? i : map.length - 1] ?? NONE,
    get under() {
      if (!copied)
        under.chars.set(paint2.s.chars), under.colors.set(paint2.s.colors), copied = true;
      return under;
    }
  };
  return (t, s) => {
    paint2.s = s;
    paint2.paper = s.paper;
    paint2.mono = s.mono;
    draws.forEach((draw, k) => {
      map = maps(k, s.paper);
      copied = false;
      draw(t, paint2);
    });
  };
}
var SPEC_KEYS = ["name", "note", "category", "cols", "rows", "fps", "ground", "loop", "still", "clock", "options", "clear", "palette", "ink", "cell"];
function picture(parts, spec) {
  partsOf("picture", parts);
  const sp = optionsOf3("picture()'s spec", spec, SPEC_KEYS);
  if (sp.palette !== void 0 || sp.ink !== void 0)
    fail2("picture() makes its palette from its parts' colours: give each material `colors` instead of a palette or an ink");
  if (sp.cell !== void 0 && sp.cell !== 2)
    fail2(`picture() draws for cells twice as tall as wide, so its cell can only be 2, not ${show2(sp.cell)}`);
  if (sp.clear !== void 0 && sp.clear !== true)
    fail2("picture() empties its grid before each frame, so a frame depends only on t: leave clear out");
  const fixed = parts.every((part) => part.extent);
  let size2 = { cols: 64, rows: 24 };
  if (fixed && sp.cols === void 0 && sp.rows === void 0) {
    size2 = { cols: Math.max(1, Math.ceil(Math.max(...parts.map((part) => part.extent.cols)))), rows: Math.max(1, Math.ceil(Math.max(...parts.map((part) => part.extent.rows)))) };
    if (size2.cols > MAX.cols || size2.rows > MAX.rows)
      fail2(`picture's parts reach ${size2.cols} by ${size2.rows} cells, past the ${MAX.cols} by ${MAX.rows} a piece can be: give the picture cols and rows, or make the areas smaller`);
  }
  const s = specOf(sp, "picture", size2);
  const { light, dark, slots } = colorsFor(parts);
  const periods = [...parts.map((part) => part.what.period), ...parts.map((part) => part.period)].filter((v) => v !== void 0);
  const loop = s.loop ?? loopOf(periods);
  const n = light.length;
  const maps = slots.map((sl) => [Uint8Array.from(sl), Uint8Array.from(sl, (k) => n + k)]);
  return piece({ ...s, fps: s.fps ?? (periods.length ? 24 : 0), category: s.category ?? "scenes", palette: { light, dark }, ink: 0, ...loop ? { loop } : {} }, {
    setup: (_o, { cols, rows }) => {
      const draw = stage(parts, cols, rows, (k, paper) => maps[k][paper ? 0 : 1]);
      return (t, grid3) => draw(t, grid3);
    }
  });
}

// node_modules/ascii.rest/dist/kit/shapes3d.js
function shown2(v) {
  if (typeof v === "function")
    return "a function";
  if (typeof v === "number" || v === void 0 || typeof v === "symbol" || typeof v === "bigint")
    return String(v);
  try {
    return JSON.stringify(v) ?? String(v);
  } catch {
    return String(v);
  }
}
function positive2(v, what, def) {
  if (v === void 0 && def !== void 0)
    return def;
  if (typeof v !== "number" || !Number.isFinite(v) || v <= 0)
    fail2(`${what} takes a number above 0, not ${shown2(v)}`);
  return v;
}
function finite2(v, what, def) {
  if (v === void 0)
    return def;
  if (typeof v !== "number" || !Number.isFinite(v))
    fail2(`${what} takes a number, not ${shown2(v)}`);
  return v;
}
function wholeIn(v, what, def, lo, hi) {
  if (v === void 0)
    return def;
  if (!Number.isInteger(v) || v < lo || v > hi)
    fail2(`${what} takes a whole number from ${lo} to ${hi}, not ${shown2(v)}`);
  return v;
}
function vec3(v, what, def) {
  if (v === void 0 && def)
    return [def[0], def[1], def[2]];
  if (!Array.isArray(v) || v.length !== 3 || !v.every((n) => typeof n === "number" && Number.isFinite(n)))
    fail2(`${what} takes [x, y, z], three numbers, not ${shown2(v)}`);
  return [v[0], v[1], v[2]];
}
var TURNS = {
  "upside-down": [Math.PI, 0, 0],
  "on-its-side": [0, 0, Math.PI / 2],
  tipped: [0.45, 0, 0],
  "facing-left": [0, -Math.PI / 2, 0],
  "facing-right": [0, Math.PI / 2, 0],
  "turned-round": [0, Math.PI, 0]
};
var SPINS = { slow: TAU / 12, normal: TAU / 6, fast: TAU / 3 };
var MEANT = {
  colour: ["color", "colors"],
  colours: ["colors", "color"],
  color: ["colors"],
  colors: ["color"],
  colourBy: ["colorBy"],
  colorby: ["colorBy"],
  shadeBy: ["colorBy"],
  position: ["at"],
  pos: ["at"],
  origin: ["at"],
  center: ["at", "center"],
  centre: ["at", "center"],
  rotation: ["rotate", "spin"],
  angle: ["rotate", "tilt", "phase"],
  angles: ["rotate"],
  orientation: ["rotate"],
  speed: ["spin", "period"],
  spins: ["spin"],
  spin: ["camera"],
  tilt: ["camera"],
  distance: ["camera"],
  zoom: ["camera", "scale"],
  fov: ["zoom"],
  pitch: ["tilt"],
  yaw: ["spin"],
  rotate: ["spin"],
  dist: ["distance"],
  size: ["radius", "width"],
  radius: ["size"],
  diameter: ["radius", "size"],
  r: ["radius"],
  thickness: ["tube"],
  tubeRadius: ["tube"],
  width: ["cols"],
  height: ["rows", "depth"],
  columns: ["cols"],
  length: ["height", "depth"],
  pattern: ["texture"],
  textures: ["texture"],
  material: ["texture"],
  edge: ["edges"],
  outline: ["edges"],
  wireframe: ["edges"],
  background: ["ground"],
  bg: ["ground"],
  lights: ["light"],
  lighting: ["light"],
  sun: ["light"],
  chars: ["ramp", "char"],
  characters: ["ramp", "char"],
  charset: ["ramp"],
  character: ["char"],
  glyph: ["char"],
  duration: ["period"],
  seconds: ["period"],
  loop: ["closed", "period"],
  close: ["closed"],
  shade: ["shades"],
  steps: ["shades", "segments"],
  resolution: ["segments"],
  detail: ["segments"],
  n: ["count"],
  number: ["count"],
  brightness: ["glow"],
  inverted: ["invert"],
  flip: ["invert"],
  fitted: ["fit"]
};
function known(o, keys, who) {
  for (const k of Object.keys(o)) {
    if (keys.includes(k))
      continue;
    const meant = Object.hasOwn(MEANT, k) ? MEANT[k].find((n) => keys.includes(n)) : void 0;
    const hint = meant === "camera" ? ` (did you mean camera: { ${k} }?)` : meant ? ` (did you mean ${meant}?)` : "";
    fail2(`${who} has no option ${JSON.stringify(k)}${hint}: it takes ${and2(keys)}`);
  }
}
function wrapped(x, y, n, seed) {
  const xi = Math.floor(x), yi = Math.floor(y), fx = x - xi, fy = y - yi;
  const a = (xi % n + n) % n, b = (a + 1) % n;
  const u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy);
  const p = hash(a, yi, seed), q = hash(b, yi, seed), r = hash(a, yi + 1, seed), s = hash(b, yi + 1, seed);
  return p + (q - p) * u + (r - p) * v + (p - q - r + s) * u * v;
}
var textures = {
  /**
   * Soft bands of light and shade along v, `count` of them (6), rippling a little round u, and one oval storm, ringed
   * in shade, just south of the middle at u 0.25: a gas giant's clouds on a sphere, its storm showing its turn.
   */
  bands(count = 6) {
    const n = wholeIn(count, "textures.bands", 6, 1, 64);
    return (u, v) => {
      const du = (fract(u - 0.25 + 0.5) - 0.5) / 0.08, dv = (v - 0.5 + 0.5 / n) / 0.05, d = du * du + dv * dv;
      if (d < 1)
        return d > 0.45 ? 0.35 : 1;
      return 0.65 + 0.35 * Math.cos(TAU * n * v + 0.3 * Math.sin(TAU * 3 * u));
    };
  },
  /** Stripes round u, `count` of them (8), every other one in shade: a beach ball's panels on a sphere. */
  stripes(count = 8) {
    const n = wholeIn(count, "textures.stripes", 8, 1, 64);
    return (u) => Math.floor(u * n) & 1 ? 0.45 : 1;
  },
  /** Squares, `across` round u (8) and `along` along v (half as many, so they are about square on a sphere), every other one in shade. */
  checker(across2 = 8, along) {
    const n = wholeIn(across2, "textures.checker", 8, 1, 64), m = wholeIn(along, "textures.checker's along", Math.max(1, Math.round(n / 2)), 1, 64);
    return (u, v) => Math.floor(u * n) + Math.floor(v * m) & 1 ? 0.45 : 1;
  },
  /** Thin lines in shade, `across` round u (12) and `along` along v (half as many): a globe's meridians and parallels. */
  grid(across2 = 12, along) {
    const n = wholeIn(across2, "textures.grid", 12, 1, 64), m = wholeIn(along, "textures.grid's along", Math.max(1, Math.round(n / 2)), 1, 64);
    return (u, v) => {
      const a = fract(u * n), b = fract(v * m);
      return Math.min(a, 1 - a) < 0.1 || Math.min(b, 1 - b) < 0.1 ? 0.3 : 1;
    };
  },
  /** Seeded patches of light on a shaded ground, about `count` across u (5): continents on a planet, maria on a moon. `seed` (1) picks the coastlines. */
  spots(count = 5, seed = 1) {
    const n = wholeIn(count, "textures.spots", 5, 1, 64), m = Math.max(1, Math.round(n / 2));
    const s = wholeIn(seed, "textures.spots' seed", 1, -(2 ** 31), 2 ** 31 - 1);
    const h = (u, v) => (4 * wrapped(u * n, v * m, n, s) + 2 * wrapped(u * n * 2, v * m * 2, n * 2, s + 101) + wrapped(u * n * 4, v * m * 4, n * 4, s + 202)) / 7;
    const heights = [];
    for (let j = 0; j < 32; j++)
      for (let i = 0; i < 64; i++)
        heights.push(h((i + 0.5) / 64, (j + 0.5) / 32));
    heights.sort((a, b) => a - b);
    const coast = heights[Math.floor(heights.length * 0.6)];
    return (u, v) => 0.45 + 0.55 * smoothstep(coast - 0.015, coast + 0.015, h(u, v));
  }
};
var TEXTURES = Object.keys(textures);
var KINDS = ["torus", "sphere", "cube", "cylinder", "cone", "plane", "points", "lines", "mesh", "parametric", "group"];
var BODIES = /* @__PURE__ */ new WeakMap();
var ORBITS = /* @__PURE__ */ new WeakMap();
var ORIGIN = [0, 0, 0];
function body(s, who) {
  const b = s !== null && typeof s === "object" ? BODIES.get(s) : void 0;
  if (!b)
    fail2(`${who} takes shapes made by ${and2(KINDS.map((k) => `${k}()`))}, not ${shown2(s)}`);
  return b;
}
var DONUT = ".,-~:;=!*#$@";
var AMBIENT = { none: 0, soft: 0.15, bright: 0.35 };
var TILTS = { level: 0, above: 0.45, high: 0.9, below: -0.45 };
var NEAR = 0.05;
var COLOR_BY = ["shape", "depth", "light"];
var SCENE_KEYS = ["camera", "light", "ambient", "ramp", "invert", "colorBy", "colors", "shades", "fit", "period"];
var SPEC_KEYS2 = ["name", "note", "category", "cols", "rows", "fps", "palette", "ink", "ground", "cell", "loop", "still", "clock", "options", "clear"];
var CAMERA_KEYS = ["distance", "zoom", "tilt", "spin"];
function settings(o, who) {
  if (o === null || typeof o !== "object")
    fail2(`${who} takes its options as an object, such as { light: [0, 1, -1] }, not ${shown2(o)}`);
  const cam = o.camera ?? {};
  if (cam === null || typeof cam !== "object" || Array.isArray(cam))
    fail2(`camera takes { distance, zoom, tilt, spin }, not ${shown2(o.camera)}`);
  known(cam, CAMERA_KEYS, "camera");
  const light = vec3(o.light, "light", [-0.4, 1, -1]);
  const len = Math.hypot(...light);
  if (!len)
    fail2("light takes a direction towards the light, not [0, 0, 0]: [-0.4, 1, -1] is from the upper left");
  const ambient = typeof o.ambient === "string" ? Object.hasOwn(AMBIENT, o.ambient) ? AMBIENT[o.ambient] : fail2(`ambient takes "none", "soft" or "bright", or a number from 0 to 1, not ${shown2(o.ambient)}${suggest(o.ambient, Object.keys(AMBIENT))}`) : finite2(o.ambient, "ambient", 0);
  if (ambient < 0 || ambient > 1)
    fail2(`ambient takes a number from 0 to 1, not ${ambient}`);
  const tilt = typeof cam.tilt === "string" ? Object.hasOwn(TILTS, cam.tilt) ? TILTS[cam.tilt] : fail2(`camera's tilt takes "level", "above", "high" or "below", or radians, not ${shown2(cam.tilt)}${suggest(cam.tilt, Object.keys(TILTS))}`) : finite2(cam.tilt, "camera's tilt", 0);
  const chars3 = o.ramp === void 0 ? DONUT : ramp(o.ramp);
  if (o.invert !== void 0 && o.invert !== true && o.invert !== false && o.invert !== "auto")
    fail2(`invert takes true, false or "auto", not ${shown2(o.invert)}`);
  if (o.colorBy !== void 0 && !COLOR_BY.includes(o.colorBy))
    fail2(`colorBy takes ${and2(COLOR_BY.map((c) => `"${c}"`))}, not ${shown2(o.colorBy)}`);
  const shades = o.shades ?? 4;
  if (!Number.isInteger(shades) || shades < 1 || shades > 16)
    fail2(`shades takes a whole number from 1 to 16, not ${shown2(o.shades)}`);
  const colors = o.colors === void 0 ? void 0 : colorsOf(o.colors, "colors");
  if (colors !== void 0)
    spread(colors, shades);
  if (o.fit !== void 0 && typeof o.fit !== "boolean")
    fail2(`fit takes true or false, not ${shown2(o.fit)}`);
  return {
    distance: positive2(cam.distance, "camera's distance", 6),
    zoom: cam.zoom === void 0 ? void 0 : positive2(cam.zoom, "camera's zoom"),
    tilt,
    spin: finite2(cam.spin, "camera's spin", 0),
    light: [light[0] / len, light[1] / len, light[2] / len],
    ambient,
    chars: Uint16Array.from({ length: chars3.length }, (_, i) => chars3.charCodeAt(i)),
    invert: o.invert ?? "auto",
    colorBy: o.colorBy ?? "shape",
    colors,
    shades,
    fit: o.fit ?? true,
    period: o.period === void 0 ? void 0 : positive2(o.period, "period")
  };
}
function luminance(c) {
  const [r, g, b] = rgb(c).map((v) => {
    const k = v / 255;
    return k <= 0.03928 ? k / 12.92 : ((k + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
var PAGE = { light: "#ffffff", dark: "#0d1117" };
function legible(c, paper) {
  const page = luminance(paper ? PAGE.light : PAGE.dark);
  const contrast = (h) => {
    const l = luminance(h);
    return (Math.max(l, page) + 0.05) / (Math.min(l, page) + 0.05);
  };
  if (contrast(c) >= 3)
    return c;
  const to = paper ? "#000000" : "#ffffff";
  let lo = 0, hi = 1;
  for (let i = 0; i < 16; i++) {
    const k = (lo + hi) / 2;
    if (contrast(mix(c, to, k)) >= 3)
      hi = k;
    else
      lo = k;
  }
  return mix(c, to, hi);
}
function shadesOf(c, by, n, paper) {
  const full = legible(c, paper);
  return Array.from({ length: n }, (_, k) => {
    const f = n > 1 ? k / (n - 1) : 1;
    if (by !== "light" || paper)
      return mix("#000000", full, 0.45 + 0.55 * f);
    return f <= 2 / 3 ? mix("#000000", full, 0.45 + 0.825 * f) : mix(full, "#ffffff", (f - 2 / 3) * 1.5);
  });
}
function listAt(shapes2, t, who) {
  const list2 = typeof shapes2 === "function" ? shapes2(t) : shapes2;
  if (!Array.isArray(list2))
    fail2(`${who} takes a list of shapes, such as [torus()], ${typeof shapes2 === "function" ? "and its function gave" : "not"} ${shown2(list2)}`);
  return list2;
}
var whole3 = (x) => x >= 1 - 1e-9 && Math.abs(x - Math.round(x)) < 1e-6 * Math.max(1, x);
var turns = (b) => typeof b.rotate === "function" || b.spin.some((w) => w !== 0);
var moves = (b) => typeof b.at === "function" || b.timed || turns(b) || !!b.children?.some(moves);
var leaves = (bodies) => bodies.flatMap((b) => b.children ? leaves(b.children) : [b]);
var lined = (b) => !!b.wire || b.edges && !!b.mesh && !!b.mesh(6, 0).edges || !!b.children?.some(lined);
function rate(w, period2) {
  if (!w || period2 === void 0)
    return w;
  return Math.sign(w) * Math.max(1, Math.round(Math.abs(w) * period2 / TAU)) * TAU / period2;
}
function orbits(bodies, period2) {
  if (period2 === void 0)
    return;
  for (const b of bodies) {
    const p = typeof b.at === "function" ? ORBITS.get(b.at)?.period : void 0;
    if (p !== void 0 && !whole3(period2 / p))
      fail2(`an orbit going round every ${p} seconds doesn't go round a whole number of times in the scene's period of ${period2}: make the period a multiple of ${p}`);
    if (b.children)
      orbits(b.children, period2);
  }
}
function speed2(b, period2) {
  const p = typeof b.at === "function" ? ORBITS.get(b.at)?.period : void 0;
  let inner = 0;
  for (const c of b.children ?? [])
    inner = Math.max(inner, speed2(c, period2));
  return b.spin.reduce((sum, w) => sum + Math.abs(rate(w, period2)), 0) + (p ? TAU / p : 0) + inner;
}
var into = (t, loop) => loop === void 0 ? t : (t % loop + loop) % loop;
function rotation(m, ax, ay, az) {
  const ca = Math.cos(ax), sa = Math.sin(ax), cb = Math.cos(ay), sb = Math.sin(ay), cc = Math.cos(az), sc = Math.sin(az);
  m[0] = cc * cb;
  m[1] = cc * sb * sa - sc * ca;
  m[2] = cc * sb * ca + sc * sa;
  m[3] = sc * cb;
  m[4] = sc * sb * sa + cc * ca;
  m[5] = sc * sb * ca - cc * sa;
  m[6] = -sb;
  m[7] = cb * sa;
  m[8] = cb * ca;
}
function times(a, b, c) {
  for (let i = 0; i < 9; i += 3)
    for (let j = 0; j < 3; j++)
      a[i + j] = b[i] * c[j] + b[i + 1] * c[3 + j] + b[i + 2] * c[6 + j];
}
var YAW = new Float64Array(9);
var TILT = new Float64Array(9);
var OWN = new Float64Array(9);
var IDENTITY = Float64Array.of(1, 0, 0, 0, 1, 0, 0, 0, 1);
var ZERO = new Float64Array(3);
function camera(c, tilt, yaw) {
  rotation(YAW, 0, yaw, 0);
  rotation(TILT, -tilt, 0, 0);
  times(c, TILT, YAW);
}
function cameraAt(c, set, t, loop) {
  camera(c, set.tilt, rate(set.spin, set.period) * into(t, loop));
}
function pose(m, b, t, period2, loop, c) {
  let rot = typeof b.rotate === "function" ? b.rotate(t) : b.rotate;
  if (!Array.isArray(rot))
    rot = ORIGIN;
  const T = into(t, loop);
  rotation(OWN, rot[0] + rate(b.spin[0], period2) * T, rot[1] + rate(b.spin[1], period2) * T, rot[2] + rate(b.spin[2], period2) * T);
  times(m, c, OWN);
}
function corners(b, t, period2, loop) {
  if (b.mesh)
    return b.mesh(6, t).pos;
  if (b.cloud) {
    const dots = b.cloud.dots;
    if (typeof dots !== "function")
      return dots;
    const list2 = dots(t);
    return Float32Array.from(Array.isArray(list2) ? list2.flat() : []);
  }
  if (b.wire) {
    const paths = b.wire.paths;
    if (typeof paths !== "function") {
      const out2 = new Float32Array(paths.reduce((n, p) => n + p.length, 0));
      paths.reduce((at3, p) => (out2.set(p, at3), at3 + p.length), 0);
      return out2;
    }
    return Float32Array.from(paths(t).flatMap((p) => Array.isArray(p) ? p.filter(Array.isArray).flat() : []));
  }
  const out = [], m = new Float64Array(9);
  for (const c of b.children ?? []) {
    const at3 = typeof c.at === "function" ? c.at(t) : c.at;
    if (!Array.isArray(at3))
      continue;
    pose(m, c, t, period2, loop, IDENTITY);
    const pts = corners(c, t, period2, loop), k = c.scale;
    for (let i = 0; i < pts.length; i += 3) {
      const x = pts[i] * k, y = pts[i + 1] * k, w = pts[i + 2] * k;
      out.push(m[0] * x + m[1] * y + m[2] * w + at3[0], m[3] * x + m[4] * y + m[5] * w + at3[1], m[6] * x + m[7] * y + m[8] * w + at3[2]);
    }
  }
  return Float32Array.from(out);
}
function side(x, d, r) {
  const h = Math.hypot(x, d);
  if (d <= 0 || r >= h)
    return Infinity;
  const c = Math.atan2(x, d), a = Math.asin(r / h);
  if (c + a >= Math.PI / 2 || c - a <= -Math.PI / 2)
    return Infinity;
  return Math.max(Math.tan(c + a), -Math.tan(c - a));
}
function measure(shapes2, set, cols, rows, aspect, loop) {
  const D = set.distance;
  const fn = typeof shapes2 === "function";
  const span2 = loop ?? 30;
  const c = new Float64Array(9), m = new Float64Array(9);
  const around2 = set.spin !== 0 && loop !== void 0;
  const sides = set.spin !== 0 && loop === void 0 ? 72 : 1;
  let ex = 0, ey = 0, zmin = Infinity, zmax = -Infinity;
  const seen = /* @__PURE__ */ new Set();
  let fastest = 0, lines = false;
  for (const s of listAt(shapes2, 0, "scene()")) {
    const b = body(s, "a scene");
    fastest = Math.max(fastest, speed2(b, set.period));
    lines ||= lined(b);
  }
  fastest += Math.abs(rate(set.spin, set.period));
  const count = Math.min(2e3, Math.max(240, Math.ceil(span2 * fastest / 0.05)));
  const ball = loop === void 0 || span2 * fastest / count > 0.05;
  const many = /* @__PURE__ */ new WeakMap();
  const heavy = (b) => {
    let h = many.get(b);
    if (h === void 0)
      many.set(b, h = corners(b, 0, set.period, loop).length / 3 * count > 4e6);
    return h;
  };
  for (let n = 0; n < count; n++) {
    const t = n * span2 / count;
    let moving = fn || around2;
    for (const s of listAt(shapes2, t, "scene()")) {
      const b = body(s, "a scene");
      if (moves(b) || around2)
        moving = true;
      else if (seen.has(b))
        continue;
      seen.add(b);
      const p = typeof b.at === "function" ? b.at(t) : b.at, k = b.scale;
      if (!Array.isArray(p) || !Number.isFinite(p[0] + p[1] + p[2]))
        continue;
      if (ball && (turns(b) || sides > 1 || b.children !== null && moves(b)) || heavy(b)) {
        const r = b.reach(t) * k;
        for (let i = 0; i < sides; i++) {
          if (sides > 1)
            camera(c, set.tilt, TAU * i / sides);
          else
            cameraAt(c, set, t, loop);
          const px2 = c[0] * p[0] + c[1] * p[1] + c[2] * p[2], py2 = c[3] * p[0] + c[4] * p[1] + c[5] * p[2], pz2 = c[6] * p[0] + c[7] * p[1] + c[8] * p[2];
          zmin = Math.min(zmin, pz2 - r);
          zmax = Math.max(zmax, pz2 + r);
          ex = Math.max(ex, side(px2, pz2 + D, r));
          ey = Math.max(ey, side(py2, pz2 + D, r));
        }
        continue;
      }
      cameraAt(c, set, t, loop);
      pose(m, b, t, set.period, loop, c);
      const px = c[0] * p[0] + c[1] * p[1] + c[2] * p[2], py = c[3] * p[0] + c[4] * p[1] + c[5] * p[2], pz = c[6] * p[0] + c[7] * p[1] + c[8] * p[2];
      const pts = corners(b, t, set.period, loop);
      for (let i = 0; i < pts.length; i += 3) {
        const x = pts[i] * k, y = pts[i + 1] * k, w = pts[i + 2] * k;
        const X = m[0] * x + m[1] * y + m[2] * w + px, Y = m[3] * x + m[4] * y + m[5] * w + py, Z = m[6] * x + m[7] * y + m[8] * w + pz;
        if (!Number.isFinite(X + Y + Z))
          continue;
        const d = Z + D;
        zmin = Math.min(zmin, Z);
        zmax = Math.max(zmax, Z);
        if (d <= NEAR)
          ex = ey = Infinity;
        else
          ex = Math.max(ex, Math.abs(X) / d), ey = Math.max(ey, Math.abs(Y) / d);
      }
    }
    if (!moving)
      break;
  }
  ex *= 1.02;
  ey *= 1.02;
  const pad2 = lines ? 1.5 : 1;
  const fitted = Math.min(ex > 0 ? Math.max(0.5, cols / 2 - pad2) / (D * ex) : Infinity, ey > 0 ? Math.max(0.5, rows / 2 - pad2) * aspect / (D * ey) : Infinity);
  let zoom = set.zoom ?? (set.fit ? fitted : rows * aspect / 8);
  if (!(zoom > 0 && Number.isFinite(zoom)))
    zoom = rows * aspect / 8;
  return { zoom, zmin: Number.isFinite(zmin) ? zmin : -1, zmax: Number.isFinite(zmax) ? zmax : 1 };
}
function loopOf2(shapes2, spin) {
  if (typeof shapes2 === "function")
    return void 0;
  const periods = spin ? [TAU / Math.abs(spin)] : [];
  const add = (b) => {
    if (b.timed || typeof b.rotate === "function")
      return false;
    if (typeof b.at === "function") {
      const p = ORBITS.get(b.at)?.period;
      if (p === void 0)
        return false;
      periods.push(p);
    }
    for (const w of b.spin)
      if (w)
        periods.push(TAU / Math.abs(w));
    return (b.children ?? []).every(add);
  };
  if (!shapes2.every((s) => add(body(s, "a scene"))))
    return void 0;
  if (!periods.length)
    return void 0;
  const top = Math.max(...periods);
  for (let k = 1; k * top <= 60 + 1e-9; k++)
    if (periods.every((p) => whole3(k * top / p)))
      return k * top;
  return void 0;
}
var S = 11;
var TRI = new Int32Array(3);
var CORNERS = new Int32Array(4);
var CUT = new Float64Array(2);
var View = class {
  cols;
  rows;
  aspect;
  set;
  fit;
  // the seconds the scene repeats in, if it does
  loop;
  // a cell's nearness, 1 / depth, of what was drawn in it this frame: 0 for nothing
  z;
  // For the points of one shape as they add up in a cell: the dark left, 1 minus each point's light multiplied in, 1
  // for none; the nearest point's nearness and how near it is in the scene, 0 to 1; and the cells they fell in.
  dark;
  nearest;
  close;
  lit;
  // which shape drew each cell this frame, by the order they were drawn in, and which drew a line there: 0 for none
  who;
  marks;
  // S numbers a corner: on screen x, y and 1 / depth; turned x, y, z; turned normal; u, v
  buf = new Float32Array(S * 1024);
  // the camera's turn this frame
  c = new Float64Array(9);
  // for each level of groups, the turn of what is being drawn as the camera sees it, row by row, and where its centre is
  #turns = [];
  #places = [];
  #steps = /* @__PURE__ */ new Map();
  #palette = null;
  // This frame's surface and time; the ramp turned round or not; columns a unit spans at the middle of the scene; for
  // colours by depth, how near a depth is in the scene. Then the shape being drawn: its number, shades and texture.
  #s = null;
  #t = 0;
  #flip = false;
  #f = 1;
  #zk = 0;
  #id = 0;
  #shade = null;
  #tex;
  // whether the surface being drawn covered any cell's centre, seen or hidden
  #hit = false;
  constructor(cols, rows, aspect, set, fit2, loop) {
    this.cols = cols;
    this.rows = rows;
    this.aspect = aspect;
    this.set = set;
    this.fit = fit2;
    this.loop = loop;
    this.z = new Float32Array(cols * rows);
    this.who = new Uint32Array(cols * rows);
    this.marks = new Uint32Array(cols * rows);
    this.dark = new Float32Array(cols * rows).fill(1);
    this.nearest = new Float32Array(cols * rows);
    this.close = new Float32Array(cols * rows);
    this.lit = new Int32Array(cols * rows);
  }
  // The palette indices of a colour's shades for this frame's page; null when the frame isn't coloured or the shape has
  // no colour, so it takes the ink.
  steps(s, color) {
    const { colors, colorBy, shades } = this.set;
    if (s.mono || !s.palette || !colors && color === void 0)
      return null;
    if (this.#palette !== s.palette) {
      this.#steps.clear();
      this.#palette = s.palette;
    }
    const key = (s.paper ? "p" : "d") + (colors ? "" : color);
    let st = this.#steps.get(key);
    if (!st) {
      const list2 = colors ? fade3(colors, shades, s.paper) : shadesOf(color, colorBy, shades, s.paper);
      st = Uint8Array.from(list2, (h) => s.resolve(h));
      this.#steps.set(key, st);
    }
    return st;
  }
  draw(s, shapes2, t) {
    const set = this.set;
    this.#s = s;
    this.#t = t;
    this.#flip = set.invert === "auto" ? s.paper : set.invert;
    this.#f = this.fit.zoom * set.distance;
    const zspan = this.fit.zmax - this.fit.zmin;
    this.#zk = zspan > 1e-6 ? 1 / zspan : 0;
    this.#id = 0;
    this.z.fill(0);
    this.who.fill(0);
    this.marks.fill(0);
    cameraAt(this.c, set, t, this.loop);
    for (const shape2 of shapes2)
      this.place(body(shape2, "a scene"), this.c, ZERO, 1, 0);
  }
  // Draws a shape where what holds it puts it: M is that one's turn as the camera sees it, P where its centre is and K
  // its size; for a shape in no group, the camera's turn, the middle of the scene and 1. A group draws what is in it.
  place(b, M, P, K, depth) {
    const t = this.#t;
    const at3 = typeof b.at === "function" ? b.at(t) : b.at;
    if (!Array.isArray(at3))
      return;
    while (this.#turns.length <= depth)
      this.#turns.push(new Float64Array(9)), this.#places.push(new Float64Array(3));
    const m = this.#turns[depth], p = this.#places[depth];
    pose(m, b, t, this.set.period, this.loop, M);
    const ax = at3[0] * K, ay = at3[1] * K, az = at3[2] * K;
    p[0] = M[0] * ax + M[1] * ay + M[2] * az + P[0];
    p[1] = M[3] * ax + M[4] * ay + M[5] * az + P[1];
    p[2] = M[6] * ax + M[7] * ay + M[8] * az + P[2];
    const k = K * b.scale;
    if (b.children) {
      for (const c of b.children)
        this.place(c, m, p, k, depth + 1);
      return;
    }
    this.#id++;
    this.#shade = this.steps(this.#s, b.color);
    this.#tex = b.texture;
    if (b.cloud)
      this.cloud(b.cloud, m, p, k);
    else if (b.wire)
      this.wire(b.wire, m, p, k);
    else
      this.surface(b, m, p, k);
  }
  // Points: each lights its cell, a near one more than a far one, and the points in one cell add up, so a cloud is
  // brightest where it is densest. They hide behind surfaces drawn before them but not behind each other.
  cloud({ dots, char, glow }, m, p, k) {
    const { cols, rows, aspect, set, z, who, dark, nearest: nearest2, close, lit } = this;
    const s = this.#s, steps = this.#shade, ns = steps ? steps.length : 0, id = this.#id, zk = this.#zk, zmax = this.fit.zmax;
    const D = set.distance, f = this.#f, cx = cols / 2, cy = rows / 2, chars3 = set.chars, nc = chars3.length;
    const byDepth = set.colorBy === "depth";
    const px = p[0], py = p[1], pz = p[2];
    const pts = typeof dots === "function" ? dots(this.#t) : null;
    const count = pts ? Array.isArray(pts) ? pts.length : 0 : dots.length / 3;
    let n = 0;
    for (let i = 0; i < count; i++) {
      let x, y, w;
      if (pts) {
        const q2 = pts[i];
        if (!q2)
          continue;
        x = q2[0] * k, y = q2[1] * k, w = q2[2] * k;
      } else
        x = dots[i * 3] * k, y = dots[i * 3 + 1] * k, w = dots[i * 3 + 2] * k;
      const X = m[0] * x + m[1] * y + m[2] * w + px, Y = m[3] * x + m[4] * y + m[5] * w + py, Z = m[6] * x + m[7] * y + m[8] * w + pz;
      const d = Z + D;
      if (!(d >= NEAR))
        continue;
      const q = 1 / d;
      const col = Math.floor(cx + f * X * q), row2 = Math.floor(cy - f * Y * q / aspect);
      if (!(col >= 0 && col < cols && row2 >= 0 && row2 < rows))
        continue;
      const cell = row2 * cols + col;
      if (q <= z[cell])
        continue;
      let g = zk ? (zmax - Z) * zk : 1;
      g = g < 0 ? 0 : g > 1 ? 1 : g;
      if (nearest2[cell] === 0)
        lit[n++] = cell;
      dark[cell] *= 1 - glow * (0.5 + 0.5 * g);
      if (q > nearest2[cell])
        nearest2[cell] = q, close[cell] = g;
    }
    for (let j = 0; j < n; j++) {
      const cell = lit[j], v = 1 - dark[cell], g = close[cell];
      z[cell] = nearest2[cell];
      who[cell] = id;
      dark[cell] = 1;
      nearest2[cell] = 0;
      let ci = v * nc | 0;
      if (ci >= nc)
        ci = nc - 1;
      const ch = char || chars3[ci];
      if (ch === 32)
        continue;
      let shade = NONE;
      if (steps) {
        const si = (byDepth ? g : v) * ns | 0;
        shade = steps[si >= ns ? ns - 1 : si];
      }
      s.put(cell, ch, shade);
    }
  }
  // Lines through each path's points, hidden behind other shapes' nearer surfaces. A point that isn't numbers breaks
  // its path there.
  wire({ paths, closed, char }, m, p, k) {
    const D = this.set.distance, px = p[0], py = p[1], pz = p[2];
    const list2 = typeof paths === "function" ? paths(this.#t) : paths;
    for (const path2 of list2) {
      const fixed = path2 instanceof Float32Array, n = fixed ? path2.length / 3 : Array.isArray(path2) ? path2.length : 0;
      let has = false, whole4 = true, x0 = 0, y0 = 0, d0 = 0, fx = 0, fy = 0, fd = 0;
      for (let i = 0; i < n; i++) {
        let x, y, w;
        if (fixed)
          x = path2[i * 3] * k, y = path2[i * 3 + 1] * k, w = path2[i * 3 + 2] * k;
        else {
          const q = path2[i];
          if (!Array.isArray(q)) {
            has = whole4 = false;
            continue;
          }
          x = q[0] * k, y = q[1] * k, w = q[2] * k;
        }
        const X = m[0] * x + m[1] * y + m[2] * w + px, Y = m[3] * x + m[4] * y + m[5] * w + py, d = m[6] * x + m[7] * y + m[8] * w + pz + D;
        if (!Number.isFinite(X + Y + d)) {
          has = whole4 = false;
          continue;
        }
        if (has)
          this.seg(x0, y0, d0, X, Y, d, char, Infinity, false);
        else if (i === 0)
          fx = X, fy = Y, fd = d;
        x0 = X, y0 = Y, d0 = d, has = true;
      }
      if (closed && whole4 && n > 2)
        this.seg(x0, y0, d0, fx, fy, fd, char, Infinity, false);
    }
  }
  // A surface: its corners turned, placed and seen, then each triangle facing the camera (each, for an open one)
  // filled, cut at the camera's near plane where it reaches behind it; then its edges.
  surface(b, m, p, k) {
    const D = this.set.distance, f = this.#f, px = p[0], py = p[1], pz = p[2];
    const mesh = b.mesh(f * k / Math.max(pz + D, NEAR), this.#t);
    const { pos, nrm, uv, tri, closed } = mesh;
    const nv = pos.length / 3;
    if (this.buf.length < (nv + 4) * S)
      this.buf = new Float32Array((nv + 4) * S);
    const V = this.buf;
    for (let i = 0, a = 0, o = 0; i < nv; i++, a += 3, o += S) {
      const x = pos[a] * k, y = pos[a + 1] * k, w = pos[a + 2] * k;
      const nx = nrm[a], ny = nrm[a + 1], nz = nrm[a + 2];
      V[o + 3] = m[0] * x + m[1] * y + m[2] * w + px;
      V[o + 4] = m[3] * x + m[4] * y + m[5] * w + py;
      V[o + 5] = m[6] * x + m[7] * y + m[8] * w + pz;
      V[o + 6] = m[0] * nx + m[1] * ny + m[2] * nz;
      V[o + 7] = m[3] * nx + m[4] * ny + m[5] * nz;
      V[o + 8] = m[6] * nx + m[7] * ny + m[8] * nz;
      V[o + 9] = uv[i * 2];
      V[o + 10] = uv[i * 2 + 1];
      const d = V[o + 5] + D;
      if (d >= NEAR)
        this.see(V, o, d);
      else
        V[o + 2] = -1;
    }
    const spare = nv * S;
    this.#hit = false;
    for (let j = 0; j < tri.length; j += 3) {
      const A = tri[j] * S, B = tri[j + 1] * S, C = tri[j + 2] * S;
      const ex = V[B + 3] - V[A + 3], ey = V[B + 4] - V[A + 4], ez = V[B + 5] - V[A + 5];
      const fx = V[C + 3] - V[A + 3], fy = V[C + 4] - V[A + 4], fz = V[C + 5] - V[A + 5];
      let gx = ey * fz - ez * fy, gy = ez * fx - ex * fz, gz = ex * fy - ey * fx;
      if (gx * (V[A + 6] + V[B + 6] + V[C + 6]) + gy * (V[A + 7] + V[B + 7] + V[C + 7]) + gz * (V[A + 8] + V[B + 8] + V[C + 8]) < 0)
        gx = -gx, gy = -gy, gz = -gz;
      const away = gx * V[A + 3] + gy * V[A + 4] + gz * (V[A + 5] + D) > 0;
      if (away && closed)
        continue;
      const sign = away ? -1 : 1;
      if (V[A + 2] >= 0 && V[B + 2] >= 0 && V[C + 2] >= 0)
        this.fill(V, A, B, C, sign);
      else
        this.cut(V, A, B, C, spare, sign);
    }
    if (!this.#hit)
      this.speck(b, p, k);
    if (b.edges && mesh.edges)
      this.edges(V, mesh, m, b.reach(this.#t) * k * 0.35);
  }
  // A corner's place on screen from where the camera sees it, at depth d.
  see(V, o, d) {
    const q = 1 / d;
    V[o] = this.cols / 2 + this.#f * V[o + 3] * q;
    V[o + 1] = this.rows / 2 - this.#f * V[o + 4] * q / this.aspect;
    V[o + 2] = q;
  }
  // A triangle reaching behind the camera, cut at the near plane: the part in front, three or four corners, the new
  // ones made in the spare room at `spare`, filled as one or two triangles.
  cut(V, A, B, C, spare, sign) {
    const D = this.set.distance;
    TRI[0] = A;
    TRI[1] = B;
    TRI[2] = C;
    let n = 0;
    for (let i = 0; i < 3; i++) {
      const P = TRI[i], Q = TRI[(i + 1) % 3], dp = V[P + 5] + D, dq = V[Q + 5] + D;
      if (dp >= NEAR)
        CORNERS[n++] = P;
      if (dp >= NEAR !== dq >= NEAR) {
        const k = (NEAR - dp) / (dq - dp);
        for (let j = 3; j < S; j++)
          V[spare + j] = V[P + j] + (V[Q + j] - V[P + j]) * k;
        this.see(V, spare, NEAR);
        CORNERS[n++] = spare;
        spare += S;
      }
    }
    if (n >= 3)
      this.fill(V, CORNERS[0], CORNERS[1], CORNERS[2], sign);
    if (n === 4)
      this.fill(V, CORNERS[0], CORNERS[2], CORNERS[3], sign);
  }
  // Fills a triangle, its corners at A, B and C in the buffer, cell by cell: each cell whose centre it covers and that
  // nothing nearer has taken gets the ramp's character for its light there, and its shade. `sign` is -1 for a triangle
  // seen from its back, lit from there.
  fill(V, A, B, C, sign) {
    const { cols, rows, z, who, set } = this;
    const s = this.#s, id = this.#id, steps = this.#shade, ns = steps ? steps.length : 0, tex = this.#tex, t = this.#t;
    const light = set.light, lx = light[0], ly = light[1], lz = light[2], amb = set.ambient, chars3 = set.chars, nc = chars3.length;
    const flip2 = this.#flip, D = set.distance, zk = this.#zk, zmax = this.fit.zmax, byDepth = set.colorBy === "depth";
    const q0 = V[A + 2], q1 = V[B + 2], q2 = V[C + 2];
    const x0 = V[A], y0 = V[A + 1], x1 = V[B], y1 = V[B + 1], x2 = V[C], y2 = V[C + 1];
    let c0 = Math.ceil((x0 < x1 ? x0 < x2 ? x0 : x2 : x1 < x2 ? x1 : x2) - 0.5);
    let c1 = Math.floor((x0 > x1 ? x0 > x2 ? x0 : x2 : x1 > x2 ? x1 : x2) - 0.5);
    let r0 = Math.ceil((y0 < y1 ? y0 < y2 ? y0 : y2 : y1 < y2 ? y1 : y2) - 0.5);
    let r1 = Math.floor((y0 > y1 ? y0 > y2 ? y0 : y2 : y1 > y2 ? y1 : y2) - 0.5);
    if (c0 < 0)
      c0 = 0;
    if (r0 < 0)
      r0 = 0;
    if (c1 >= cols)
      c1 = cols - 1;
    if (r1 >= rows)
      r1 = rows - 1;
    if (c0 > c1 || r0 > r1)
      return;
    const area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0);
    if (!area)
      return;
    const inv = 1 / area;
    let hit = false;
    for (let r = r0; r <= r1; r++) {
      const sy = r + 0.5;
      for (let cc = c0; cc <= c1; cc++) {
        const sx = cc + 0.5;
        const w0 = ((x1 - sx) * (y2 - sy) - (x2 - sx) * (y1 - sy)) * inv;
        const w1 = ((x2 - sx) * (y0 - sy) - (x0 - sx) * (y2 - sy)) * inv;
        const w2 = 1 - w0 - w1;
        if (w0 < -1e-9 || w1 < -1e-9 || w2 < -1e-9)
          continue;
        hit = true;
        const q = w0 * q0 + w1 * q1 + w2 * q2;
        const i = r * cols + cc;
        if (q <= z[i])
          continue;
        z[i] = q;
        who[i] = id;
        const a0 = w0 * q0 / q, a1 = w1 * q1 / q, a2 = 1 - a0 - a1;
        const nx = a0 * V[A + 6] + a1 * V[B + 6] + a2 * V[C + 6];
        const ny = a0 * V[A + 7] + a1 * V[B + 7] + a2 * V[C + 7];
        const nz = a0 * V[A + 8] + a1 * V[B + 8] + a2 * V[C + 8];
        const len = Math.sqrt(nx * nx + ny * ny + nz * nz);
        let v = len > 0 ? sign * (nx * lx + ny * ly + nz * lz) / len : 0;
        v = (v > 0 ? v : 0) * (1 - amb) + amb;
        if (tex) {
          const g = tex(a0 * V[A + 9] + a1 * V[B + 9] + a2 * V[C + 9], a0 * V[A + 10] + a1 * V[B + 10] + a2 * V[C + 10], t);
          v *= g > 0 ? g < 1 ? g : 1 : 0;
        }
        let ci = v * nc | 0;
        if (ci >= nc)
          ci = nc - 1;
        const ch = chars3[flip2 ? nc - 1 - ci : ci];
        if (ch === 32)
          continue;
        let shade = NONE;
        if (steps) {
          let g = byDepth ? zk ? (zmax - (1 / q - D)) * zk : 1 : v;
          g = g < 0 ? 0 : g;
          const si = g * ns | 0;
          shade = steps[si >= ns ? ns - 1 : si];
        }
        s.put(i, ch, shade);
      }
    }
    if (hit)
      this.#hit = true;
  }
  // A surface too small on screen to cover a cell's centre, a moon far off, still shows, as a point does: the cell its
  // centre falls in, at its front's depth, lit as its side facing the camera is. A larger one that covered none is off
  // the grid, edge on or seen from inside, and draws nothing.
  speck(b, p, k) {
    const { cols, rows, aspect, set, z, who } = this;
    const D = set.distance, f = this.#f, d = p[2] + D;
    if (!(d >= NEAR))
      return;
    const r = b.reach(this.#t) * k;
    if (!(f * r / d < 1.5))
      return;
    const col = Math.floor(cols / 2 + f * p[0] / d), row2 = Math.floor(rows / 2 - f * p[1] / d / aspect);
    if (!(col >= 0 && col < cols && row2 >= 0 && row2 < rows))
      return;
    const i = row2 * cols + col, q = 1 / Math.max(NEAR, d - r);
    if (q <= z[i])
      return;
    z[i] = q;
    who[i] = this.#id;
    const l = set.light, len = Math.hypot(p[0], p[1], d);
    let v = -(p[0] * l[0] + p[1] * l[1] + d * l[2]) / len;
    v = (v > 0 ? v : 0) * (1 - set.ambient) + set.ambient;
    const chars3 = set.chars, nc = chars3.length;
    let ci = v * nc | 0;
    if (ci >= nc)
      ci = nc - 1;
    const ch = chars3[this.#flip ? nc - 1 - ci : ci];
    if (ch === 32)
      return;
    const steps = this.#shade;
    let shade = NONE;
    if (steps) {
      const ns = steps.length;
      let g = set.colorBy === "depth" ? this.#zk ? (this.fit.zmax - p[2]) * this.#zk : 1 : v;
      g = g < 0 ? 0 : g;
      const si = g * ns | 0;
      shade = steps[si >= ns ? ns - 1 : si];
    }
    this.#s.put(i, ch, shade);
  }
  // A surface's edges as lines: a closed one's where a face it joins is towards the camera, the others' all, each
  // hidden where another shape is nearer or its own is more than `slack` nearer.
  edges(V, mesh, m, slack) {
    const edges = mesh.edges, sides = mesh.sides, D = this.set.distance;
    for (let e = 0; e < edges.length; e += 2) {
      const A = edges[e] * S, B = edges[e + 1] * S;
      const X = V[A + 3], Y = V[A + 4], Z = V[A + 5] + D;
      if (mesh.closed) {
        const j = e * 3;
        const a = (m[0] * sides[j] + m[1] * sides[j + 1] + m[2] * sides[j + 2]) * X + (m[3] * sides[j] + m[4] * sides[j + 1] + m[5] * sides[j + 2]) * Y + (m[6] * sides[j] + m[7] * sides[j + 1] + m[8] * sides[j + 2]) * Z;
        const b = (m[0] * sides[j + 3] + m[1] * sides[j + 4] + m[2] * sides[j + 5]) * X + (m[3] * sides[j + 3] + m[4] * sides[j + 4] + m[5] * sides[j + 5]) * Y + (m[6] * sides[j + 3] + m[7] * sides[j + 4] + m[8] * sides[j + 5]) * Z;
        if (!(a < 0 || b < 0))
          continue;
      }
      this.seg(X, Y, Z, V[B + 3], V[B + 4], V[B + 5] + D, 0, slack, mesh.corners);
    }
  }
  // A line between two points as the camera sees them, x, y and depth, cut at the near plane, in the cells along it:
  // `ch`, or by its slope as it looks - | / or \. Where another shape has drawn something nearer it is hidden, and
  // where its own shape has, only when that is more than `slack` nearer. With `corner`, an end that meets another of
  // its shape's lines in another character is a +. It takes its shape's full shade, or its shade by depth.
  seg(x0, y0, d0, x1, y1, d1, ch, slack, corner) {
    if (!(d0 >= NEAR)) {
      if (!(d1 >= NEAR))
        return;
      const k = (NEAR - d0) / (d1 - d0);
      x0 += (x1 - x0) * k, y0 += (y1 - y0) * k, d0 = NEAR;
    } else if (!(d1 >= NEAR)) {
      const k = (NEAR - d1) / (d0 - d1);
      x1 += (x0 - x1) * k, y1 += (y0 - y1) * k, d1 = NEAR;
    }
    const { cols, rows, aspect, z, who, marks } = this, f = this.#f, q0 = 1 / d0, q1 = 1 / d1;
    const ax = cols / 2 + f * x0 * q0, ay = rows / 2 - f * y0 * q0 / aspect;
    const dx = cols / 2 + f * x1 * q1 - ax, dy = rows / 2 - f * y1 * q1 / aspect - ay;
    if (!Number.isFinite(ax + ay + dx + dy))
      return;
    let code3 = ch;
    if (!code3) {
      const w = Math.abs(dx), h = Math.abs(dy) * aspect;
      code3 = h < w * 0.8 ? 45 : h > w * 3 ? 124 : dx * dy < 0 ? 47 : 92;
    }
    CUT[0] = 0;
    CUT[1] = 1;
    span(ax, dx, cols);
    span(ay, dy, rows);
    const k0 = CUT[0], k1 = CUT[1];
    if (!(k0 <= k1))
      return;
    const s = this.#s, id = this.#id, steps = this.#shade, ns = steps ? steps.length : 0, zk = this.#zk, zmax = this.fit.zmax;
    const byDepth = this.set.colorBy === "depth", D = this.set.distance;
    const n = Math.ceil(Math.max(Math.abs(dx), Math.abs(dy)) * (k1 - k0));
    for (let i = 0; i <= n; i++) {
      const k = n ? k0 + (k1 - k0) * i / n : k0;
      const col = Math.floor(ax + dx * k), row2 = Math.floor(ay + dy * k);
      if (col < 0 || col >= cols || row2 < 0 || row2 >= rows)
        continue;
      const cell = row2 * cols + col, q = q0 + (q1 - q0) * k, zc = z[cell];
      if (zc > 0 && (who[cell] === id ? 1 / q - 1 / zc > slack : q < zc))
        continue;
      if (q > zc)
        z[cell] = q;
      who[cell] = id;
      let shade = NONE;
      if (steps) {
        let g = byDepth ? zk ? (zmax - (1 / q - D)) * zk : 1 : 1;
        g = g < 0 ? 0 : g;
        const si = g * ns | 0;
        shade = steps[si >= ns ? ns - 1 : si];
      }
      const end = i === 0 ? k0 === 0 : i === n && k1 === 1, mine = marks[cell] === id, was = s.chars[cell];
      s.put(cell, mine && (was === 43 || corner && end && was !== code3) ? 43 : code3, shade);
      marks[cell] = id;
    }
  }
};
function span(a, d, size2) {
  if (d === 0) {
    if (a < 0 || a >= size2)
      CUT[0] = 1, CUT[1] = 0;
    return;
  }
  const p = -a / d, q = (size2 - a) / d;
  const lo = p < q ? p : q, hi = p < q ? q : p;
  if (lo > CUT[0])
    CUT[0] = lo;
  if (hi < CUT[1])
    CUT[1] = hi;
}
function fade3(colors, shades, paper) {
  const f = spread(colors, shades);
  if (Array.isArray(f))
    return f.map((c) => legible(c, paper));
  return paper ? f.light : f.dark;
}
var usedColors = (bodies) => [...new Set(leaves(bodies).map((b) => b.color).filter((c) => !!c))];
function colorsOf3(bodies, set, paper) {
  if (set.colors)
    return [...fade3(set.colors, set.shades, paper)];
  return usedColors(bodies).flatMap((c) => shadesOf(c, set.colorBy, set.shades, paper));
}
var tally = (bodies, set) => set.colors ? `a fade of ${set.shades} shades` : `${usedColors(bodies).length} colours in ${set.shades} shades each`;
function scene(first, second) {
  const drawable2 = one(first) || Array.isArray(first) || typeof first === "function";
  if (drawable2 && second !== void 0)
    fail2("scene() takes its spec first and its shapes second, such as scene({ cols: 40, rows: 20 }, torus()), or the shapes alone");
  const spec = drawable2 ? {} : first;
  let shapes2 = drawable2 ? first : second;
  const base = specOf(spec, "scene");
  if (spec)
    known(spec, [...SPEC_KEYS2, ...SCENE_KEYS], "scene()");
  const set = settings(spec ?? {}, "scene()");
  if (one(shapes2))
    shapes2 = [shapes2];
  if (typeof shapes2 !== "function" && !Array.isArray(shapes2))
    fail2(`scene() takes a shape, a list of shapes, such as [torus()], or a function of t that gives a list, not ${shown2(shapes2)}`);
  const list2 = shapes2;
  const bodies = listAt(list2, 0, "scene()").map((s) => body(s, "a scene"));
  orbits(bodies, set.period);
  let palette = base.palette, ink = base.ink;
  if (palette === void 0) {
    const light = colorsOf3(bodies, set, true), dark = colorsOf3(bodies, set, false);
    if (light.length) {
      const plain = !set.colors && leaves(bodies).some((b) => b.color === void 0);
      if (plain) {
        light.push(INK2.light);
        ink = dark.push(INK2.dark) - 1;
      }
      if (light.length > 32)
        fail2(`this scene's colours come to ${light.length} a page, ${tally(bodies, set)}${plain ? " and the ink for shapes with none" : ""}, past the 32 a page a piece can have: use fewer colours or fewer shades`);
      palette = { light, dark };
    }
  }
  const moving = typeof list2 === "function" || set.spin !== 0 || bodies.some(moves);
  const repeats = set.period ?? loopOf2(list2, set.spin);
  const loop = base.loop ?? repeats;
  const aspect = base.cell === 1 ? 1 : 2;
  const made = piece({ ...base, category: base.category ?? "shapes", fps: base.fps ?? (moving ? 30 : 0), palette, ink, ...loop !== void 0 ? { loop } : {} }, {
    setup: (_, size2) => {
      const view = new View(size2.cols, size2.rows, aspect, set, fit2, repeats);
      return (t, s) => view.draw(s, listAt(list2, t, "scene()"), t);
    }
  });
  const fit2 = measure(list2, set, base.cols, base.rows, aspect, repeats);
  return made;
}
var one = (v) => v !== null && typeof v === "object" && BODIES.has(v);

// node_modules/ascii.rest/dist/kit/math.js
var G3 = new Float64Array([1, 1, 0, -1, 1, 0, 1, -1, 0, -1, -1, 0, 1, 0, 1, -1, 0, 1, 1, 0, -1, -1, 0, -1, 0, 1, 1, 0, -1, 1, 0, 1, -1, 0, -1, -1]);
var G4 = new Float64Array([
  0,
  1,
  1,
  1,
  0,
  1,
  1,
  -1,
  0,
  1,
  -1,
  1,
  0,
  1,
  -1,
  -1,
  0,
  -1,
  1,
  1,
  0,
  -1,
  1,
  -1,
  0,
  -1,
  -1,
  1,
  0,
  -1,
  -1,
  -1,
  1,
  0,
  1,
  1,
  1,
  0,
  1,
  -1,
  1,
  0,
  -1,
  1,
  1,
  0,
  -1,
  -1,
  -1,
  0,
  1,
  1,
  -1,
  0,
  1,
  -1,
  -1,
  0,
  -1,
  1,
  -1,
  0,
  -1,
  -1,
  1,
  1,
  0,
  1,
  1,
  1,
  0,
  -1,
  1,
  -1,
  0,
  1,
  1,
  -1,
  0,
  -1,
  -1,
  1,
  0,
  1,
  -1,
  1,
  0,
  -1,
  -1,
  -1,
  0,
  1,
  -1,
  -1,
  0,
  -1,
  1,
  1,
  1,
  0,
  1,
  1,
  -1,
  0,
  1,
  -1,
  1,
  0,
  1,
  -1,
  -1,
  0,
  -1,
  1,
  1,
  0,
  -1,
  1,
  -1,
  0,
  -1,
  -1,
  1,
  0,
  -1,
  -1,
  -1,
  0
]);
var F2 = 0.5 * (Math.sqrt(3) - 1);
var H2 = (3 - Math.sqrt(3)) / 6;
var F3 = 1 / 3;
var H3 = 1 / 6;
var F4 = (Math.sqrt(5) - 1) / 4;
var H4 = (5 - Math.sqrt(5)) / 20;
var OFF = Array.from({ length: 16 }, (_, i) => [i * 0.6180339887 % 1 * 97.3, i * 0.7548776662 % 1 * 89.1]);
var B1 = 1.70158;
var B2 = B1 * 1.525;
var B3 = B1 + 1;
var E4 = TAU / 3;
var E5 = TAU / 4.5;
var bounce = (k) => {
  const n = 7.5625, d = 2.75;
  if (k < 1 / d)
    return n * k * k;
  if (k < 2 / d)
    return n * (k -= 1.5 / d) * k + 0.75;
  if (k < 2.5 / d)
    return n * (k -= 2.25 / d) * k + 0.9375;
  return n * (k -= 2.625 / d) * k + 0.984375;
};
var curves = {
  linear: (k) => k,
  inQuad: (k) => k * k,
  outQuad: (k) => 1 - (1 - k) * (1 - k),
  inOutQuad: (k) => k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2,
  inCubic: (k) => k ** 3,
  outCubic: (k) => 1 - (1 - k) ** 3,
  inOutCubic: (k) => k < 0.5 ? 4 * k ** 3 : 1 - (-2 * k + 2) ** 3 / 2,
  inQuart: (k) => k ** 4,
  outQuart: (k) => 1 - (1 - k) ** 4,
  inOutQuart: (k) => k < 0.5 ? 8 * k ** 4 : 1 - (-2 * k + 2) ** 4 / 2,
  inSine: (k) => 1 - Math.cos(k * Math.PI / 2),
  outSine: (k) => Math.sin(k * Math.PI / 2),
  inOutSine: (k) => -(Math.cos(Math.PI * k) - 1) / 2,
  inExpo: (k) => 2 ** (10 * k - 10),
  outExpo: (k) => 1 - 2 ** (-10 * k),
  inOutExpo: (k) => k < 0.5 ? 2 ** (20 * k - 10) / 2 : (2 - 2 ** (-20 * k + 10)) / 2,
  inCirc: (k) => 1 - Math.sqrt(1 - k * k),
  outCirc: (k) => Math.sqrt(1 - (k - 1) ** 2),
  inOutCirc: (k) => k < 0.5 ? (1 - Math.sqrt(1 - (2 * k) ** 2)) / 2 : (Math.sqrt(1 - (-2 * k + 2) ** 2) + 1) / 2,
  inBack: (k) => B3 * k ** 3 - B1 * k * k,
  outBack: (k) => 1 + B3 * (k - 1) ** 3 + B1 * (k - 1) ** 2,
  inOutBack: (k) => k < 0.5 ? (2 * k) ** 2 * ((B2 + 1) * 2 * k - B2) / 2 : ((2 * k - 2) ** 2 * ((B2 + 1) * (k * 2 - 2) + B2) + 2) / 2,
  inElastic: (k) => -(2 ** (10 * k - 10)) * Math.sin((k * 10 - 10.75) * E4),
  outElastic: (k) => 2 ** (-10 * k) * Math.sin((k * 10 - 0.75) * E4) + 1,
  inOutElastic: (k) => k < 0.5 ? -(2 ** (20 * k - 10) * Math.sin((20 * k - 11.125) * E5)) / 2 : 2 ** (-20 * k + 10) * Math.sin((20 * k - 11.125) * E5) / 2 + 1,
  inBounce: (k) => 1 - bounce(1 - k),
  outBounce: bounce,
  inOutBounce: (k) => k < 0.5 ? (1 - bounce(1 - 2 * k)) / 2 : (1 + bounce(2 * k - 1)) / 2
};
var ease = Object.freeze(Object.fromEntries(Object.entries(curves).map(([name, f]) => [name, (k) => !(k > 0) ? 0 : k >= 1 ? 1 : f(k)])));

// node_modules/ascii.rest/dist/kit/recipes/checks.js
var easings = Object.freeze({
  steady: "linear",
  smooth: "inOutSine",
  snappy: "outBack",
  springy: "outElastic",
  bouncy: "outBounce"
});
var HEADINGS = {
  left: [-1, 0],
  right: [1, 0],
  up: [0, -1],
  down: [0, 1],
  "up-left": [-Math.SQRT1_2, -Math.SQRT1_2],
  "up-right": [Math.SQRT1_2, -Math.SQRT1_2],
  "down-left": [-Math.SQRT1_2, Math.SQRT1_2],
  "down-right": [Math.SQRT1_2, Math.SQRT1_2]
};
function show3(v) {
  if (typeof v === "function")
    return v.name ? `${v.name}, a function: call it, ${v.name}()` : "a function";
  if (typeof v === "string")
    return JSON.stringify(v);
  if (Array.isArray(v))
    return `[${v.map(show3).join(", ")}]`;
  if (v !== null && typeof v === "object") {
    try {
      return JSON.stringify(v) ?? String(v);
    } catch {
      return "an object";
    }
  }
  return String(v);
}
var or4 = (words2) => words2.length > 1 ? `${words2.slice(0, -1).join(", ")} or ${words2.at(-1)}` : words2[0] ?? "";
var quoted = (words2) => or4(words2.map((w) => JSON.stringify(w)));
var and3 = (words2) => words2.length > 1 ? `${words2.slice(0, -1).join(", ")} and ${words2.at(-1)}` : words2[0] ?? "";
var isObject2 = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
function optionsOf4(what, o, keys) {
  if (o === void 0)
    return {};
  if (!isObject2(o))
    fail2(`${what} takes its options as an object, such as { ${keys[0]}: ... }, not ${show3(o)}`);
  for (const [k, v] of Object.entries(o))
    if (v !== void 0 && !keys.includes(k))
      fail2(`${what} has no option ${JSON.stringify(k)}${suggest(k, keys)}: it takes ${and3(keys)}`);
  return o;
}
function numberOf2(what, v, def, lo = -Infinity, hi = Infinity) {
  if (v === void 0)
    return def;
  if (typeof v !== "number" || !Number.isFinite(v) || v < lo || v > hi)
    fail2(`${what} takes a number${hi === Infinity ? lo === -Infinity ? "" : ` of ${lo} or more` : ` from ${lo} to ${hi}`}, not ${show3(v)}`);
  return v;
}
function wholeOf(what, v, def, lo, hi = Infinity) {
  if (v === void 0)
    return def;
  if (!Number.isInteger(v) || v < lo || v > hi)
    fail2(`${what} takes a whole number ${hi === Infinity ? `of ${lo} or more` : `from ${lo} to ${hi}`}, not ${show3(v)}`);
  return v;
}
function wordOf2(what, v, words2, def) {
  if (v === void 0)
    return def;
  if (!words2.includes(v))
    fail2(`${what} takes ${quoted(words2)}, not ${show3(v)}${suggest(v, words2)}`);
  return v;
}
function textOf2(what, v, o = {}) {
  if (v === void 0)
    return void 0;
  if (typeof v !== "string")
    fail2(`${what} takes words, not ${show3(v)}`);
  const text2 = v.replace(/\r\n?/g, "\n");
  for (const ch of text2) {
    if (ch === "\n" && o.lines)
      continue;
    const c = ch.charCodeAt(0);
    if (ch.length > 1 || c < 32 || c >= 127 && c <= 159 || c >= 55296 && c <= 57343)
      fail2(`${what} takes words a cell can hold, one character each from the Basic Multilingual Plane${o.lines ? "" : " on one line"}: not ${JSON.stringify(ch)} in ${show3(v.length > 40 ? v.slice(0, 40) + "..." : v)}`);
  }
  return text2;
}
function boolOf2(what, v, def) {
  if (v === void 0)
    return def;
  if (typeof v !== "boolean")
    fail2(`${what} takes true or false, not ${show3(v)}`);
  return v;
}
var LOOPS3 = [0.25, 0.5, 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60];
function loopOf3(seconds, up = false) {
  if (up)
    return LOOPS3.find((l) => l >= seconds - 1e-9) ?? 60;
  let best = LOOPS3[0];
  for (const l of LOOPS3)
    if (Math.abs(Math.log(l / seconds)) < Math.abs(Math.log(best / seconds)))
      best = l;
  return best;
}
function colorOf3(what, v) {
  return v === void 0 ? void 0 : colorOf(v, what);
}
var isArea2 = (v) => isObject2(v) && v.kind === "area" && typeof v.place === "function";
var isPart2 = (v) => isObject2(v) && v.kind === "part" && typeof v.setup === "function";
var isPiece2 = (v) => isObject2(v) && isObject2(v.meta) && typeof v.default === "function";
var isShape3d = (v) => isObject2(v) && typeof v.kind === "string" && v.kind !== "area" && v.kind !== "part" && v.kind !== "mask" && !("meta" in v) && !("src" in v);
var is3d = (v) => isShape3d(v) || Array.isArray(v) && v.length > 0 && v.every(isShape3d);
function titled(p, name, note) {
  if (name === void 0 && note === void 0)
    return p;
  if (name !== void 0 && (typeof name !== "string" || !name.trim()))
    fail2(`a name takes one line of words, such as "hello", not ${show3(name)}`);
  const n = name?.trim() ?? p.meta.name;
  return chained({ ...p, meta: checkMeta({ ...p.meta, name: n, note: (note ?? n).slice(0, 72) }) });
}
var NAMING = ["name", "note"];

// node_modules/ascii.rest/dist/kit/recipes/words.js
var isObject3 = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
var ROOM = { cols: 64, rows: 24 };
function pieceOf(thing, what = "this") {
  if (isObject3(thing) && !isPiece2(thing) && isPiece2(thing.default))
    thing = thing.default;
  if (typeof thing === "function")
    fail2(`${what} takes a thing to show, not ${show3(thing)}`);
  if (typeof thing === "string")
    return chained(asPiece(thing, thing.split("\n").map((l) => l.trim()).find(Boolean)?.slice(0, 40) ?? "text"));
  if (thing instanceof Surface || isPiece2(thing))
    return chained(asPiece(thing));
  if (isPart2(thing))
    return picture([thing]);
  if (Array.isArray(thing) && thing.length && thing.every(isPart2))
    return picture(thing);
  if (isArea2(thing)) {
    const box2 = thing.place(ROOM.cols, ROOM.rows);
    const x0 = Math.max(0, Math.floor(box2.x0) - 1), y0 = Math.max(0, Math.floor(box2.y0) - 1);
    const x1 = Math.min(ROOM.cols, Math.ceil(box2.x1) + 1), y1 = Math.min(ROOM.rows, Math.ceil(box2.y1) + 1);
    const drawn = picture([shape(thing)], { name: "shape", ...ROOM });
    return x1 > x0 && y1 > y0 ? crop(drawn, { x: x0, y: y0, cols: x1 - x0, rows: y1 - y0 }) : drawn;
  }
  if (is3d(thing))
    return scene({ name: "shapes" }, thing);
  return fail2(`${what} takes a piece, text, a grid, a 3D shape such as torus(), an area such as heart(), or parts, not ${show3(thing)}`);
}

// node_modules/ascii.rest/dist/kit/draw.js
function grid2(s, what) {
  const g = s;
  if (!g || typeof g !== "object" || !(g.chars instanceof Uint16Array) || !(g.colors instanceof Uint8Array) || typeof g.put !== "function")
    fail2(`${what}() takes the Surface to draw on first: the grid a drawing is given, (t, s) => { ${what}(s, ...) }`);
  return g;
}
function paint(s, color) {
  if (color === void 0 || color === null)
    return NONE;
  if (s.palette)
    return s.palette.index(color, s.paper);
  if (typeof color === "number" ? !(Number.isInteger(color) && color >= 0) : !isHex(color))
    fail2(`a colour takes #rrggbb or an index into the palette, not ${show4(color)}`);
  return NONE;
}
function brush(ch, what) {
  if (ch === "")
    return EMPTY;
  if (typeof ch !== "string" || [...ch].length !== 1)
    fail2(`${what} takes one character, or "" to clear, not ${show4(ch)}`);
  return code(ch);
}
var finite3 = (...v) => v.every((n) => typeof n === "number" && Number.isFinite(n));
function show4(v, depth = 0) {
  if (typeof v === "string")
    return JSON.stringify(v.length > 40 ? v.slice(0, 40) + "\u2026" : v);
  if (typeof v === "function")
    return "a function";
  if (!v || typeof v !== "object")
    return String(v);
  if (depth > 1)
    return Array.isArray(v) ? "[...]" : "{...}";
  const more = (n) => n > 6 ? ", ..." : "";
  if (Array.isArray(v))
    return `[${Array.from(v.slice(0, 6), (x) => show4(x, depth + 1)).join(", ")}${more(v.length)}]`;
  const entries = Object.entries(v);
  return entries.length ? `{ ${entries.slice(0, 6).map(([k, x]) => `${k}: ${show4(x, depth + 1)}`).join(", ")}${more(entries.length)} }` : "{}";
}
var or5 = (words2) => and2(words2.map((w) => `"${w}"`)).replace(/ and ("[^"]*")$/, " or $1");
function opts(o, what) {
  if (o === void 0)
    return {};
  if (o === null || typeof o !== "object")
    fail2(`${what}() takes its options as an object, such as { color: 1 }`);
  return o;
}
function yes(v, name, fallback) {
  if (v === void 0)
    return fallback;
  if (typeof v !== "boolean")
    fail2(`${name} takes true or false, not ${show4(v)}`);
  return v;
}
var XS = new Int32Array(256);
var YS = new Int32Array(256);
function trace(x0, y0, x1, y1, w, h) {
  if (!finite3(x0, y0, x1, y1))
    return 0;
  const m = w + h + 8;
  if (Math.min(x0, x1) < -m || Math.max(x0, x1) > w + m || Math.min(y0, y1) < -m || Math.max(y0, y1) > h + m) {
    const dx2 = x1 - x0, dy2 = y1 - y0;
    let a = 0, b = 1;
    for (const [p, q] of [[-dx2, x0 + 2], [dx2, w + 2 - x0], [-dy2, y0 + 2], [dy2, h + 2 - y0]]) {
      if (p === 0) {
        if (q < 0)
          return 0;
        continue;
      }
      const r = q / p;
      if (p < 0)
        a = Math.max(a, r);
      else
        b = Math.min(b, r);
      if (a > b)
        return 0;
    }
    [x0, y0, x1, y1] = [x0 + a * dx2, y0 + a * dy2, x0 + b * dx2, y0 + b * dy2];
  }
  x0 = Math.floor(x0);
  y0 = Math.floor(y0);
  x1 = Math.floor(x1);
  y1 = Math.floor(y1);
  const dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0), sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
  if (XS.length < dx - dy + 1)
    XS = new Int32Array(dx - dy + 1), YS = new Int32Array(dx - dy + 1);
  let err = dx + dy, n = 0;
  for (; ; ) {
    XS[n] = x0;
    YS[n++] = y0;
    if (x0 === x1 && y0 === y1)
      return n;
    const e2 = 2 * err;
    if (e2 >= dy)
      err += dy, x0 += sx;
    if (e2 <= dx)
      err += dx, y0 += sy;
  }
}
var UP = 124;
var RISE = 47;
var FALL = 92;
var RUN = 95;
var FLAT = 45;
var DOT = 42;
var JOINS = "\u25000101 \u25010202 \u25021010 \u25032020 \u250C0110 \u250D0210 \u250E0120 \u250F0220 \u25100011 \u25110012 \u25120021 \u25130022 \u25141100 \u25151200 \u25162100 \u25172200 \u25181001 \u25191002 \u251A2001 \u251B2002 \u251C1110 \u251D1210 \u251E2110 \u251F1120 \u25202120 \u25212210 \u25221220 \u25232220 \u25241011 \u25251012 \u25262011 \u25271021 \u25282021 \u25292012 \u252A1022 \u252B2022 \u252C0111 \u252D0112 \u252E0211 \u252F0212 \u25300121 \u25310122 \u25320221 \u25330222 \u25341101 \u25351102 \u25361201 \u25371202 \u25382101 \u25392102 \u253A2201 \u253B2202 \u253C1111 \u253D1112 \u253E1211 \u253F1212 \u25402111 \u25411121 \u25422121 \u25432112 \u25442211 \u25451122 \u25461221 \u25472212 \u25481222 \u25492122 \u254A2221 \u254B2222 \u25500303 \u25513030 \u25520310 \u25530130 \u25540330 \u25550013 \u25560031 \u25570033 \u25581300 \u25593100 \u255A3300 \u255B1003 \u255C3001 \u255D3003 \u255E1310 \u255F3130 \u25603330 \u25611013 \u25623031 \u25633033 \u25640313 \u25650131 \u25660333 \u25671303 \u25683101 \u25693303 \u256A1313 \u256B3131 \u256C3333 \u256D0110 \u256E0011 \u256F1001 \u25701100 \u25740001 \u25751000 \u25760100 \u25770010 \u25780002 \u25792000 \u257A0200 \u257B0020 \u257C0201 \u257D1020 \u257E0102 \u257F2010";
var AU = 0;
var AR = 2;
var AD = 4;
var AL = 6;
var ARMS = /* @__PURE__ */ new Map();
var GLYPH = /* @__PURE__ */ new Map();
var ROUND = /* @__PURE__ */ new Map();
for (const e of JOINS.split(" ")) {
  const c = e.charCodeAt(0);
  let a = 0;
  for (let k = 0; k < 4; k++)
    a |= Number(e[k + 1]) << 2 * k;
  ARMS.set(c, a);
  if (!GLYPH.has(a))
    GLYPH.set(a, c);
  else if (c >= 9581 && c <= 9584)
    ROUND.set(a, c);
}
function glyph(a, round, weight) {
  if (round && ROUND.has(a))
    return ROUND.get(a);
  let c = GLYPH.get(a);
  if (c === void 0) {
    let n = 0;
    for (let k = 0; k < 8; k += 2)
      if (a >> k & 3)
        n |= weight << k;
    c = GLYPH.get(n);
  }
  return c ?? DOT;
}
var PLUS = 43;
var DASH = 45;
var BAR = 124;
var asciiGlyph = (a) => a & 51 && a & 204 ? PLUS : a & 204 ? DASH : BAR;
var asciiArms = (c) => c === DASH ? 68 : c === BAR ? 17 : c === PLUS ? 85 : void 0;
function linked(s, j, b, ascii) {
  const x = j % s.cols, y = (j - x) / s.cols;
  let m = 0;
  for (let k = 0; k < 8; k += 2) {
    if (!(b >> k & 3))
      continue;
    const nx = x + (k === AR ? 1 : k === AL ? -1 : 0), ny = y + (k === AD ? 1 : k === AU ? -1 : 0);
    if (nx < 0 || ny < 0 || nx >= s.cols || ny >= s.rows)
      continue;
    const n = s.chars[ny * s.cols + nx], nb = ascii ? asciiArms(n) : ARMS.get(n);
    if (nb !== void 0 && nb >> (k ^ 4) & 3)
      m |= b & 3 << k;
  }
  return m;
}
function place2(s, j, c, k, join, a = ARMS.get(c), ascii = false, round = false) {
  if (join && a !== void 0) {
    const old = s.chars[j], b = ascii ? asciiArms(old) : ARMS.get(old);
    if (b !== void 0) {
      const kept = linked(s, j, b, ascii);
      let m = 0, w = 1;
      for (let i = 0; i < 8; i += 2) {
        const v = a >> i & 3;
        m |= (v || kept >> i & 3) << i;
        if (v > w)
          w = v;
      }
      c = m === b ? old : ascii ? asciiGlyph(m) : glyph(m, round, w);
    }
  }
  s.put(j, c, c === EMPTY ? NONE : k);
}
function strokeCells(s, n, ch, k, join = false) {
  if (ch !== "auto") {
    for (let i = 0; i < n; i++) {
      const j = s.index(XS[i], YS[i]);
      if (j >= 0)
        place2(s, j, ch, k, join);
    }
    return;
  }
  const dx = XS[n - 1] - XS[0], dy = YS[n - 1] - YS[0];
  const ax = Math.abs(dx), ay = Math.abs(dy);
  const rising = dx > 0 !== dy > 0;
  const runs = ax > ay;
  const upright = ay * s.aspect > 4 * ax;
  for (let i = 0; i < n; i++) {
    const j = s.index(XS[i], YS[i]);
    if (j < 0)
      continue;
    let c;
    if (n === 1)
      c = DOT;
    else if (upright)
      c = UP;
    else if (!runs)
      c = rising ? RISE : FALL;
    else if (!dy)
      c = FLAT;
    else if (rising) {
      const r = dx > 0 ? i + 1 : i - 1;
      c = r >= 0 && r < n && YS[r] !== YS[i] ? RISE : RUN;
    } else {
      const l = dx > 0 ? i - 1 : i + 1;
      c = l >= 0 && l < n && YS[l] !== YS[i] ? FALL : RUN;
    }
    s.put(j, c, k);
  }
}
function stroke(char, style, what, fallback = "auto") {
  if (style !== void 0) {
    if (char !== void 0)
      fail2(`${what} takes a char or a style, not both: a style draws in a box's lines, \u2500 \u2502 \u250C and the rest`);
    if (typeof style !== "string" || !Object.hasOwn(boxes, style))
      fail2(`${what}'s style takes ${or5(Object.keys(boxes))}, not ${show4(style)}`);
    return style;
  }
  const ch = char ?? fallback;
  return ch === "auto" ? "auto" : brush(ch, `${what}'s char`);
}
var PX = new Int32Array(256);
var PY = new Int32Array(256);
var PS = new Uint8Array(256);
function boxPath(s, pts, closed, style, k, join) {
  let n = 0;
  const push = (x, y, straight) => {
    if (n && PX[n - 1] === x && PY[n - 1] === y) {
      PS[n - 1] |= straight;
      return;
    }
    if (n === PX.length) {
      const nx = new Int32Array(2 * n), ny = new Int32Array(2 * n), ns = new Uint8Array(2 * n);
      nx.set(PX);
      ny.set(PY);
      ns.set(PS);
      PX = nx, PY = ny, PS = ns;
    }
    PX[n] = x;
    PY[n] = y;
    PS[n++] = straight;
  };
  const segs = pts.length === 1 ? 1 : closed && pts.length > 2 ? pts.length : pts.length - 1;
  for (let i = 0; i < segs; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    const m = trace(a[0], a[1], b[0], b[1], s.cols, s.rows);
    const straight = Math.floor(a[0]) === Math.floor(b[0]) || Math.floor(a[1]) === Math.floor(b[1]);
    if (!straight && m)
      strokeCells(s, m, "auto", k);
    for (let d = 0; d < m; d++)
      push(XS[d], YS[d], straight ? 1 : 0);
  }
  if (closed && n > 2 && PX[n - 1] === PX[0] && PY[n - 1] === PY[0])
    PS[0] |= PS[--n];
  const ring2 = closed && n > 2;
  const ascii = style === "ascii", round = style === "rounded";
  const w = style === "heavy" ? 2 : style === "double" ? 3 : 1;
  const across2 = w << AL | w << AR, down2 = w << AU | w << AD;
  for (let i = 0; i < n; i++) {
    const j = s.index(PX[i], PY[i]);
    if (j < 0 || !PS[i])
      continue;
    let a = 0;
    const before = i > 0 ? i - 1 : ring2 ? n - 1 : -1, after = i < n - 1 ? i + 1 : ring2 ? 0 : -1;
    for (let side2 = 0; side2 < 2; side2++) {
      const o = side2 ? after : before;
      if (o < 0 || !PS[o])
        continue;
      const dx = PX[o] - PX[i], dy = PY[o] - PY[i];
      if (!dx && (dy === 1 || dy === -1))
        a |= w << (dy < 0 ? AU : AD);
      else if (!dy && (dx === 1 || dx === -1))
        a |= w << (dx < 0 ? AL : AR);
    }
    const ends = (a & 3 ? 1 : 0) + (a & 12 ? 1 : 0) + (a & 48 ? 1 : 0) + (a & 192 ? 1 : 0);
    const full = ends > 1 ? a : a & 51 ? down2 : across2;
    place2(s, j, ascii ? asciiGlyph(full) : glyph(full, round, w), k, join, a || full, ascii, round);
  }
}
var ALIGN = ["left", "center", "right"];
var VALIGN = ["top", "middle", "bottom"];
function size(v, what) {
  if (typeof v !== "number" || !Number.isFinite(v) || v < 1)
    fail2(`${what} takes a number of cells of 1 or more, not ${show4(v)}`);
  return Math.floor(v);
}
var BAD = /[\ud800-\udbff][\udc00-\udfff]|[\u0000-\u0009\u000b-\u001f\u007f-\u009f\ud800-\udfff]/;
function words(str, what) {
  if (typeof str === "number")
    return String(str);
  if (typeof str !== "string")
    fail2(`${what}() takes a string to write, or a number, not ${show4(str)}`);
  const t = str.replace(/\r\n?/g, "\n");
  const bad = BAD.exec(t);
  if (bad)
    code(bad[0]);
  return t;
}
function writeLines(s, lines, lefts, top, k, transparent) {
  let left = Infinity, right = -Infinity;
  lines.forEach((line2, r) => {
    const lx = lefts[r], len = line2.length;
    if (len)
      left = Math.min(left, lx), right = Math.max(right, lx + len);
    for (let i = 0; i < len; i++) {
      const c = line2.charCodeAt(i);
      if (transparent && c === 32)
        continue;
      const j = s.index(lx + i, top + r);
      if (j >= 0)
        s.put(j, c, k);
    }
  });
  return left === Infinity ? { x: lefts[0] ?? 0, y: top, cols: 0, rows: lines.length } : { x: left, y: top, cols: right - left, rows: lines.length };
}
function layout(str, width, wrap) {
  const out = [];
  for (const para of str.split("\n")) {
    if (!wrap || para.length <= width) {
      out.push(para.slice(0, width));
      continue;
    }
    let line2 = "";
    for (let word of para.split(" ").filter(Boolean)) {
      while (word.length > width) {
        if (line2)
          out.push(line2);
        line2 = "";
        out.push(word.slice(0, width));
        word = word.slice(width);
      }
      if (!line2)
        line2 = word;
      else if (line2.length + 1 + word.length <= width)
        line2 += " " + word;
      else {
        out.push(line2);
        line2 = word;
      }
    }
    out.push(line2);
  }
  return out;
}
function regionOf(r, what) {
  const g = r;
  if (!g || typeof g !== "object" || !finite3(g.x, g.y, g.cols, g.rows))
    fail2(`${what}() takes a region as { x, y, cols, rows } in numbers, not ${show4(r)}`);
  return g;
}
function text(s, ...a) {
  grid2(s, "text");
  if (a[0] !== null && typeof a[0] === "object") {
    const r = regionOf(a[0], "text");
    return write(s, r.x, r.y, a[1], a[2], r);
  }
  return write(s, a[0], a[1], a[2], a[3]);
}
function write(s, x, y, str, o, region) {
  const { color, align = "left", valign = "top", width: w, height: h } = opts(o, "text");
  if (!ALIGN.includes(align))
    fail2(`align takes ${or5(ALIGN)}, not ${show4(align)}`);
  if (!VALIGN.includes(valign))
    fail2(`valign takes ${or5(VALIGN)}, not ${show4(valign)}`);
  const transparent = yes(o?.transparent, "transparent", false);
  const width = w === void 0 ? void 0 : size(w, "width"), height = h === void 0 ? void 0 : size(h, "height");
  const wrap = yes(o?.wrap, "wrap", width !== void 0 || !!region);
  const t = words(str, "text");
  const k = paint(s, color);
  if (!finite3(x, y))
    return { x: 0, y: 0, cols: 0, rows: 0 };
  const fx = Math.floor(x), fy = Math.floor(y);
  const bw = width ?? (region ? Math.floor(region.cols) : s.cols - fx), bh = height ?? (region ? Math.floor(region.rows) : s.rows - fy);
  if (t === "" || bw < 1 || bh < 1)
    return { x: fx, y: fy, cols: 0, rows: 0 };
  let lines = layout(t, bw, wrap);
  if (lines.length > bh)
    lines = lines.slice(0, bh);
  const n = lines.length;
  const top = valign === "top" ? fy : valign === "middle" ? fy + Math.floor((bh - n) / 2) : fy + bh - n;
  const lefts = lines.map((l) => align === "left" ? fx : align === "center" ? fx + Math.floor((bw - l.length) / 2) : fx + bw - l.length);
  return writeLines(s, lines, lefts, top, k, transparent);
}
function line(s, x0, y0, x1, y1, o) {
  grid2(s, "line");
  const { char, style, color } = opts(o, "line");
  const ch = stroke(char, style, "a line");
  const k = paint(s, color);
  const join = yes(o?.join, "join", true);
  path(s, [[x0, y0], [x1, y1]], ch, k, false, join);
}
function path(s, pts, ch, k, closed, join) {
  if (typeof ch === "string" && ch !== "auto")
    return boxPath(s, pts, closed, ch, k, join);
  if (pts.length === 1) {
    const n = trace(pts[0][0], pts[0][1], pts[0][0], pts[0][1], s.cols, s.rows);
    if (n)
      strokeCells(s, n, ch, k, join);
    return;
  }
  const last = closed && pts.length > 2 ? pts.length : pts.length - 1;
  const rank = (i) => {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    const ax = Math.abs(Math.floor(b[0]) - Math.floor(a[0])), ay = Math.abs(Math.floor(b[1]) - Math.floor(a[1]));
    return !ay ? 0 : ay * s.aspect > 4 * ax ? 1 : 2;
  };
  for (let pass = 0; pass < (ch === "auto" ? 3 : 1); pass++)
    for (let i = 0; i < last; i++) {
      if (ch === "auto" && rank(i) !== pass)
        continue;
      const a = pts[i], b = pts[(i + 1) % pts.length];
      const n = trace(a[0], a[1], b[0], b[1], s.cols, s.rows);
      if (n)
        strokeCells(s, n, ch, k, join);
    }
}
var boxes = Object.freeze({
  single: "\u250C\u2510\u2514\u2518\u2500\u2502",
  double: "\u2554\u2557\u255A\u255D\u2550\u2551",
  rounded: "\u256D\u256E\u2570\u256F\u2500\u2502",
  heavy: "\u250F\u2513\u2517\u251B\u2501\u2503",
  ascii: "++++-|"
});
var EDGE_ARMS = [1 << AR | 1 << AD, 1 << AL | 1 << AD, 1 << AU | 1 << AR, 1 << AU | 1 << AL, 1 << AL | 1 << AR, 1 << AU | 1 << AD];
function rect(s, x, y, w, h, o) {
  grid2(s, "rect");
  const { style = "single", fill, color, fillColor, title } = opts(o, "rect");
  let edges = null;
  if (style !== "none") {
    const chars3 = typeof style === "string" ? Object.hasOwn(boxes, style) ? boxes[style] : style : "";
    if ([...chars3].length !== 6 || /^[a-z]+$/i.test(chars3))
      fail2(`style takes ${or5([...Object.keys(boxes), "none"])}, or 6 characters of your own (top left, top right, bottom left, bottom right, across, down), not ${show4(style)}`);
    edges = [...chars3].map(code);
  }
  const f = fill === void 0 || fill === false ? null : brush(fill, "fill");
  if (title !== void 0 && typeof title !== "string")
    fail2(`title takes a string, not ${show4(title)}`);
  if (title)
    for (const ch of title)
      code(ch);
  const join = yes(o?.join, "join", true);
  const k = paint(s, color), fk = fillColor === void 0 ? k : paint(s, fillColor);
  if (!finite3(x, y, w, h))
    return { x: 0, y: 0, cols: 0, rows: 0 };
  x = Math.floor(x);
  y = Math.floor(y);
  w = Math.floor(w);
  h = Math.floor(h);
  const inset2 = edges ? 1 : 0;
  const inside = { x: x + inset2, y: y + inset2, cols: Math.max(0, w - 2 * inset2), rows: Math.max(0, h - 2 * inset2) };
  if (w < 1 || h < 1)
    return { x, y, cols: 0, rows: 0 };
  if (f !== null) {
    const r = s.clip(inside);
    for (let cy = r.y; cy < r.y + r.rows; cy++)
      for (let cx = r.x; cx < r.x + r.cols; cx++)
        s.put(cy * s.cols + cx, f, f === EMPTY ? NONE : fk);
  }
  if (edges) {
    const ed = edges, ascii = style === "ascii", round = style === "rounded";
    const put = (cx, cy, e, reach = 255) => {
      const j = s.index(cx, cy), a = ascii ? EDGE_ARMS[e] : ARMS.get(ed[e]);
      if (j >= 0)
        place2(s, j, ed[e], k, join, a === void 0 ? a : a & reach, ascii, round);
    };
    const end = (i, n, first, last) => n < 2 ? 255 : i === 0 ? 3 << first : i === n - 1 ? 3 << last : 255;
    const from = (o2, lo) => Math.max(lo, -o2), to = (o2, hi, n) => Math.min(hi, n - o2);
    if (h === 1)
      for (let i = from(x, 0); i < to(x, w, s.cols); i++)
        put(x + i, y, 4, end(i, w, AR, AL));
    else if (w === 1)
      for (let i = from(y, 0); i < to(y, h, s.rows); i++)
        put(x, y + i, 5, end(i, h, AD, AU));
    else {
      for (let i = from(x, 1); i < to(x, w - 1, s.cols); i++) {
        put(x + i, y, 4);
        put(x + i, y + h - 1, 4);
      }
      for (let i = from(y, 1); i < to(y, h - 1, s.rows); i++) {
        put(x, y + i, 5);
        put(x + w - 1, y + i, 5);
      }
      put(x, y, 0);
      put(x + w - 1, y, 1);
      put(x, y + h - 1, 2);
      put(x + w - 1, y + h - 1, 3);
    }
  }
  const room = w - 6;
  if (title && room >= 1) {
    const t = title.length > room ? room > 1 ? title.slice(0, room - 1) + "\u2026" : title.slice(0, 1) : title;
    const label2 = ` ${t} `;
    for (let i = Math.max(0, -(x + 2)); i < Math.min(label2.length, s.cols - x - 2); i++) {
      const j = s.index(x + 2 + i, y);
      if (j >= 0)
        s.put(j, label2.charCodeAt(i), k);
    }
  }
  return inside;
}
var EDGE = new Uint8Array(1024);

// node_modules/ascii.rest/dist/kit/recipes/widgets.js
var TONES = {
  ink: INK2,
  accent: { light: "#0969da", dark: "#58a6ff" },
  muted: { light: "#8c959f", dark: "#6e7681" },
  good: { light: "#1a7f37", dark: "#3fb950" },
  warn: { light: "#9a6700", dark: "#d29922" },
  bad: { light: "#cf222e", dark: "#f85149" }
};
var ACCENT = 1;
var MUTED = 2;
var GOOD = 3;
var themed2 = colorOf3;
function tones(accent, more = []) {
  const list2 = [TONES.ink, accent ?? TONES.accent, TONES.muted, TONES.good, TONES.warn, TONES.bad, ...more];
  return { light: list2.map((c) => c.light), dark: list2.map((c) => c.dark) };
}
var WIDGET = ["color", ...NAMING];
var naming2 = (o, name, note) => ({ name: o.name ?? name, note: (o.note ?? note).slice(0, 72) });
var framing = (p, framed) => framed ? Object.assign(p, { frames: true }) : p;
function amountOf(what, v, min, max, share) {
  if (v === void 0)
    return void 0;
  if (typeof v === "function") {
    return () => {
      const got = v();
      return typeof got === "number" && Number.isFinite(got) ? Math.max(min, Math.min(max, got)) : min;
    };
  }
  if (typeof v === "string") {
    const m = /^\s*(\d+(?:\.\d+)?)\s*%\s*$/.exec(v);
    if (!m || +m[1] > 100)
      fail2(`${what}'s value takes a percentage from "0%" to "100%", or a number, not ${show3(v)}`);
    return min + +m[1] / 100 * (max - min);
  }
  if (typeof v !== "number" || !Number.isFinite(v) || v < min || v > max) {
    const hint = share && typeof v === "number" && v > 1 && v <= 100 ? `: did you mean ${+(v / 100).toFixed(4)}, or "${v}%"?` : "";
    fail2(`${what}'s value takes a number from ${min} to ${max}, a percentage such as "64%", or a function that reads one, not ${show3(v)}${hint}`);
  }
  if (!share && min === 0 && max === 100 && v > 0 && v < 1)
    fail2(`${what}'s value is a reading from 0 to 100, and ${v} is less than 1: did you mean ${+(v * 100).toFixed(2)}, or "${+(v * 100).toFixed(2)}%"? Give it max: 1 for a reading from 0 to 1`);
  return v;
}
var EIGHTHS = "\u258F\u258E\u258D\u258C\u258B\u258A\u2589\u2588";
function progressBar(o) {
  const p = optionsOf4("progressBar()", o, ["value", "min", "max", "label", "width", "style", "percent", "seconds", ...WIDGET]);
  const min = numberOf2("progressBar's min", p.min, 0), max = numberOf2("progressBar's max", p.max, 1);
  if (!(max > min))
    fail2(`progressBar's max takes a number above its min, ${min}, not ${show3(p.max)}`);
  const value = amountOf("progressBar", p.value, min, max, min === 0 && max === 1);
  const live = typeof value === "function";
  const words2 = textOf2("progressBar's label", p.label);
  const label2 = words2 ? `${words2} ` : "";
  const width = wholeOf("progressBar's width", p.width, 30, 3, 300);
  const style = wordOf2("progressBar's style", p.style, ["blocks", "ascii", "dots"], "blocks");
  const percent = boolOf2("progressBar's percent", p.percent, true);
  const fill = numberOf2("progressBar's seconds", p.seconds, 4, 0.1, 59);
  const smooth = ease.inOutSine;
  const loop = loopOf3(fill + 1, true);
  const cols = label2.length + width + (percent ? 5 : 0);
  const share = (v) => (v - min) / (max - min);
  const timing = live ? { fps: 4, clock: true } : value === void 0 ? { fps: 24, loop, still: fill } : { fps: 0 };
  const note = live ? "a progress bar, live" : value === void 0 ? "a progress bar filling" : `a progress bar at ${Math.round(share(value) * 100)}%`;
  return piece({ ...naming2(p, label2.trim() || "progress", note), category: "ui", cols, rows: 1, ...timing, palette: tones(themed2("progressBar's color", p.color)) }, (t, s) => {
    const k = typeof value === "function" ? share(value()) : value !== void 0 ? share(value) : smooth(Math.min(1, (t % loop + loop) % loop / fill));
    const color = k >= 1 ? GOOD : ACCENT;
    s.write(0, 0, label2);
    const x = label2.length;
    if (style === "ascii") {
      const n = Math.round(k * (width - 2));
      s.write(x, 0, "[", MUTED);
      for (let i = 0; i < width - 2; i++)
        s.set(x + 1 + i, 0, i < n ? "#" : "-", i < n ? color : MUTED);
      s.write(x + width - 1, 0, "]", MUTED);
    } else if (style === "dots") {
      const n = Math.round(k * width);
      for (let i = 0; i < width; i++)
        s.set(x + i, 0, i < n ? "\u25CF" : "\u25CB", i < n ? color : MUTED);
    } else {
      const eighths = Math.round(k * width * 8);
      for (let i = 0; i < width; i++) {
        const e = eighths - i * 8;
        s.set(x + i, 0, e >= 8 ? "\u2588" : e > 0 ? EIGHTHS[e - 1] : "\u2591", e > 0 ? color : MUTED);
      }
    }
    if (percent)
      s.write(x + width, 0, `${Math.round(k * 100)}%`.padStart(5));
  });
}
var BARS = [
  { light: "#0969da", dark: "#58a6ff" },
  { light: "#1a7f37", dark: "#3fb950" },
  { light: "#9a6700", dark: "#d29922" },
  { light: "#cf222e", dark: "#f85149" },
  { light: "#8250df", dark: "#bc8cff" },
  { light: "#bf3989", dark: "#ff80c8" }
];
var RISE2 = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588";
function barChart(data, o) {
  const p = optionsOf4("barChart()", o, ["horizontal", "size", "max", "values", "seconds", "hold", ...WIDGET]);
  const entries = Array.isArray(data) ? data.map((v, i) => [String(i + 1), v]) : data && typeof data === "object" ? Object.entries(data) : [];
  if (!entries.length || entries.length > 64 || !entries.every(([, v]) => typeof v === "number" && Number.isFinite(v) && v >= 0))
    fail2(`barChart() takes names and values, such as { mon: 3, tue: 5 }, or a list of values, 1 to 64 of them, each 0 or more, not ${show3(data)}`);
  for (const [k] of entries)
    textOf2("barChart's names", k);
  const horizontal = boolOf2("barChart's horizontal", p.horizontal, false);
  const size2 = wholeOf("barChart's size", p.size, horizontal ? 30 : 10, 1, 300);
  const top = numberOf2("barChart's max", p.max, Math.max(...entries.map(([, v]) => v)) || 1, 0);
  const values = boolOf2("barChart's values", p.values, true);
  const grow = numberOf2("barChart's seconds", p.seconds, 0.8, 0, 30);
  const hold = numberOf2("barChart's hold", p.hold, 3, 0, 60);
  const own = themed2("barChart's color", p.color);
  const snappy = ease.outBack;
  const shown3 = entries.map(([, v]) => String(+v.toFixed(2)));
  const names = entries.map(([k]) => k);
  const grown = grow + 0.1 * (entries.length - 1);
  const loop = grow ? loopOf3(grown + hold, true) : void 0;
  const lengthAt = (i, t) => {
    const full = Math.min(1, entries[i][1] / top);
    if (!loop)
      return full;
    const u = (t % loop + loop) % loop - 0.1 * i;
    return full * Math.min(1.08, snappy(Math.max(0, Math.min(1, u / grow))));
  };
  const colorOf4 = (i) => own ? ACCENT : 6 + i % BARS.length;
  const palette = tones(own, own ? [] : BARS);
  const spec = { ...naming2(p, "bar chart", `a bar chart of ${entries.length} bars${loop ? ", growing in" : ""}`), category: "data", fps: loop ? 24 : 0, palette, ...loop ? { loop, still: Math.min(loop - 0.01, grown + 0.05) } : {} };
  if (horizontal) {
    const nameW = Math.max(...names.map((n) => n.length)), valueW = values ? Math.max(...shown3.map((v) => v.length)) + 1 : 0;
    return piece({ ...spec, cols: nameW + 1 + size2 + valueW, rows: entries.length }, (t, s) => {
      entries.forEach((_, i) => {
        s.write(nameW - names[i].length, i, names[i]);
        const eighths = Math.min(size2 * 8, Math.round(lengthAt(i, t) * size2 * 8));
        for (let x = 0; x * 8 < eighths; x++)
          s.set(nameW + 1 + x, i, eighths - x * 8 >= 8 ? "\u2588" : EIGHTHS[eighths - x * 8 - 1], colorOf4(i));
        if (values)
          s.write(nameW + 2 + Math.ceil(eighths / 8), i, shown3[i], MUTED);
      });
    });
  }
  const bar = Math.max(3, ...names.map((n) => n.length), ...values ? shown3.map((v) => v.length) : []), gap = 2;
  return piece({ ...spec, cols: entries.length * (bar + gap) - gap, rows: size2 + 2 }, (t, s) => {
    entries.forEach((_, i) => {
      const x = i * (bar + gap);
      const eighths = Math.min(size2 * 8, Math.round(lengthAt(i, t) * size2 * 8));
      for (let y = 0; y * 8 < eighths; y++) {
        const e = eighths - y * 8;
        for (let c = 0; c < bar; c++)
          s.set(x + c, size2 - y, e >= 8 ? "\u2588" : RISE2[e - 1], colorOf4(i));
      }
      if (values && eighths)
        text(s, x, size2 - Math.ceil(eighths / 8), shown3[i], { width: bar, align: "center", color: MUTED });
      text(s, x, size2 + 1, names[i], { width: bar, align: "center" });
    });
  });
}
function panel(content, o) {
  const p = optionsOf4("panel()", o, ["title", "style", "cols", "rows", ...WIDGET]);
  const title = textOf2("panel's title", p.title);
  const style = wordOf2("panel's style", p.style, ["rounded", "single", "double", "heavy", "ascii"], "rounded");
  const inner = content === void 0 ? null : pieceOf(content, "panel()");
  const cols = wholeOf("panel's cols", p.cols, (inner?.meta.cols ?? 20) + 4, 3, 320), rows = wholeOf("panel's rows", p.rows, (inner?.meta.rows ?? 4) + 2, 3, 120);
  if (inner && (inner.meta.cols > cols - 4 || inner.meta.rows > rows - 2))
    fail2(`panel's room inside is ${cols - 4} by ${rows - 2}, and ${inner.meta.name} is ${inner.meta.cols} by ${inner.meta.rows}: give the panel cols ${inner.meta.cols + 4} and rows ${inner.meta.rows + 2} or more, or leave them out`);
  const room = new Surface(Math.max(1, cols - 4), Math.max(1, rows - 2));
  const filled = inner ? layer(room, { src: inner, anchor: "center" }) : room;
  const color = themed2("panel's color", p.color);
  const boxed = border(filled, { style, pad: [0, 1], ...title ? { title } : {}, ...color ? { color } : {} });
  const name = p.name ?? title ?? inner?.meta.name ?? "panel";
  return framing(titled(boxed, name, p.note ?? `${name}, in a box`), true);
}
function card(o) {
  const p = optionsOf4("card()", o, ["title", "text", "footer", "width", "style", "frame", ...WIDGET]);
  const title = textOf2("card's title", p.title), words2 = textOf2("card's text", p.text, { lines: true }), footer = textOf2("card's footer", p.footer);
  if (!title && !words2 && !footer)
    fail2('card() takes a title, text or a footer, such as { title: "hello", text: "..." }');
  const style = wordOf2("card's style", p.style, ["rounded", "single", "double", "heavy", "ascii"], "rounded");
  const framed = boolOf2("card's frame", p.frame, true);
  const width = wholeOf("card's width", p.width, 36, 8, 320);
  const edge = framed ? 1 : 0;
  const room = width - 2 - 2 * edge;
  const body2 = words2 ? text(new Surface(room, 120), 0, 0, words2, { width: room }).rows : 0;
  if (body2 > 100)
    fail2(`card's text wraps to ${body2} rows at this width, past the 100 a card can hold: give it fewer words or more width`);
  const head = title ? 2 : 0, foot = footer ? body2 ? 2 : 1 : 0;
  const rows = 2 * edge + head + body2 + foot;
  const made = piece({ ...naming2(p, title || "card", title ? `a card: ${title}` : "a card"), category: "ui", cols: width, rows, fps: 0, palette: tones(themed2("card's color", p.color)) }, (_, s) => {
    if (framed)
      rect(s, 0, 0, width, rows, { style, color: MUTED });
    const x = edge + 1;
    let y = edge;
    if (title) {
      text(s, x, y, title, { width: room, wrap: false, color: ACCENT });
      line(s, 0, y + 1, width - 1, y + 1, { style: style === "rounded" ? "single" : style, color: MUTED });
      y += 2;
    }
    if (words2)
      y += text(s, x, y, words2, { width: room }).rows;
    if (footer)
      text(s, x, rows - 1 - edge, footer, { width: room, align: "right", wrap: false, color: MUTED });
  });
  return framing(made, framed);
}

// src/ascii-studio.mjs
var THEME = {
  fg: "#c8c8c8",
  accent: "#e6e6e6",
  mute: "#6e6e6e",
  ok: "#3fb950",
  warn: "#d29922"
};
var unmounts = /* @__PURE__ */ new WeakMap();
function clearMount(el) {
  const prev = unmounts.get(el);
  if (typeof prev === "function") {
    try {
      prev();
    } catch (_) {
    }
  }
  unmounts.delete(el);
  el.replaceChildren();
}
function attach(el, piece2, { live = false } = {}) {
  clearMount(el);
  const stop = mount(el, piece2, live ? { fps: 8 } : { fps: 0 });
  unmounts.set(el, stop);
  return stop;
}
function clamp01(n) {
  const x = Number(n);
  if (!Number.isFinite(x)) return 0;
  if (x < 0) return 0;
  if (x > 1) return x > 1 && x <= 100 ? x / 100 : 1;
  return x;
}
function fmt(n, digits = 3) {
  if (n == null || n === "") return "\u2014";
  const x = Number(n);
  if (!Number.isFinite(x)) return "\u2014";
  return x.toFixed(digits);
}
function mountOverviewBoard(el, dash, opts2 = {}) {
  if (!el) return () => {
  };
  const h = dash && dash.header || {};
  const scores = dash && dash.scores || {};
  const levers = dash && dash.levers || {};
  const missions = dash && dash.missions || {};
  const dead = dash && dash.dead_ends || {};
  const kaggle = dash && dash.kaggle || {};
  const progress = clamp01(h.progress_pct);
  const publicScore = scores.best_public != null ? scores.best_public : kaggle.public_score;
  const isKaggle = opts2.kind === "kaggle" || Boolean(kaggle.linked);
  const goalCard = card({
    title: "GOAL",
    text: [
      String(h.primary_goal_title || "no primary goal").slice(0, 34),
      `thr ${fmt(h.primary_threshold)}   now ${fmt(h.primary_latest)}`,
      `gap ${fmt(h.primary_gap)}   ${h.primary_status || "OPEN"}`
    ].join("\n"),
    footer: `${(progress * 100).toFixed(0)}% campaign`,
    width: 38,
    color: THEME.accent
  });
  const scoreCard = card({
    title: "SCORE",
    text: isKaggle ? [
      `public  ${fmt(publicScore)}`,
      `rank    ${kaggle.rank ?? "\u2014"}`,
      `best cv ${fmt(scores.best_cv)}`
    ].join("\n") : [`best cv ${fmt(scores.best_cv)}`, "public  \u2014", "standalone"].join("\n"),
    footer: isKaggle ? "kaggle public LB" : "notebook",
    width: 38,
    color: THEME.ok
  });
  const workCard = card({
    title: "WORK",
    text: [
      `levers    ${levers.open || 0} open / ${levers.closed || 0} closed`,
      `missions  ${missions.queued || 0}q ${missions.running || 0}run ${missions.succeeded || 0}ok`,
      `dead ends ${dead.count || 0}`
    ].join("\n"),
    footer: "0.5 G + 0.3 L + 0.2 M",
    width: 38,
    color: THEME.warn
  });
  const board = grid(
    [
      progressBar({
        value: progress,
        label: "progress",
        width: 52,
        style: "blocks",
        color: THEME.accent
      }),
      goalCard,
      scoreCard,
      workCard
    ],
    { columns: 3, gap: 2, border: false, name: "studio-overview" }
  );
  return attach(el, board, { live: Boolean(opts2.live) });
}
var WIZARD_COPY = {
  kind: [
    "Pick a real campaign name (slug follows).",
    "kaggle \u2192 competition workspace + Kaggle mode.",
    "standalone \u2192 notebook / research only.",
    "Do not invent a Demo Campaign."
  ],
  goals: [
    "One measurable primary goal is required.",
    "kaggle \u2192 kind kaggle_public, metric public_score.",
    "standalone \u2192 kind notebook_score, metric cv_mean.",
    "Threshold is the bar you must beat \u2014 be honest."
  ],
  link: [
    "Kaggle: paste the competition slug exactly.",
    "Example: playground-series-s6e11",
    "Seal API token later under Kaggle \u2192 token.",
    "Git remote optional; link from Ops later."
  ],
  review: [
    "Create stores the project in Mongo (org-scoped).",
    "Next: Overview \u2192 Sync Kaggle if linked.",
    "Then Lab for levers; never auto-submit overnight.",
    "Progress = 0.5\xB7goals + 0.3\xB7levers + 0.2\xB7missions."
  ]
};
function mountWizardTutorial(el, stepName, ctx = {}) {
  if (!el) return () => {
  };
  const lines = WIZARD_COPY[stepName] || WIZARD_COPY.kind;
  const kind = ctx.kind === "kaggle" ? "kaggle" : "standalone";
  const head = banner("new project", {
    font: "slim",
    shadow: "none",
    fill: "#",
    color: [THEME.accent, THEME.mute],
    effect: "still"
  });
  const tip = panel(lines.join("\n"), {
    title: `${stepName} \xB7 ${kind}`,
    cols: 56,
    rows: 8,
    color: THEME.fg
  });
  const checklist = barChart(
    {
      name: ctx.name ? 1 : 0,
      goal: stepName === "kind" ? 0 : 1,
      link: ["link", "review"].includes(stepName) ? 1 : 0,
      go: stepName === "review" ? 1 : 0
    },
    { color: THEME.ok }
  );
  const board = grid([head, tip, checklist], {
    columns: 1,
    gap: 1,
    border: { title: true },
    name: "wizard-guide"
  });
  return attach(el, board, { live: false });
}
function unmountAscii(el) {
  if (el) clearMount(el);
}
export {
  THEME,
  mountOverviewBoard,
  mountWizardTutorial,
  unmountAscii
};
//# sourceMappingURL=mymlfw-ascii.js.map
