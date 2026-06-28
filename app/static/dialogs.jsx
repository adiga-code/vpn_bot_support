// Dialogs screen — 3-column layout

const { useState: useStateD, useEffect: useEffectD, useRef: useRefD, useMemo: useMemoD } = React;

function StarRating({ rating, size = "sm" }) {
  if (!rating) return null;
  const sz = size === "lg" ? "text-base" : "text-[11px]";
  return (
    <span className={"inline-flex gap-0.5 " + sz}>
      {[1,2,3,4,5].map(i => (
        <span key={i} className={i <= rating ? "text-[#eab308]" : "text-[#3a3a4a]"}>★</span>
      ))}
    </span>
  );
}

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
          : conv.operatorCalled && conv.status === "new" && !conv.assignedOperator
          ? "bg-[#1a0a0a] ring-1 ring-[#ef4444]/50 hover:bg-[#1a1a24]/60"
          : conv.status === "in_progress" && conv.unread > 0
          ? "bg-[#1a1a18] ring-1 ring-[#eab308]/30 hover:bg-[#1a1a24]/60"
          : "hover:bg-[#1a1a24]/60")
      }
    >
      {active && <div className="absolute left-0 top-2 bottom-2 w-0.5 bg-[#4F8EF7] rounded-r"></div>}
      {!active && conv.operatorCalled && conv.status === "new" && !conv.assignedOperator && (
        <div className="absolute left-0 top-2 bottom-2 w-0.5 bg-[#ef4444] rounded-r animate-pulse"></div>
      )}
      {!active && conv.status === "in_progress" && conv.unread > 0 && (
        <div className="absolute left-0 top-2 bottom-2 w-0.5 bg-[#eab308] rounded-r"></div>
      )}
      <div className="flex items-start gap-2.5">
        <div className="relative">
          <Avatar initials={conv.initials} color={conv.avatarColor} size={36} />
          {conv.unread > 0 && (
            <div className={
              "absolute -top-1 -right-1 min-w-[16px] h-[16px] px-1 rounded-full text-white text-[10px] font-bold flex items-center justify-center ring-2 ring-[#13131a] " +
              (conv.status === "in_progress" ? "bg-[#eab308] animate-pulse" : "bg-[#ef4444]")
            }>
              {conv.unread}
            </div>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2 mb-0.5">
            <div className="text-sm font-medium text-[#f1f1f5] truncate">{conv.name}</div>
            <div className="text-[10px] text-[#6b7280] shrink-0">{conv.time}</div>
          </div>
          <div className="text-[10px] text-[#6b7280]/70 truncate -mt-0.5 mb-0.5">{conv.username}</div>
          <div className="text-xs text-[#6b7280] truncate mb-1.5">{conv.preview}</div>
          <div className="flex items-center gap-1.5">
            <StatusBadge status={conv.status} />
            {conv.operatorCalled && (
              <span
                title="Вызван оператор"
                className={"inline-flex items-center justify-center w-4 h-4 rounded-full text-[#ef4444] " +
                  (conv.status === "new" && !conv.assignedOperator
                    ? "bg-[#ef4444]/25 animate-pulse"
                    : "bg-[#ef4444]/15")}
              >
                <Icon name="bellRing" className="w-2.5 h-2.5" strokeWidth={2.5} />
              </span>
            )}
          </div>
          {conv.assignedOperator ? (
            <div className="flex items-center gap-1 mt-1 text-[10px] text-[#6b7280]">
              <Icon name="user" className="w-2.5 h-2.5 shrink-0" />
              <span className="truncate">{conv.assignedOperator}</span>
            </div>
          ) : conv.status !== "closed" ? (
            <div className="mt-1 text-[10px] text-[#6b7280]/60">В очереди</div>
          ) : null}
        </div>
      </div>
    </button>
  );
}

