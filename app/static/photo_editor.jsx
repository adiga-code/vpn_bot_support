// ── Редактор фото перед отправкой ────────────────────────────────────────────
// Как в Telegram: кисть, обрезка рамкой, поворот на 90°, отмена. Чистый canvas
// 2D без библиотек. Все правки хранятся моделью в координатах ПОВЁРНУТОГО
// исходника, картинка растеризуется один раз — при «Готово», — поэтому
// поворот и обрезка не теряют качества и штрихи переживают поворот.

const { useState: useStateP, useEffect: useEffectP, useRef: useRefP } = React;

const PE_COLORS = ["#ef4444", "#facc15", "#22c55e", "#3b82f6", "#ffffff", "#111111"];
// Толщина — доля длинной стороны картинки: на скрине 3000px линия не должна
// превращаться в волосок, а на 400px — в малярный валик.
const PE_SIZES = [0.004, 0.009, 0.018];
const PE_RATIOS = [["Свободно", null], ["1:1", 1], ["4:3", 4 / 3], ["16:9", 16 / 9]];
const PE_MAX_SIDE = 4096;
const PE_HANDLE = 14;       // радиус попадания в ручку рамки, экранные px
const PE_MIN_CROP = 24;     // минимальный размер рамки, экранные px

function peRotatedSize(img, rotation) {
  return rotation % 180 ? { w: img.naturalHeight, h: img.naturalWidth }
                        : { w: img.naturalWidth, h: img.naturalHeight };
}

// Поворот точки/рамки на 90° по часовой в пространстве ширины×высоты (w×h):
// (x, y) → (h − y, x).
function peRotPoint([x, y], h) { return [h - y, x]; }
function peRotRect(r, h) { return r && { x: h - (r.y + r.h), y: r.x, w: r.h, h: r.w }; }

// Нарисовать повёрнутый исходник и штрихи в текущей системе координат ctx
// (1 единица = 1 пиксель повёрнутого исходника).
function peDrawScene(ctx, img, model, extraStroke) {
  const W = img.naturalWidth, H = img.naturalHeight;
  ctx.save();
  if (model.rotation === 90)       { ctx.translate(H, 0); ctx.rotate(Math.PI / 2); }
  else if (model.rotation === 180) { ctx.translate(W, H); ctx.rotate(Math.PI); }
  else if (model.rotation === 270) { ctx.translate(0, W); ctx.rotate(-Math.PI / 2); }
  ctx.drawImage(img, 0, 0);
  ctx.restore();
  const strokes = extraStroke ? [...model.strokes, extraStroke] : model.strokes;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const s of strokes) {
    ctx.strokeStyle = s.color;
    ctx.fillStyle = s.color;
    ctx.lineWidth = s.width;
    const p = s.points;
    if (p.length === 1) {
      ctx.beginPath();
      ctx.arc(p[0][0], p[0][1], s.width / 2, 0, Math.PI * 2);
      ctx.fill();
      continue;
    }
    // Сглаживание через середины отрезков — линия от мыши не выглядит ломаной.
    ctx.beginPath();
    ctx.moveTo(p[0][0], p[0][1]);
    for (let i = 1; i < p.length - 1; i++) {
      const mx = (p[i][0] + p[i + 1][0]) / 2, my = (p[i][1] + p[i + 1][1]) / 2;
      ctx.quadraticCurveTo(p[i][0], p[i][1], mx, my);
    }
    ctx.lineTo(p[p.length - 1][0], p[p.length - 1][1]);
    ctx.stroke();
  }
}

function peClampRect(r, W, H, minW, minH) {
  const w = Math.min(Math.max(r.w, minW), W), h = Math.min(Math.max(r.h, minH), H);
  return { x: Math.min(Math.max(r.x, 0), W - w), y: Math.min(Math.max(r.y, 0), H - h), w, h };
}

// Самая большая рамка заданной пропорции, вписанная в `r` по центру.
function peFitRatio(r, ratio) {
  if (!ratio) return r;
  let w = r.w, h = w / ratio;
  if (h > r.h) { h = r.h; w = h * ratio; }
  return { x: r.x + (r.w - w) / 2, y: r.y + (r.h - h) / 2, w, h };
}

