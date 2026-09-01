// Reusable UI components

const { useState, useEffect, useRef, useMemo } = React;

// Generic avatar circle with initials or real photo
function Avatar({ initials, color, size = 36, ring = false, photoUrl = null }) {
  const [imgError, setImgError] = useState(false);
  const ringCls = ring ? "ring-2 ring-[#13131a]" : "";

  if (photoUrl && !imgError) {
    return (
      <img
        src={photoUrl}
        alt={initials}
        className={"rounded-full shrink-0 object-cover " + ringCls}
        style={{ width: size, height: size }}
        onError={() => setImgError(true)}
      />
    );
  }
  return (
    <div
      className={"flex items-center justify-center rounded-full text-white font-medium shrink-0 " + ringCls}
      style={{ width: size, height: size, background: color, fontSize: size * 0.38 }}
    >
      {initials}
    </div>
  );
}

function StatusBadge({ status }) {
  const map = {
    ai: { label: "ИИ", cls: "bg-[#4F8EF7]/15 text-[#7BA8F9] border-[#4F8EF7]/30" },
    queue: { label: "Очередь", cls: "bg-[#f97316]/15 text-[#f97316] border-[#f97316]/30" },
    in_progress: { label: "В работе", cls: "bg-[#eab308]/15 text-[#eab308] border-[#eab308]/30" },
    waiting: { label: "Ожидание", cls: "bg-[#A855F7]/15 text-[#c084fc] border-[#A855F7]/30" },
    closed: { label: "Закрыт", cls: "bg-zinc-500/15 text-zinc-400 border-zinc-600/40" },
    // legacy rows that predate the ai/queue/waiting model
    new: { label: "Новый", cls: "bg-[#4F8EF7]/15 text-[#7BA8F9] border-[#4F8EF7]/30" },
  };
  const cfg = map[status] || map.queue;
  return (
    <span className={"inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium border " + cfg.cls}>
      {cfg.label}
    </span>
  );
}

// Waiting-reason label: why the ticket sits in «Ожидание»
// operator_replied → blue «ждём ответ» (ball is on the client's side)
// manual → red «клиент ждёт ответ» (operator paused it, client is owed an answer)
function WaitingLabel({ reason }) {
  if (!reason) return null;
  const cfg = reason === "manual"
    ? { label: "клиент ждёт ответ", cls: "bg-[#ef4444]/15 text-[#ef4444] border-[#ef4444]/30" }
    : { label: "ждём ответ", cls: "bg-[#4F8EF7]/15 text-[#7BA8F9] border-[#4F8EF7]/30" };
  return (
    <span className={"inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium border whitespace-nowrap " + cfg.cls}>
      {cfg.label}
    </span>
  );
}

// Accumulated time the ticket has spent «В работе» (SLA); ticks only while
// slaStartedAt is set (i.e. the ticket is in_progress right now).
function fmtSla(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(sec).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

function SlaTimer({ slaSeconds, slaStartedAt, className = "" }) {
  const running = !!slaStartedAt;
  // Each running timer ticks itself — idle cards never re-render.
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setTick((v) => v + 1), 1000);
    return () => clearInterval(t);
  }, [running]);
  const base = slaSeconds || 0;
  const extra = running ? Math.max(0, (Date.now() - Date.parse(slaStartedAt)) / 1000) : 0;
  const total = base + extra;
  if (!running && total === 0) return null;
  const cls = running ? "text-[#eab308]" : "text-zinc-500";
  return (
    <span className={"inline-flex items-center gap-1 text-[11px] font-medium tabular-nums " + cls + " " + className}
          title="Время в работе (SLA)">
      <Icon name="clock" className="w-3 h-3" />
      {fmtSla(total)}
    </span>
  );
}

