// Service switcher — the pill row that lets an operator move between VPN brands.

const { useMemo: useServiceMemo } = React;

const ALL_SERVICES = "all";

// A dialog counts towards a service badge while it still needs attention:
// nobody has answered it yet, or the user wrote something unread. Merely
// opening a dialog does not clear it — only replying does.
function needsAttention(conv) {
  return conv.status !== "closed" && (conv.status === "new" || conv.unread > 0);
}

// Counters are derived from the conversations already in memory rather than
// polled, so they stay consistent with whatever the WebSocket last delivered.
function useServiceCounts(conversations) {
  return useServiceMemo(() => {
    const counts = {};
    let total = 0;
    for (const c of conversations) {
      const slug = c.serviceSlug;
      if (!counts[slug]) counts[slug] = { badge: 0, open: 0 };
      if (c.status !== "closed") counts[slug].open += 1;
      if (needsAttention(c)) {
        counts[slug].badge += 1;
        total += 1;
      }
    }
    return { counts, total };
  }, [conversations]);
}

function ServicePill({ active, color, label, count, muted, onClick }) {
  return (
    <button
      onClick={onClick}
      title={label}
      className={
        "group flex items-center gap-2 pl-3 pr-2.5 py-1.5 rounded-lg border text-sm shrink-0 transition " +
        (active
          ? "bg-[#1a1a24] border-[#3a3a4a] text-[#f1f1f5]"
          : "bg-transparent border-transparent text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24]/60")
      }
    >
      {color && (
        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color }}></span>
      )}
      <span className={active ? "font-semibold" : "font-medium"}>{label}</span>
      {count > 0 && (
        <span
          className={
            "min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-bold flex items-center justify-center tabular-nums " +
            (muted ? "bg-[#2a2a3a] text-[#9ca3af]" : "bg-[#ef4444] text-white")
          }
        >
          {count > 99 ? "99+" : count}
        </span>
      )}
    </button>
  );
}

function ServiceTabs({ services, activeService, setActiveService, conversations }) {
  const { counts, total } = useServiceCounts(conversations);

  // With a single brand the switcher is just noise.
  if (!services || services.length < 2) return null;

  return (
    <div className="shrink-0 bg-[#0d0d12] border-b border-[#2a2a3a] px-3 py-2">
      <div className="flex items-center gap-1 overflow-x-auto scrollbar-thin">
        <ServicePill
          active={activeService === ALL_SERVICES}
          label="Все сервисы"
          count={total}
          muted
          onClick={() => setActiveService(ALL_SERVICES)}
        />
        <span className="w-px h-5 bg-[#2a2a3a] mx-1 shrink-0"></span>
        {services.map((s) => (
          <ServicePill
            key={s.slug}
            active={activeService === s.slug}
            color={s.color}
            label={s.name}
            count={(counts[s.slug] || {}).badge || 0}
            onClick={() => setActiveService(s.slug)}
          />
        ))}
      </div>
    </div>
  );
}

function ContextChip({ label, value, mono, accentColor }) {
  return (
    <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#13131a] border border-[#2a2a3a] shrink-0">
      {accentColor && (
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: accentColor }}></span>
      )}
      <span className="text-[11px] text-[#6b7280]">{label}:</span>
      <span className={"text-[11px] text-[#f1f1f5] " + (mono ? "font-mono" : "font-medium")}>
        {value}
      </span>
    </div>
  );
}

// Shows which brand's settings an answer will actually be sent under — the
// knowledge base and prompt differ per service, so this is worth surfacing.
function ServiceContextBar({ services, activeService, conversations, aiPrompt }) {
  const { counts, total } = useServiceCounts(conversations);
  if (!services || services.length < 2) return null;

  const service = services.find((s) => s.slug === activeService);
  const badge = service ? (counts[service.slug] || {}).badge || 0 : total;
  const promptPreview = (aiPrompt || "").trim().split(/\s+/).slice(0, 6).join(" ");

  return (
    <div className="shrink-0 bg-[#0d0d12] border-b border-[#2a2a3a] px-3 pb-2 flex items-center gap-2 overflow-x-auto scrollbar-thin">
      <ContextChip
        label="Активен"
        value={service ? service.name : "Все сервисы"}
        accentColor={service ? service.color : null}
      />
      {service && <ContextChip label="База знаний" value={service.kbCollection} mono />}
      {service && promptPreview && <ContextChip label="Промпт ИИ" value={promptPreview + "…"} />}
      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#13131a] border border-[#2a2a3a] shrink-0">
        <span className="text-[11px] text-[#6b7280]">Требуют ответа:</span>
        <span className={"text-[11px] font-semibold tabular-nums " + (badge ? "text-[#ef4444]" : "text-[#22c55e]")}>
          {badge}
        </span>
      </div>
    </div>
  );
}

Object.assign(window, {
  ALL_SERVICES,
  ServiceTabs,
  ServiceContextBar,
  useServiceCounts,
  needsAttention,
});
