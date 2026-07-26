// Экран «Состояние» — серверы и боты по каждому ВПН-сервису.
// Данные приходят из /api/health; источник у каждого сервиса свой (см.
// app/health.py). Пока источник — мок, это помечено баннером и бейджами.

const { useState: useStateSv, useEffect: useEffectSv } = React;

const HEALTH_STATUS = {
  ok:      { dot: "bg-[#22c55e]", label: "В сети",           color: "text-[#22c55e]", border: "border-[#22c55e]/20" },
  high:    { dot: "bg-[#eab308]", label: "Высокая нагрузка", color: "text-[#eab308]", border: "border-[#eab308]/20" },
  down:    { dot: "bg-[#ef4444]", label: "Недоступен",       color: "text-[#ef4444]", border: "border-[#ef4444]/20" },
  unknown: { dot: "bg-zinc-500",  label: "Неизвестно",       color: "text-zinc-400",  border: "border-[#2a2a3a]" },
};

function MockBadge({ show }) {
  if (!show) return null;
  return (
    <span title="Выдуманные данные — реальный источник не подключён"
      className="shrink-0 px-1.5 py-0.5 rounded text-[9px] font-bold tracking-wider bg-[#f59e0b]/20 text-[#f59e0b] border border-[#f59e0b]/30">
      MOCK
    </span>
  );
}

function Metric({ label, value }) {
  return (
    <div className="bg-[#0d0d12] rounded-lg p-2">
      <div className="text-xs text-[#6b7280] mb-0.5">{label}</div>
      <div className="text-sm font-semibold text-[#f1f1f5] tabular-nums truncate">{value ?? "—"}</div>
    </div>
  );
}

function HealthCardShell({ item, children }) {
  const cfg = HEALTH_STATUS[item.status] || HEALTH_STATUS.unknown;
  return (
    <div className={"bg-[#13131a] border rounded-xl p-5 flex flex-col gap-3 " + cfg.border}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className={"w-2.5 h-2.5 rounded-full shrink-0 " + cfg.dot + (item.status === "ok" ? " animate-pulse" : "")}></span>
          <span className="font-medium text-[#f1f1f5] truncate">{item.name}</span>
          <MockBadge show={item.isMock} />
        </div>
        <span className={"text-xs font-medium shrink-0 " + cfg.color}>{cfg.label}</span>
      </div>
      {children}
      {item.message && (
        <div className={"text-[11px] " + cfg.color}>{item.message}</div>
      )}
      <div className="text-[10px] text-[#3a3a4a]">источник: {item.source}</div>
    </div>
  );
}

function ServerCard({ server }) {
  const m = server.metrics || {};
  return (
    <HealthCardShell item={server}>
      <div className="grid grid-cols-3 gap-3 text-center">
        <Metric label="Нагрузка" value={m.load != null ? m.load + "%" : null} />
        <Metric label="Пинг" value={m.ping != null ? m.ping + " мс" : null} />
        <Metric label="Uptime" value={m.uptime != null ? m.uptime + "%" : null} />
      </div>
      {server.location && <div className="text-[11px] text-[#6b7280]">📍 {server.location}</div>}
    </HealthCardShell>
  );
}

function BotCard({ bot }) {
  const m = bot.metrics || {};
  const lastUpdate = m.lastUpdate
    ? new Date(m.lastUpdate).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" })
    : null;
  return (
    <HealthCardShell item={bot}>
      <div className="grid grid-cols-3 gap-3 text-center">
        <Metric label="Режим" value={m.mode} />
        <Metric label="В очереди" value={m.pendingUpdates != null ? m.pendingUpdates : null} />
        <Metric label="Апдейт" value={lastUpdate} />
      </div>
      {m.role && <div className="text-[11px] text-[#6b7280]">🤖 {m.role}</div>}
    </HealthCardShell>
  );
}

