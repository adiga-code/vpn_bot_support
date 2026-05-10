// Settings screen

const { useState: useStateT } = React;

function SettingsScreen({ operators: ops, setOperators, showToast }) {
  const [section, setSection] = useStateT("operators");
  const [modalOpen, setModalOpen] = useStateT(false);
  const [editingOp, setEditingOp] = useStateT(null);
  const [confirmDelete, setConfirmDelete] = useStateT(null);

  const sections = [
    { id: "operators", label: "Операторы", icon: "operators" },
    { id: "schedule", label: "Расписание", icon: "clock" },
    { id: "ai", label: "ИИ-настройки", icon: "sparkles" },
    { id: "notifications", label: "Уведомления", icon: "bell" },
    { id: "kb", label: "База знаний", icon: "book" },
  ];

  return (
    <div className="flex-1 flex bg-[#0d0d12] min-h-0">
      {/* Settings sidebar */}
      <aside className="w-[240px] shrink-0 bg-[#13131a] border-r border-[#2a2a3a] p-4">
        <div className="text-[10px] uppercase tracking-wider text-[#6b7280] font-semibold mb-3 px-2">Настройки</div>
        <nav className="space-y-0.5">
          {sections.map((s) => (
            <button
              key={s.id}
              onClick={() => setSection(s.id)}
              className={
                "w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition " +
                (section === s.id
                  ? "bg-[#4F8EF7]/15 text-[#7BA8F9]"
                  : "text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24]")
              }
            >
              <Icon name={s.icon} className="w-4 h-4" />
              {s.label}
            </button>
          ))}
        </nav>
      </aside>

      {/* Settings content */}
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {section === "operators" && (
          <OperatorsSection
            operators={ops}
            setOperators={setOperators}
            onAdd={() => { setEditingOp(null); setModalOpen(true); }}
            onEdit={(op) => { setEditingOp(op); setModalOpen(true); }}
            onDelete={(op) => setConfirmDelete(op)}
          />
        )}
        {section === "schedule" && <ScheduleSection />}
        {section === "ai" && <AISection showToast={showToast} />}
        {section === "notifications" && <NotificationsSection showToast={showToast} />}
        {section === "kb" && <KBSection />}
      </div>

      {modalOpen && (
        <OperatorModal
          editing={editingOp}
          onClose={() => setModalOpen(false)}
          onSave={(data) => {
            if (editingOp) {
              setOperators((arr) => arr.map((o) => (o.id === editingOp.id ? { ...o, ...data } : o)));
              showToast("Оператор обновлён");
            } else {
              const id = Math.max(...ops.map((o) => o.id)) + 1;
              const initials = data.name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();
              const colors = ["#A855F7", "#4F8EF7", "#22c55e", "#eab308", "#f97316", "#ef4444", "#06b6d4"];
              setOperators((arr) => [...arr, { ...data, id, initials, color: colors[arr.length % colors.length], online: false, closed: 0, avgTime: "—" }]);
              showToast("Оператор добавлен");
            }
            setModalOpen(false);
          }}
        />
      )}

      {confirmDelete && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => setConfirmDelete(null)}>
          <div className="bg-[#13131a] border border-[#2a2a3a] rounded-xl p-6 w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
            <div className="font-semibold text-[#f1f1f5] mb-1">Удалить оператора?</div>
            <div className="text-sm text-[#6b7280] mb-5">«{confirmDelete.name}» больше не сможет отвечать на диалоги.</div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setConfirmDelete(null)} className="px-3 py-1.5 rounded-lg text-sm text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24]">
                Отмена
              </button>
              <button
                onClick={() => {
                  setOperators((arr) => arr.filter((o) => o.id !== confirmDelete.id));
                  showToast("Оператор удалён");
                  setConfirmDelete(null);
                }}
                className="px-3 py-1.5 rounded-lg text-sm font-medium bg-[#ef4444]/20 text-[#ef4444] border border-[#ef4444]/30 hover:bg-[#ef4444]/30"
              >
                Удалить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function OperatorsSection({ operators, setOperators, onAdd, onEdit, onDelete }) {
  return (
    <div className="max-w-[1100px] mx-auto p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[#f1f1f5]">Операторы</h1>
          <div className="text-xs text-[#6b7280] mt-0.5">{operators.length} операторов · {operators.filter((o) => o.online).length} онлайн</div>
        </div>
        <button
          onClick={onAdd}
          className="px-3 py-2 rounded-lg bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white text-xs font-semibold transition flex items-center gap-1.5"
        >
          <Icon name="plus" className="w-3.5 h-3.5" strokeWidth={2.5} />
          Добавить оператора
        </button>
      </div>

      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] uppercase tracking-wider text-[#6b7280] border-b border-[#2a2a3a]/60">
              <th className="text-left px-5 py-3 font-medium">Имя</th>
              <th className="text-left px-3 py-3 font-medium">Telegram</th>
              <th className="text-left px-3 py-3 font-medium">Роль</th>
              <th className="text-left px-3 py-3 font-medium">Статус</th>
              <th className="text-right px-5 py-3 font-medium w-[120px]">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#2a2a3a]/40">
            {operators.map((op) => (
              <tr key={op.id} className="hover:bg-[#1a1a24]/40 transition">
                <td className="px-5 py-3">
                  <div className="flex items-center gap-3">
                    <Avatar initials={op.initials} color={op.color} size={32} />
                    <div className="font-medium text-[#f1f1f5]">{op.name}</div>
                  </div>
                </td>
                <td className="px-3 py-3 text-[#6b7280] font-mono text-xs">{op.tg}</td>
                <td className="px-3 py-3">
                  <span className={
                    "inline-flex px-2 py-0.5 rounded-md text-[11px] font-medium border " +
                    (op.role === "admin"
                      ? "bg-[#A855F7]/15 text-[#C084FC] border-[#A855F7]/30"
                      : "bg-[#1a1a24] text-[#f1f1f5] border-[#2a2a3a]")
                  }>
                    {op.role === "admin" ? "Администратор" : "Агент"}
                  </span>
                </td>
                <td className="px-3 py-3">
                  <span className="inline-flex items-center gap-1.5 text-xs">
                    <span className={"w-1.5 h-1.5 rounded-full " + (op.online ? "bg-[#22c55e]" : "bg-zinc-600")}></span>
                    <span className={op.online ? "text-[#22c55e]" : "text-[#6b7280]"}>
                      {op.online ? "Онлайн" : "Офлайн"}
                    </span>
                  </span>
                </td>
                <td className="px-5 py-3">
                  <div className="flex items-center justify-end gap-1">
                    <button
                      onClick={() => onEdit(op)}
                      className="p-1.5 text-[#6b7280] hover:text-[#7BA8F9] hover:bg-[#4F8EF7]/10 rounded transition"
                      title="Редактировать"
                    >
                      <Icon name="edit" className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => onDelete(op)}
                      className="p-1.5 text-[#6b7280] hover:text-[#ef4444] hover:bg-[#ef4444]/10 rounded transition"
                      title="Удалить"
                    >
                      <Icon name="trash" className="w-4 h-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function OperatorModal({ editing, onClose, onSave }) {
  const [name, setName] = useStateT(editing?.name || "");
  const [tg, setTg] = useStateT(editing?.tg || "@");
  const [role, setRole] = useStateT(editing?.role || "agent");

  function submit(e) {
    e?.preventDefault();
    if (!name.trim() || tg.length < 2) return;
    onSave({ name: name.trim(), tg: tg.trim(), role });
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <form onSubmit={submit} className="bg-[#13131a] border border-[#2a2a3a] rounded-xl w-full max-w-md overflow-hidden" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-[#2a2a3a] flex items-center justify-between">
          <div className="font-semibold text-[#f1f1f5]">{editing ? "Редактировать оператора" : "Добавить оператора"}</div>
          <button type="button" onClick={onClose} className="p-1 text-[#6b7280] hover:text-[#f1f1f5] rounded">
            <Icon name="x" />
          </button>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <label className="block text-xs text-[#6b7280] mb-1.5">Имя</label>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Алексей Петров"
              className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2 text-sm text-[#f1f1f5] placeholder:text-[#6b7280] focus:outline-none focus:border-[#4F8EF7]/50"
            />
          </div>
          <div>
            <label className="block text-xs text-[#6b7280] mb-1.5">Telegram username</label>
            <input
              value={tg}
              onChange={(e) => {
                let v = e.target.value;
                if (!v.startsWith("@")) v = "@" + v.replace(/^@*/, "");
                setTg(v);
              }}
              placeholder="@username"
              className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2 text-sm text-[#f1f1f5] placeholder:text-[#6b7280] focus:outline-none focus:border-[#4F8EF7]/50 font-mono"
            />
          </div>
          <div>
            <label className="block text-xs text-[#6b7280] mb-1.5">Роль</label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setRole("agent")}
                className={
                  "px-3 py-2.5 rounded-lg text-sm font-medium border transition text-left " +
                  (role === "agent"
                    ? "bg-[#4F8EF7]/15 border-[#4F8EF7]/40 text-[#7BA8F9]"
                    : "bg-[#0d0d12] border-[#2a2a3a] text-[#6b7280] hover:text-[#f1f1f5]")
                }
              >
                <div>Агент</div>
                <div className="text-[10px] text-[#6b7280] mt-0.5">Отвечает на диалоги</div>
              </button>
              <button
                type="button"
                onClick={() => setRole("admin")}
                className={
                  "px-3 py-2.5 rounded-lg text-sm font-medium border transition text-left " +
                  (role === "admin"
                    ? "bg-[#A855F7]/15 border-[#A855F7]/40 text-[#C084FC]"
                    : "bg-[#0d0d12] border-[#2a2a3a] text-[#6b7280] hover:text-[#f1f1f5]")
                }
              >
                <div>Администратор</div>
                <div className="text-[10px] text-[#6b7280] mt-0.5">Полный доступ</div>
              </button>
            </div>
          </div>
        </div>
        <div className="px-5 py-4 border-t border-[#2a2a3a] flex justify-end gap-2 bg-[#0d0d12]/50">
          <button type="button" onClick={onClose} className="px-3 py-1.5 rounded-lg text-sm text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24]">
            Отмена
          </button>
          <button
            type="submit"
            disabled={!name.trim() || tg.length < 2}
            className="px-4 py-1.5 rounded-lg text-sm font-semibold bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {editing ? "Сохранить" : "Добавить"}
          </button>
        </div>
      </form>
    </div>
  );
}

function ScheduleSection() {
  const days = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"];
  return (
    <div className="max-w-[1100px] mx-auto p-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-[#f1f1f5]">Расписание</h1>
        <div className="text-xs text-[#6b7280] mt-0.5">Когда боту переключаться на ручной режим</div>
      </div>
      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl p-5">
        <div className="text-sm font-medium text-[#f1f1f5] mb-4">Рабочие часы операторов</div>
        <div className="space-y-2">
          {days.map((d, i) => {
            const off = i >= 5;
            return (
              <div key={d} className="flex items-center gap-4">
                <div className="w-10 text-sm text-[#f1f1f5]">{d}</div>
                <div className="flex-1 h-8 bg-[#0d0d12] rounded-md relative overflow-hidden">
                  {!off && (
                    <div className="absolute top-0 bottom-0 bg-[#4F8EF7]/30 border-l border-r border-[#4F8EF7] rounded" style={{ left: "37.5%", width: "33.3%" }}>
                      <div className="text-[10px] text-[#7BA8F9] px-2 py-1.5 font-medium">09:00 – 21:00</div>
                    </div>
                  )}
                  {[0,4,8,12,16,20,24].map((h) => (
                    <div key={h} className="absolute top-0 bottom-0 border-l border-[#2a2a3a]/40" style={{ left: (h / 24 * 100) + "%" }}></div>
                  ))}
                </div>
                <span className={"text-xs " + (off ? "text-[#6b7280]" : "text-[#22c55e]")}>{off ? "Выходной" : "Рабочий"}</span>
              </div>
            );
          })}
        </div>
        <div className="flex justify-between text-[10px] text-[#6b7280] mt-2 ml-14 tabular-nums">
          <span>00</span><span>04</span><span>08</span><span>12</span><span>16</span><span>20</span><span>24</span>
        </div>
      </div>
    </div>
  );
}

function AISection({ showToast }) {
  const [autoReply, setAutoReply] = useStateT(true);
  const [handoff, setHandoff] = useStateT(true);
  const [temp, setTemp] = useStateT(0.7);
  const [prompt, setPrompt] = useStateT("Ты — дружелюбный ассистент поддержки VPN-сервиса. Отвечай кратко, на русском. Если не знаешь ответ — предложи передать диалог оператору.");

  return (
    <div className="max-w-[1100px] mx-auto p-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-[#f1f1f5]">ИИ-настройки</h1>
        <div className="text-xs text-[#6b7280] mt-0.5">Поведение бота по умолчанию</div>
      </div>

      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl divide-y divide-[#2a2a3a]/60">
        <SettingsRow
          title="Автоматические ответы"
          desc="Бот сам отвечает на сообщения пользователей"
          control={<Switch on={autoReply} onChange={() => setAutoReply((v) => !v)} />}
        />
        <SettingsRow
          title="Передавать оператору при низкой уверенности"
          desc="Если уверенность ИИ < 60%, диалог уходит человеку"
          control={<Switch on={handoff} onChange={() => setHandoff((v) => !v)} />}
        />
        <div className="px-5 py-4">
          <div className="flex justify-between mb-2">
            <div>
              <div className="text-sm text-[#f1f1f5]">Температура модели</div>
              <div className="text-xs text-[#6b7280]">Чем выше — тем креативнее ответы</div>
            </div>
            <div className="text-sm font-medium text-[#7BA8F9] tabular-nums">{temp.toFixed(2)}</div>
          </div>
          <input
            type="range" min="0" max="1" step="0.05"
            value={temp}
            onChange={(e) => setTemp(parseFloat(e.target.value))}
            className="w-full accent-[#4F8EF7]"
          />
        </div>
      </div>

      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl p-5">
        <div className="text-sm font-medium text-[#f1f1f5] mb-1">Системный промпт</div>
        <div className="text-xs text-[#6b7280] mb-3">Инструкции, которые получает модель в начале каждого диалога</div>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={6}
          className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2 text-sm text-[#f1f1f5] focus:outline-none focus:border-[#4F8EF7]/50 leading-relaxed"
        />
        <div className="flex justify-end mt-3">
          <button
            onClick={() => showToast("Настройки ИИ сохранены")}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white"
          >
            Сохранить
          </button>
        </div>
      </div>
    </div>
  );
}

function NotificationsSection({ showToast }) {
  const [n1, setN1] = useStateT(true);
  const [n2, setN2] = useStateT(true);
  const [n3, setN3] = useStateT(false);
  const [n4, setN4] = useStateT(true);
  return (
    <div className="max-w-[1100px] mx-auto p-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-[#f1f1f5]">Уведомления</h1>
        <div className="text-xs text-[#6b7280] mt-0.5">Что отправлять оператору</div>
      </div>
      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl divide-y divide-[#2a2a3a]/60">
        <SettingsRow title="Новый диалог" desc="Пинг в Telegram при появлении нового запроса" control={<Switch on={n1} onChange={() => setN1((v) => !v)} />} />
        <SettingsRow title="Пользователь вызвал оператора" desc="Звуковое уведомление в браузере" control={<Switch on={n2} onChange={() => setN2((v) => !v)} />} />
        <SettingsRow title="Email-дайджест" desc="Сводка за день каждое утро в 09:00" control={<Switch on={n3} onChange={() => setN3((v) => !v)} />} />
        <SettingsRow title="Сервер VPN недоступен" desc="Мгновенное оповещение об инцидентах" control={<Switch on={n4} onChange={() => setN4((v) => !v)} />} />
      </div>
    </div>
  );
}

function KBSection() {
  const articles = [
    { title: "Как настроить WireGuard на iPhone", views: 4821, updated: "5 мая 2026" },
    { title: "Оплата через USDT — пошаговая инструкция", views: 3204, updated: "2 мая 2026" },
    { title: "Список серверов и их назначение", views: 2876, updated: "30 апр 2026" },
    { title: "Подключение на macOS", views: 2104, updated: "27 апр 2026" },
    { title: "Что делать при низкой скорости", views: 1893, updated: "18 апр 2026" },
    { title: "Возврат средств — условия и сроки", views: 1240, updated: "12 апр 2026" },
  ];
  return (
    <div className="max-w-[1100px] mx-auto p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[#f1f1f5]">База знаний</h1>
          <div className="text-xs text-[#6b7280] mt-0.5">{articles.length} статей · используется ИИ для ответов</div>
        </div>
        <button className="px-3 py-2 rounded-lg bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white text-xs font-semibold flex items-center gap-1.5">
          <Icon name="plus" className="w-3.5 h-3.5" strokeWidth={2.5} />
          Добавить статью
        </button>
      </div>
      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl divide-y divide-[#2a2a3a]/60">
        {articles.map((a, i) => (
          <div key={i} className="px-5 py-3 flex items-center justify-between hover:bg-[#1a1a24]/40 transition group cursor-pointer">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-9 h-9 rounded-lg bg-[#4F8EF7]/10 text-[#7BA8F9] flex items-center justify-center shrink-0">
                <Icon name="book" />
              </div>
              <div className="min-w-0">
                <div className="text-sm text-[#f1f1f5] truncate">{a.title}</div>
                <div className="text-xs text-[#6b7280]">{a.views.toLocaleString("ru-RU")} просмотров · обновлено {a.updated}</div>
              </div>
            </div>
            <Icon name="chevronRight" className="w-4 h-4 text-[#6b7280] opacity-0 group-hover:opacity-100 transition" />
          </div>
        ))}
      </div>
    </div>
  );
}

function SettingsRow({ title, desc, control }) {
  return (
    <div className="px-5 py-4 flex items-center justify-between gap-4">
      <div>
        <div className="text-sm text-[#f1f1f5]">{title}</div>
        <div className="text-xs text-[#6b7280] mt-0.5">{desc}</div>
      </div>
      {control}
    </div>
  );
}

function Switch({ on, onChange }) {
  return (
    <button
      type="button"
      onClick={onChange}
      className={"relative w-10 h-[22px] rounded-full transition shrink-0 " + (on ? "bg-[#4F8EF7]" : "bg-[#2a2a3a]")}
    >
      <span className={"absolute top-[2px] w-[18px] h-[18px] bg-white rounded-full transition-all " + (on ? "left-[20px]" : "left-[2px]")}></span>
    </button>
  );
}

Object.assign(window, { SettingsScreen });
