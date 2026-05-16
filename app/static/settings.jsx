// Settings screen

const { useState: useStateT, useEffect: useEffectT } = React;

function SettingsScreen({ operators: ops, setOperators, showToast }) {
  const [section, setSection] = useStateT("operators");
  const [modalOpen, setModalOpen] = useStateT(false);
  const [editingOp, setEditingOp] = useStateT(null);
  const [confirmDelete, setConfirmDelete] = useStateT(null);

  const sections = [
    { id: "operators",     label: "Операторы",    icon: "operators" },
    { id: "profile",       label: "Профиль",      icon: "user"      },
    { id: "schedule",      label: "Расписание",   icon: "clock"     },
    { id: "ai",            label: "ИИ-настройки", icon: "sparkles"  },
    { id: "notifications", label: "Уведомления",  icon: "bell"      },
    { id: "kb",            label: "База знаний",  icon: "book"      },
  ];

  async function saveOperator(data) {
    try {
      if (editingOp) {
        const updated = await window.apiFetch("PUT", `/api/operators/${editingOp.id}`, data);
        setOperators((arr) => arr.map((o) => (o.id === editingOp.id ? { ...o, ...updated } : o)));
        showToast("Оператор обновлён");
      } else {
        const created = await window.apiFetch("POST", "/api/operators", data);
        setOperators((arr) => [...arr, { ...created, closed: 0, avgTime: "—" }]);
        showToast("Оператор добавлен");
      }
    } catch (e) {
      showToast("Ошибка сохранения");
    }
    setModalOpen(false);
  }

  async function deleteOperator(op) {
    try {
      await window.apiFetch("DELETE", `/api/operators/${op.id}`);
      setOperators((arr) => arr.filter((o) => o.id !== op.id));
      showToast("Оператор удалён");
    } catch (e) {
      showToast("Ошибка удаления");
    }
    setConfirmDelete(null);
  }

  return (
    <div className="flex-1 flex bg-[#0d0d12] min-h-0">
      <aside className="w-[240px] shrink-0 bg-[#13131a] border-r border-[#2a2a3a] p-4">
        <div className="text-[10px] uppercase tracking-wider text-[#6b7280] font-semibold mb-3 px-2">Настройки</div>
        <nav className="space-y-0.5">
          {sections.map((s) => (
            <button key={s.id} onClick={() => setSection(s.id)}
              className={"w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition " +
                (section === s.id ? "bg-[#4F8EF7]/15 text-[#7BA8F9]" : "text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24]")}>
              <Icon name={s.icon} className="w-4 h-4" />
              {s.label}
            </button>
          ))}
        </nav>
      </aside>

      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {section === "operators"     && <OperatorsSection operators={ops} onAdd={() => { setEditingOp(null); setModalOpen(true); }} onEdit={(op) => { setEditingOp(op); setModalOpen(true); }} onDelete={(op) => setConfirmDelete(op)} />}
        {section === "profile"       && <ProfileSection showToast={showToast} />}
        {section === "schedule"      && <ScheduleSection showToast={showToast} />}
        {section === "ai"            && <AISection showToast={showToast} />}
        {section === "notifications" && <NotificationsSection showToast={showToast} />}
        {section === "kb"            && <KBSection />}
      </div>

      {modalOpen && <OperatorModal editing={editingOp} onClose={() => setModalOpen(false)} onSave={saveOperator} />}

      {confirmDelete && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => setConfirmDelete(null)}>
          <div className="bg-[#13131a] border border-[#2a2a3a] rounded-xl p-6 w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
            <div className="font-semibold text-[#f1f1f5] mb-1">Удалить оператора?</div>
            <div className="text-sm text-[#6b7280] mb-5">«{confirmDelete.name}» больше не сможет отвечать.</div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setConfirmDelete(null)} className="px-3 py-1.5 rounded-lg text-sm text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24]">Отмена</button>
              <button onClick={() => deleteOperator(confirmDelete)} className="px-3 py-1.5 rounded-lg text-sm font-medium bg-[#ef4444]/20 text-[#ef4444] border border-[#ef4444]/30 hover:bg-[#ef4444]/30">Удалить</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function OperatorsSection({ operators, onAdd, onEdit, onDelete }) {
  return (
    <div className="max-w-[1100px] mx-auto p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[#f1f1f5]">Операторы</h1>
          <div className="text-xs text-[#6b7280] mt-0.5">{operators.length} операторов · {operators.filter((o) => o.online).length} онлайн</div>
        </div>
        <button onClick={onAdd} className="px-3 py-2 rounded-lg bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white text-xs font-semibold transition flex items-center gap-1.5">
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
                    <Avatar initials={op.initials || "??"} color={op.color || "#4F8EF7"} size={32} />
                    <div className="font-medium text-[#f1f1f5]">{op.name}</div>
                  </div>
                </td>
                <td className="px-3 py-3 text-[#6b7280] font-mono text-xs">{op.tg}</td>
                <td className="px-3 py-3">
                  <span className={"inline-flex px-2 py-0.5 rounded-md text-[11px] font-medium border " +
                    (op.role === "admin" ? "bg-[#A855F7]/15 text-[#C084FC] border-[#A855F7]/30" : "bg-[#1a1a24] text-[#f1f1f5] border-[#2a2a3a]")}>
                    {op.role === "admin" ? "Администратор" : "Агент"}
                  </span>
                </td>
                <td className="px-3 py-3">
                  <span className="inline-flex items-center gap-1.5 text-xs">
                    <span className={"w-1.5 h-1.5 rounded-full " + (op.online ? "bg-[#22c55e]" : "bg-zinc-600")}></span>
                    <span className={op.online ? "text-[#22c55e]" : "text-[#6b7280]"}>{op.online ? "Онлайн" : "Офлайн"}</span>
                  </span>
                </td>
                <td className="px-5 py-3">
                  <div className="flex items-center justify-end gap-1">
                    <button onClick={() => onEdit(op)} className="p-1.5 text-[#6b7280] hover:text-[#7BA8F9] hover:bg-[#4F8EF7]/10 rounded transition"><Icon name="edit" className="w-4 h-4" /></button>
                    <button onClick={() => onDelete(op)} className="p-1.5 text-[#6b7280] hover:text-[#ef4444] hover:bg-[#ef4444]/10 rounded transition"><Icon name="trash" className="w-4 h-4" /></button>
                  </div>
                </td>
              </tr>
            ))}
            {operators.length === 0 && <tr><td colSpan={5} className="px-5 py-8 text-center text-xs text-[#6b7280]">Нет операторов</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function OperatorModal({ editing, onClose, onSave }) {
  const [name, setName] = useStateT(editing?.name || "");
  const [tg,   setTg]   = useStateT(editing?.tg   || "@");
  const [role, setRole] = useStateT(editing?.role  || "agent");

  function submit(e) {
    e?.preventDefault();
    if (!name.trim() || tg.length < 2) return;
    onSave({ name: name.trim(), tg: tg.trim(), role });
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <form onSubmit={submit} className="bg-[#13131a] border border-[#2a2a3a] rounded-xl w-full max-w-md overflow-hidden" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-[#2a2a3a] flex items-center justify-between">
          <div className="font-semibold text-[#f1f1f5]">{editing ? "Редактировать" : "Добавить оператора"}</div>
          <button type="button" onClick={onClose} className="p-1 text-[#6b7280] hover:text-[#f1f1f5] rounded"><Icon name="x" /></button>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <label className="block text-xs text-[#6b7280] mb-1.5">Имя</label>
            <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Алексей Петров"
              className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2 text-sm text-[#f1f1f5] placeholder:text-[#6b7280] focus:outline-none focus:border-[#4F8EF7]/50" />
          </div>
          <div>
            <label className="block text-xs text-[#6b7280] mb-1.5">Telegram username</label>
            <input value={tg} onChange={(e) => { let v = e.target.value; if (!v.startsWith("@")) v = "@" + v.replace(/^@*/, ""); setTg(v); }} placeholder="@username"
              className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2 text-sm text-[#f1f1f5] placeholder:text-[#6b7280] focus:outline-none focus:border-[#4F8EF7]/50 font-mono" />
          </div>
          <div>
            <label className="block text-xs text-[#6b7280] mb-1.5">Роль</label>
            <div className="grid grid-cols-2 gap-2">
              {[["agent","Агент","Отвечает на диалоги"],["admin","Администратор","Полный доступ"]].map(([val, label, desc]) => (
                <button key={val} type="button" onClick={() => setRole(val)}
                  className={"px-3 py-2.5 rounded-lg text-sm font-medium border transition text-left " +
                    (role === val ? (val === "admin" ? "bg-[#A855F7]/15 border-[#A855F7]/40 text-[#C084FC]" : "bg-[#4F8EF7]/15 border-[#4F8EF7]/40 text-[#7BA8F9]") : "bg-[#0d0d12] border-[#2a2a3a] text-[#6b7280] hover:text-[#f1f1f5]")}>
                  <div>{label}</div>
                  <div className="text-[10px] text-[#6b7280] mt-0.5">{desc}</div>
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="px-5 py-4 border-t border-[#2a2a3a] flex justify-end gap-2 bg-[#0d0d12]/50">
          <button type="button" onClick={onClose} className="px-3 py-1.5 rounded-lg text-sm text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24]">Отмена</button>
          <button type="submit" disabled={!name.trim() || tg.length < 2}
            className="px-4 py-1.5 rounded-lg text-sm font-semibold bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white transition disabled:opacity-40 disabled:cursor-not-allowed">
            {editing ? "Сохранить" : "Добавить"}
          </button>
        </div>
      </form>
    </div>
  );
}

function ProfileSection({ showToast }) {
  const [current,  setCurrent]  = useStateT("");
  const [newPw,    setNewPw]    = useStateT("");
  const [newPw2,   setNewPw2]   = useStateT("");
  const [loading,  setLoading]  = useStateT(false);
  const [err,      setErr]      = useStateT(null);

  async function submit(e) {
    e?.preventDefault();
    if (newPw !== newPw2)  { setErr("Пароли не совпадают"); return; }
    if (newPw.length < 6)  { setErr("Новый пароль — минимум 6 символов"); return; }
    setLoading(true);
    setErr(null);
    try {
      await window.apiFetch("PUT", "/api/auth/password", {
        current_password: current,
        new_password: newPw,
      });
      setCurrent(""); setNewPw(""); setNewPw2("");
      showToast("Пароль изменён");
    } catch {
      setErr("Неверный текущий пароль");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-[600px] mx-auto p-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-[#f1f1f5]">Профиль</h1>
        <div className="text-xs text-[#6b7280] mt-0.5">Управление своим аккаунтом</div>
      </div>
      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl p-5">
        <div className="text-sm font-medium text-[#f1f1f5] mb-4">Смена пароля</div>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-xs text-[#6b7280] mb-1.5">Текущий пароль</label>
            <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)}
              className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2 text-sm text-[#f1f1f5] focus:outline-none focus:border-[#4F8EF7]/50" />
          </div>
          <div>
            <label className="block text-xs text-[#6b7280] mb-1.5">Новый пароль</label>
            <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)}
              className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2 text-sm text-[#f1f1f5] focus:outline-none focus:border-[#4F8EF7]/50" />
          </div>
          <div>
            <label className="block text-xs text-[#6b7280] mb-1.5">Повторите новый пароль</label>
            <input type="password" value={newPw2} onChange={(e) => setNewPw2(e.target.value)}
              className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2 text-sm text-[#f1f1f5] focus:outline-none focus:border-[#4F8EF7]/50" />
          </div>
          {err && (
            <div className="text-xs text-[#ef4444] bg-[#ef4444]/10 border border-[#ef4444]/20 rounded-lg px-3 py-2">
              {err}
            </div>
          )}
          <button type="submit" disabled={loading || !current || !newPw || !newPw2}
            className="px-4 py-2 rounded-lg bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white text-sm font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed">
            {loading ? "Сохранение..." : "Изменить пароль"}
          </button>
        </form>
      </div>
    </div>
  );
}

function ScheduleSection({ showToast }) {
  const DAYS = [
    {key:"mon",label:"Пн"},{key:"tue",label:"Вт"},{key:"wed",label:"Ср"},
    {key:"thu",label:"Чт"},{key:"fri",label:"Пт"},{key:"sat",label:"Сб"},{key:"sun",label:"Вс"},
  ];
  const [schedule, setSchedule] = useStateT(null);

  useEffectT(() => {
    window.apiFetch("GET", "/api/settings/schedule").then(setSchedule).catch(() => {});
  }, []);

  function setDay(key, field, value) {
    setSchedule((s) => ({ ...s, [key]: { ...s[key], [field]: value } }));
  }

  async function save() {
    try {
      await window.apiFetch("PUT", "/api/settings/schedule", { schedule });
      showToast("Расписание сохранено");
    } catch { showToast("Ошибка сохранения"); }
  }

  if (!schedule) return <div className="p-6 text-[#6b7280] text-sm">Загрузка...</div>;

  return (
    <div className="max-w-[1100px] mx-auto p-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-[#f1f1f5]">Расписание</h1>
        <div className="text-xs text-[#6b7280] mt-0.5">Вне рабочего времени — автоответ пользователю</div>
      </div>
      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl divide-y divide-[#2a2a3a]/60">
        {DAYS.map(({ key, label }) => {
          const day = schedule[key] || { enabled: false, from: "09:00", to: "21:00" };
          return (
            <div key={key} className="px-5 py-3 flex items-center gap-4 flex-wrap">
              <div className="w-8 text-sm text-[#f1f1f5] font-medium">{label}</div>
              <Switch on={day.enabled} onChange={() => setDay(key, "enabled", !day.enabled)} />
              {day.enabled ? (
                <div className="flex items-center gap-2">
                  <input type="time" value={day.from} onChange={(e) => setDay(key, "from", e.target.value)}
                    className="bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-2 py-1 text-sm text-[#f1f1f5] focus:outline-none focus:border-[#4F8EF7]/50" />
                  <span className="text-[#6b7280]">—</span>
                  <input type="time" value={day.to} onChange={(e) => setDay(key, "to", e.target.value)}
                    className="bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-2 py-1 text-sm text-[#f1f1f5] focus:outline-none focus:border-[#4F8EF7]/50" />
                  <span className="text-xs text-[#22c55e]">Рабочий</span>
                </div>
              ) : (
                <span className="text-xs text-[#6b7280]">Выходной</span>
              )}
            </div>
          );
        })}
      </div>
      <div className="flex justify-end">
        <button onClick={save} className="px-4 py-2 rounded-lg bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white text-sm font-semibold">Сохранить</button>
      </div>
    </div>
  );
}

function AISection({ showToast }) {
  const [settings, setSettings] = useStateT(null);

  useEffectT(() => {
    window.apiFetch("GET", "/api/settings/ai").then(setSettings).catch(() => {});
  }, []);

  async function save() {
    try {
      await window.apiFetch("PUT", "/api/settings/ai", settings);
      showToast("Настройки ИИ сохранены");
    } catch { showToast("Ошибка сохранения"); }
  }

  if (!settings) return <div className="p-6 text-[#6b7280] text-sm">Загрузка...</div>;

  return (
    <div className="max-w-[1100px] mx-auto p-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-[#f1f1f5]">ИИ-настройки</h1>
        <div className="text-xs text-[#6b7280] mt-0.5">Сохраняется в БД и Redis — n8n подхватывает сразу</div>
      </div>
      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl divide-y divide-[#2a2a3a]/60">
        <SettingsRow title="Автоматические ответы" desc="ИИ сам отвечает на сообщения" control={<Switch on={settings.auto_reply} onChange={() => setSettings((s) => ({ ...s, auto_reply: !s.auto_reply }))} />} />
        <SettingsRow title="Передавать при низкой уверенности" desc="Если ИИ не уверен — зовёт оператора" control={<Switch on={settings.handoff_enabled} onChange={() => setSettings((s) => ({ ...s, handoff_enabled: !s.handoff_enabled }))} />} />
        <div className="px-5 py-4">
          <div className="flex justify-between mb-2">
            <div>
              <div className="text-sm text-[#f1f1f5]">Температура модели</div>
              <div className="text-xs text-[#6b7280]">Чем выше — тем креативнее</div>
            </div>
            <div className="text-sm font-medium text-[#7BA8F9] tabular-nums">{Number(settings.temperature).toFixed(2)}</div>
          </div>
          <input type="range" min="0" max="1" step="0.05" value={settings.temperature}
            onChange={(e) => setSettings((s) => ({ ...s, temperature: parseFloat(e.target.value) }))}
            className="w-full accent-[#4F8EF7]" />
        </div>
      </div>
      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl p-5">
        <div className="text-sm font-medium text-[#f1f1f5] mb-1">Системный промпт</div>
        <div className="text-xs text-[#6b7280] mb-3">Инструкции для ИИ в начале каждого диалога</div>
        <textarea value={settings.prompt} onChange={(e) => setSettings((s) => ({ ...s, prompt: e.target.value }))} rows={6}
          className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2 text-sm text-[#f1f1f5] focus:outline-none focus:border-[#4F8EF7]/50 leading-relaxed" />
      </div>
      <div className="flex justify-end">
        <button onClick={save} className="px-4 py-2 rounded-lg bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white text-sm font-semibold">Сохранить</button>
      </div>
    </div>
  );
}

function NotificationsSection({ showToast }) {
  const [n1,setN1]=useStateT(true); const [n2,setN2]=useStateT(true);
  const [n3,setN3]=useStateT(false); const [n4,setN4]=useStateT(true);
  return (
    <div className="max-w-[1100px] mx-auto p-6 space-y-5">
      <div><h1 className="text-xl font-semibold text-[#f1f1f5]">Уведомления</h1></div>
      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl divide-y divide-[#2a2a3a]/60">
        <SettingsRow title="Новый диалог" desc="Пинг в Telegram при новом обращении" control={<Switch on={n1} onChange={()=>setN1(v=>!v)} />} />
        <SettingsRow title="Пользователь вызвал оператора" desc="Уведомление в браузере" control={<Switch on={n2} onChange={()=>setN2(v=>!v)} />} />
        <SettingsRow title="Email-дайджест" desc="Сводка за день каждое утро в 09:00" control={<Switch on={n3} onChange={()=>setN3(v=>!v)} />} />
        <SettingsRow title="Сервер VPN недоступен" desc="Мгновенное оповещение об инцидентах" control={<Switch on={n4} onChange={()=>setN4(v=>!v)} />} />
      </div>
      <div className="flex justify-end">
        <button onClick={() => showToast("Настройки уведомлений сохранены")} className="px-4 py-2 rounded-lg bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white text-sm font-semibold">Сохранить</button>
      </div>
    </div>
  );
}

function KBSection() {
  const articles = [
    {title:"Как настроить WireGuard на iPhone",views:4821,updated:"5 мая 2026"},
    {title:"Оплата через USDT — пошаговая инструкция",views:3204,updated:"2 мая 2026"},
    {title:"Список серверов и их назначение",views:2876,updated:"30 апр 2026"},
    {title:"Подключение на macOS",views:2104,updated:"27 апр 2026"},
    {title:"Что делать при низкой скорости",views:1893,updated:"18 апр 2026"},
    {title:"Возврат средств — условия и сроки",views:1240,updated:"12 апр 2026"},
  ];
  return (
    <div className="max-w-[1100px] mx-auto p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div><h1 className="text-xl font-semibold text-[#f1f1f5]">База знаний</h1><div className="text-xs text-[#6b7280] mt-0.5">{articles.length} статей · используется ИИ</div></div>
        <button className="px-3 py-2 rounded-lg bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white text-xs font-semibold flex items-center gap-1.5"><Icon name="plus" className="w-3.5 h-3.5" strokeWidth={2.5} />Добавить статью</button>
      </div>
      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl divide-y divide-[#2a2a3a]/60">
        {articles.map((a,i)=>(
          <div key={i} className="px-5 py-3 flex items-center justify-between hover:bg-[#1a1a24]/40 transition group cursor-pointer">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-9 h-9 rounded-lg bg-[#4F8EF7]/10 text-[#7BA8F9] flex items-center justify-center shrink-0"><Icon name="book" /></div>
              <div className="min-w-0">
                <div className="text-sm text-[#f1f1f5] truncate">{a.title}</div>
                <div className="text-xs text-[#6b7280]">{a.views.toLocaleString("ru-RU")} просмотров · {a.updated}</div>
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
    <button type="button" onClick={onChange}
      className={"relative w-10 h-[22px] rounded-full transition shrink-0 " + (on ? "bg-[#4F8EF7]" : "bg-[#2a2a3a]")}>
      <span className={"absolute top-[2px] w-[18px] h-[18px] bg-white rounded-full transition-all " + (on ? "left-[20px]" : "left-[2px]")}></span>
    </button>
  );
}

Object.assign(window, { SettingsScreen });
