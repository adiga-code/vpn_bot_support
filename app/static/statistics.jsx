// Statistics screen

const { useState: useStateS, useEffect: useEffectS, useMemo: useMemoS } = React;

function fmtDuration(seconds) {
  if (seconds == null) return "—";
  const s = Math.round(seconds);
  if (s < 60)   return `${s} сек`;
  if (s < 3600) { const m = Math.floor(s / 60), r = s % 60; return r ? `${m} мин ${r} сек` : `${m} мин`; }
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  if (s < 86400) return m ? `${h} ч ${m} мин` : `${h} ч`;
  const d = Math.floor(s / 86400), rh = Math.floor((s % 86400) / 3600);
  return rh ? `${d} д ${rh} ч` : `${d} д`;
}

function StatCard({ label, value, sub }) {
  return (
    <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl p-4">
      <div className="text-xs text-[#6b7280] mb-2">{label}</div>
      <div className="flex items-end justify-between gap-2">
        <div className="text-2xl font-semibold text-[#f1f1f5] tabular-nums leading-none">{value}</div>
        {sub && <div className="text-[11px] text-[#6b7280]">{sub}</div>}
      </div>
    </div>
  );
}

function LineChart({ data, days = 14 }) {
  if (!data || data.length < 2) {
    return (
      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl p-5 flex items-center justify-center h-[300px]">
        <div className="text-sm text-[#6b7280]">Нет данных за период</div>
      </div>
    );
  }
  const max = Math.max(...data);
  const min = Math.min(...data);
  const w = 100, h = 100;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / (max - min || 1)) * h * 0.85 - 5;
    return [x, y];
  });
  const path = pts.map(([x, y], i) => (i === 0 ? `M ${x} ${y}` : `L ${x} ${y}`)).join(" ");
  const area = path + ` L ${w} ${h} L 0 ${h} Z`;

  const today = new Date();
  const labelCount = 7;
  const step = Math.floor((data.length - 1) / (labelCount - 1));
  const labels = Array.from({ length: labelCount }, (_, i) => {
    const d = new Date(today);
    d.setDate(d.getDate() - (data.length - 1 - i * step));
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" }).replace(".", "");
  });

  const lastVal = data[data.length - 1];

  return (
    <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm font-medium text-[#f1f1f5]">Обращения по дням</div>
        <div className="text-xs text-[#6b7280]">последние {days} дней</div>
      </div>
      <div className="relative h-[200px]">
        <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="w-full h-full overflow-visible">
          <defs>
            <linearGradient id="lineFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#4F8EF7" stopOpacity="0.35" />
              <stop offset="100%" stopColor="#4F8EF7" stopOpacity="0" />
            </linearGradient>
          </defs>
          {[0, 25, 50, 75].map((y) => (
            <line key={y} x1="0" x2={w} y1={y} y2={y} stroke="#2a2a3a" strokeWidth="0.3" strokeDasharray="0.5 0.5" />
          ))}
          <path d={area} fill="url(#lineFill)" />
          <path d={path} fill="none" stroke="#4F8EF7" strokeWidth="0.6" vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" />
          {pts.map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r="0.8" fill="#4F8EF7" stroke="#0d0d12" strokeWidth="0.4" />
          ))}
        </svg>
        {lastVal > 0 && (
          <div className="absolute top-1 right-2 bg-[#1a1a24] border border-[#4F8EF7]/30 rounded-md px-2 py-1 text-xs">
            <div className="text-[10px] text-[#6b7280]">сегодня</div>
            <div className="font-semibold text-[#7BA8F9] tabular-nums">{lastVal} обращ.</div>
          </div>
        )}
      </div>
      <div className="flex justify-between mt-3 text-[10px] text-[#6b7280] px-1">
        {labels.map((l, i) => <span key={i}>{l}</span>)}
      </div>
    </div>
  );
}