function FileContent({ msg, side, onImageClick }) {
  const ft = msg.fileType;
  const url = msg.fileUrl;
  const tl = side === "left" ? "rounded-tl-md" : "rounded-tr-md";
  if (ft === "photo") {
    if (url) {
      return (
        <button onClick={() => onImageClick(url)} className={"block overflow-hidden rounded-2xl " + tl + " hover:ring-2 hover:ring-[#4F8EF7]/40 transition"}>
          <img src={url} alt="" className="max-w-[260px] max-h-[300px] object-cover" onError={(e) => { e.target.style.display="none"; }} />
        </button>
      );
    }
    return (
      <div className={"bg-[#1a1a24] rounded-2xl " + tl + " px-3.5 py-3 flex items-center gap-2 text-[#6b7280] text-sm"}>
        <Icon name="image" className="w-4 h-4" /> Фото
      </div>
    );
  }
  if (ft === "sticker") {
    if (url) {
      const isTgs = url.toLowerCase().endsWith(".tgs");
      if (isTgs) {
        return (
          <div className={"overflow-hidden rounded-2xl " + tl}>
            <lottie-player src={url} autoplay loop style={{width:"160px",height:"160px"}} />
          </div>
        );
      }
      return (
        <button onClick={() => onImageClick(url)} className={"block overflow-hidden rounded-2xl " + tl + " hover:ring-2 hover:ring-[#4F8EF7]/40 transition"}>
          <img src={url} alt="" className="max-w-[160px] max-h-[160px] object-contain" onError={(e) => { e.target.style.display="none"; }} />
        </button>
      );
    }
    return (
      <div className={"bg-[#1a1a24] rounded-2xl " + tl + " px-3.5 py-3 flex items-center gap-2 text-[#6b7280] text-sm"}>
        <Icon name="image" className="w-4 h-4" /> Стикер
      </div>
    );
  }
  if (ft === "video") {
    return url
      ? <video controls src={url} className={"max-w-[260px] rounded-2xl " + tl} />
      : <div className={"bg-[#1a1a24] rounded-2xl " + tl + " px-3.5 py-3 flex items-center gap-2 text-[#6b7280] text-sm"}><Icon name="video" className="w-4 h-4" /> Видео</div>;
  }
  if (ft === "voice" || ft === "audio") {
    return url
      ? <audio controls src={url} className="max-w-[260px]" />
      : <div className={"bg-[#1a1a24] rounded-2xl " + tl + " px-3.5 py-3 flex items-center gap-2 text-[#6b7280] text-sm"}><Icon name="mic" className="w-4 h-4" /> Голосовое</div>;
  }
  if (ft === "document") {
    const name = url ? url.split("/").pop() : "файл";
    return (
      <a href={url || "#"} target="_blank" rel="noreferrer"
        className={"bg-[#1a1a24] rounded-2xl " + tl + " px-3.5 py-3 flex items-center gap-2 text-[#7BA8F9] text-sm hover:underline"}>
        <Icon name="paperclip" className="w-4 h-4 shrink-0" />{name}
      </a>
    );
  }
  return (
    <div className={"bg-[#1a1a24] text-[#f1f1f5] px-3.5 py-2.5 rounded-2xl " + tl + " text-sm leading-relaxed"}>
      {msg.text || `[${ft}]`}
    </div>
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
    const hasFile = msg.fileType && msg.fileType !== "text";
    return (
      <div className="flex justify-start">
        <div className="max-w-[70%]">
          {hasFile
            ? <>
                <FileContent msg={msg} side="left" onImageClick={onImageClick} />
                {msg.text ? <div className="bg-[#1a1a24] text-[#f1f1f5] px-3.5 py-2 rounded-2xl rounded-tl-md text-sm leading-relaxed mt-1">{msg.text}</div> : null}
              </>
            : <div className="bg-[#1a1a24] text-[#f1f1f5] px-3.5 py-2.5 rounded-2xl rounded-tl-md text-sm leading-relaxed">{msg.text}</div>
          }
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
    const hasFile = msg.fileType && msg.fileType !== "text";
    return (
      <div className="flex justify-end">
        <div className="max-w-[70%]">
          {hasFile
            ? <>
                <FileContent msg={msg} side="right" onImageClick={onImageClick} />
                {msg.text ? <div className="bg-[#A855F7]/15 border border-[#A855F7]/30 text-[#f1f1f5] px-3.5 py-2 rounded-2xl rounded-tr-md text-sm leading-relaxed mt-1">{msg.text}</div> : null}
              </>
            : <div className="bg-[#A855F7]/15 border border-[#A855F7]/30 text-[#f1f1f5] px-3.5 py-2.5 rounded-2xl rounded-tr-md text-sm leading-relaxed">{msg.text}</div>
          }
          <div className="text-[10px] text-[#6b7280] mt-1 mr-2 text-right">
            {msg.operator} · {msg.time}
          </div>
        </div>
      </div>
    );
  }
  if (msg.kind === "comment") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[70%]">
          <div className="bg-[#eab308]/10 border border-[#eab308]/20 rounded-2xl rounded-tr-sm px-4 py-2.5">
            <div className="flex items-center gap-1.5 mb-1.5">
              <Icon name="edit" className="w-3 h-3 text-[#eab308]/60" />
              <span className="text-[10px] text-[#eab308]/70 font-semibold uppercase tracking-wider">Комментарий</span>
            </div>
            <p className="text-sm text-[#f1f1f5]/90 leading-relaxed whitespace-pre-wrap">{msg.text}</p>
            <p className="text-[10px] text-[#6b7280] mt-1.5 text-right">{msg.operator} · {msg.time}</p>
          </div>
        </div>
      </div>
    );
  }
  return null;
}

