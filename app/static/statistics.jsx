// Statistics screen

function StatCard({ label, value }) {
  return (
    <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl p-4">
      <div className="text-xs text-[#6b7280] mb-2">{label}</div>
      <div className="text-2xl font-semibold text-[#f1f1f5] tabular-nums leading-none">{value}</div>
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
            <th className="text-left px-3 py-2 font-medium">Роль</th>
            <th className="text-right px-5 py-2 font-medium">Статус</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#2a2a3a]/40">
          {operators.map((op) => (
            <tr key={op.id} className="hover:bg-[#1a1a24]/40 transition">
              <td className="px-5 py-3">
                <div className="flex items-center gap-3">
                  <Avatar initials={op.initials} color={op.color} size={28} />
                  <div className="text-[#f1f1f5]">{op.name}</div>
                </div>
              </td>
              <td className="px-3 py-3 text-xs text-[#6b7280]">
                {op.role === "admin" ? "Администратор" : "Агент"}
              </td>
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

function StatisticsScreen({ operators: ops, todayTotal, todayClosed }) {
  const operators = ops || [];

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin bg-[#0d0d12]">
      <div className="max-w-[900px] mx-auto p-6 space-y-5">
        <div>
          <h1 className="text-xl font-semibold text-[#f1f1f5]">Статистика</h1>
          <div className="text-xs text-[#6b7280] mt-0.5">данные за сегодня</div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <StatCard label="Обращений сегодня" value={todayTotal != null ? String(todayTotal) : "—"} />
          <StatCard label="Закрыто диалогов" value={todayClosed != null ? String(todayClosed) : "—"} />
        </div>

        <OperatorsTable operators={operators} />
      </div>
    </div>
  );
}

Object.assign(window, { StatisticsScreen });