function PhotoEditor({ file, onDone, onCancel }) {
  const [img,      setImg]      = useStateP(null);
  const [loadErr,  setLoadErr]  = useStateP(false);
  const [model,    setModel]    = useStateP({ rotation: 0, crop: null, strokes: [] });
  const [history,  setHistory]  = useStateP([]);
  const [tool,     setTool]     = useStateP("brush");   // brush | crop
  const [color,    setColor]    = useStateP(PE_COLORS[0]);
  const [sizeIdx,  setSizeIdx]  = useStateP(1);
  const [ratio,    setRatio]    = useStateP(null);
  const [draft,    setDraft]    = useStateP(null);       // рамка в режиме обрезки
  const [busy,     setBusy]     = useStateP(false);
  const [viewTick, setViewTick] = useStateP(0);
  const wrapRef   = useRefP(null);
  const canvasRef = useRefP(null);
  const viewRef   = useRefP(null);   // {s, ox, oy, region} — для перевода координат
  const strokeRef = useRefP(null);   // штрих, который рисуется прямо сейчас
  const dragRef   = useRefP(null);   // перетаскивание рамки обрезки
  const rafRef    = useRefP(0);

  useEffectP(() => {
    const url = URL.createObjectURL(file);
    const im = new Image();
    im.onload = () => setImg(im);
    im.onerror = () => setLoadErr(true);
    im.src = url;
    return () => URL.revokeObjectURL(url);
  }, [file]);

  // Перерисовка при изменении размеров области (поворот телефона, окно).
  useEffectP(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver(() => setViewTick((t) => t + 1));
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, [img]);

  const size = img ? peRotatedSize(img, model.rotation) : { w: 1, h: 1 };
  const full = { x: 0, y: 0, w: size.w, h: size.h };

  function commit(next) {
    setHistory((h) => [...h.slice(-49), model]);
    setModel(next);
  }

  function undo() {
    // В режиме обрезки «отменить» возвращает рамку к применённой.
    if (tool === "crop") { setDraft(model.crop || full); return; }
    if (!history.length) return;
    setModel(history[history.length - 1]);
    setHistory(history.slice(0, -1));
  }

  useEffectP(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); undo(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function redraw() {
    const canvas = canvasRef.current, wrap = wrapRef.current;
    if (!canvas || !wrap || !img) return;
    const dpr = window.devicePixelRatio || 1;
    const cw = wrap.clientWidth, ch = wrap.clientHeight;
    if (canvas.width !== Math.round(cw * dpr) || canvas.height !== Math.round(ch * dpr)) {
      canvas.width = Math.round(cw * dpr);
      canvas.height = Math.round(ch * dpr);
      canvas.style.width = cw + "px";
      canvas.style.height = ch + "px";
    }
    // В режиме обрезки видна вся картинка, иначе — только обрезанная часть.
    const region = tool === "crop" ? full : (model.crop || full);
    const pad = 16;
    const s = Math.min((cw - pad * 2) / region.w, (ch - pad * 2) / region.h, 4);
    const ox = (cw - region.w * s) / 2, oy = (ch - region.h * s) / 2;
    viewRef.current = { s, ox, oy, region };
    const ctx = canvas.getContext("2d");
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.setTransform(dpr * s, 0, 0, dpr * s, dpr * (ox - region.x * s), dpr * (oy - region.y * s));
    ctx.save();
    ctx.beginPath();
    ctx.rect(region.x, region.y, region.w, region.h);
    ctx.clip();
    peDrawScene(ctx, img, model, strokeRef.current);
    ctx.restore();
    if (tool === "crop" && draft) {
      // Затемнение вне рамки, сетка третей и ручки — в экранных координатах.
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const r = { x: ox + (draft.x - region.x) * s, y: oy + (draft.y - region.y) * s,
                  w: draft.w * s, h: draft.h * s };
      const iw = region.w * s, ih = region.h * s;
      ctx.fillStyle = "rgba(0,0,0,0.6)";
      ctx.fillRect(ox, oy, iw, r.y - oy);
      ctx.fillRect(ox, r.y + r.h, iw, oy + ih - (r.y + r.h));
      ctx.fillRect(ox, r.y, r.x - ox, r.h);
      ctx.fillRect(r.x + r.w, r.y, ox + iw - (r.x + r.w), r.h);
      ctx.strokeStyle = "rgba(255,255,255,0.35)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let i = 1; i < 3; i++) {
        ctx.moveTo(r.x + (r.w * i) / 3, r.y); ctx.lineTo(r.x + (r.w * i) / 3, r.y + r.h);
        ctx.moveTo(r.x, r.y + (r.h * i) / 3); ctx.lineTo(r.x + r.w, r.y + (r.h * i) / 3);
      }
      ctx.stroke();
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 2;
      ctx.strokeRect(r.x, r.y, r.w, r.h);
      ctx.fillStyle = "#fff";
      for (const [hx, hy] of peHandles(r)) ctx.fillRect(hx - 5, hy - 5, 10, 10);
    }
  }

  useEffectP(() => { redraw(); });

  function peHandles(r) {
    const pts = [[r.x, r.y], [r.x + r.w, r.y], [r.x, r.y + r.h], [r.x + r.w, r.y + r.h]];
    if (!ratio) pts.push([r.x + r.w / 2, r.y], [r.x + r.w / 2, r.y + r.h],
                         [r.x, r.y + r.h / 2], [r.x + r.w, r.y + r.h / 2]);
    return pts;
  }

  function toModel(e) {
    const rect = canvasRef.current.getBoundingClientRect();
    const v = viewRef.current;
    const px = e.clientX - rect.left, py = e.clientY - rect.top;
    return { mx: (px - v.ox) / v.s + v.region.x, my: (py - v.oy) / v.s + v.region.y, px, py };
  }

  function scheduleRedraw() {
    if (rafRef.current) return;
    rafRef.current = requestAnimationFrame(() => { rafRef.current = 0; redraw(); });
  }

  function onPointerDown(e) {
    if (!img || busy) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const { mx, my, px, py } = toModel(e);
    if (tool === "brush") {
      const region = model.crop || full;
      if (mx < region.x || my < region.y || mx > region.x + region.w || my > region.y + region.h) return;
      const width = Math.max(2, Math.max(size.w, size.h) * PE_SIZES[sizeIdx]);
      strokeRef.current = { color, width, points: [[mx, my]] };
      scheduleRedraw();
      return;
    }
    if (tool === "crop" && draft) {
      const v = viewRef.current;
      const r = { x: v.ox + (draft.x - v.region.x) * v.s, y: v.oy + (draft.y - v.region.y) * v.s,
                  w: draft.w * v.s, h: draft.h * v.s };
      const near = (a, b) => Math.abs(a - b) <= PE_HANDLE;
      const edges = { l: near(px, r.x), r: near(px, r.x + r.w), t: near(py, r.y), b: near(py, r.y + r.h) };
      const midX = px > r.x + PE_HANDLE && px < r.x + r.w - PE_HANDLE;
      const midY = py > r.y + PE_HANDLE && py < r.y + r.h - PE_HANDLE;
      const inY = py >= r.y - PE_HANDLE && py <= r.y + r.h + PE_HANDLE;
      const inX = px >= r.x - PE_HANDLE && px <= r.x + r.w + PE_HANDLE;
      let mode = null;
      const corner = (edges.l || edges.r) && (edges.t || edges.b);
      if (corner) mode = { l: edges.l, r: edges.r && !edges.l, t: edges.t, b: edges.b && !edges.t };
      else if (!ratio && (edges.l || edges.r) && midY) mode = { l: edges.l, r: edges.r && !edges.l };
      else if (!ratio && (edges.t || edges.b) && midX) mode = { t: edges.t, b: edges.b && !edges.t };
      else if (inX && inY && px > r.x && px < r.x + r.w && py > r.y && py < r.y + r.h) mode = { move: true };
      if (mode) dragRef.current = { mode, start: [mx, my], rect: draft };
    }
  }

  function onPointerMove(e) {
    if (strokeRef.current) {
      const { mx, my } = toModel(e);
      const pts = strokeRef.current.points;
      const [lx, ly] = pts[pts.length - 1];
      if (Math.hypot(mx - lx, my - ly) * viewRef.current.s >= 1.5) {
        pts.push([mx, my]);
        scheduleRedraw();
      }
      return;
    }
    const d = dragRef.current;
    if (!d) return;
    const { mx, my } = toModel(e);
    const dx = mx - d.start[0], dy = my - d.start[1];
    const minM = PE_MIN_CROP / viewRef.current.s;
    const r0 = d.rect;
    if (d.mode.move) {
      setDraft(peClampRect({ ...r0, x: r0.x + dx, y: r0.y + dy }, size.w, size.h, minM, minM));
      return;
    }
    let l = r0.x, t = r0.y, r = r0.x + r0.w, b = r0.y + r0.h;
    if (d.mode.l) l = Math.min(Math.max(0, l + dx), r - minM);
    if (d.mode.r) r = Math.max(Math.min(size.w, r + dx), l + minM);
    if (d.mode.t) t = Math.min(Math.max(0, t + dy), b - minM);
    if (d.mode.b) b = Math.max(Math.min(size.h, b + dy), t + minM);
    if (ratio) {
      // Угол с фиксированной пропорцией: высота следует за шириной, а если
      // упёрлись в край — ширина за высотой.
      let w = r - l, h = w / ratio;
      const maxH = d.mode.t ? b : size.h - t;
      if (h > maxH) { h = maxH; w = h * ratio; }
      if (d.mode.l) l = r - w; else r = l + w;
      if (d.mode.t) t = b - h; else b = t + h;
    }
    setDraft({ x: l, y: t, w: r - l, h: b - t });
  }

  function onPointerUp() {
    if (strokeRef.current) {
      const stroke = strokeRef.current;
      strokeRef.current = null;
      commit({ ...model, strokes: [...model.strokes, stroke] });
    }
    dragRef.current = null;
  }

  function enterCrop() {
    setDraft(model.crop || full);
    setTool("crop");
  }

  function applyCrop() {
    const d = draft;
    const isFull = !d || (d.x < 1 && d.y < 1 && d.w > size.w - 1 && d.h > size.h - 1);
    const next = isFull ? null : { x: Math.round(d.x), y: Math.round(d.y),
                                   w: Math.round(d.w), h: Math.round(d.h) };
    if (JSON.stringify(next) !== JSON.stringify(model.crop)) commit({ ...model, crop: next });
    setTool("brush");
  }

  function pickRatio(value) {
    setRatio(value);
    setDraft((d) => peClampRect(peFitRatio(d || full, value), size.w, size.h, 1, 1));
  }

  function rotate() {
    const h = size.h;
    commit({
      rotation: (model.rotation + 90) % 360,
      crop: peRotRect(model.crop, h),
      strokes: model.strokes.map((s) => ({ ...s, points: s.points.map((p) => peRotPoint(p, h)) })),
    });
    if (tool === "crop") {
      // Пропорция рамки поворачивается вместе с картинкой.
      setDraft((d) => peRotRect(d || full, h));
      if (ratio) setRatio(null);
    }
  }

  async function finish() {
    if (!img) return;
    // Рамка, которую тянули, но не применили, — применяется при «Готово».
    const m = tool === "crop" && draft
      ? { ...model, crop: (draft.x < 1 && draft.y < 1 && draft.w > size.w - 1 && draft.h > size.h - 1)
            ? null : draft }
      : model;
    if (!m.rotation && !m.crop && !m.strokes.length) { onDone(file); return; }
    setBusy(true);
    try {
      const region = m.crop || full;
      const k = Math.min(1, PE_MAX_SIDE / Math.max(region.w, region.h));
      const out = document.createElement("canvas");
      out.width = Math.max(1, Math.round(region.w * k));
      out.height = Math.max(1, Math.round(region.h * k));
      const ctx = out.getContext("2d");
      ctx.setTransform(k, 0, 0, k, -region.x * k, -region.y * k);
      peDrawScene(ctx, img, m, null);
      const png = file.type === "image/png";
      const blob = await new Promise((res) => out.toBlob(res, png ? "image/png" : "image/jpeg", 0.92));
      if (!blob) throw new Error("toBlob");
      const base = (file.name || "image").replace(/\.[^.]+$/, "");
      onDone(new File([blob], base + (png ? ".png" : ".jpg"), { type: blob.type }));
    } catch {
      setBusy(false);
      onDone(file);
    }
  }

  const btn = "px-3 py-1.5 rounded-lg text-sm transition disabled:opacity-40";
  const toolBtn = (active) => "flex flex-col items-center gap-1 px-3 py-1.5 rounded-lg text-[11px] transition " +
    (active ? "text-[#7BA8F9] bg-[#4F8EF7]/15" : "text-[#9ca3af] hover:text-[#f1f1f5] hover:bg-[#1a1a24]");
  const changed = model.rotation || model.crop || model.strokes.length;

  return (
    <ModalOverlay onClose={busy ? null : onCancel} zIndex={70} className="bg-black/85">
      <div className="w-full h-full sm:w-[min(1100px,96vw)] sm:h-[min(820px,94vh)] bg-[#0d0d12] sm:border sm:border-[#2a2a3a] sm:rounded-xl flex flex-col overflow-hidden"
           style={{ paddingTop: "env(safe-area-inset-top)", paddingBottom: "env(safe-area-inset-bottom)" }}>
        <div className="flex items-center gap-2 px-3 py-2.5 border-b border-[#2a2a3a] shrink-0">
          <button onClick={onCancel} disabled={busy} className={btn + " text-[#9ca3af] hover:text-[#f1f1f5] hover:bg-[#1a1a24]"}>Отмена</button>
          <div className="flex-1 text-center text-sm font-semibold text-[#f1f1f5] truncate">Редактор фото</div>
          <button onClick={() => onDone(file)} disabled={busy}
            className={btn + " hidden sm:inline-block text-[#9ca3af] hover:text-[#f1f1f5] hover:bg-[#1a1a24]"}>Без правок</button>
          <button onClick={finish} disabled={busy || !img}
            className={btn + " font-semibold bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white"}>
            {busy ? "Сохранение…" : "Готово"}
          </button>
        </div>

        <div ref={wrapRef} className="relative flex-1 min-h-0 bg-[#08080b]">
          {loadErr ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-sm text-[#9ca3af] p-6 text-center">
              Браузер не смог открыть эту картинку для редактирования.
              <button onClick={() => onDone(file)} className={btn + " bg-[#4F8EF7] text-white"}>Отправить как есть</button>
            </div>
          ) : (
            <canvas ref={canvasRef}
              onPointerDown={onPointerDown} onPointerMove={onPointerMove}
              onPointerUp={onPointerUp} onPointerCancel={onPointerUp}
              className={"absolute inset-0 " + (tool === "brush" ? "cursor-crosshair" : "cursor-move")}
              style={{ touchAction: "none" }} />
          )}
          {!img && !loadErr && (
            <div className="absolute inset-0 flex items-center justify-center text-sm text-[#6b7280]">Загрузка…</div>
          )}
        </div>

        <div className="shrink-0 border-t border-[#2a2a3a] bg-[#13131a]">
          <div className="flex items-center justify-center gap-2 flex-wrap px-3 py-2 min-h-[48px]">
            {tool === "brush" ? (
              <>
                {PE_COLORS.map((c) => (
                  <button key={c} onClick={() => setColor(c)} aria-label={"Цвет " + c}
                    className={"w-7 h-7 rounded-full border-2 transition " +
                      (color === c ? "border-white scale-110" : "border-[#2a2a3a]")}
                    style={{ background: c }} />
                ))}
                <div className="w-px h-6 bg-[#2a2a3a] mx-1" />
                {PE_SIZES.map((_, i) => (
                  <button key={i} onClick={() => setSizeIdx(i)} aria-label={"Толщина " + (i + 1)}
                    className={"w-8 h-8 rounded-lg flex items-center justify-center transition " +
                      (sizeIdx === i ? "bg-[#4F8EF7]/20" : "hover:bg-[#1a1a24]")}>
                    <span className="rounded-full" style={{ background: color, width: 4 + i * 5, height: 4 + i * 5 }} />
                  </button>
                ))}
              </>
            ) : (
              <>
                {PE_RATIOS.map(([label, value]) => (
                  <button key={label} onClick={() => pickRatio(value)}
                    className={"px-2.5 py-1 rounded-full text-xs border transition " +
                      (ratio === value ? "bg-[#4F8EF7]/15 text-[#7BA8F9] border-[#4F8EF7]/40"
                                       : "text-[#9ca3af] border-[#2a2a3a] hover:text-[#f1f1f5]")}>
                    {label}
                  </button>
                ))}
                <div className="w-px h-6 bg-[#2a2a3a] mx-1" />
                <button onClick={() => { setRatio(null); setDraft(full); }}
                  className="px-2.5 py-1 rounded-full text-xs text-[#9ca3af] hover:text-[#f1f1f5]">Сбросить</button>
                <button onClick={applyCrop}
                  className="px-3 py-1 rounded-full text-xs font-semibold bg-[#4F8EF7] text-white">Применить</button>
              </>
            )}
          </div>
          <div className="flex items-center justify-center gap-1 px-3 pb-2">
            <button onClick={() => (tool === "crop" ? applyCrop() : null)} className={toolBtn(tool === "brush")}>
              <Icon name="brush" className="w-5 h-5" />Кисть
            </button>
            <button onClick={() => (tool === "crop" ? applyCrop() : enterCrop())} className={toolBtn(tool === "crop")}>
              <Icon name="crop" className="w-5 h-5" />Обрезать
            </button>
            <button onClick={rotate} disabled={!img} className={toolBtn(false)}>
              <Icon name="rotate" className="w-5 h-5" />Повернуть
            </button>
            <button onClick={undo} disabled={tool === "brush" && !history.length}
              className={toolBtn(false) + " disabled:opacity-30"}>
              <Icon name="undo" className="w-5 h-5" />Отменить
            </button>
            <button onClick={() => onDone(file)} disabled={busy}
              className={toolBtn(false) + " sm:hidden"}>
              <Icon name="x" className="w-5 h-5" />Как есть
            </button>
          </div>
          {changed ? null : (
            <div className="hidden sm:block text-center text-[11px] text-[#6b7280] pb-2">
              Рисуйте прямо на картинке · Ctrl+Z — отменить
            </div>
          )}
        </div>
      </div>
    </ModalOverlay>
  );
}