function TemplatePickerModal({ onSelect, onClose }) {
  const [templates, setTemplates] = useStateD(null);
  const [search, setSearch] = useStateD("");
  const [group, setGroup] = useStateD("all");

  useEffectD(() => {
    window.apiFetch("GET", "/api/templates").then(setTemplates).catch(() => setTemplates([]));
  }, []);

  const groups = useMemoD(() => {
    if (!templates) return [];
    return [...new Set(templates.map(t => t.group_name))];
  }, [templates]);

  const filtered = useMemoD(() => {
    if (!templates) return [];
    let list = group === "all" ? templates : templates.filter(t => t.group_name === group);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(t => t.title.toLowerCase().includes(q) || t.text.toLowerCase().includes(q));
    }
    return list;
  }, [templates, group, search]);

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[#13131a] border border-[#2a2a3a] rounded-xl w-full max-w-2xl flex flex-col"
           style={{ maxHeight: "70vh" }} onClick={e => e.stopPropagation()}>
        {/* Search header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[#2a2a3a] shrink-0">
          <Icon name="search" className="w-4 h-4 text-[#6b7280] shrink-0" />
          <input autoFocus value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Поиск шаблонов..."
            className="flex-1 bg-transparent text-sm text-[#f1f1f5] placeholder:text-[#6b7280] focus:outline-none" />
          <button onClick={onClose} className="text-[#6b7280] hover:text-[#f1f1f5]">
            <Icon name="x" className="w-4 h-4" />
          </button>
        </div>
        {/* Body */}
        <div className="flex min-h-0 flex-1 overflow-hidden">
          {/* Template list */}
          <div className="flex-1 overflow-y-auto py-1 scrollbar-thin">
            {filtered.length === 0 ? (
              <div className="px-4 py-10 text-center text-sm text-[#6b7280]">
                {templates === null ? "Загрузка..." : "Шаблоны не найдены"}
              </div>
            ) : filtered.map(t => (
              <button key={t.id} onClick={() => onSelect(t.text)}
                className="w-full px-4 py-3 text-left hover:bg-[#1a1a24] transition group">
                <div className="text-sm text-[#f1f1f5] font-medium group-hover:text-[#7BA8F9] transition">{t.title}</div>
                <div className="text-xs text-[#6b7280] mt-0.5 line-clamp-2 leading-relaxed">{t.text}</div>
              </button>
            ))}
          </div>
          {/* Groups sidebar */}
          <div className="w-44 shrink-0 border-l border-[#2a2a3a] overflow-y-auto py-1 scrollbar-thin">
            {["all", ...groups].map(g => (
              <button key={g} onClick={() => setGroup(g)}
                className={"w-full px-4 py-2.5 text-left text-sm transition " +
                  (group === g
                    ? "text-[#7BA8F9] bg-[#4F8EF7]/10 font-medium"
                    : "text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24]")}>
                {g === "all" ? "Все" : g}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function TransferModal({ activeDialog, operators, currentOperator, onTransfer, onClose }) {
  const candidates = (operators || []).filter(op => op.name !== activeDialog?.assignedOperator);
  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-[#13131a] border border-[#2a2a3a] rounded-xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-[#2a2a3a] flex items-center justify-between">
          <div className="font-medium text-sm text-[#f1f1f5]">Передать тикет</div>
          <button onClick={onClose} className="text-[#6b7280] hover:text-[#f1f1f5]"><Icon name="x" className="w-4 h-4" /></button>
        </div>
        <div className="divide-y divide-[#2a2a3a]/60 max-h-[360px] overflow-y-auto scrollbar-thin">
          {candidates.length === 0 && (
            <div className="px-5 py-8 text-center text-sm text-[#6b7280]">Нет доступных операторов</div>
          )}
          {candidates.map(op => (
            <button key={op.id} onClick={() => onTransfer(op.name)}
              className="w-full px-5 py-3 flex items-center gap-3 hover:bg-[#1a1a24] transition">
              <Avatar initials={op.initials} color={op.color} size={32} />
              <div className="flex-1 text-left min-w-0">
                <div className="text-sm text-[#f1f1f5]">{op.name}</div>
                <div className="text-xs text-[#6b7280]">{op.role === "admin" ? "Администратор" : "Агент"}</div>
              </div>
              <span className={"flex items-center gap-1 text-xs " + (op.online ? "text-[#22c55e]" : "text-zinc-500")}>
                <span className={"w-1.5 h-1.5 rounded-full " + (op.online ? "bg-[#22c55e]" : "bg-zinc-600")}></span>
                {op.online ? "Онлайн" : "Офлайн"}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function DialogsScreen({
  conversations, setConversations,
  activeId, setActiveId,
  showToast,
  onReply, onToggleAI, onClose, onHandoff, onReopen, onBillingAction,
  currentOperator, operators,
  servers,
}) {
  const [searchQ, setSearchQ] = useStateD("");
  const [view,   setView]   = useStateD("my");  // "my" | "all"
  const [filter, setFilter] = useStateD("all");
  const [draft, setDraft] = useStateD("");
  const [mode, setMode] = useStateD("message"); // "message" | "comment"
  const [aiEnabled, setAiEnabled] = useStateD(true);
  const [lightboxUrl, setLightboxUrl] = useStateD(null);
  const [pendingFile, setPendingFile] = useStateD(null);
  const [confirmClose, setConfirmClose] = useStateD(false);
  const [showTemplates, setShowTemplates] = useStateD(false);
  const [showTransfer, setShowTransfer] = useStateD(false);
  const scrollRef = useRefD(null);
  const fileInputRef = useRefD(null);

  const active = conversations.find((c) => c.id === activeId) || conversations[0];

  // Sync AI toggle state when active dialog changes; reset composer mode
  useEffectD(() => {
    if (active) setAiEnabled(active.aiEnabled ?? true);
    setMode("message");
  }, [active?.id, active?.aiEnabled]);

  useEffectD(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [active?.id, active?.messages?.length]);

  const filtered = useMemoD(() => {
    let list = view === "my"
      ? conversations.filter((c) => c.assignedOperator === currentOperator?.name)
      : conversations;
    if (filter === "open") list = list.filter((c) => c.status === "new");
    if (filter === "wip") list = list.filter((c) => c.status === "in_progress");
    if (filter === "closed") list = list.filter((c) => c.status === "closed");
    if (searchQ.trim()) {
      const q = searchQ.toLowerCase();
      list = list.filter(
        (c) => c.name.toLowerCase().includes(q) || c.username.toLowerCase().includes(q) || c.preview.toLowerCase().includes(q)
      );
    }
    return [...list].sort((a, b) => {
      const ta = a.updatedAt || "";
      const tb = b.updatedAt || "";
      return tb.localeCompare(ta);
    });
  }, [conversations, view, filter, searchQ, currentOperator]);

  const baseList = useMemoD(() =>
    view === "my"
      ? conversations.filter((c) => c.assignedOperator === currentOperator?.name)
      : conversations,
    [conversations, view, currentOperator]
  );

  const counts = useMemoD(() => ({
    all: baseList.length,
    open: baseList.filter((c) => c.status === "new").length,
    wip: baseList.filter((c) => c.status === "in_progress").length,
    closed: baseList.filter((c) => c.status === "closed").length,
  }), [baseList]);

  async function handleTransfer(operatorName) {
    setShowTransfer(false);
    if (!active) return;
    try {
      await window.apiFetch("POST", `/api/dialogs/${active.id}/transfer`, { operator_name: operatorName });
      showToast(`Тикет передан: ${operatorName}`);
    } catch { showToast("Ошибка передачи"); }
  }

  async function handleFileSelect(e) {
    const file = e.target.files?.[0];
    if (!file || !active) return;
    e.target.value = "";
    try {
      const { url } = await window.apiFetch("UPLOAD", "/api/upload", file);
      const type = file.type.startsWith("image/") ? "photo" : file.type.startsWith("video/") ? "video" : file.type.startsWith("audio/") ? "audio" : "document";
      setPendingFile({ url, type, name: file.name });
    } catch { showToast("Ошибка загрузки файла"); }
  }

  async function sendMessage() {
    const text = draft.trim();
    if (!active) return;
    if (mode === "comment") {
      if (!text) return;
      setDraft("");
      try {
        await window.apiFetch("POST", `/api/dialogs/${active.id}/comment`, { text });
      } catch (e) {
        console.error("Comment error", e);
      }
      return;
    }
    if (!text && !pendingFile) return;
    setDraft("");
    const fileArgs = pendingFile ? { file_url: pendingFile.url, file_type: pendingFile.type } : {};
    setPendingFile(null);
    if (onReply) onReply(active.id, text, fileArgs);
  }

  function pickTemplate(text) {
    setDraft(prev => prev ? prev + "\n" + text : text);
    setShowTemplates(false);
  }

  function handoffToOperator() {
    if (!active) return;
    showToast("Диалог взят в работу");
    if (onHandoff) onHandoff(active.id);
  }

  function reopenDialog() {
    if (!active) return;
    showToast("Диалог возвращён в очередь");
    if (onReopen) onReopen(active.id);
  }

  function closeDialog() {
    if (!active) return;
    setConfirmClose(false);
    showToast("Диалог закрыт");
    if (onClose) onClose(active.id);
  }

  async function reopenClosed() {
    if (!active) return;
    try {
      await window.apiFetch("POST", `/api/dialogs/${active.id}/reopen-closed`);
      showToast("Диалог переоткрыт");
    } catch (e) {
      if (e?.status === 409 && e?.active_dialog_id) {
        setActiveId(e.active_dialog_id);
      } else {
        showToast("Ошибка при переоткрытии");
      }
    }
  }

  const activeDialogForSameUser = active?.status === "closed"
    ? conversations.find((c) => c.chatId === active.chatId && c.id !== active.id && c.status !== "closed")
    : null;

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
            {/* Мои / Все */}
            <div className="flex bg-[#0d0d12] rounded-lg p-0.5 gap-0.5">
              {[["my", "Мои"], ["all", "Все"]].map(([v, label]) => (
                <button key={v} onClick={() => setView(v)}
                  className={"flex-1 py-1.5 rounded-md text-xs font-medium transition " +
                    (view === v ? "bg-[#4F8EF7] text-white" : "text-[#6b7280] hover:text-[#f1f1f5]")}>
                  {label}
                </button>
              ))}
            </div>
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
                  {active.status === "new" && (
                    <button
                      onClick={handoffToOperator}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[#A855F7]/15 text-[#C084FC] border border-[#A855F7]/30 hover:bg-[#A855F7]/25 transition flex items-center gap-1.5"
                    >
                      <Icon name="user" className="w-3.5 h-3.5" />
                      Взять в работу
                    </button>
                  )}
                  {active.status === "in_progress" && (
                    <>
                      {active.assignedOperator && (
                        <span className="flex items-center gap-1.5 text-xs text-[#6b7280] px-2">
                          <Icon name="user" className="w-3.5 h-3.5" />
                          {active.assignedOperator}
                        </span>
                      )}
                      <button
                        onClick={reopenDialog}
                        className="px-3 py-1.5 rounded-lg text-xs font-medium text-[#6b7280] border border-[#2a2a3a] hover:text-[#f1f1f5] hover:bg-[#1a1a24] transition flex items-center gap-1.5"
                      >
                        <Icon name="arrowLeft" className="w-3.5 h-3.5" />
                        Вернуть в очередь
                      </button>
                    </>
                  )}
                  {active.status !== "closed" && (
                    <button
                      onClick={() => setShowTransfer(true)}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium text-[#6b7280] border border-[#2a2a3a] hover:text-[#f1f1f5] hover:bg-[#1a1a24] transition flex items-center gap-1.5"
                    >
                      <Icon name="arrowRight" className="w-3.5 h-3.5" />
                      Передать
                    </button>
                  )}
                  <button
                    onClick={() => {
                      const url = `${window.location.origin}${window.location.pathname}?dialog=${active.id}`;
                      navigator.clipboard.writeText(url)
                        .then(() => showToast("Ссылка скопирована"))
                        .catch(() => showToast("Не удалось скопировать ссылку"));
                    }}
                    className="p-1.5 text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24] rounded-lg transition"
                    title="Скопировать ссылку на диалог"
                  >
                    <Icon name="link" className="w-4 h-4" />
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

              {/* Closed dialog banner */}
              {active.status === "closed" && (
                <div className="px-4 py-2.5 bg-[#1a1a18] border-b border-[#2a2a3a] flex items-center gap-3">
                  {activeDialogForSameUser ? (
                    <>
                      <Icon name="bellRing" className="w-4 h-4 text-[#eab308] shrink-0" />
                      <span className="text-xs text-[#d1a800] flex-1">Пользователь написал в новый чат</span>
                      <button
                        onClick={() => setActiveId(activeDialogForSameUser.id)}
                        className="text-xs px-2.5 py-1 rounded-lg bg-[#eab308]/15 text-[#eab308] hover:bg-[#eab308]/25 transition font-medium shrink-0"
                      >
                        Перейти
                      </button>
                    </>
                  ) : (
                    <>
                      <Icon name="x" className="w-4 h-4 text-[#6b7280] shrink-0" />
                      <span className="text-xs text-[#6b7280] flex-1">Диалог закрыт</span>
                      <button
                        onClick={reopenClosed}
                        className="text-xs px-2.5 py-1 rounded-lg bg-[#4F8EF7]/15 text-[#7BA8F9] hover:bg-[#4F8EF7]/25 transition font-medium shrink-0"
                      >
                        Открыть снова
                      </button>
                    </>
                  )}
                </div>
              )}

              {/* Messages */}
              <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-5 space-y-3 scrollbar-thin">
                {(active.messages || []).length === 0 && (
                  <div className="text-center text-xs text-[#6b7280] py-8">Загрузка сообщений...</div>
                )}
                {(active.messages || []).map((m) => (
                  <MessageBubble key={m.id} msg={m} onImageClick={(url) => setLightboxUrl(url)} />
                ))}
              </div>

              {/* Composer */}
              <div className="border-t border-[#2a2a3a] bg-[#13131a]/40">
                <input ref={fileInputRef} type="file" className="hidden"
                  accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.zip,.txt"
                  onChange={handleFileSelect} />
                {/* Mode tabs */}
                <div className="flex border-b border-[#2a2a3a] px-3.5">
                  {[["message", "Сообщение"], ["comment", "Комментарий"]].map(([m, label]) => (
                    <button key={m} onClick={() => { setMode(m); if (m === "comment") setPendingFile(null); }}
                      disabled={active.status === "closed"}
                      className={"px-3 py-2 text-xs font-medium transition border-b-2 -mb-px disabled:opacity-40 " +
                        (mode === m
                          ? (m === "comment" ? "border-[#eab308] text-[#eab308]" : "border-[#4F8EF7] text-[#7BA8F9]")
                          : "border-transparent text-[#6b7280] hover:text-[#f1f1f5]")}>
                      {label}
                    </button>
                  ))}
                </div>
                <div className="p-3.5">
                  {pendingFile && mode === "message" && (
                    <div className="mb-2 flex items-center gap-2 bg-[#1a1a24] border border-[#2a2a3a] rounded-lg px-3 py-2">
                      <Icon name="paperclip" className="w-4 h-4 text-[#4F8EF7] shrink-0" />
                      <span className="text-xs text-[#f1f1f5] truncate flex-1">{pendingFile.name}</span>
                      <button onClick={() => setPendingFile(null)} className="text-[#6b7280] hover:text-[#ef4444]"><Icon name="x" className="w-3.5 h-3.5" /></button>
                    </div>
                  )}
                  <div className={"bg-[#1a1a24] border rounded-xl focus-within:border-[#4F8EF7]/50 transition " +
                    (mode === "comment" ? "border-[#eab308]/30 focus-within:border-[#eab308]/50" : "border-[#2a2a3a]")}>
                    <textarea
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                          e.preventDefault();
                          sendMessage();
                        }
                      }}
                      placeholder={
                        active.status === "closed" ? "Диалог закрыт" :
                        mode === "comment" ? "Комментарий виден только операторам..." :
                        "Написать сообщение..."
                      }
                      disabled={active.status === "closed"}
                      rows={2}
                      className="w-full bg-transparent px-3.5 py-2.5 text-sm text-[#f1f1f5] placeholder:text-[#6b7280] focus:outline-none resize-none disabled:opacity-50"
                    />
                    <div className="flex items-center justify-between px-2 py-2 border-t border-[#2a2a3a]/60">
                      <div className="flex items-center gap-1">
                        {mode === "message" && (
                          <>
                            <button
                              className="p-1.5 text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#0d0d12] rounded transition"
                              disabled={active.status === "closed"}
                              onClick={() => fileInputRef.current?.click()}
                              title="Прикрепить файл"
                            >
                              <Icon name="paperclip" />
                            </button>
                            <button
                              className="p-1.5 text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#0d0d12] rounded transition"
                              disabled={active.status === "closed"}
                              onClick={() => setShowTemplates(true)}
                              title="Шаблоны сообщений"
                            >
                              <Icon name="template" />
                            </button>
                            <div className="w-px h-4 bg-[#2a2a3a] mx-1"></div>
                          </>
                        )}
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
                        disabled={(mode === "message" ? (!draft.trim() && !pendingFile) : !draft.trim()) || active.status === "closed"}
                        className={"px-4 py-1.5 rounded-lg text-white text-xs font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5 " +
                          (mode === "comment" ? "bg-[#eab308]/80 hover:bg-[#eab308]" : "bg-[#4F8EF7] hover:bg-[#3d7ce8]")}
                      >
                        <Icon name="send" className="w-3.5 h-3.5" />
                        {mode === "comment" ? "Комментарий" : "Отправить"}
                      </button>
                    </div>
                  </div>
                  <div className="text-[10px] text-[#6b7280] mt-1.5 ml-1">Cmd/Ctrl + Enter для отправки</div>
                </div>
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
              onTicketClick={setActiveId}
            />
          )}
        </aside>
      </div>

      {/* Lightbox */}
      {lightboxUrl && (
        <div
          onClick={() => setLightboxUrl(null)}
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-8"
        >
          <div className="relative max-w-4xl max-h-[90vh]" onClick={(e) => e.stopPropagation()}>
            <img src={lightboxUrl} alt="" className="max-w-full max-h-[90vh] rounded-xl object-contain" />
            <button
              onClick={() => setLightboxUrl(null)}
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
      {showTemplates && <TemplatePickerModal onSelect={pickTemplate} onClose={() => setShowTemplates(false)} />}
      {showTransfer && (
        <TransferModal
          activeDialog={active}
          operators={operators}
          currentOperator={currentOperator}
          onTransfer={handleTransfer}
          onClose={() => setShowTransfer(false)}
        />
      )}
    </>
  );
}

function NotesEditor({ convId, initialValue, showToast }) {
  const [value, setValue] = React.useState(initialValue);
  const [saving, setSaving] = React.useState(false);
  const savedRef = React.useRef(initialValue);

  React.useEffect(() => {
    setValue(initialValue);
    savedRef.current = initialValue;
  }, [convId]);

  const save = async () => {
    if (value === savedRef.current) return;
    setSaving(true);
    try {
      const res = await fetch(`/api/dialogs/${convId}/notes`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "Authorization": "Bearer " + localStorage.getItem("token") },
        body: JSON.stringify({ text: value }),
      });
      if (!res.ok) throw new Error();
      savedRef.current = value;
      showToast && showToast("Заметка сохранена");
    } catch {
      showToast && showToast("Ошибка сохранения", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="relative">
      <textarea
        value={value}
        onChange={e => setValue(e.target.value)}
        onBlur={save}
        rows={4}
        placeholder="Заметки об этом пользователе..."
        className="w-full bg-[#1a1a24] border border-[#2a2a3a]/60 rounded-xl px-3 py-2.5 text-xs text-[#f1f1f5] placeholder-[#6b7280]/60 resize-none focus:outline-none focus:border-[#eab308]/40 transition scrollbar-thin"
      />
      {saving && (
        <div className="absolute bottom-2 right-2 text-[10px] text-[#eab308]/70">Сохранение…</div>
      )}
    </div>
  );
}

function UserInfoPanel({ conv, showToast, servers, onBillingAction, onTicketClick }) {
  const [historyOpen, setHistoryOpen] = useStateD(true);
  const trafficPct = Math.min(100, (conv.traffic.used / conv.traffic.total) * 100);
  const trafficColor = trafficPct > 85 ? "#ef4444" : trafficPct > 60 ? "#eab308" : "#22c55e";

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
            <div className="flex justify-between items-center">
              <span className="text-[#6b7280]">Последний платёж</span>
              <span className="text-[#f1f1f5] tabular-nums">
                {conv.lastPayment.amount} <span className="text-[#6b7280]">· {conv.lastPayment.date}</span>
              </span>
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

      {/* Rating */}
      {conv.rating && (
        <section>
          <div className="text-[10px] uppercase tracking-wider text-[#6b7280] font-semibold mb-2">Оценка поддержки</div>
          <div className="bg-[#1a1a24] rounded-xl p-3.5 border border-[#2a2a3a]/60 flex items-center justify-between">
            <StarRating rating={conv.rating} size="lg" />
            <span className="text-[11px] text-[#6b7280]">{conv.rating} / 5</span>
          </div>
        </section>
      )}

      {/* Notes */}
      <section>
        <div className="text-[10px] uppercase tracking-wider text-[#6b7280] font-semibold mb-2">Заметки</div>
        <NotesEditor convId={conv.id} initialValue={conv.notes || ""} showToast={showToast} />
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
              <div key={t.id}
                onClick={() => t.dialogId && onTicketClick && onTicketClick(t.dialogId)}
                className="bg-[#1a1a24] rounded-lg px-3 py-2 border border-[#2a2a3a]/60 hover:border-[#4F8EF7]/40 hover:bg-[#1a1a2e] transition cursor-pointer">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-[10px] font-mono text-[#6b7280]">{t.id}</span>
                  <span className="inline-flex items-center gap-1 text-[10px] text-[#22c55e]">
                    <Icon name="check" className="w-2.5 h-2.5" strokeWidth={3} />
                    Решён
                  </span>
                </div>
                <div className="text-xs text-[#f1f1f5] mb-0.5 truncate">{t.title}</div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-[#6b7280]">{t.date}</span>
                  {t.rating && <StarRating rating={t.rating} />}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

Object.assign(window, { DialogsScreen });