// «16:12 - 25.02.2026» — формат, в котором операторы читают время последнего
// визита коллеги. Он же используется в ленте действий клиента.
function fmtDateTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())} - ` +
         `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}`;
}

// Присутствие оператора. Раньше здесь стояло «Офлайн», из которого не понять,
// ждать человека или забирать тикет; теперь видно, когда он был в сети.
function PresenceLabel({ online, paused, lastSeen, className = "" }) {
  const state = online
    ? (paused
        ? { dot: "bg-[#eab308]", text: "text-[#eab308]", label: "На паузе" }
        : { dot: "bg-[#22c55e]", text: "text-[#22c55e]", label: "Онлайн" })
    : { dot: "bg-zinc-600", text: "text-[#6b7280]",
        label: lastSeen ? `был в сети ${fmtDateTime(lastSeen)}` : "не заходил" };
  return (
    <span className={"inline-flex items-center gap-1.5 text-xs min-w-0 " + className}>
      <span className={"w-1.5 h-1.5 rounded-full shrink-0 " + state.dot}></span>
      <span className={state.text + " truncate"}>{state.label}</span>
    </span>
  );
}

function PlanBadge({ plan }) {
  const map = {
    Pro: "bg-gradient-to-r from-[#A855F7] to-[#4F8EF7] text-white",
    Basic: "bg-[#1f2a44] text-[#7BA8F9] border border-[#4F8EF7]/30",
    Trial: "bg-[#3d3320] text-[#eab308] border border-[#eab308]/30",
  };
  return (
    <span className={"inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold " + (map[plan] || map.Basic)}>
      {plan}
    </span>
  );
}

function SubStatus({ status }) {
  const map = {
    active: { label: "Активна", color: "text-[#22c55e]", dot: "bg-[#22c55e]" },
    expiring: { label: "Истекает", color: "text-[#eab308]", dot: "bg-[#eab308]" },
    blocked: { label: "Заблокирована", color: "text-[#ef4444]", dot: "bg-[#ef4444]" },
  };
  const cfg = map[status] || map.active;
  return (
    <span className={"inline-flex items-center gap-1.5 text-xs font-medium " + cfg.color}>
      <span className={"w-1.5 h-1.5 rounded-full " + cfg.dot}></span>
      {cfg.label}
    </span>
  );
}

// Icons (inline SVG, stroke-based)
function Icon({ name, className = "w-4 h-4", strokeWidth = 1.75 }) {
  const paths = {
    search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3-3" /></>,
    bell: <><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10 21a2 2 0 0 0 4 0" /></>,
    menu: <><path d="M3 6h18M3 12h18M3 18h18" /></>,
    send: <><path d="m22 2-7 20-4-9-9-4Z" /><path d="M22 2 11 13" /></>,
    paperclip: <><path d="m21 12-9.5 9.5a5 5 0 0 1-7-7L13 5a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L15 7" /></>,
    chevronDown: <><path d="m6 9 6 6 6-6" /></>,
    chevronRight: <><path d="m9 6 6 6-6 6" /></>,
    x: <><path d="M18 6 6 18M6 6l12 12" /></>,
    check: <><path d="M20 6 9 17l-5-5" /></>,
    plus: <><path d="M12 5v14M5 12h14" /></>,
    edit: <><path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z" /></>,
    trash: <><path d="M3 6h18" /><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /><path d="m19 6-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /></>,
    chat: <><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></>,
    chart: <><path d="M3 3v18h18" /><path d="m7 14 4-4 4 4 5-6" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></>,
    bellRing: <><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10 21a2 2 0 0 0 4 0" /></>,
    image: <><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="9" cy="9" r="2" /><path d="m21 15-5-5L5 21" /></>,
    sparkles: <><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" /></>,
    user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
    refresh: <><path d="M3 12a9 9 0 0 1 15-6.7L21 8" /><path d="M21 3v5h-5" /><path d="M21 12a9 9 0 0 1-15 6.7L3 16" /><path d="M3 21v-5h5" /></>,
    key: <><circle cx="7.5" cy="15.5" r="4.5" /><path d="m21 2-9.6 9.6" /><path d="m15.5 7.5 3 3L22 7l-3-3" /></>,
    plus2: <><path d="M12 5v14M5 12h14" /></>,
    arrowLeft: <><path d="M19 12H5" /><path d="m12 19-7-7 7-7" /></>,
    arrowRight: <><path d="M5 12h14" /><path d="m12 5 7 7-7 7" /></>,
    calendar: <><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></>,
    operators: <><circle cx="9" cy="8" r="4" /><path d="M3 21a6 6 0 0 1 12 0" /><circle cx="17" cy="9" r="3" /><path d="M21 19a4 4 0 0 0-4-4" /></>,
    book: <><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    server:    <><rect x="2" y="2" width="20" height="8" rx="2" /><rect x="2" y="14" width="20" height="8" rx="2" /><path d="M6 6h.01M6 18h.01" /></>,
    zap:       <><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" /></>,
    megaphone: <><path d="M3 11v2" /><path d="M11.5 5.5L19 3v18l-7.5-2.5" /><path d="M11.5 5.5v13" /><path d="M3 11a2 2 0 0 0 0 4v-4z" /></>,
    template:  <><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" /><rect x="9" y="3" width="6" height="4" rx="1" /><path d="M9 12h6M9 16h4" /></>,
    link:      <><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" /><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" /></>,
    grid:      <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    info:      <><circle cx="12" cy="12" r="9" /><path d="M12 16v-4M12 8h.01" /></>,
    dots:      <><circle cx="12" cy="5" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="12" cy="19" r="1.6" /></>,
    pause:     <><rect x="6" y="4" width="4" height="16" rx="1" /><rect x="14" y="4" width="4" height="16" rx="1" /></>,
    logout:    <><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="m16 17 5-5-5-5" /><path d="M21 12H9" /></>,
    lock:      <><rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></>,
    handRaise: <><path d="M12 11V4.5a1.5 1.5 0 0 1 3 0V12" /><path d="M9 12V6.5a1.5 1.5 0 0 0-3 0V14a7 7 0 0 0 7 7h1a6 6 0 0 0 6-6v-4.5a1.5 1.5 0 0 0-3 0" /></>,
  };
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" className={className}>
      {paths[name]}
    </svg>
  );
}

// ── Переключатель ВПН-сервисов ───────────────────────────────────────────────
// Ряд пилюль под шапкой: слева «Все сервисы» с суммарным счётчиком, дальше по
// пилюле на каждый ВПН — точка фирменного цвета, название и счётчик активных
// обращений («новые + непрочитанные»). Нулевой счётчик не рисуется.
// currentServiceId === null означает режим «Все сервисы».

function ServicePill({ service, count, active, onClick, allMode = false }) {
  return (
    <button
      onClick={onClick}
      title={service?.name}
      className={
        "shrink-0 flex items-center gap-2 pl-2.5 pr-2 py-1.5 rounded-lg text-sm font-medium transition border " +
        (active
          ? "bg-[#1a1a24] text-[#f1f1f5] border-[#3a3a4a]"
          : "text-[#9ca3af] hover:text-[#f1f1f5] hover:bg-[#1a1a24]/60 border-transparent")
      }
    >
      {allMode ? (
        <span className="whitespace-nowrap">Все сервисы</span>
      ) : (
        <>
          <span className="w-2 h-2 rounded-full shrink-0" style={{ background: service.color }}></span>
          <span className="whitespace-nowrap">{service.emoji ? service.emoji + " " : ""}{service.name}</span>
        </>
      )}
      {count > 0 && (
        <span className={
          "min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-bold flex items-center justify-center " +
          (allMode ? "bg-[#2a2a3a] text-[#9ca3af]" : "bg-[#ef4444] text-white")
        }>
          {count}
        </span>
      )}
    </button>
  );
}

function ServiceSwitcher({ services, currentServiceId, onSelect, activeService, aiPromptPreview }) {
  // Один сервис — переключать нечего, ряд не занимает место.
  if (!services || services.length < 2) return null;
  const total = services.reduce((sum, s) => sum + (s.activeCount || 0), 0);
  return (
    <div className="shrink-0 bg-[#13131a] border-b border-[#2a2a3a] relative z-20">
      <div className="flex items-center gap-1 px-3 py-2 overflow-x-auto scrollbar-thin">
        <ServicePill allMode count={total} active={currentServiceId === null}
                     onClick={() => onSelect(null)} />
        <div className="w-px h-5 bg-[#2a2a3a] mx-1 shrink-0"></div>
        {services.map((s) => (
          <ServicePill key={s.id} service={s} count={s.activeCount || 0}
                       active={currentServiceId === s.id} onClick={() => onSelect(s.id)} />
        ))}
      </div>
      <div className="flex items-center gap-2 px-3 pb-2 overflow-x-auto scrollbar-thin text-[11px]">
        {activeService ? (
          <>
            <ContextChip label="Активен" value={activeService.name} dot={activeService.color} strong />
            <ContextChip label="База знаний" value={activeService.qdrantCollection} mono />
            {aiPromptPreview && <ContextChip label="Промпт ИИ" value={aiPromptPreview} />}
            <ContextChip label="Новых" value={String(activeService.activeCount || 0)} accent />
          </>
        ) : (
          <ContextChip label="Все сервисы" value={`${services.length} шт · ${total} обращений`} />
        )}
      </div>
    </div>
  );
}

function ContextChip({ label, value, dot, mono, strong, accent }) {
  return (
    <span className="shrink-0 inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-[#0d0d12] border border-[#2a2a3a]/70">
      {dot && <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: dot }}></span>}
      <span className="text-[#6b7280]">{label}:</span>
      <span className={
        "max-w-[220px] truncate " +
        (accent ? "text-[#ef4444] font-semibold " : strong ? "text-[#f1f1f5] font-semibold " : "text-[#d1d1d8] ") +
        (mono ? "font-mono" : "")
      }>
        {value}
      </span>
    </span>
  );
}

// Точка цвета сервиса — метка в списке диалогов в режиме «Все сервисы».
function ServiceDot({ color, name }) {
  if (!color) return null;
  return (
    <span title={name} className="w-2 h-2 rounded-full shrink-0" style={{ background: color }}></span>
  );
}

// ── Мобильная адаптация ──────────────────────────────────────────────────────
// Раскладка ветвится по трём брейкпоинтам. Одна кодовая база: карточки, пузыри
// и панели те же, меняется только их размещение.

const VIEWPORT_MOBILE_MAX = 699.98;   // телефон
const VIEWPORT_TABLET_MAX = 1099.98;  // планшет и узкое окно на десктопе

function readViewport() {
  if (typeof window === "undefined") return "desktop";
  const w = window.innerWidth;
  return w <= VIEWPORT_MOBILE_MAX ? "mobile" : w <= VIEWPORT_TABLET_MAX ? "tablet" : "desktop";
}

// matchMedia вместо ручного resize: событие приходит только при переходе через
// границу, а не на каждый пиксель перетаскивания окна.
function useViewport() {
  const [mode, setMode] = useState(readViewport);
  useEffect(() => {
    const mq = [
      window.matchMedia(`(max-width: ${VIEWPORT_MOBILE_MAX}px)`),
      window.matchMedia(`(max-width: ${VIEWPORT_TABLET_MAX}px)`),
    ];
    const onChange = () => setMode(readViewport());
    mq.forEach((m) => m.addEventListener("change", onChange));
    onChange();
    return () => mq.forEach((m) => m.removeEventListener("change", onChange));
  }, []);
  return {
    mode,
    isMobile:  mode === "mobile",
    isTablet:  mode === "tablet",
    isDesktop: mode === "desktop",
    // Карточка клиента и меню действий уезжают в шторку и на планшете тоже.
    isCompact: mode !== "desktop",
  };
}

// Читаемый цвет поверх фирменного цвета сервиса.
function contrastOn(hex) {
  if (!hex || hex[0] !== "#" || hex.length < 7) return "#fff";
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return (r * 299 + g * 587 + b * 114) / 1000 > 150 ? "#0d0d12" : "#fff";
}

// Подложка модального окна. Закрывает окно только если на ней прошли ОБА
// события мыши — и нажатие, и отпускание. Прежний вариант ловил `click`, а он
// всплывает до общего предка: выделение текста в поле, законченное за краем
// формы, читалось как клик по подложке, и окно закрывалось с набранным.
// Escape закрывает всегда — раньше это умела только шторка.
function ModalOverlay({ onClose, zIndex = 50, className = "", children }) {
  const downOnBackdrop = useRef(false);

  useEffect(() => {
    if (!onClose) return;
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      style={{ zIndex }}
      onMouseDown={(e) => { downOnBackdrop.current = e.target === e.currentTarget; }}
      onMouseUp={(e) => {
        if (downOnBackdrop.current && e.target === e.currentTarget && onClose) onClose();
        downOnBackdrop.current = false;
      }}
      className={"fixed inset-0 backdrop-blur-sm flex items-center justify-center " +
        (className || "bg-black/60 p-4")}
    >
      {children}
    </div>
  );
}

// Шторка снизу: затемнение, «грабер», закрытие по свайпу вниз, тапу вне и Esc.
// Общая для карточки клиента, выбора сервиса и меню действий над тикетом.
function BottomSheet({ open, onClose, title, subtitle, children, maxHeight = "88%" }) {
  const [mounted, setMounted] = useState(open);
  const [shown, setShown] = useState(false);
  const [dragY, setDragY] = useState(0);
  const dragging = useRef(false);
  const startY = useRef(0);

  useEffect(() => {
    if (open) {
      setMounted(true);
      setDragY(0);
      const t = requestAnimationFrame(() => setShown(true));
      return () => cancelAnimationFrame(t);
    }
    setShown(false);
    // Размонтируем после анимации ухода, иначе шторка исчезает рывком.
    const t = setTimeout(() => setMounted(false), 280);
    return () => clearTimeout(t);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onClose && onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!mounted) return null;

  const onTouchStart = (e) => {
    dragging.current = true;
    startY.current = e.touches[0].clientY;
  };
  const onTouchMove = (e) => {
    if (!dragging.current) return;
    setDragY(Math.max(0, e.touches[0].clientY - startY.current));
  };
  const onTouchEnd = () => {
    dragging.current = false;
    // Больше трети «грабера пути» — считаем жест закрытием.
    if (dragY > 90) onClose && onClose();
    setDragY(0);
  };

  const transform = shown
    ? (dragY ? `translateY(${dragY}px)` : "none")
    : "translateY(101%)";

  return (
    <>
      <div
        onClick={onClose}
        className={"fixed inset-0 z-[60] bg-[#030306]/70 transition-opacity duration-200 " +
          (shown ? "opacity-100" : "opacity-0 pointer-events-none")}
      ></div>
      <div
        role="dialog"
        aria-modal="true"
        className="fixed left-0 right-0 bottom-0 z-[61] bg-[#13131a] border-t border-[#2a2a3a] rounded-t-[22px] flex flex-col shadow-2xl"
        style={{
          transform,
          transition: dragY ? "none" : "transform .28s cubic-bezier(.32,.72,0,1)",
          maxHeight,
          paddingBottom: "env(safe-area-inset-bottom)",
        }}
      >
        <div onTouchStart={onTouchStart} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd}
             className="shrink-0 pt-2 pb-1.5 cursor-grab">
          <div className="w-9 h-1 rounded-full bg-[#3a3a4a] mx-auto"></div>
        </div>
        {(title || subtitle) && (
          <div className="shrink-0 px-[18px] pt-1.5 pb-3 flex items-baseline justify-between gap-2.5">
            <h3 className="text-[17px] font-semibold text-[#f1f1f5] truncate">{title}</h3>
            {subtitle && <span className="text-xs text-[#6b7280] shrink-0">{subtitle}</span>}
          </div>
        )}
        <div className="overflow-y-auto scrollbar-thin pb-4">{children}</div>
      </div>
    </>
  );
}

// Лента сервисов на мобильном: плитка 44×44 со счётчиком, подпись под ней,
// первая плитка «Все» пунктиром. Данные те же, что у ServiceSwitcher.
function ServiceTile({ service, count, active, onClick, allMode = false }) {
  const color = service?.color || "#4F8EF7";
  const letter = service ? (service.emoji || (service.name || "?").trim()[0].toUpperCase()) : "";
  return (
    <button onClick={onClick} title={allMode ? "Все сервисы" : service?.name}
            className="shrink-0 w-[62px] flex flex-col items-center gap-1.5 py-0.5">
      <span
        className={"relative w-11 h-11 rounded-[14px] flex items-center justify-center font-bold text-[15px] " +
          (allMode ? "bg-[#202030] border-[1.5px] border-dashed border-[#33334a] text-[#9095a3]" : "")}
        style={allMode ? undefined : {
          background: color,
          color: contrastOn(color),
          boxShadow: active ? `0 0 0 2px #13131a, 0 0 0 4px ${color}` : undefined,
        }}
      >
        {allMode ? <Icon name="grid" className="w-[18px] h-[18px]" strokeWidth={1.9} /> : letter}
        {count > 0 && (
          <span className={"absolute -top-1 -right-1 min-w-[17px] h-[17px] px-1 rounded-full text-white text-[10px] font-bold flex items-center justify-center ring-2 ring-[#13131a] " +
            (allMode ? "bg-[#6b7280]" : "bg-[#ef4444]")}>
            {count}
          </span>
        )}
      </span>
      <span className={"text-[10.5px] max-w-[60px] truncate " +
        (active ? "text-[#f1f1f5] font-semibold" : "text-[#6b7280]")}>
        {allMode ? "Все" : service.name}
      </span>
    </button>
  );
}