function HealthSummary({ items }) {
  const count = (st) => items.filter((i) => i.status === st).length;
  const cells = [
    { label: "В сети", value: count("ok"), color: "#22c55e" },
    { label: "Высокая нагрузка", value: count("high"), color: "#eab308" },
    { label: "Недоступно", value: count("down"), color: "#ef4444" },
  ];
  return (
    <div className="grid grid-cols-3 gap-2.5 sm:gap-4">
      {cells.map((c) => (
        <div key={c.label} className="bg-[#13131a] border rounded-xl p-3 sm:p-4 flex items-center gap-3"
             style={{ borderColor: c.color + "33" }}>
          {/* Иконка съедает ширину на телефоне — там достаточно цифры и подписи */}
          <div className="w-10 h-10 rounded-lg hidden sm:flex items-center justify-center shrink-0"
               style={{ background: c.color + "26" }}>
            <span className="w-3 h-3 rounded-full" style={{ background: c.color }}></span>
          </div>
          <div className="min-w-0">
            <div className="text-xl sm:text-2xl font-semibold tabular-nums" style={{ color: c.color }}>{c.value}</div>
            <div className="text-[10.5px] sm:text-xs text-[#6b7280] leading-tight">{c.label}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function ServiceHealthSection({ snapshot, showServiceTitle }) {
  const servers = snapshot.servers || [];
  const bots = snapshot.bots || [];
  return (
    <div className="space-y-4">
      {showServiceTitle && (
        <div className="flex items-center gap-2.5 pt-2">
          <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: snapshot.serviceColor }}></span>
          <h2 className="text-base font-semibold text-[#f1f1f5]">{snapshot.serviceName}</h2>
          <MockBadge show={snapshot.isMock} />
          <div className="flex-1 h-px bg-[#2a2a3a]"></div>
        </div>
      )}

      <div className="text-[10px] uppercase tracking-wider text-[#6b7280] font-semibold">Серверы</div>
      {servers.length === 0 ? (
        <div className="text-xs text-[#6b7280]">Нет данных</div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {servers.map((s) => <ServerCard key={s.id} server={s} />)}
        </div>
      )}

      <div className="text-[10px] uppercase tracking-wider text-[#6b7280] font-semibold pt-2">Боты</div>
      {bots.length === 0 ? (
        <div className="text-xs text-[#6b7280]">Нет данных</div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {bots.map((b) => <BotCard key={b.id} bot={b} />)}
        </div>
      )}
    </div>
  );
}

// Админский блок: какой источник данных опрашивается у сервиса. Список
// провайдеров приходит с бэкенда из реестра app.health — свой провайдер
// появляется здесь сам, без правки фронта.
function SourcePicker({ serviceId, onChanged }) {
  const [cfg, setCfg] = useStateSv(null);
  const [saving, setSaving] = useStateSv(false);

  useEffectSv(() => {
    if (serviceId === null) { setCfg(null); return; }
    window.apiFetch("GET", `/api/settings/monitoring?service_id=${serviceId}`)
      .then(setCfg).catch(() => setCfg(null));
  }, [serviceId]);

  async function pick(kind, provider) {
    const next = { interval: cfg.interval, servers: cfg.servers, bots: cfg.bots };
    next[kind] = { provider, config: next[kind].config || {} };
    setCfg((c) => ({ ...c, ...next }));
    setSaving(true);
    try {
      await window.apiFetch("PUT", `/api/settings/monitoring?service_id=${serviceId}`, next);
      onChanged && onChanged();
    } catch { /* сообщение покажет общий тост */ }
    setSaving(false);
  }

  if (!cfg) return null;
  const rows = [["servers", "Серверы"], ["bots", "Боты"]];

  return (
    <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl p-4 space-y-3">
      <div className="text-[10px] uppercase tracking-wider text-[#6b7280] font-semibold">
        Источник данных · {cfg.serviceName}
      </div>
      {rows.map(([kind, label]) => (
        <div key={kind} className="flex items-center gap-3 flex-wrap">
          <span className="text-xs text-[#6b7280] w-[70px] shrink-0">{label}</span>
          {(cfg.available?.[kind] || []).map((p) => {
            const on = cfg[kind]?.provider === p.name;
            return (
              <button key={p.name} disabled={saving} onClick={() => pick(kind, p.name)}
                title={p.description}
                className={"px-2.5 py-1 rounded-md text-xs font-medium border transition disabled:opacity-40 " +
                  (on ? "bg-[#1a1a24] text-[#f1f1f5] border-[#3a3a4a]"
                      : "text-[#6b7280] border-[#2a2a3a] hover:text-[#f1f1f5] hover:bg-[#1a1a24]/60")}>
                {p.name}{p.isMock ? " (мок)" : ""}
              </button>
            );
          })}
        </div>
      ))}
      <div className="text-[10px] text-[#6b7280]">
        Параметры источника (адреса серверов, токены) задаются в настройке
        <code className="mx-1 text-[#7BA8F9]">monitoring</code> сервиса.
      </div>
    </div>
  );
}

function HealthScreen({ serviceId = null, currentOperator = null, mobileChrome = null }) {
  const [data, setData] = useStateSv(null);
  const [loading, setLoading] = useStateSv(true);

  function load(refresh = false) {
    setLoading(true);
    const q = serviceId === null ? "" : `?service_id=${serviceId}`;
    window
      .apiFetch(refresh ? "POST" : "GET", `/api/health${refresh ? "/refresh" : ""}${q}`)
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => { setData({ services: [] }); setLoading(false); });
  }

  useEffectSv(() => { load(); }, [serviceId]);

  const snapshots = (data && data.services) || [];
  const all = snapshots.flatMap((s) => [...(s.servers || []), ...(s.bots || [])]);
  const lastUpdated = snapshots.map((s) => s.lastUpdated).sort().slice(-1)[0];
  // serviceId === null — режим «Все сервисы»: секция на каждый ВПН.
  const multi = serviceId === null && snapshots.length > 1;

  const chrome = mobileChrome;
  const currentName = chrome && (chrome.currentServiceId == null
    ? "Все сервисы"
    : (chrome.services || []).find((s) => s.id === chrome.currentServiceId)?.name || "");

  return (
    <div className={"h-full bg-[#0d0d12] " +
                    (chrome ? "flex flex-col min-h-0" : "overflow-y-auto scrollbar-thin")}>
      {chrome && (
        <>
          <MobileAppBar title="Состояние" subtitle={currentName}
            right={<>
              <AppBarButton icon="refresh" label="Обновить" onClick={() => load(true)} />
              <AppBarButton icon="bell" label="Уведомления" badge={chrome.bellBadge} onClick={chrome.onBell} />
            </>} />
          <ServiceRail services={chrome.services} currentServiceId={chrome.currentServiceId}
                       onSelect={chrome.onSelectService} />
        </>
      )}
      <div className={"max-w-[1200px] w-full mx-auto space-y-4 sm:space-y-6 p-3 sm:p-6 " +
                      (chrome ? "flex-1 min-h-0 overflow-y-auto scrollbar-thin" : "")}>

        {data && data.isMock && (
          <div className="flex items-start gap-3 bg-[#2a1f0a] border border-[#f59e0b]/30 rounded-xl px-4 py-3 text-sm text-[#f59e0b]">
            <span className="text-base leading-none mt-0.5">⚠</span>
            <div>
              <span className="font-medium">Тестовые данные (мок)</span>
              <span className="text-[#f59e0b]/70 ml-2">
                — серверы и боты здесь выдуманы, реальный источник ещё не подключён.
                Источник задаётся на сервис в настройке мониторинга: реализуйте
                <code className="bg-[#1a1200] px-1 rounded text-xs mx-1">HealthProvider</code>
                и укажите его имя вместо <code className="bg-[#1a1200] px-1 rounded text-xs">mock</code>.
              </span>
            </div>
          </div>
        )}

        <div className={"items-center justify-between " + (chrome ? "hidden" : "flex")}>
          <div>
            <h1 className="text-xl font-semibold text-[#f1f1f5]">Состояние</h1>
            <div className="text-xs text-[#6b7280] mt-0.5">
              {lastUpdated
                ? "Обновлено: " + new Date(lastUpdated).toLocaleString("ru", { dateStyle: "short", timeStyle: "short" })
                : "Ожидание первой проверки..."}
            </div>
          </div>
          <button onClick={() => load(true)} disabled={loading}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#13131a] border border-[#2a2a3a] text-sm text-[#f1f1f5] hover:bg-[#1a1a24] transition disabled:opacity-50">
            <Icon name="refresh" className={"w-4 h-4 " + (loading ? "animate-spin" : "")} />
            Обновить
          </button>
        </div>

        {chrome && (
          <div className="text-[11px] text-[#6b7280] -mb-1">
            {lastUpdated
              ? "Обновлено: " + new Date(lastUpdated).toLocaleString("ru", { dateStyle: "short", timeStyle: "short" })
              : "Ожидание первой проверки..."}
          </div>
        )}

        {all.length > 0 && <HealthSummary items={all} />}

        {currentOperator?.role === "admin" && serviceId !== null && (
          <SourcePicker serviceId={serviceId} onChanged={() => load(true)} />
        )}

        {loading && snapshots.length === 0 && (
          <div className="text-center py-16 text-[#6b7280] text-sm">Загрузка...</div>
        )}

        {!loading && snapshots.length === 0 && (
          <div className="bg-[#13131a] border border-dashed border-[#2a2a3a] rounded-xl p-12 text-center">
            <Icon name="server" className="w-10 h-10 text-[#2a2a3a] mx-auto mb-3" />
            <div className="text-sm font-medium text-[#f1f1f5] mb-1">Нет данных о состоянии</div>
            <div className="text-xs text-[#6b7280] max-w-sm mx-auto">
              Ни один ВПН-сервис недоступен для вашей учётной записи либо мониторинг ещё не отработал.
            </div>
          </div>
        )}

        {snapshots.map((s) => (
          <ServiceHealthSection key={s.serviceId} snapshot={s} showServiceTitle={multi} />
        ))}
      </div>
    </div>
  );
}

Object.assign(window, { HealthScreen, ServerCard, BotCard });
