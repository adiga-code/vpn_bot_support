// Servers screen — VPN server monitoring

const { useState: useStateSv, useEffect: useEffectSv } = React;

function ServerCard({ server }) {
  const statusCfg = {
    ok:   { dot: "bg-[#22c55e]", label: "В сети",          labelColor: "text-[#22c55e]", bg: "border-[#22c55e]/20" },
    high: { dot: "bg-[#eab308]", label: "Высокая нагрузка", labelColor: "text-[#eab308]", bg: "border-[#eab308]/20" },
    down: { dot: "bg-[#ef4444]", label: "Недоступен",       labelColor: "text-[#ef4444]", bg: "border-[#ef4444]/20" },
  }[server.status] || { dot: "bg-zinc-500", label: "Неизвестно", labelColor: "text-zinc-400", bg: "" };

  return (
    <div className={"bg-[#13131a] border rounded-xl p-5 flex flex-col gap-3 " + statusCfg.bg}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className={"w-2.5 h-2.5 rounded-full shrink-0 " + statusCfg.dot + (server.status === "ok" ? " animate-pulse" : "")}></span>
          <span className="font-medium text-[#f1f1f5] truncate">{server.name}</span>
        </div>
        <span className={"text-xs font-medium shrink-0 " + statusCfg.labelColor}>{statusCfg.label}</span>
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        <div className="bg-[#0d0d12] rounded-lg p-2">
          <div className="text-xs text-[#6b7280] mb-0.5">Нагрузка</div>
          <div className="text-sm font-semibold text-[#f1f1f5] tabular-nums">
            {server.load != null ? server.load + "%" : "—"}
          </div>
        </div>
        <div className="bg-[#0d0d12] rounded-lg p-2">
          <div className="text-xs text-[#6b7280] mb-0.5">Пинг</div>
          <div className="text-sm font-semibold text-[#f1f1f5] tabular-nums">
            {server.ping != null ? server.ping + " мс" : "—"}
          </div>
        </div>
        <div className="bg-[#0d0d12] rounded-lg p-2">
          <div className="text-xs text-[#6b7280] mb-0.5">Uptime</div>
          <div className="text-sm font-semibold text-[#f1f1f5] tabular-nums">
            {server.uptime != null ? server.uptime + "%" : "—"}
          </div>
        </div>
      </div>

      {server.location && (
        <div className="text-[11px] text-[#6b7280]">📍 {server.location}</div>
      )}
    </div>
  );
}

function ServersScreen() {
  const [data, setData] = useStateSv({ servers: [], last_updated: null });
  const [loading, setLoading] = useStateSv(true);

  function load() {
    setLoading(true);
    fetch("/api/servers")
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }

  useEffectSv(() => { load(); }, []);

  const servers = data.servers || [];
  const online = servers.filter((s) => s.status === "ok").length;
  const high   = servers.filter((s) => s.status === "high").length;
  const down   = servers.filter((s) => s.status === "down").length;

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin bg-[#0d0d12]">
      <div className="max-w-[1200px] mx-auto p-6 space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-[#f1f1f5]">Серверы VPN</h1>
            <div className="text-xs text-[#6b7280] mt-0.5">
              {data.last_updated ? `Обновлено: ${data.last_updated}` : "Данные не получены от n8n"}
            </div>
          </div>
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#13131a] border border-[#2a2a3a] text-sm text-[#f1f1f5] hover:bg-[#1a1a24] transition disabled:opacity-50"
          >
            <Icon name="refresh" className={"w-4 h-4 " + (loading ? "animate-spin" : "")} />
            Обновить
          </button>
        </div>

        {/* Summary */}
        {servers.length > 0 && (
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-[#13131a] border border-[#22c55e]/20 rounded-xl p-4 flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-[#22c55e]/15 flex items-center justify-center">
                <span className="w-3 h-3 rounded-full bg-[#22c55e]"></span>
              </div>
              <div>
                <div className="text-2xl font-semibold text-[#f1f1f5] tabular-nums">{online}</div>
                <div className="text-xs text-[#6b7280]">В сети</div>
              </div>
            </div>
            <div className="bg-[#13131a] border border-[#eab308]/20 rounded-xl p-4 flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-[#eab308]/15 flex items-center justify-center">
                <span className="w-3 h-3 rounded-full bg-[#eab308]"></span>
              </div>
              <div>
                <div className="text-2xl font-semibold text-[#f1f1f5] tabular-nums">{high}</div>
                <div className="text-xs text-[#6b7280]">Высокая нагрузка</div>
              </div>
            </div>
            <div className="bg-[#13131a] border border-[#ef4444]/20 rounded-xl p-4 flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-[#ef4444]/15 flex items-center justify-center">
                <span className="w-3 h-3 rounded-full bg-[#ef4444]"></span>
              </div>
              <div>
                <div className="text-2xl font-semibold text-[#f1f1f5] tabular-nums">{down}</div>
                <div className="text-xs text-[#6b7280]">Недоступно</div>
              </div>
            </div>
          </div>
        )}

        {/* Server grid */}
        {loading && (
          <div className="text-center py-16 text-[#6b7280] text-sm">Загрузка...</div>
        )}

        {!loading && servers.length === 0 && (
          <div className="bg-[#13131a] border border-dashed border-[#2a2a3a] rounded-xl p-12 text-center">
            <Icon name="settings" className="w-10 h-10 text-[#2a2a3a] mx-auto mb-3" />
            <div className="text-sm font-medium text-[#f1f1f5] mb-1">Данные не получены</div>
            <div className="text-xs text-[#6b7280] max-w-sm mx-auto">
              Настройте в n8n cron-воркфлоу, который проверяет серверы и пушит статус в Redis ключ <code className="bg-[#1a1a24] px-1 rounded">vpn_bot:servers</code>
            </div>
          </div>
        )}

        {!loading && servers.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {servers.map((s) => <ServerCard key={s.name} server={s} />)}
          </div>
        )}
      </div>
    </div>
  );
}

Object.assign(window, { ServersScreen });