function HeatmapChart({ data }) {
  const max = data && data.length ? Math.max(...data) : 1;
  const peakHour = data && data.length ? data.indexOf(Math.max(...data)) : 0;
  return (
    <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl p-5">
      <div className="text-sm font-medium text-[#f1f1f5] mb-1">Обращения по часам</div>
      <div className="text-xs text-[#6b7280] mb-4">средние значения за 14 дней · пик в {peakHour}:00</div>
      <div className="grid grid-cols-24 gap-[3px] h-[120px]" style={{ gridTemplateColumns: "repeat(24, 1fr)" }}>
        {(data || Array(24).fill(0)).map((v, i) => {
          const intensity = v / (max || 1);
          const h = Math.max(8, intensity * 100);
          return (
            <div key={i} className="flex flex-col justify-end group relative">
              <div
                className="rounded-sm transition-all hover:ring-2 hover:ring-[#4F8EF7]/60"
                style={{ height: h + "%", background: `oklch(0.58 0.16 250 / ${0.2 + intensity * 0.8})` }}
                title={`${i}:00 — ${v}`}
              ></div>
              <div className="opacity-0 group-hover:opacity-100 absolute -top-7 left-1/2 -translate-x-1/2 bg-[#1a1a24] border border-[#2a2a3a] rounded px-1.5 py-0.5 text-[10px] text-[#f1f1f5] whitespace-nowrap pointer-events-none z-10">
                {i}:00 · {v}
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex justify-between mt-2 text-[10px] text-[#6b7280] tabular-nums">
        <span>00</span><span>04</span><span>08</span><span>12</span><span>16</span><span>20</span><span>23</span>
      </div>
    </div>
  );
}

function TopQuestionsChart({ data }) {
  if (!data || data.length === 0) {
    return (
      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl p-5">
        <div className="text-sm font-medium text-[#f1f1f5] mb-1">Топ-10 частых вопросов</div>
        <div className="text-xs text-[#6b7280] mb-4">за последние 30 дней</div>
        <div className="py-10 text-center text-sm text-[#6b7280]">Нет данных</div>
      </div>
    );
  }
  const max = data[0].count;
  return (
    <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl p-5">
      <div className="text-sm font-medium text-[#f1f1f5] mb-1">Топ-10 частых вопросов</div>
      <div className="text-xs text-[#6b7280] mb-4">за последние 30 дней</div>
      <div className="space-y-2">
        {data.map((q, i) => (
          <div key={i} className="flex items-center gap-3 group cursor-pointer">
            <div className="text-[10px] text-[#6b7280] w-4 tabular-nums">{i + 1}</div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between mb-1">
                <div className="text-xs text-[#f1f1f5] truncate">{q.q}</div>
                <div className="text-xs text-[#6b7280] tabular-nums shrink-0 ml-2">{q.count}</div>
              </div>
              <div className="h-1.5 bg-[#0d0d12] rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all group-hover:bg-[#7BA8F9]"
                  style={{ width: (q.count / max) * 100 + "%", background: i < 3 ? "#4F8EF7" : "#4F8EF7aa" }}
                ></div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function OperatorsTable({ operators }) {
  return (
    <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-[#2a2a3a]/60">
        <div className="text-sm font-medium text-[#f1f1f5]">Операторы</div>
        <div className="text-xs text-[#6b7280]">{operators.filter((o) => o.online).length} онлайн</div>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-[10px] uppercase tracking-wider text-[#6b7280]">
            <th className="text-left px-5 py-2 font-medium">Имя</th>
            <th className="text-right px-3 py-2 font-medium">Диалогов</th>
            <th className="text-right px-3 py-2 font-medium">Первый ответ</th>
            <th className="text-right px-3 py-2 font-medium">Ср. ответ</th>
            <th className="text-right px-5 py-2 font-medium">Статус</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#2a2a3a]/40">
          {operators.map((op) => (
            <tr key={op.id} className="hover:bg-[#1a1a24]/40 transition">
              <td className="px-5 py-3">
                <div className="flex items-center gap-3">
                  <Avatar initials={op.initials} color={op.color} size={28} />
                  <div>
                    <div className="text-[#f1f1f5]">{op.name}</div>
                    <div className="text-[10px] text-[#6b7280]">
                      {op.role === "admin" ? "Администратор" : "Агент"} · {op.tg}
                    </div>
                  </div>
                </div>
              </td>
              <td className="px-3 py-3 text-right tabular-nums text-[#f1f1f5]">{op.dialogs_count ?? 0}</td>
              <td className="px-3 py-3 text-right tabular-nums text-[#f1f1f5]">{fmtDuration(op.first_response_avg)}</td>
              <td className="px-3 py-3 text-right tabular-nums text-[#f1f1f5]">{fmtDuration(op.next_response_avg)}</td>
              <td className="px-5 py-3 text-right">
                <span className="inline-flex items-center gap-1.5 text-xs">
                  <span className={"w-1.5 h-1.5 rounded-full " + (op.online ? "bg-[#22c55e]" : "bg-zinc-600")}></span>
                  <span className={op.online ? "text-[#22c55e]" : "text-[#6b7280]"}>
                    {op.online ? "Онлайн" : "Офлайн"}
                  </span>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatisticsScreen() {
  const [range,  setRange]  = useStateS("14d");
  const [stats,  setStats]  = useStateS(null);
  const [times,  setTimes]  = useStateS(null);

  const days = range === "today" ? 1 : range === "7d" ? 7 : range === "14d" ? 14 : 30;

  useEffectS(() => {
    setStats(null);
    setTimes(null);
    Promise.all([
      window.apiFetch("GET", `/api/stats?days=${days}`),
      window.apiFetch("GET", `/api/stats/times?days=${days}`),
    ]).then(([s, t]) => { setStats(s); setTimes(t); }).catch(() => {});
  }, [days]);

  const ranges = [
    { id: "today", label: "Сегодня" },
    { id: "7d",   label: "7 дней"  },
    { id: "14d",  label: "14 дней" },
    { id: "30d",  label: "30 дней" },
  ];

  const team = times?.team || {};

  // Merge operator time stats into base operators list from /api/stats
  const operators = useMemoS(() => {
    const base = stats?.operators || [];
    const timeOps = times?.operators || [];
    const timeMap = Object.fromEntries(timeOps.map((o) => [o.id, o]));
    return base.map((op) => ({ ...op, ...(timeMap[op.id] || {}) }));
  }, [stats, times]);

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin bg-[#0d0d12]">
      <div className="max-w-[1400px] mx-auto p-6 space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-[#f1f1f5]">Статистика</h1>
            <div className="text-xs text-[#6b7280] mt-0.5">данные за выбранный период</div>
          </div>
          <div className="flex items-center gap-3">
            <div className="bg-[#13131a] border border-[#2a2a3a] rounded-lg p-1 flex gap-0.5">
              {ranges.map((r) => (
                <button
                  key={r.id}
                  onClick={() => setRange(r.id)}
                  className={
                    "px-3 py-1.5 rounded-md text-xs font-medium transition " +
                    (range === r.id ? "bg-[#4F8EF7] text-white" : "text-[#6b7280] hover:text-[#f1f1f5]")
                  }
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* KPI row */}
        <div className="grid grid-cols-4 gap-4">
          <StatCard label="Обращений сегодня" value={stats ? String(stats.today_total) : "—"} />
          <StatCard label="Первый ответ (команда)" value={fmtDuration(team.first_response_avg)} />
          <StatCard label="Закрыто диалогов" value={stats ? String(stats.today_closed) : "—"} />
          <StatCard label="Ср. ответ (команда)" value={fmtDuration(team.next_response_avg)} />
        </div>

        {/* Close time banner */}
        {team.close_time_avg != null && (
          <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl px-5 py-3 flex items-center justify-between">
            <div className="text-xs text-[#6b7280]">Среднее время закрытия тикета</div>
            <div className="text-sm font-semibold text-[#f1f1f5] tabular-nums">{fmtDuration(team.close_time_avg)}</div>
          </div>
        )}

        {/* Charts row */}
        <div className="grid grid-cols-3 gap-4">
          <div className="col-span-2">
            <LineChart data={stats?.daily || []} days={days} />
          </div>
          <HeatmapChart data={stats?.hourly || Array(24).fill(0)} />
        </div>

        {/* Bottom row */}
        <div className="grid grid-cols-3 gap-4">
          <div className="col-span-2">
            <OperatorsTable operators={operators} />
          </div>
          <TopQuestionsChart data={stats?.top_questions || []} />
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { StatisticsScreen });
