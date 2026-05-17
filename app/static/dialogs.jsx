// Dialogs screen — 3-column layout

const { useState: useStateD, useEffect: useEffectD, useRef: useRefD, useMemo: useMemoD } = React;

function ConvCard({ conv, active, onClick }) {
  const statusDot = {
    new: "bg-[#4F8EF7]",
    in_progress: "bg-[#eab308]",
    closed: "bg-zinc-500",
  }[conv.status];
  return (
    <button
      onClick={onClick}
      className={
        "w-full text-left p-3 rounded-lg transition relative group " +
        (active
          ? "bg-[#1a1a24] ring-1 ring-[#4F8EF7]/40"
          : "hover:bg-[#1a1a24]/60")
      }
    >
      {active && <div className="absolute left-0 top-2 bottom-2 w-0.5 bg-[#4F8EF7] rounded-r"></div>}
      <div className="flex items-start gap-2.5">
        <div className="relative">
          <Avatar initials={conv.initials} color={conv.avatarColor} size={36} />
          {conv.unread > 0 && (
            <div className="absolute -top-1 -right-1 min-w-[16px] h-[16px] px-1 rounded-full bg-[#ef4444] text-white text-[10px] font-bold flex items-center justify-center ring-2 ring-[#13131a]">
              {conv.unread}
            </div>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2 mb-0.5">
            <div className="text-sm font-medium text-[#f1f1f5] truncate">{conv.name}</div>
            <div className="text-[10px] text-[#6b7280] shrink-0">{conv.time}</div>
          </div>
          <div className="text-xs text-[#6b7280] truncate mb-1.5">{conv.preview}</div>
          <div className="flex items-center gap-1.5">
            <StatusBadge status={conv.status} />
            {conv.operatorCalled && (
              <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-[#ef4444]/15 text-[#ef4444]" title="Вызван оператор">
                <Icon name="bellRing" className="w-2.5 h-2.5" strokeWidth={2.5} />
              </span>
            )}
          </div>
        </div>
      </div>
    </button>
  );
}

function MessageBubble({ msg, onImageClick }) {
  if (msg.kind === "system") {
    return (
      <div className="flex justify-center my-2">
        <div className="text-[11px] text-[#6b7280] bg-[#1a1a24]/60 px-3 py-1 rounded-full">
          {msg.text} · {msg.time}
        </div>
      </div>
    );
  }
  if (msg.kind === "user") {
    return (
      <div className="flex justify-start">
        <div className="max-w-[70%]">
          {msg.fileType === "photo" || msg.kindOfContent === "image" ? (
            <button
              onClick={() => onImageClick(msg)}
              className="block bg-[#1a1a24] rounded-2xl rounded-tl-md overflow-hidden hover:ring-2 hover:ring-[#4F8EF7]/40 transition"
            >
              <div className="w-[260px] h-[180px] relative" style={{ background: "linear-gradient(135deg,#1f1f2a,#0d0d12)" }}>
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="text-center">
                    <Icon name="image" className="w-8 h-8 text-[#4F8EF7]/60 mx-auto mb-2" />
                    <div className="text-[11px] text-[#6b7280] font-mono">screenshot.png</div>
                    <div className="text-[10px] text-[#6b7280]/60 mt-0.5">нажмите чтобы открыть</div>
                  </div>
                </div>
                <div className="absolute inset-0 opacity-[0.04]" style={{ backgroundImage: "repeating-linear-gradient(45deg, #fff 0 1px, transparent 1px 8px)" }}></div>
              </div>
            </button>
          ) : (
            <div className="bg-[#1a1a24] text-[#f1f1f5] px-3.5 py-2.5 rounded-2xl rounded-tl-md text-sm leading-relaxed">
              {msg.text}
            </div>
          )}
          <div className="text-[10px] text-[#6b7280] mt-1 ml-2">{msg.time}</div>
        </div>
      </div>
    );
  }
  if (msg.kind === "ai") {
    return (
      <div className="flex justify-start">
        <div className="max-w-[70%]">
          <div className="bg-[#4F8EF7]/12 border border-[#4F8EF7]/25 text-[#f1f1f5] px-3.5 py-2.5 rounded-2xl rounded-tl-md text-sm leading-relaxed relative">
            <div className="absolute -top-2 left-3 flex items-center gap-1 bg-[#4F8EF7] text-white text-[9px] font-bold px-1.5 py-0.5 rounded">
              <Icon name="sparkles" className="w-2.5 h-2.5" strokeWidth={2.5} />
              ИИ
            </div>
            {msg.text}
          </div>
          <div className="text-[10px] text-[#6b7280] mt-1 ml-2">{msg.time}</div>
        </div>
      </div>
    );
  }
  if (msg.kind === "operator") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[70%]">
          <div className="bg-[#A855F7]/15 border border-[#A855F7]/30 text-[#f1f1f5] px-3.5 py-2.5 rounded-2xl rounded-tr-md text-sm leading-relaxed">
            {msg.text}
          </div>
          <div className="text-[10px] text-[#6b7280] mt-1 mr-2 text-right">
            {msg.operator} · {msg.time}
          </div>
        </div>
      </div>
    );
  }
  return null;
}

function DialogsScreen({
  conversations, setConversations,
  activeId, setActiveId,
  showToast,
  onReply, onToggleAI, onClose, onHandoff, onBillingAction,
  servers,
}) {
  const [searchQ, setSearchQ] = useStateD("");
  const [filter, setFilter] = useStateD("all");
  const [draft, setDraft] = useStateD("");
  const [aiEnabled, setAiEnabled] = useStateD(true);
  const [lightboxOpen, setLightboxOpen] = useStateD(false);
  const [confirmClose, setConfirmClose] = useStateD(false);
  const scrollRef = useRefD(null);

  const active = conversations.find((c) => c.id === activeId) || conversations[0];

  // Sync AI toggle state when active dialog changes
  useEffectD(() => {
    if (active) setAiEnabled(active.aiEnabled ?? true);
  }, [active?.id, active?.aiEnabled]);

  useEffectD(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [active?.id, active?.messages?.length]);

  const filtered = useMemoD(() => {
    let list = conversations;
    if (filter === "open") list = list.filter((c) => c.status === "new");
    if (filter === "wip") list = list.filter((c) => c.status === "in_progress");
    if (filter === "closed") list = list.filter((c) => c.status === "closed");
    if (searchQ.trim()) {
      const q = searchQ.toLowerCase();
      list = list.filter(
        (c) => c.name.toLowerCase().includes(q) || c.username.toLowerCase().includes(q) || c.preview.toLowerCase().includes(q)
      );
    }
    return list;
  }, [conversations, filter, searchQ]);

  const counts = useMemoD(() => ({
    all: conversations.length,
    open: conversations.filter((c) => c.status === "new").length,
    wip: conversations.filter((c) => c.status === "in_progress").length,
    closed: conversations.filter((c) => c.status === "closed").length,
  }), [conversations]);

  function sendMessage() {
    const text = draft.trim();
    if (!text || !active) return;
    setDraft("");
    if (onReply) onReply(active.id, text);
  }

  function handoffToOperator() {
    if (!active) return;
    showToast("Диалог взят в работу");
    if (onHandoff) onHandoff(active.id);
  }

  function closeDialog() {
    if (!active) return;
    setConfirmClose(false);
    showToast("Диалог закрыт");
    if (onClose) onClose(active.id);
  }

  async function toggleAI() {
    if (!active) return;
    if (onToggleAI) {
      const result = await onToggleAI(active.id);
      if (result && result.ai_enabled !== undefined) {
        setAiEnabled(result.ai_enabled);
      }
    } else {
      setAiEnabled((v) => !v);
    }
  }

  const filterTabs = [
    { id: "all", label: "Все", count: counts.all },
    { id: "open", label: "Открытые", count: counts.open },
    { id: "wip", label: "В работе", count: counts.wip },
    { id: "closed", label: "Закрытые", count: counts.closed },
  ];

  return (
    <>
      <div className="flex h-full min-h-0">
        {/* Left: conversation list */}
        <aside className="w-[260px] shrink-0 bg-[#13131a] border-r border-[#2a2a3a] flex flex-col min-h-0">
          <div className="p-3 border-b border-[#2a2a3a] space-y-2.5">
            <div className="relative">
              <Icon name="search" className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[#6b7280]" />
              <input
                value={searchQ}
                onChange={(e) => setSearchQ(e.target.value)}
                placeholder="Поиск по диалогам..."
                className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg pl-9 pr-3 py-2 text-sm text-[#f1f1f5] placeholder:text-[#6b7280] focus:outline-none focus:border-[#4F8EF7]/50"
              />
            </div>
            <div className="flex gap-1 text-[11px]">
              {filterTabs.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setFilter(t.id)}
                  className={
                    "flex-1 px-1.5 py-1.5 rounded-md font-medium transition " +
                    (filter === t.id
                      ? "bg-[#4F8EF7]/15 text-[#7BA8F9]"
                      : "text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24]")
                  }
                >
                  {t.label}
                  <span className="ml-1 opacity-60">{t.count}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1 scrollbar-thin">
            {filtered.length === 0 && (
              <div className="text-center text-xs text-[#6b7280] py-8">Диалоги не найдены</div>
            )}
            {filtered.map((c) => (
              <ConvCard key={c.id} conv={c} active={c.id === activeId} onClick={() => setActiveId(c.id)} />
            ))}
          </div>
        </aside>

        {/* Center: chat */}
        <section className="flex-1 flex flex-col bg-[#0d0d12] min-w-0 min-h-0">
          {active && (
            <>
              {/* Top bar */}
              <div className="h-[60px] px-5 border-b border-[#2a2a3a] flex items-center justify-between bg-[#13131a]/40">
                <div className="flex items-center gap-3 min-w-0">
                  <Avatar initials={active.initials} color={active.avatarColor} size={36} />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <div className="font-medium text-[#f1f1f5] truncate">{active.name}</div>
                      <StatusBadge status={active.status} />
                    </div>
                    <div className="text-xs text-[#6b7280]">{active.username} · ID {active.tgId}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={handoffToOperator}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[#A855F7]/15 text-[#C084FC] border border-[#A855F7]/30 hover:bg-[#A855F7]/25 transition flex items-center gap-1.5"
                  >
                    <Icon name="user" className="w-3.5 h-3.5" />
                    Передать оператору
                  </button>
                  <button
                    onClick={() => setConfirmClose(true)}
                    disabled={active.status === "closed"}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24] transition disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Закрыть диалог
                  </button>
                </div>
              </div>

              {/* Messages */}
              <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-5 space-y-3 scrollbar-thin">
                {(active.messages || []).length === 0 && (
                  <div className="text-center text-xs text-[#6b7280] py-8">Загрузка сообщений...</div>
                )}
                {(active.messages || []).map((m) => (
                  <MessageBubble key={m.id} msg={m} onImageClick={() => setLightboxOpen(true)} />
                ))}
              </div>

              {/* Composer */}
              <div className="border-t border-[#2a2a3a] p-3.5 bg-[#13131a]/40">
                <div className="bg-[#1a1a24] border border-[#2a2a3a] rounded-xl focus-within:border-[#4F8EF7]/50 transition">
                  <textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                        e.preventDefault();
                        sendMessage();
                      }
                    }}
                    placeholder={active.status === "closed" ? "Диалог закрыт" : "Написать сообщение..."}
                    disabled={active.status === "closed"}
                    rows={2}
                    className="w-full bg-transparent px-3.5 py-2.5 text-sm text-[#f1f1f5] placeholder:text-[#6b7280] focus:outline-none resize-none disabled:opacity-50"
                  />
                  <div className="flex items-center justify-between px-2 py-2 border-t border-[#2a2a3a]/60">
                    <div className="flex items-center gap-1">
                      <button
                        className="p-1.5 text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#0d0d12] rounded transition"
                        onClick={() => showToast("Прикрепить файл")}
                      >
                        <Icon name="paperclip" />
                      </button>
                      <div className="w-px h-4 bg-[#2a2a3a] mx-1"></div>
                      <label className="flex items-center gap-2 text-xs text-[#6b7280] cursor-pointer select-none px-2 py-1 hover:text-[#f1f1f5]">
                        <span>ИИ отвечает</span>
                        <button
                          type="button"
                          onClick={toggleAI}
                          className={
                            "relative w-8 h-[18px] rounded-full transition " +
                            (aiEnabled ? "bg-[#4F8EF7]" : "bg-[#2a2a3a]")
                          }
                        >
                          <span
                            className={
                              "absolute top-[2px] w-[14px] h-[14px] bg-white rounded-full transition-all " +
                              (aiEnabled ? "left-[16px]" : "left-[2px]")
                            }
                          ></span>
                        </button>
                      </label>
                    </div>
                    <button
                      onClick={sendMessage}
                      disabled={!draft.trim() || active.status === "closed"}
                      className="px-4 py-1.5 rounded-lg bg-[#4F8EF7] hover:bg-[#3d7ce8] text-white text-xs font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
                    >
                      <Icon name="send" className="w-3.5 h-3.5" />
                      Отправить
                    </button>
                  </div>
                </div>
                <div className="text-[10px] text-[#6b7280] mt-1.5 ml-1">Cmd/Ctrl + Enter для отправки</div>
              </div>
            </>
          )}
        </section>

        {/* Right: user info */}
        <aside className="w-[280px] shrink-0 bg-[#13131a] border-l border-[#2a2a3a] overflow-y-auto scrollbar-thin">
          {active && (
            <UserInfoPanel
              conv={active}
              showToast={showToast}
              servers={servers || []}
              onBillingAction={onBillingAction}
            />
          )}
        </aside>
      </div>

      {/* Lightbox */}
      {lightboxOpen && (
        <div
          onClick={() => setLightboxOpen(false)}
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-8"
        >
          <div className="relative max-w-3xl w-full bg-[#1a1a24] rounded-xl overflow-hidden border border-[#2a2a3a]">
            <div className="aspect-video relative" style={{ background: "linear-gradient(135deg,#1f1f2a,#0d0d12)" }}>
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="text-center">
                  <Icon name="image" className="w-16 h-16 text-[#4F8EF7]/40 mx-auto mb-3" />
                  <div className="text-sm text-[#6b7280] font-mono">screenshot.png</div>
                  <div className="text-xs text-[#6b7280]/60 mt-1">1280 × 720 · 284 KB</div>
                </div>
              </div>
              <div className="absolute inset-0 opacity-[0.04]" style={{ backgroundImage: "repeating-linear-gradient(45deg, #fff 0 1px, transparent 1px 12px)" }}></div>
            </div>
            <button
              onClick={() => setLightboxOpen(false)}
              className="absolute top-3 right-3 w-8 h-8 rounded-full bg-black/60 hover:bg-black text-white flex items-center justify-center"
            >
              <Icon name="x" />
            </button>
          </div>
        </div>
      )}

      {/* Close confirm */}
      {confirmClose && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => setConfirmClose(false)}>
          <div className="bg-[#13131a] border border-[#2a2a3a] rounded-xl p-6 w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
            <div className="font-semibold text-[#f1f1f5] mb-1">Закрыть диалог?</div>
            <div className="text-sm text-[#6b7280] mb-5">Пользователь сможет открыть новый, написав в чат.</div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setConfirmClose(false)} className="px-3 py-1.5 rounded-lg text-sm text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24]">
                Отмена
              </button>
              <button onClick={closeDialog} className="px-3 py-1.5 rounded-lg text-sm font-medium bg-[#ef4444]/20 text-[#ef4444] border border-[#ef4444]/30 hover:bg-[#ef4444]/30">
                Закрыть диалог
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function UserInfoPanel({ conv, showToast, servers, onBillingAction }) {
  const [historyOpen, setHistoryOpen] = useStateD(true);
  const [billingOpen, setBillingOpen] = useStateD(null);
  const [months, setMonths] = useStateD(1);
  const [gb, setGb] = useStateD(10);
  const trafficPct = Math.min(100, (conv.traffic.used / conv.traffic.total) * 100);
  const trafficColor = trafficPct > 85 ? "#ef4444" : trafficPct > 60 ? "#eab308" : "#22c55e";

  function billingAction(action, params) {
    if (onBillingAction) onBillingAction(conv.id, action, params);
    setBillingOpen(null);
  }

  function toggleBilling(action) {
    setBillingOpen((v) => (v === action ? null : action));
  }

  return (
    <div className="p-4 space-y-5">
      {/* User section */}
      <section>
        <div className="text-[10px] uppercase tracking-wider text-[#6b7280] font-semibold mb-3">Пользователь</div>
        <div className="bg-[#1a1a24] rounded-xl p-3.5 border border-[#2a2a3a]/60">
          <div className="flex items-center gap-3 mb-3">
            <Avatar initials={conv.initials} color={conv.avatarColor} size={44} />
            <div className="min-w-0">
              <div className="font-medium text-[#f1f1f5] text-sm truncate">{conv.name}</div>
              <div className="text-xs text-[#6b7280]">{conv.username}</div>
              <div className="text-[10px] text-[#6b7280]/70 font-mono">ID {conv.tgId}</div>
            </div>
          </div>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between items-center">
              <span className="text-[#6b7280]">Тариф</span>
              <PlanBadge plan={conv.plan} />
            </div>
            <div className="flex justify-between items-center">
              <span className="text-[#6b7280]">Подписка</span>
              <SubStatus status={conv.subStatus} />
            </div>
            <div className="flex justify-between items-center">
              <span className="text-[#6b7280]">След. платёж</span>
              <span className="text-[#f1f1f5]">{conv.nextPayment}</span>
            </div>
            <div className="pt-2 mt-2 border-t border-[#2a2a3a]/60">
              <div className="flex justify-between items-center mb-1.5">
                <span className="text-[#6b7280]">Трафик</span>
                <span className="text-[#f1f1f5] font-medium tabular-nums">
                  {conv.traffic.used} <span className="text-[#6b7280]">/ {conv.traffic.total} GB</span>
                </span>
              </div>
              <div className="h-1.5 bg-[#0d0d12] rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: trafficPct + "%", background: trafficColor }}
                ></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Billing */}
      <section>
        <div className="text-[10px] uppercase tracking-wider text-[#6b7280] font-semibold mb-3">Биллинг</div>
        <div className="space-y-1.5">

          {/* Renew */}
          <button
            onClick={() => toggleBilling("renew")}
            className={"w-full px-3 py-2 border rounded-lg text-xs font-medium transition flex items-center justify-between " + (billingOpen === "renew" ? "bg-[#4F8EF7]/25 border-[#4F8EF7]/50 text-[#7BA8F9]" : "bg-[#4F8EF7]/15 border-[#4F8EF7]/30 text-[#7BA8F9] hover:bg-[#4F8EF7]/25")}
          >
            <span>Продлить подписку</span>
            <Icon name={billingOpen === "renew" ? "chevronDown" : "refresh"} className="w-3.5 h-3.5" />
          </button>
          {billingOpen === "renew" && (
            <div className="bg-[#13131a] border border-[#4F8EF7]/20 rounded-lg p-3 space-y-2.5">
              <div className="text-[10px] text-[#6b7280]">Срок продления</div>
              <div className="grid grid-cols-4 gap-1">
                {[1, 3, 6, 12].map((m) => (
                  <button
                    key={m}
                    onClick={() => setMonths(m)}
                    className={"py-1.5 rounded text-[11px] font-medium transition " + (months === m ? "bg-[#4F8EF7] text-white" : "bg-[#1a1a24] text-[#6b7280] hover:text-[#f1f1f5] border border-[#2a2a3a]")}
                  >
                    {m} мес.
                  </button>
                ))}
              </div>
              <div className="text-[10px] text-[#6b7280]">
                Итого: <span className="text-[#f1f1f5]">{months} {months === 1 ? "месяц" : months < 5 ? "месяца" : "месяцев"}</span>
              </div>
              <button
                onClick={() => billingAction("renew", { months })}
                className="w-full py-1.5 bg-[#4F8EF7] hover:bg-[#4F8EF7]/80 text-white rounded text-xs font-medium transition"
              >
                Подтвердить
              </button>
            </div>
          )}

          {/* Buy traffic */}
          <button
            onClick={() => toggleBilling("buy_traffic")}
            className={"w-full px-3 py-2 border rounded-lg text-xs font-medium transition flex items-center justify-between " + (billingOpen === "buy_traffic" ? "bg-[#1f1f2a] border-[#4F8EF7]/30 text-[#f1f1f5]" : "bg-[#1a1a24] border-[#2a2a3a] text-[#f1f1f5] hover:bg-[#1f1f2a]")}
          >
            <span>Докупить трафик</span>
            <Icon name={billingOpen === "buy_traffic" ? "chevronDown" : "plus2"} className="w-3.5 h-3.5" />
          </button>
          {billingOpen === "buy_traffic" && (
            <div className="bg-[#13131a] border border-[#2a2a3a] rounded-lg p-3 space-y-2.5">
              <div className="text-[10px] text-[#6b7280]">Объём трафика</div>
              <div className="grid grid-cols-3 gap-1">
                {[10, 50, 100].map((g) => (
                  <button
                    key={g}
                    onClick={() => setGb(g)}
                    className={"py-1.5 rounded text-[11px] font-medium transition " + (gb === g ? "bg-[#4F8EF7] text-white" : "bg-[#1a1a24] text-[#6b7280] hover:text-[#f1f1f5] border border-[#2a2a3a]")}
                  >
                    {g} GB
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-[#6b7280] shrink-0">Другой объём:</span>
                <input
                  type="number"
                  min="1"
                  max="999"
                  value={gb}
                  onChange={(e) => setGb(Math.max(1, parseInt(e.target.value) || 1))}
                  className="w-full bg-[#1a1a24] border border-[#2a2a3a] rounded px-2 py-1 text-xs text-[#f1f1f5] focus:outline-none focus:border-[#4F8EF7]/50"
                />
                <span className="text-[10px] text-[#6b7280] shrink-0">GB</span>
              </div>
              <button
                onClick={() => billingAction("buy_traffic", { gb })}
                className="w-full py-1.5 bg-[#4F8EF7] hover:bg-[#4F8EF7]/80 text-white rounded text-xs font-medium transition"
              >
                Подтвердить
              </button>
            </div>
          )}

          {/* Reset key */}
          <button
            onClick={() => toggleBilling("reset_key")}
            className={"w-full px-3 py-2 border rounded-lg text-xs font-medium transition flex items-center justify-between " + (billingOpen === "reset_key" ? "bg-[#1f1f2a] border-[#ef4444]/30 text-[#f87171]" : "bg-[#1a1a24] border-[#2a2a3a] text-[#f1f1f5] hover:bg-[#1f1f2a]")}
          >
            <span>Сбросить ключ</span>
            <Icon name={billingOpen === "reset_key" ? "chevronDown" : "key"} className="w-3.5 h-3.5" />
          </button>
          {billingOpen === "reset_key" && (
            <div className="bg-[#13131a] border border-[#ef4444]/20 rounded-lg p-3 space-y-2.5">
              <div className="text-[11px] text-[#fca5a5]">Ключ будет отозван и выдан новый. Все текущие подключения оборвутся.</div>
              <button
                onClick={() => billingAction("reset_key", {})}
                className="w-full py-1.5 bg-[#ef4444]/80 hover:bg-[#ef4444] text-white rounded text-xs font-medium transition"
              >
                Сбросить ключ
              </button>
            </div>
          )}

          {/* Last payment */}
          <div className="bg-[#1a1a24]/60 rounded-lg px-3 py-2 mt-1 border border-[#2a2a3a]/60">
            <div className="text-[10px] text-[#6b7280] mb-0.5">Последний платёж</div>
            <div className="text-xs text-[#f1f1f5] tabular-nums">
              {conv.lastPayment.amount} <span className="text-[#6b7280]">· {conv.lastPayment.date}</span>
            </div>
          </div>
        </div>
      </section>

      {/* History */}
      <section>
        <button
          onClick={() => setHistoryOpen((v) => !v)}
          className="w-full flex items-center justify-between mb-2"
        >
          <span className="text-[10px] uppercase tracking-wider text-[#6b7280] font-semibold">
            История ({(conv.tickets || []).length})
          </span>
          <Icon name="chevronDown" className={"w-3.5 h-3.5 text-[#6b7280] transition " + (historyOpen ? "" : "-rotate-90")} />
        </button>
        {historyOpen && (
          <div className="space-y-1.5">
            {(conv.tickets || []).length === 0 && (
              <div className="text-xs text-[#6b7280] italic px-3 py-2">Нет закрытых обращений</div>
            )}
            {(conv.tickets || []).map((t) => (
              <div key={t.id} className="bg-[#1a1a24] rounded-lg px-3 py-2 border border-[#2a2a3a]/60 hover:border-[#2a2a3a] transition cursor-pointer">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-[10px] font-mono text-[#6b7280]">{t.id}</span>
                  <span className="inline-flex items-center gap-1 text-[10px] text-[#22c55e]">
                    <Icon name="check" className="w-2.5 h-2.5" strokeWidth={3} />
                    Решён
                  </span>
                </div>
                <div className="text-xs text-[#f1f1f5] mb-0.5 truncate">{t.title}</div>
                <div className="text-[10px] text-[#6b7280]">{t.date}</div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

Object.assign(window, { DialogsScreen });