function ServiceRail({ services, currentServiceId, onSelect }) {
  if (!services || services.length < 2) return null;
  const total = services.reduce((sum, s) => sum + (s.activeCount || 0), 0);
  return (
    <div className="shrink-0 flex gap-[3px] px-2 py-2.5 bg-[#13131a] border-b border-[#2a2a3a] overflow-x-auto no-scrollbar">
      <ServiceTile allMode count={total} active={currentServiceId === null}
                   onClick={() => onSelect(null)} />
      {services.map((s) => (
        <ServiceTile key={s.id} service={s} count={s.activeCount || 0}
                     active={currentServiceId === s.id} onClick={() => onSelect(s.id)} />
      ))}
    </div>
  );
}

// Шапка мобильного экрана: слева либо логотип, либо «назад».
// leading — что показать слева, когда кнопка «назад» не нужна (например,
// аватар клиента в двухколоночной раскладке планшета).
function MobileAppBar({ title, subtitle, onBack, right, leading }) {
  return (
    <header className="shrink-0 min-h-[52px] flex items-center gap-2.5 px-2.5 py-1.5 bg-[#13131a] border-b border-[#2a2a3a]">
      {onBack ? (
        <button onClick={onBack} aria-label="Назад"
                className="w-11 h-11 shrink-0 rounded-xl flex items-center justify-center text-[#f1f1f5] active:bg-[#1a1a24]">
          <Icon name="arrowLeft" className="w-[22px] h-[22px]" />
        </button>
      ) : leading ? leading : (
        <div className="w-[30px] h-[30px] shrink-0 rounded-[9px] bg-gradient-to-br from-[#4F8EF7] to-[#A855F7] flex items-center justify-center text-white text-[13px] font-bold">Х</div>
      )}
      <div className="flex-1 min-w-0">
        <div className="text-base font-semibold text-[#f1f1f5] truncate leading-tight">{title}</div>
        {subtitle && <div className="text-[11px] text-[#6b7280] truncate">{subtitle}</div>}
      </div>
      {right}
    </header>
  );
}

