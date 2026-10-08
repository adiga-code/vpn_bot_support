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

function TopQuestionsChart({ data, meta, classification, rangeLabel, onClassify, classifying, notice }) {
  const unclassified = classification?.unclassified || 0;
  const off = classification?.off_services || [];
  const header = (
    <>
      <div className="text-sm font-medium text-[#f1f1f5] mb-1">Топ-10 частых вопросов</div>
      <div className="text-xs text-[#6b7280] mb-4">
        {rangeLabel}
        {meta && meta.total_tickets > 0 && <> · размечено {meta.classified} из {meta.total_tickets} обращений</>}
      </div>
    </>
  );
  const classifyBtn = unclassified > 0 && (
    <button onClick={onClassify} disabled={classifying}
      className="px-3 py-2 rounded-lg bg-[#4F8EF7]/10 hover:bg-[#4F8EF7]/20 text-[#7BA8F9] text-xs font-semibold border border-[#4F8EF7]/30 disabled:opacity-50">
      {classifying ? "Размечаю…" : `Разметить прошлые обращения (${unclassified})`}
    </button>
  );
  const noticeEl = notice && <div className="text-xs text-[#9ca3af] mt-3">{notice}</div>;

  if (!data || data.length === 0) {
    return (
      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl p-5">
        {header}
        <div className="py-8 text-center space-y-3">
          <div className="text-sm text-[#9ca3af]">Пока нет данных</div>
          {off.length > 0 && (
            <div className="text-xs text-[#f59e0b] max-w-xs mx-auto leading-relaxed">
              Определение темы выключено в «ИИ-настройках» ({off.join(", ")}). Включите его там —
              новые обращения начнут попадать в топ.
            </div>
          )}
          {off.length === 0 && unclassified > 0 && (
            <div className="text-xs text-[#6b7280] max-w-xs mx-auto leading-relaxed">
              Темы получают новые обращения, а прошлые ещё не размечены — их можно разметить сейчас.
            </div>
          )}
          {classifyBtn}
          {noticeEl}
        </div>
      </div>
    );
  }
  const max = data[0].count;
  return (
    <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl p-5">
      {header}
      <div className="space-y-2">
        {data.map((q, i) => (
          <div key={i} className="flex items-center gap-3 group">
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
      {(classifyBtn || noticeEl) && <div className="mt-4">{classifyBtn}{noticeEl}</div>}
    </div>
  );
}

// ── Оценки поддержки ─────────────────────────────────────────────────────────
// Клиент ставит 1–5 после закрытия тикета (включается в «Автоматизации»).

const ratingColor = (v) => (v == null ? "#6b7280" : v >= 4 ? "#22c55e" : v >= 3 ? "#eab308" : "#ef4444");

// Звёзды с дробной заливкой: серый ряд и жёлтый поверх, обрезанный по значению.
function Stars({ value, className = "text-base" }) {
  const pct = Math.max(0, Math.min(5, value || 0)) / 5 * 100;
  return (
    <span className={"relative inline-block leading-none tracking-tight whitespace-nowrap " + className}
          aria-label={value != null ? `Оценка ${value} из 5` : "Нет оценок"}>
      <span className="text-[#2a2a3a]">★★★★★</span>
      <span className="absolute left-0 top-0 overflow-hidden text-[#facc15]" style={{ width: pct + "%" }}>★★★★★</span>
    </span>
  );
}

function RatingTrend({ daily }) {
  const pts = daily.map((d, i) => ({ i, v: d.avg, d: d.d, n: d.count })).filter((p) => p.v != null);
  if (pts.length < 2) return null;
  const W = 300, H = 56, n = Math.max(1, daily.length - 1);
  const x = (i) => (i / n) * W;
  const y = (v) => H - 4 - ((v - 1) / 4) * (H - 8);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-14" preserveAspectRatio="none" role="img"
         aria-label="Средняя оценка по дням">
      <line x1="0" x2={W} y1={y(3)} y2={y(3)} stroke="#2a2a3a" strokeDasharray="3 4" />
      <polyline fill="none" stroke="#4F8EF7" strokeWidth="1.5" strokeLinejoin="round" vectorEffect="non-scaling-stroke"
                points={pts.map((p) => `${x(p.i)},${y(p.v)}`).join(" ")} />
      {pts.map((p) => (
        <circle key={p.i} cx={x(p.i)} cy={y(p.v)} r="2.5" fill={ratingColor(p.v)} vectorEffect="non-scaling-stroke">
          <title>{p.d}: {p.v} ({p.n})</title>
        </circle>
      ))}
    </svg>
  );
}

function RatingsSection({ data, rangeLabel }) {
  const off = data?.rating_off_services || [];
  const wrap = (children) => (
    <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-[#2a2a3a]/60">
        <div className="text-sm font-medium text-[#f1f1f5]">Оценки поддержки</div>
        <div className="text-xs text-[#6b7280]">{rangeLabel} · клиент ставит оценку после закрытия тикета</div>
      </div>
      {children}
    </div>
  );
  if (!data) return wrap(<div className="py-10 text-center text-sm text-[#6b7280]">Загрузка…</div>);
  if (!data.count) {
    return wrap(
      <div className="py-10 px-5 text-center space-y-2">
        <div className="text-sm text-[#9ca3af]">За период оценок нет</div>
        {off.length > 0 && (
          <div className="text-xs text-[#f59e0b] max-w-md mx-auto leading-relaxed">
            Запрос оценки выключен ({off.join(", ")}). Включите его: Настройки → Автоматизация →
            «Запрашивать оценку после закрытия» — тогда клиенты начнут её ставить.
          </div>
        )}
      </div>
    );
  }
  const dist = data.distribution || [0, 0, 0, 0, 0];
  const maxD = Math.max(1, ...dist);
  return wrap(
    <div className="p-5 space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="space-y-3">
          <div className="flex items-end gap-3">
            <div className="text-4xl font-semibold tabular-nums" style={{ color: ratingColor(data.avg) }}>
              {data.avg.toFixed(1)}
            </div>
            <div className="pb-1.5">
              <Stars value={data.avg} className="text-lg" />
              <div className="text-xs text-[#6b7280] mt-1">{data.count} оценок</div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-[#0d0d12] rounded-lg px-3 py-2">
              <div className="text-[10px] text-[#6b7280]">Довольны (4–5★)</div>
              <div className="text-sm text-[#f1f1f5] tabular-nums">{data.csat}%</div>
            </div>
            <div className="bg-[#0d0d12] rounded-lg px-3 py-2">
              <div className="text-[10px] text-[#6b7280]">Оценили</div>
              <div className="text-sm text-[#f1f1f5] tabular-nums">
                {data.count} из {Math.max(data.closed, data.count)}
                {data.response_rate != null && <span className="text-[#6b7280]"> · {Math.min(100, data.response_rate)}%</span>}
              </div>
            </div>
          </div>
        </div>
        <div className="space-y-1.5">
          {[5, 4, 3, 2, 1].map((star) => {
            const n = dist[star - 1] || 0;
            return (
              <div key={star} className="flex items-center gap-2 text-xs">
                <span className="w-6 text-[#9ca3af] tabular-nums shrink-0">{star}★</span>
                <div className="flex-1 h-2 bg-[#0d0d12] rounded-full overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: (n / maxD) * 100 + "%", background: ratingColor(star) }}></div>
                </div>
                <span className="w-8 text-right text-[#6b7280] tabular-nums shrink-0">{n}</span>
              </div>
            );
          })}
        </div>
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wider text-[#6b7280] mb-1">Средняя по дням</div>
          <RatingTrend daily={data.daily || []} />
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wider text-[#6b7280] mb-2">По исполнителям</div>
          <div className="border border-[#2a2a3a]/60 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] uppercase tracking-wider text-[#6b7280] bg-[#0d0d12]/60">
                  <th className="text-left px-3 py-2 font-medium">Кто</th>
                  <th className="text-right px-3 py-2 font-medium">Оценка</th>
                  <th className="text-right px-3 py-2 font-medium">Оценок</th>
                  <th className="text-right px-3 py-2 font-medium" title="Оценки 1–2★">1–2★</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#2a2a3a]/40">
                {(data.operators || []).map((o) => (
                  <tr key={o.name}>
                    <td className="px-3 py-2 text-[#f1f1f5] truncate max-w-[160px]">
                      {o.name}{o.ai && <span className="ml-1.5 text-[10px] text-[#6b7280]">бот</span>}
                    </td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">
                      <span className="tabular-nums font-medium mr-1.5" style={{ color: ratingColor(o.avg) }}>{o.avg.toFixed(1)}</span>
                      <Stars value={o.avg} className="text-xs" />
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-[#9ca3af]">{o.count}</td>
                    <td className={"px-3 py-2 text-right tabular-nums " + (o.low ? "text-[#ef4444]" : "text-[#6b7280]")}>{o.low}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wider text-[#6b7280] mb-2">Низкие оценки — разобрать</div>
          {(data.low || []).length === 0 ? (
            <div className="text-xs text-[#6b7280] border border-[#2a2a3a]/60 rounded-lg px-3 py-4 text-center">
              Оценок 1–2★ за период нет
            </div>
          ) : (
            <div className="border border-[#2a2a3a]/60 rounded-lg divide-y divide-[#2a2a3a]/40 max-h-[320px] overflow-y-auto scrollbar-thin">
              {data.low.map((l) => (
                <div key={l.dialog_id} className="px-3 py-2.5">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="font-semibold" style={{ color: ratingColor(l.rating) }}>{l.rating}★</span>
                    <span className="text-[#f1f1f5] truncate">{l.name || l.username || l.dialog_id}</span>
                    <span className="text-[#6b7280] shrink-0 ml-auto">{new Date(l.at).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" })}</span>
                  </div>
                  <div className="text-[11px] text-[#6b7280] mt-0.5 truncate">
                    {l.operator}{l.service ? ` · ${l.service}` : ""} · <span className="font-mono">{l.dialog_id}</span>
                  </div>
                  {l.text && <div className="text-xs text-[#9ca3af] mt-1 line-clamp-2 break-words">{l.text}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// На телефоне таблица из пяти колонок не читается — те же данные показываем
// карточками: имя со статусом сверху, метрики в ряд под ним.
function OperatorCards({ operators }) {
  return (
    <div className="divide-y divide-[#2a2a3a]/40">
      {operators.map((op) => (
        <div key={op.id} className="px-4 py-3">
          <div className="flex items-center gap-3">
            <Avatar initials={op.initials} color={op.color} size={32} />
            <div className="min-w-0 flex-1">
              <div className="text-sm text-[#f1f1f5] truncate">{op.name}</div>
              <div className="text-[10px] text-[#6b7280] truncate">
                {op.role === "admin" ? "Администратор" : "Агент"} · {op.tg}
              </div>
            </div>
            <span className="inline-flex items-center gap-1.5 text-[11px] shrink-0">
              <span className={"w-1.5 h-1.5 rounded-full " + (op.online ? "bg-[#22c55e]" : "bg-zinc-600")}></span>
              <span className={op.online ? "text-[#22c55e]" : "text-[#6b7280]"}>
                {op.online ? "Онлайн" : "Офлайн"}
              </span>
            </span>
          </div>
          <div className="grid grid-cols-3 gap-2 mt-2.5">
            {[["Диалогов", op.dialogs_count ?? 0],
              ["Первый ответ", fmtDuration(op.first_response_avg)],
              ["Ср. ответ", fmtDuration(op.next_response_avg)]].map(([l, v]) => (
              <div key={l} className="bg-[#0d0d12] rounded-lg px-2 py-1.5">
                <div className="text-[10px] text-[#6b7280] truncate">{l}</div>
                <div className="text-xs text-[#f1f1f5] tabular-nums truncate">{v}</div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function OperatorsTable({ operators, compact = false }) {
  return (
    <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-[#2a2a3a]/60">
        <div className="text-sm font-medium text-[#f1f1f5]">Операторы</div>
        <div className="text-xs text-[#6b7280]">{operators.filter((o) => o.online).length} онлайн</div>
      </div>
      {compact ? <OperatorCards operators={operators} /> : (
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
      )}
    </div>
  );
}

// Чем закончились закрытые за период тикеты: переданы людям, закрыты по
// тишине после последнего сообщения или закрыты без участия оператора.
const AI_OUTCOMES = [
  { key: "timeout",  label: "Закрыто по таймауту", color: "#22c55e",
    hint: "ИИ отвечал, клиент перестал писать — тикет закрылся сам" },
  { key: "handed",   label: "Передано оператору",  color: "#4F8EF7",
    hint: "ИИ передал тикет, оператор взял его сам или писал клиенту" },
  { key: "no_human", label: "Закрыто без оператора", color: "#f59e0b",
    hint: "Оператор закрыл тикет ИИ, не написав клиенту" },
];

function AiOutcomesSection({ data, rangeLabel }) {
  const total = data?.total || 0;
  const pct = (n) => (total ? Math.round((n / total) * 100) : 0);
  return (
    <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-[#2a2a3a]/60 flex items-baseline justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-[#f1f1f5]">Чем закончились диалоги</div>
          <div className="text-xs text-[#6b7280]">{rangeLabel} · закрытые тикеты</div>
        </div>
        {total > 0 && <div className="text-xs text-[#9ca3af] tabular-nums">всего {total}</div>}
      </div>
      {!data ? (
        <div className="py-10 text-center text-sm text-[#6b7280]">Загрузка…</div>
      ) : !total ? (
        <div className="py-10 text-center text-sm text-[#9ca3af]">За период закрытых диалогов нет</div>
      ) : (
        <div className="p-5 space-y-4">
          <div className="flex h-2.5 rounded-full overflow-hidden bg-[#1a1a24]">
            {AI_OUTCOMES.map((o) => data[o.key] > 0 && (
              <div key={o.key} style={{ width: `${(data[o.key] / total) * 100}%`, background: o.color }}
                   title={`${o.label}: ${data[o.key]} (${pct(data[o.key])}%)`} />
            ))}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {AI_OUTCOMES.map((o) => (
              <div key={o.key} className="bg-[#0d0d12] border border-[#2a2a3a]/60 rounded-lg p-3" title={o.hint}>
                <div className="flex items-center gap-2 text-xs text-[#9ca3af]">
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ background: o.color }} />
                  {o.label}
                </div>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="text-2xl font-semibold text-[#f1f1f5] tabular-nums leading-none">{data[o.key]}</span>
                  <span className="text-xs text-[#6b7280] tabular-nums">{pct(data[o.key])}%</span>
                </div>
                <div className="mt-1.5 text-[11px] text-[#6b7280] leading-snug">{o.hint}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatisticsScreen({ serviceId = null, mobileChrome = null }) {
  const [range,  setRange]  = useStateS("14d");
  const [stats,  setStats]  = useStateS(null);
  const [times,  setTimes]  = useStateS(null);
  const [ratings, setRatings] = useStateS(null);
  const [classifying, setClassifying] = useStateS(false);
  const [classifyNote, setClassifyNote] = useStateS(null);

  const days = range === "today" ? 1 : range === "7d" ? 7 : range === "14d" ? 14 : 30;

  useEffectS(() => {
    setStats(null);
    setTimes(null);
    setRatings(null);
    setClassifyNote(null);
    let stale = false;
    // serviceId === null — сводная статистика по всем доступным сервисам
    // (режим «Все сервисы» в переключателе).
    const svc = serviceId === null ? "" : `&service_id=${serviceId}`;
    Promise.all([
      window.apiFetch("GET", `/api/stats?days=${days}${svc}`),
      window.apiFetch("GET", `/api/stats/times?days=${days}${svc}`),
    ]).then(([s, t]) => { if (!stale) { setStats(s); setTimes(t); } }).catch(() => {});
    // Оценки грузятся отдельно: их сбой не должен гасить остальную статистику.
    window.apiFetch("GET", `/api/stats/ratings?days=${days}${svc}`)
      .then((r) => { if (!stale) setRatings(r); })
      .catch(() => { if (!stale) setRatings({ count: 0, rating_off_services: [] }); });
    return () => { stale = true; };
  }, [days, serviceId]);

  // Разметка прошлых обращений идёт фоном на сервере: запускаем и несколько раз
  // перечитываем статистику, пока темы не появятся.
  async function classifyHistory() {
    const svc = serviceId === null ? "" : `&service_id=${serviceId}`;
    setClassifying(true);
    setClassifyNote(null);
    try {
      const r = await window.apiFetch("POST", `/api/stats/classify-history?days=${days}${svc}`);
      if (!r.queued && !r.running) { setClassifyNote("Размечать нечего."); setClassifying(false); return; }
      setClassifyNote(`Размечаю обращения: ${r.queued || ""}. Результат появится через минуту-другую.`);
      for (let i = 0; i < 20; i++) {
        await new Promise((res) => setTimeout(res, 4000));
        const fresh = await window.apiFetch("GET", `/api/stats?days=${days}${svc}`);
        setStats(fresh);
        if (!fresh.classification?.unclassified) break;
      }
      setClassifyNote(null);
    } catch (e) {
      setClassifyNote(typeof e?.detail === "string" ? e.detail : "Не удалось запустить разметку");
    }
    setClassifying(false);
  }

  const ranges = [
    { id: "today", label: "Сегодня" },
    { id: "7d",   label: "7 дней"  },
    { id: "14d",  label: "14 дней" },
    { id: "30d",  label: "30 дней" },
  ];

  const team = times?.team || {};
  const rangeLabel = range === "today" ? "за сутки" : `за ${ranges.find((r) => r.id === range).label.toLowerCase()}`;

  // Merge operator time stats into base operators list from /api/stats
  const operators = useMemoS(() => {
    const base = stats?.operators || [];
    const timeOps = times?.operators || [];
    const timeMap = Object.fromEntries(timeOps.map((o) => [o.id, o]));
    return base.map((op) => ({ ...op, ...(timeMap[op.id] || {}) }));
  }, [stats, times]);

  const chrome = mobileChrome;
  const currentName = chrome && (chrome.currentServiceId == null
    ? "Все сервисы"
    : (chrome.services || []).find((s) => s.id === chrome.currentServiceId)?.name || "");

  return (
    <div className={"h-full bg-[#0d0d12] " +
                    (chrome ? "flex flex-col min-h-0" : "overflow-y-auto scrollbar-thin")}>
      {chrome && (
        <>
          <MobileAppBar title="Статистика" subtitle={currentName}
            right={<AppBarButton icon="bell" label="Уведомления" badge={chrome.bellBadge} onClick={chrome.onBell} />} />
          <ServiceRail services={chrome.services} currentServiceId={chrome.currentServiceId}
                       onSelect={chrome.onSelectService} />
        </>
      )}
      <div className={"max-w-[1400px] w-full mx-auto space-y-4 sm:space-y-5 p-3 sm:p-6 " +
                      (chrome ? "flex-1 min-h-0 overflow-y-auto scrollbar-thin" : "")}>
        {/* Header */}
        <div className="flex items-center justify-between gap-3">
          <div className={chrome ? "hidden" : ""}>
            <h1 className="text-xl font-semibold text-[#f1f1f5]">Статистика</h1>
            <div className="text-xs text-[#6b7280] mt-0.5">данные за выбранный период</div>
          </div>
          <div className="flex items-center gap-3 min-w-0 overflow-x-auto no-scrollbar">
            {/* shrink-0 обязателен: без него флекс-дети сжимаются раньше, чем
                включится прокрутка, и whitespace-nowrap обрезает подписи. */}
            <div className="shrink-0 bg-[#13131a] border border-[#2a2a3a] rounded-lg p-1 flex gap-0.5">
              {ranges.map((r) => (
                <button
                  key={r.id}
                  onClick={() => setRange(r.id)}
                  className={
                    "shrink-0 px-3 rounded-md text-xs font-medium transition whitespace-nowrap " +
                    (chrome ? "min-h-[40px] " : "py-1.5 ") +
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
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4">
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

        <AiOutcomesSection data={stats?.ai_outcomes} rangeLabel={rangeLabel} />

        {/* Charts row */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 sm:gap-4">
          <div className="xl:col-span-2 min-w-0">
            <LineChart data={stats?.daily || []} days={days} />
          </div>
          <div className="min-w-0">
            <HeatmapChart data={stats?.hourly || Array(24).fill(0)} />
          </div>
        </div>

        {/* Bottom row */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-3 sm:gap-4">
          <div className="xl:col-span-2 min-w-0">
            <OperatorsTable operators={operators} compact={!!chrome} />
          </div>
          <div className="min-w-0">
            <TopQuestionsChart data={stats?.top_questions || []} meta={stats?.top_meta}
              classification={stats?.classification} rangeLabel={rangeLabel}
              onClassify={classifyHistory} classifying={classifying} notice={classifyNote} />
          </div>
        </div>

        {/* Ratings */}
        <RatingsSection data={ratings} rangeLabel={rangeLabel} />
      </div>
    </div>
  );
}

Object.assign(window, { StatisticsScreen });
