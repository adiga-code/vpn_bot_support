// Settings screen

const { useState: useStateT, useEffect: useEffectT, useMemo: useMemoT } = React;

function SettingsScreen({ operators: ops, setOperators, showToast, currentOperator }) {
  const isAdmin = currentOperator?.role === "admin";
  const defaultSection = isAdmin ? "operators" : "profile";
  const [section, setSection] = useStateT(defaultSection);
  const [modalOpen, setModalOpen] = useStateT(false);
  const [editingOp, setEditingOp] = useStateT(null);
  const [confirmDelete, setConfirmDelete] = useStateT(null);

  const allSections = [
    { id: "operators",     label: "Операторы",    icon: "operators", adminOnly: true  },
    { id: "profile",       label: "Профиль",      icon: "user",      adminOnly: false },
    { id: "ai",            label: "ИИ-настройки", icon: "sparkles",  adminOnly: true  },
    { id: "kb",            label: "База знаний",  icon: "book",      adminOnly: true  },
    { id: "automation",    label: "Автоматизация",icon: "zap",       adminOnly: true  },
    { id: "broadcast",     label: "Рассылка",     icon: "megaphone", adminOnly: true  },
    { id: "templates",     label: "Шаблоны",      icon: "template",  adminOnly: true  },
  ];
  const sections = allSections.filter(s => !s.adminOnly || isAdmin);

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
        {section === "ai"            && <AISection showToast={showToast} />}
        {section === "kb"            && <KBSection />}
        {section === "automation"    && <AutomationSection showToast={showToast} />}
        {section === "broadcast"     && <BroadcastSection showToast={showToast} />}
        {section === "templates"     && <TemplatesSection showToast={showToast} />}
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
                <td className="px-3 py-3 font-mono text-xs">
                  <div className="text-[#6b7280]">{op.tg}</div>
                  {op.tgId && <div className="text-[#3a3a4a] text-[10px] mt-0.5">ID {op.tgId}</div>}
                  {!op.tgId && <div className="text-[#ef4444]/60 text-[10px] mt-0.5">ID не задан</div>}
                </td>
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
  const [name,     setName]     = useStateT(editing?.name || "");
  const [tg,       setTg]       = useStateT(editing?.tg   || "@");
  const [tgId,     setTgId]     = useStateT(editing?.tgId != null ? String(editing.tgId) : "");
  const [role,     setRole]     = useStateT(editing?.role  || "agent");
  const [password, setPassword] = useStateT("");
  const [pwErr,    setPwErr]    = useStateT(null);

  function submit(e) {
    e?.preventDefault();
    if (!name.trim() || tg.length < 2) return;
    if (!editing && password && password.length < 6) {
      setPwErr("Минимум 6 символов"); return;
    }
    setPwErr(null);
    const tg_id = tgId.trim() ? parseInt(tgId.trim(), 10) : null;
    onSave({ name: name.trim(), tg: tg.trim(), tg_id, role, password });
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
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[#6b7280] mb-1.5">Telegram username</label>
              <input value={tg} onChange={(e) => { let v = e.target.value; if (!v.startsWith("@")) v = "@" + v.replace(/^@*/, ""); setTg(v); }} placeholder="@username"
                className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2 text-sm text-[#f1f1f5] placeholder:text-[#6b7280] focus:outline-none focus:border-[#4F8EF7]/50 font-mono" />
            </div>
            <div>
              <label className="block text-xs text-[#6b7280] mb-1.5">Telegram ID <span className="text-[#3a3a4a]">(числовой)</span></label>
              <input value={tgId} onChange={(e) => setTgId(e.target.value.replace(/\D/g, ""))} placeholder="123456789"
                className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2 text-sm text-[#f1f1f5] placeholder:text-[#6b7280] focus:outline-none focus:border-[#4F8EF7]/50 font-mono" />
            </div>
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
          {!editing && (
            <div>
              <label className="block text-xs text-[#6b7280] mb-1.5">Пароль <span className="text-[#3a3a4a]">(необязательно — можно задать позже)</span></label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••"
                className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2 text-sm text-[#f1f1f5] placeholder:text-[#6b7280] focus:outline-none focus:border-[#4F8EF7]/50" />
              {pwErr && <div className="text-xs text-[#ef4444] mt-1">{pwErr}</div>}
            </div>
          )}
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
  const [current,    setCurrent]    = useStateT("");
  const [newPw,      setNewPw]      = useStateT("");
  const [newPw2,     setNewPw2]     = useStateT("");
  const [loading,    setLoading]    = useStateT(false);
  const [err,        setErr]        = useStateT(null);
  const [notifPrefs, setNotifPrefs] = useStateT(null);

  useEffectT(() => {
    window.apiFetch("GET", "/api/operators/me/notifications").then(setNotifPrefs).catch(() => {});
  }, []);

  async function saveNotifPrefs() {
    try {
      await window.apiFetch("PUT", "/api/operators/me/notifications", notifPrefs);
      showToast("Настройки уведомлений сохранены");
    } catch { showToast("Ошибка сохранения"); }
  }

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

      {notifPrefs && (
        <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl divide-y divide-[#2a2a3a]/60">
          <div className="px-5 py-3.5 flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-[#f1f1f5]">Уведомления в Telegram</div>
              <div className="text-xs text-[#6b7280] mt-0.5">Какие события присылать вам в личку</div>
            </div>
            <button onClick={saveNotifPrefs} className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white transition">Сохранить</button>
          </div>
          {[
            ["new_dialog",      "Новый диалог",        "Пользователь впервые написал в бот"],
            ["operator_called", "Вызов оператора",     "Пользователь или ИИ запросили человека"],
          ].map(([key, title, desc]) => (
            <div key={key} className="px-5 py-3 flex items-center justify-between">
              <div>
                <div className="text-sm text-[#f1f1f5]">{title}</div>
                <div className="text-xs text-[#6b7280]">{desc}</div>
              </div>
              <Switch on={!!notifPrefs[key]} onChange={() => setNotifPrefs((p) => ({ ...p, [key]: !p[key] }))} />
            </div>
          ))}
        </div>
      )}

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
        <div className="text-xs text-[#6b7280] mt-0.5">Уведомления в нерабочее время накапливаются и отправляются операторам в начале рабочего дня. ИИ работает круглосуточно.</div>
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
  const [s, setS] = useStateT(null);

  useEffectT(() => {
    window.apiFetch("GET", "/api/settings/notifications").then(setS).catch(() => {});
  }, []);

  async function save() {
    try {
      await window.apiFetch("PUT", "/api/settings/notifications", s);
      showToast("Настройки уведомлений сохранены");
    } catch { showToast("Ошибка сохранения"); }
  }

  function toggle(key) { setS(v => ({ ...v, [key]: !v[key] })); }

  if (!s) return <div className="p-6 text-[#6b7280] text-sm">Загрузка...</div>;

  return (
    <div className="max-w-[1100px] mx-auto p-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-[#f1f1f5]">Уведомления</h1>
        <div className="text-xs text-[#6b7280] mt-0.5">Python публикует события в Redis → n8n доставляет в Telegram</div>
      </div>
      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl divide-y divide-[#2a2a3a]/60">
        <SettingsRow title="Новый диалог" desc="Пинг в Telegram при новом обращении" control={<Switch on={s.new_dialog} onChange={()=>toggle("new_dialog")} />} />
        <SettingsRow title="Пользователь вызвал оператора" desc="При handoff или operator_called из n8n" control={<Switch on={s.operator_called} onChange={()=>toggle("operator_called")} />} />
        <SettingsRow title="Сервер VPN недоступен" desc="Мгновенное оповещение при переходе в down" control={<Switch on={s.server_down} onChange={()=>toggle("server_down")} />} />
      </div>
      <div className="flex justify-end">
        <button onClick={() => showToast("Настройки уведомлений сохранены")} className="px-4 py-2 rounded-lg bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white text-sm font-semibold">Сохранить</button>
      </div>
    </div>
  );
}

const CATEGORY_LABELS = {
  troubleshooting: "Решение проблем",
  setup:           "Настройка",
  payment:         "Оплата",
  faq:             "FAQ",
  escalation:      "Эскалация",
};

const CATEGORY_COLORS = {
  troubleshooting: "bg-[#ef4444]/15 text-[#f87171] border-[#ef4444]/30",
  setup:           "bg-[#22c55e]/15 text-[#4ade80] border-[#22c55e]/30",
  payment:         "bg-[#eab308]/15 text-[#facc15] border-[#eab308]/30",
  faq:             "bg-[#4F8EF7]/15 text-[#7BA8F9] border-[#4F8EF7]/30",
  escalation:      "bg-[#A855F7]/15 text-[#C084FC] border-[#A855F7]/30",
};

function KBSection() {
  const [articles,   setArticles]   = useStateT(null);
  const [uploading,  setUploading]  = useStateT(false);
  const [uploadErr,  setUploadErr]  = useStateT(null);
  const [deleting,   setDeleting]   = useStateT(null);
  const [expanded,   setExpanded]   = useStateT(null);
  const fileRef = React.createRef();

  useEffectT(() => {
    window.apiFetch("GET", "/api/kb").then(setArticles).catch(() => setArticles([]));
  }, []);

  async function handleUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setUploading(true);
    setUploadErr(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const headers = {};
      const token = localStorage.getItem("hd_token");
      if (token) headers["Authorization"] = "Bearer " + token;
      const res = await fetch("/api/kb/upload", { method: "POST", headers, body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || res.statusText);
      }
      const data = await res.json();
      const fresh = await window.apiFetch("GET", "/api/kb");
      setArticles(fresh);
      setUploadErr(null);
    } catch (err) {
      setUploadErr(err.message || "Ошибка загрузки");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(id) {
    setDeleting(id);
    try {
      await window.apiFetch("DELETE", `/api/kb/${id}`);
      setArticles((arr) => arr.filter((a) => a.id !== id));
    } catch {
    } finally {
      setDeleting(null);
    }
  }

  if (articles === null) return <div className="p-6 text-[#6b7280] text-sm">Загрузка...</div>;

  return (
    <div className="max-w-[1100px] mx-auto p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[#f1f1f5]">База знаний</h1>
          <div className="text-xs text-[#6b7280] mt-0.5">{articles.length} чанков · используется ИИ для поиска</div>
        </div>
        <div className="flex items-center gap-2">
          {uploading && <span className="text-xs text-[#6b7280] animate-pulse">Обработка ИИ...</span>}
          <button onClick={() => fileRef.current?.click()} disabled={uploading}
            className="px-3 py-2 rounded-lg bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white text-xs font-semibold flex items-center gap-1.5 disabled:opacity-50">
            <Icon name="plus" className="w-3.5 h-3.5" strokeWidth={2.5} />
            Загрузить документ
          </button>
          <input ref={fileRef} type="file" accept=".txt,.md" className="hidden" onChange={handleUpload} />
        </div>
      </div>

      {uploadErr && (
        <div className="text-sm text-[#ef4444] bg-[#ef4444]/10 border border-[#ef4444]/20 rounded-lg px-4 py-2">
          {uploadErr}
        </div>
      )}

      {!uploading && articles.length === 0 && (
        <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl p-10 text-center">
          <div className="w-12 h-12 rounded-xl bg-[#4F8EF7]/10 text-[#7BA8F9] flex items-center justify-center mx-auto mb-3">
            <Icon name="book" className="w-6 h-6" />
          </div>
          <div className="text-sm text-[#f1f1f5] font-medium mb-1">База знаний пуста</div>
          <div className="text-xs text-[#6b7280]">Загрузите .txt или .md файл — ИИ разобьёт его на чанки и проиндексирует</div>
        </div>
      )}

      {articles.length > 0 && (
        <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl divide-y divide-[#2a2a3a]/40">
          {articles.map((a) => {
            const kw = Array.isArray(a.keywords) ? a.keywords : [];
            const catColor = CATEGORY_COLORS[a.category] || CATEGORY_COLORS.faq;
            const catLabel = CATEGORY_LABELS[a.category] || a.category;
            const isOpen = expanded === a.id;
            return (
              <div key={a.id}>
                <div className="px-5 py-3 flex items-start justify-between gap-3 hover:bg-[#1a1a24]/40 transition">
                  <button className="flex items-start gap-3 min-w-0 flex-1 text-left" onClick={() => setExpanded(isOpen ? null : a.id)}>
                    <div className="w-9 h-9 rounded-lg bg-[#4F8EF7]/10 text-[#7BA8F9] flex items-center justify-center shrink-0 mt-0.5">
                      <Icon name="book" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm text-[#f1f1f5] font-medium">{a.title}</span>
                        <span className={"inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium border " + catColor}>{catLabel}</span>
                      </div>
                      {kw.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {kw.slice(0, 6).map((k, i) => (
                            <span key={i} className="text-[10px] text-[#6b7280] bg-[#1a1a24] px-1.5 py-0.5 rounded">{k}</span>
                          ))}
                          {kw.length > 6 && <span className="text-[10px] text-[#6b7280]">+{kw.length - 6}</span>}
                        </div>
                      )}
                    </div>
                  </button>
                  <button onClick={() => handleDelete(a.id)} disabled={deleting === a.id}
                    className="p-1.5 text-[#6b7280] hover:text-[#ef4444] hover:bg-[#ef4444]/10 rounded transition shrink-0 mt-0.5 disabled:opacity-40">
                    <Icon name="trash" className="w-4 h-4" />
                  </button>
                </div>
                {isOpen && (
                  <div className="px-5 pb-4 pt-0">
                    <div className="ml-12 bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-4 py-3 text-xs text-[#9ca3af] leading-relaxed whitespace-pre-wrap">
                      {a.content}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function AutomationSection({ showToast }) {
  const [s, setS] = useStateT(null);

  useEffectT(() => {
    window.apiFetch("GET", "/api/settings/automation").then(setS).catch(() => {});
  }, []);

  async function save() {
    try {
      await window.apiFetch("PUT", "/api/settings/automation", s);
      showToast("Настройки автоматизации сохранены");
    } catch { showToast("Ошибка сохранения"); }
  }

  function toggle(key) { setS(v => ({ ...v, [key]: !v[key] })); }
  function set(key, val) { setS(v => ({ ...v, [key]: val })); }

  if (!s) return <div className="p-6 text-[#6b7280] text-sm">Загрузка...</div>;

  return (
    <div className="max-w-[1100px] mx-auto p-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-[#f1f1f5]">Автоматизация</h1>
        <div className="text-xs text-[#6b7280] mt-0.5">Автоматические действия при диалогах</div>
      </div>

      {/* Operator button */}
      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl divide-y divide-[#2a2a3a]/60">
        <div className="px-5 py-3.5">
          <div className="text-[10px] uppercase tracking-wider text-[#6b7280] font-semibold mb-3">Кнопка вызова оператора</div>
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm text-[#f1f1f5]">Показывать кнопку «Позвать оператора»</div>
              <div className="text-xs text-[#6b7280] mt-0.5">Кнопка появляется у пользователя в Telegram</div>
            </div>
            <Switch on={s.operator_button_enabled} onChange={() => toggle("operator_button_enabled")} />
          </div>
          {s.operator_button_enabled && (
            <div className="mt-3 flex items-center gap-3">
              <span className="text-sm text-[#6b7280] shrink-0">Показать после</span>
              <input
                type="number" min="1" max="20" value={s.operator_button_after_msgs}
                onChange={e => set("operator_button_after_msgs", Math.max(1, parseInt(e.target.value) || 1))}
                className="w-20 bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-1.5 text-sm text-[#f1f1f5] focus:outline-none focus:border-[#4F8EF7]/50 text-center"
              />
              <span className="text-sm text-[#6b7280] shrink-0">сообщений от пользователя</span>
            </div>
          )}
        </div>
        <SettingsRow
          title="Авто-вызов от ИИ"
          desc="ИИ сам передаёт диалог оператору, если не уверен в ответе"
          control={<Switch on={s.auto_handoff_enabled} onChange={() => toggle("auto_handoff_enabled")} />}
        />
      </div>

      {/* Rating */}
      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl divide-y divide-[#2a2a3a]/60">
        <SettingsRow
          title="Запрашивать оценку после закрытия"
          desc="Пользователь получает кнопки ⭐ — ⭐⭐⭐⭐⭐ в Telegram"
          control={<Switch on={s.rating_enabled} onChange={() => toggle("rating_enabled")} />}
        />
        {s.rating_enabled && (
          <div className="px-5 py-4">
            <label className="block text-xs text-[#6b7280] mb-2">Текст запроса оценки</label>
            <textarea
              value={s.rating_message_text}
              onChange={e => set("rating_message_text", e.target.value)}
              rows={2}
              className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2 text-sm text-[#f1f1f5] focus:outline-none focus:border-[#4F8EF7]/50 leading-relaxed"
              placeholder="Оцените качество поддержки:"
            />
          </div>
        )}
      </div>

      {/* Close message */}
      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl divide-y divide-[#2a2a3a]/60">
        <SettingsRow
          title="Отправлять сообщение при закрытии"
          desc="Пользователь получает текст после закрытия диалога оператором"
          control={<Switch on={s.close_message_enabled} onChange={() => toggle("close_message_enabled")} />}
        />
        {s.close_message_enabled && (
          <div className="px-5 py-4">
            <label className="block text-xs text-[#6b7280] mb-2">Текст сообщения</label>
            <textarea
              value={s.close_message_text}
              onChange={e => set("close_message_text", e.target.value)}
              rows={3}
              className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2 text-sm text-[#f1f1f5] focus:outline-none focus:border-[#4F8EF7]/50 leading-relaxed"
              placeholder="Спасибо за обращение!..."
            />
          </div>
        )}
      </div>

      <div className="flex justify-end">
        <button onClick={save} className="px-4 py-2 rounded-lg bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white text-sm font-semibold">
          Сохранить
        </button>
      </div>
    </div>
  );
}

function BroadcastSection({ showToast }) {
  const [text, setText] = useStateT("");
  const [confirm, setConfirm] = useStateT(false);
  const [result, setResult] = useStateT(null);
  const [loading, setLoading] = useStateT(false);

  async function sendBroadcast() {
    setConfirm(false);
    setLoading(true);
    setResult(null);
    try {
      const res = await window.apiFetch("POST", "/api/broadcast", { text });
      setResult(res);
      if (res.failed === 0) showToast(`Отправлено ${res.sent} пользователям`);
      else showToast(`Отправлено ${res.sent}, ошибок ${res.failed}`);
    } catch (e) {
      showToast("Ошибка рассылки");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-[700px] mx-auto p-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-[#f1f1f5]">Рассылка</h1>
        <div className="text-xs text-[#6b7280] mt-0.5">Отправить сообщение всем пользователям из базы</div>
      </div>

      <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl p-5 space-y-4">
        <div>
          <label className="block text-xs text-[#6b7280] mb-2">Текст сообщения</label>
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            rows={5}
            placeholder="Введите текст рассылки..."
            className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2.5 text-sm text-[#f1f1f5] placeholder:text-[#6b7280] focus:outline-none focus:border-[#4F8EF7]/50 leading-relaxed"
          />
        </div>

        {result && (
          <div className="bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-4 py-3 text-sm">
            <div className="flex items-center gap-4">
              <span className="text-[#22c55e]">✓ Отправлено: <span className="font-semibold tabular-nums">{result.sent}</span></span>
              {result.failed > 0 && <span className="text-[#ef4444]">✗ Ошибок: <span className="font-semibold tabular-nums">{result.failed}</span></span>}
              <span className="text-[#6b7280]">Всего: {result.total}</span>
            </div>
          </div>
        )}

        <div className="flex justify-end">
          <button
            onClick={() => setConfirm(true)}
            disabled={!text.trim() || loading}
            className="px-4 py-2 rounded-lg bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white text-sm font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <Icon name="megaphone" className="w-4 h-4" />
            {loading ? "Отправка..." : "Отправить всем"}
          </button>
        </div>
      </div>

      {confirm && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => setConfirm(false)}>
          <div className="bg-[#13131a] border border-[#2a2a3a] rounded-xl p-6 w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <div className="font-semibold text-[#f1f1f5] mb-2">Отправить рассылку?</div>
            <div className="text-sm text-[#6b7280] mb-4 leading-relaxed">
              Сообщение получат все пользователи, которые когда-либо писали боту. Отменить нельзя.
            </div>
            <div className="bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2 text-xs text-[#f1f1f5] mb-5 leading-relaxed max-h-24 overflow-y-auto">
              {text}
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setConfirm(false)} className="px-3 py-1.5 rounded-lg text-sm text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24]">Отмена</button>
              <button onClick={sendBroadcast} className="px-4 py-1.5 rounded-lg text-sm font-semibold bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white transition">
                Отправить
              </button>
            </div>
          </div>
        </div>
      )}
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

function TemplateModal({ template, groups, onSave, onClose }) {
  const [form, setForm] = useStateT({
    title: template?.title || "",
    group_name: template?.group_name || (groups[0] || "Общие"),
    text: template?.text || "",
  });
  function set(k, v) { setForm(f => ({ ...f, [k]: v })); }
  function submit(e) {
    e.preventDefault();
    if (!form.title.trim() || !form.text.trim()) return;
    onSave({ ...form, id: template?.id });
  }
  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[#13131a] border border-[#2a2a3a] rounded-xl p-6 w-full max-w-lg" onClick={e => e.stopPropagation()}>
        <div className="font-semibold text-[#f1f1f5] mb-4">{template ? "Редактировать шаблон" : "Добавить шаблон"}</div>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-xs text-[#6b7280] mb-1.5">Название</label>
            <input value={form.title} onChange={e => set("title", e.target.value)} required
              placeholder="Занимаюсь решением вопроса"
              className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2 text-sm text-[#f1f1f5] focus:outline-none focus:border-[#4F8EF7]/50 placeholder:text-[#6b7280]" />
          </div>
          <div>
            <label className="block text-xs text-[#6b7280] mb-1.5">Группа</label>
            <input value={form.group_name} onChange={e => set("group_name", e.target.value)}
              list="tpl-groups" placeholder="Общие"
              className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2 text-sm text-[#f1f1f5] focus:outline-none focus:border-[#4F8EF7]/50 placeholder:text-[#6b7280]" />
            <datalist id="tpl-groups">
              {groups.map(g => <option key={g} value={g} />)}
            </datalist>
          </div>
          <div>
            <label className="block text-xs text-[#6b7280] mb-1.5">Текст шаблона</label>
            <textarea value={form.text} onChange={e => set("text", e.target.value)} required rows={4}
              placeholder="Принял вашу заявку. Как только у меня будет решение, вернусь к вам..."
              className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2 text-sm text-[#f1f1f5] focus:outline-none focus:border-[#4F8EF7]/50 leading-relaxed resize-none placeholder:text-[#6b7280]" />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose}
              className="px-3 py-1.5 rounded-lg text-sm text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24]">Отмена</button>
            <button type="submit"
              className="px-4 py-1.5 rounded-lg text-sm font-medium bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white">Сохранить</button>
          </div>
        </form>
      </div>
    </div>
  );
}

function TemplatesSection({ showToast }) {
  const [templates, setTemplates] = useStateT(null);
  const [modal, setModal] = useStateT(null); // null | { template?: obj }
  const [deleting, setDeleting] = useStateT(null);

  useEffectT(() => {
    window.apiFetch("GET", "/api/templates").then(setTemplates).catch(() => setTemplates([]));
  }, []);

  const groups = useMemoT(() => {
    if (!templates) return [];
    return [...new Set(templates.map(t => t.group_name))];
  }, [templates]);

  const grouped = useMemoT(() => {
    if (!templates) return {};
    return templates.reduce((acc, t) => {
      (acc[t.group_name] = acc[t.group_name] || []).push(t);
      return acc;
    }, {});
  }, [templates]);

  async function saveTemplate(data) {
    try {
      const method = data.id ? "PUT" : "POST";
      const url = data.id ? `/api/templates/${data.id}` : "/api/templates";
      const saved = await window.apiFetch(method, url, data);
      setTemplates(prev => data.id
        ? prev.map(t => t.id === data.id ? saved : t)
        : [...prev, saved].sort((a, b) => a.group_name.localeCompare(b.group_name) || a.title.localeCompare(b.title)));
      showToast(data.id ? "Шаблон обновлён" : "Шаблон добавлен");
    } catch { showToast("Ошибка сохранения"); }
    setModal(null);
  }

  async function deleteTemplate(id) {
    setDeleting(id);
    try {
      await window.apiFetch("DELETE", `/api/templates/${id}`);
      setTemplates(prev => prev.filter(t => t.id !== id));
      showToast("Шаблон удалён");
    } catch { showToast("Ошибка удаления"); }
    setDeleting(null);
  }

  if (templates === null) return <div className="p-6 text-[#6b7280] text-sm">Загрузка...</div>;

  return (
    <div className="max-w-[1100px] mx-auto p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[#f1f1f5]">Шаблоны сообщений</h1>
          <div className="text-xs text-[#6b7280] mt-0.5">{templates.length} шаблонов · {groups.length} групп</div>
        </div>
        <button onClick={() => setModal({})}
          className="px-3 py-2 rounded-lg bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white text-xs font-semibold flex items-center gap-1.5">
          <Icon name="plus" className="w-3.5 h-3.5" strokeWidth={2.5} />
          Добавить шаблон
        </button>
      </div>

      {templates.length === 0 && (
        <div className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl p-10 text-center">
          <div className="w-12 h-12 rounded-xl bg-[#4F8EF7]/10 text-[#7BA8F9] flex items-center justify-center mx-auto mb-3">
            <Icon name="template" className="w-6 h-6" />
          </div>
          <div className="text-sm text-[#f1f1f5] font-medium mb-1">Шаблонов пока нет</div>
          <div className="text-xs text-[#6b7280]">Добавьте готовые ответы — операторы смогут вставлять их в один клик</div>
        </div>
      )}

      {Object.entries(grouped).map(([group, items]) => (
        <div key={group} className="bg-[#13131a] border border-[#2a2a3a]/60 rounded-xl overflow-hidden">
          <div className="px-5 py-2.5 bg-[#1a1a24]/60 border-b border-[#2a2a3a]/60">
            <span className="text-xs font-semibold text-[#6b7280] uppercase tracking-wider">{group}</span>
            <span className="ml-2 text-xs text-[#4a4a5a]">{items.length}</span>
          </div>
          <div className="divide-y divide-[#2a2a3a]/40">
            {items.map(t => (
              <div key={t.id} className="px-5 py-3 flex items-start justify-between gap-3 hover:bg-[#1a1a24]/40 transition">
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-[#f1f1f5] font-medium">{t.title}</div>
                  <div className="text-xs text-[#6b7280] mt-0.5 truncate">{t.text}</div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button onClick={() => setModal({ template: t })}
                    className="p-1.5 text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#0d0d12] rounded transition">
                    <Icon name="edit" className="w-4 h-4" />
                  </button>
                  <button onClick={() => deleteTemplate(t.id)} disabled={deleting === t.id}
                    className="p-1.5 text-[#6b7280] hover:text-[#ef4444] hover:bg-[#ef4444]/10 rounded transition disabled:opacity-40">
                    <Icon name="trash" className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      {modal !== null && (
        <TemplateModal
          template={modal.template}
          groups={groups}
          onSave={saveTemplate}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}

Object.assign(window, { SettingsScreen });