// Круглая кнопка шапки с необязательным бейджем.
function AppBarButton({ icon, label, badge, onClick, tone = "muted" }) {
  return (
    <button onClick={onClick} aria-label={label} title={label}
            className={"relative w-11 h-11 shrink-0 rounded-xl flex items-center justify-center active:bg-[#1a1a24] " +
              (tone === "accent" ? "text-[#7BA8F9]" : "text-[#9095a3]")}>
      <Icon name={icon} className="w-5 h-5" />
      {badge > 0 && (
        <span className="absolute top-1.5 right-1.5 min-w-[16px] h-4 px-1 rounded-full bg-[#ef4444] text-white text-[10px] font-bold flex items-center justify-center ring-2 ring-[#13131a]">
          {badge}
        </span>
      )}
    </button>
  );
}

// Нижняя навигация. «Статистика» — только у админа, как и в TopBar.
function MobileNav({ screen, setScreen, badge = 0, isAdmin = false }) {
  const items = [
    { id: "dialogs",  label: "Диалоги",    icon: "chat"     },
    { id: "health",   label: "Состояние",  icon: "server"   },
    { id: "stats",    label: "Статистика", icon: "chart"    },
    { id: "settings", label: "Настройки",  icon: "settings" },
  ].filter((i) => i.id !== "stats" || isAdmin);
  return (
    <nav aria-label="Основная навигация"
         className="shrink-0 flex bg-[#13131a] border-t border-[#2a2a3a] px-1 pt-1.5"
         style={{ paddingBottom: "calc(10px + env(safe-area-inset-bottom))" }}>
      {items.map((it) => (
        <button key={it.id} onClick={() => setScreen(it.id)}
                className={"flex-1 min-h-[44px] py-1.5 flex flex-col items-center gap-0.5 relative " +
                  (screen === it.id ? "text-[#4F8EF7]" : "text-[#6b7280]")}>
          <Icon name={it.icon} className="w-[22px] h-[22px]" />
          <span className="text-[10.5px] font-medium">{it.label}</span>
          {it.id === "dialogs" && badge > 0 && (
            <span className="absolute top-0.5 min-w-[16px] h-4 px-1 rounded-full bg-[#ef4444] text-white text-[9.5px] font-bold flex items-center justify-center ring-2 ring-[#13131a]"
                  style={{ right: "calc(50% - 22px)" }}>
              {badge}
            </span>
          )}
        </button>
      ))}
    </nav>
  );
}

function Toast({ msg, type = "ok" }) {
  if (!msg) return null;
  const dot = type === "warn" ? "bg-[#f59e0b]" : "bg-[#22c55e]";
  return (
    <div className="hd-toast animate-[slideUp_.2s_ease-out]">
      <div className="bg-[#1a1a24] border border-[#2a2a3a] rounded-lg px-4 py-3 shadow-2xl flex items-center gap-2.5 text-sm text-[#f1f1f5]">
        <span className={"w-1.5 h-1.5 rounded-full " + dot}></span>
        {msg}
      </div>
    </div>
  );
}

Object.assign(window, { Avatar, StatusBadge, WaitingLabel, SlaTimer, fmtSla, PlanBadge, SubStatus, Icon, Toast,
                        ModalOverlay, fmtDateTime, PresenceLabel,
                        ServiceSwitcher, ServicePill, ContextChip, ServiceDot,
                        useViewport, contrastOn, BottomSheet, ServiceRail, ServiceTile,
                        MobileAppBar, AppBarButton, MobileNav });
