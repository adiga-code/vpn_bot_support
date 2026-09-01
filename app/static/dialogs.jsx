// Dialogs screen — 3-column layout

const { useState: useStateD, useEffect: useEffectD, useRef: useRefD, useMemo: useMemoD } = React;

function fmtClock(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

function fmtDayLabel(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const now = new Date();
  const day      = new Date(d.getFullYear(),   d.getMonth(),   d.getDate());
  const today    = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diffDays = Math.round((today - day) / 86400000);
  if (diffDays === 0) return "Сегодня";
  if (diffDays === 1) return "Вчера";
  const opts = { day: "numeric", month: "long" };
  if (d.getFullYear() !== now.getFullYear()) opts.year = "numeric";
  return d.toLocaleDateString("ru-RU", opts);
}

function msgTime(msg) {
  return msg.createdAt ? fmtClock(msg.createdAt) : msg.time;
}

function DaySeparator({ label }) {
  return (
    <div className="flex justify-center my-2">
      <span className="text-[10px] text-[#6b7280] bg-[#1a1a24] border border-[#2a2a3a] rounded-full px-3 py-1">{label}</span>
    </div>
  );
}

function DeliveryStatus({ status }) {
  if (!status || status === "failed") return null;
  const delivered = status === "delivered";
  return (
    <span className={"ml-1 font-bold " + (delivered ? "text-[#4F8EF7]" : "text-[#6b7280]")}>
      {delivered ? "✓✓" : "✓"}
    </span>
  );
}

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

// flat — вид для телефона: строка во всю ширину с разделителем вместо карточки
// с закруглениями, чтобы список читался как обычный мобильный лист.
function ConvCard({ conv, active, onClick, showServiceTag = false, flat = false,
                    lockedForMe = false }) {
  // escalated but not yet served — grabs attention in «ИИ»/«Очередь»
  const calledUnserved = conv.operatorCalled && ["ai", "queue"].includes(conv.status);
  return (
    <button
      onClick={onClick}
      className={
        "w-full text-left relative group transition " +
        (flat ? "p-3.5 border-b border-[#2a2a3a]/50 " : "p-3 rounded-lg ") +
        (active
          ? "bg-[#1a1a24] ring-1 ring-[#4F8EF7]/40"
          : calledUnserved
          ? (flat ? "bg-[#ef4444]/[.06] active:bg-[#1a1a24]" : "bg-[#1a0a0a] ring-1 ring-[#ef4444]/50 hover:bg-[#1a1a24]/60")
          : conv.status === "in_progress" && conv.unread > 0
          ? (flat ? "bg-[#eab308]/[.05] active:bg-[#1a1a24]" : "bg-[#1a1a18] ring-1 ring-[#eab308]/30 hover:bg-[#1a1a24]/60")
          : (flat ? "active:bg-[#1a1a24]" : "hover:bg-[#1a1a24]/60"))
      }
    >
      {active && <div className="absolute left-0 top-2 bottom-2 w-0.5 bg-[#4F8EF7] rounded-r"></div>}
      {!active && calledUnserved && (
        <div className="absolute left-0 top-2 bottom-2 w-0.5 bg-[#ef4444] rounded-r animate-pulse"></div>
      )}
      {!active && conv.status === "in_progress" && conv.unread > 0 && (
        <div className="absolute left-0 top-2 bottom-2 w-0.5 bg-[#eab308] rounded-r"></div>
      )}
      <div className="flex items-start gap-2.5">
        <div className="relative">
          <Avatar initials={conv.initials} color={conv.avatarColor} size={36} photoUrl={conv.photoUrl} />
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
            <div className="flex items-center gap-1.5 min-w-0">
              {/* В режиме «Все сервисы» — чей это тикет */}
              {showServiceTag && <ServiceDot color={conv.serviceColor} name={conv.serviceName} />}
              {conv.folderEmoji && (
                <span title={"Папка: " + conv.folderName} className="shrink-0 text-[11px] leading-none">
                  {conv.folderEmoji}
                </span>
              )}
              <div className="text-sm font-medium text-[#f1f1f5] truncate">{conv.name}</div>
            </div>
            <div className="text-[10px] text-[#6b7280] shrink-0">{conv.time}</div>
          </div>
          <div className="text-[10px] text-[#6b7280]/70 truncate -mt-0.5 mb-0.5">{conv.username}</div>
          <div className="text-xs text-[#6b7280] truncate mb-1.5">{conv.preview}</div>
          <div className="flex items-center gap-1.5 flex-wrap">
            <StatusBadge status={conv.status} />
            {conv.status === "waiting" && <WaitingLabel reason={conv.waitingReason} />}
            <SlaTimer slaSeconds={conv.slaSeconds} slaStartedAt={conv.slaStartedAt} />
            {conv.operatorCalled && (
              <span
                title="Вызван оператор"
                className={"inline-flex items-center justify-center w-4 h-4 rounded-full text-[#ef4444] " +
                  (calledUnserved ? "bg-[#ef4444]/25 animate-pulse" : "bg-[#ef4444]/15")}
              >
                <Icon name="bellRing" className="w-2.5 h-2.5" strokeWidth={2.5} />
              </span>
            )}
          </div>
          {conv.assignedOperator && (
            <div className="flex items-center gap-1 mt-1 text-[10px] text-[#6b7280]">
              {/* Замок — тикет в работе у другого оператора, писать в него нельзя */}
              <Icon name={lockedForMe ? "lock" : "user"} className="w-2.5 h-2.5 shrink-0" />
              <span className="truncate">{conv.assignedOperator}</span>
              {conv.claimRequestedBy && (
                <span className="shrink-0 text-[#eab308]" title={`${conv.claimRequestedBy} просит передать`}>
                  · запрос
                </span>
              )}
            </div>
          )}
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

function MessageBubble({ msg, onImageClick, compact = false }) {
  // На узких экранах пузырь может занимать больше ширины — иначе текст
  // ломается на две-три буквы в строке.
  const wide = compact ? "max-w-[82%]" : "max-w-[70%]";
  if (msg.kind === "system") {
    return (
      <div className="flex justify-center my-2">
        <div className="text-[11px] text-[#6b7280] bg-[#1a1a24]/60 px-3 py-1 rounded-full">
          {msg.text} · {msgTime(msg)}
        </div>
      </div>
    );
  }
  if (msg.kind === "user") {
    const hasFile = msg.fileType && msg.fileType !== "text";
    return (
      <div className="flex justify-start">
        <div className={wide}>
          {hasFile
            ? <>
                <FileContent msg={msg} side="left" onImageClick={onImageClick} />
                {msg.text ? <div className="bg-[#1a1a24] text-[#f1f1f5] px-3.5 py-2 rounded-2xl rounded-tl-md text-sm leading-relaxed mt-1">{msg.text}</div> : null}
              </>
            : <div className="bg-[#1a1a24] text-[#f1f1f5] px-3.5 py-2.5 rounded-2xl rounded-tl-md text-sm leading-relaxed">{msg.text}</div>
          }
          <div className="text-[10px] text-[#6b7280] mt-1 ml-2">{msgTime(msg)}</div>
        </div>
      </div>
    );
  }
  if (msg.kind === "ai") {
    return (
      <div className="flex justify-start">
        <div className={wide}>
          <div className="bg-[#4F8EF7]/12 border border-[#4F8EF7]/25 text-[#f1f1f5] px-3.5 py-2.5 rounded-2xl rounded-tl-md text-sm leading-relaxed relative">
            <div className="absolute -top-2 left-3 flex items-center gap-1 bg-[#4F8EF7] text-white text-[9px] font-bold px-1.5 py-0.5 rounded">
              <Icon name="sparkles" className="w-2.5 h-2.5" strokeWidth={2.5} />
              ИИ
            </div>
            {msg.text}
          </div>
          <div className="text-[10px] text-[#6b7280] mt-1 ml-2">{msgTime(msg)}</div>
        </div>
      </div>
    );
  }
  if (msg.kind === "operator") {
    const hasFile = msg.fileType && msg.fileType !== "text";
    const failed = msg.deliveryStatus === "failed";
    const bubbleBorder = failed
      ? "bg-[#A855F7]/15 border border-[#ef4444]/60 text-[#f1f1f5]"
      : "bg-[#A855F7]/15 border border-[#A855F7]/30 text-[#f1f1f5]";
    return (
      <div className="flex justify-end">
        <div className={wide}>
          {hasFile
            ? <>
                <FileContent msg={msg} side="right" onImageClick={onImageClick} />
                {msg.text ? <div className={bubbleBorder + " px-3.5 py-2 rounded-2xl rounded-tr-md text-sm leading-relaxed mt-1"}>{msg.text}</div> : null}
              </>
            : <div className={bubbleBorder + " px-3.5 py-2.5 rounded-2xl rounded-tr-md text-sm leading-relaxed"}>{msg.text}</div>
          }
          <div className="text-[10px] text-[#6b7280] mt-1 mr-2 text-right">
            {msg.operator} · {msgTime(msg)}
            <DeliveryStatus status={msg.deliveryStatus} />
          </div>
          {failed && msg.deliveryError && (
            <div className="text-[10px] text-[#ef4444] mt-0.5 mr-2 text-right">✗ {msg.deliveryError}</div>
          )}
        </div>
      </div>
    );
  }
  if (msg.kind === "comment") {
    return (
      <div className="flex justify-end">
        <div className={wide}>
          <div className="bg-[#eab308]/10 border border-[#eab308]/20 rounded-2xl rounded-tr-sm px-4 py-2.5">
            <div className="flex items-center gap-1.5 mb-1.5">
              <Icon name="edit" className="w-3 h-3 text-[#eab308]/60" />
              <span className="text-[10px] text-[#eab308]/70 font-semibold uppercase tracking-wider">Комментарий</span>
            </div>
            <p className="text-sm text-[#f1f1f5]/90 leading-relaxed whitespace-pre-wrap">{msg.text}</p>
            <p className="text-[10px] text-[#6b7280] mt-1.5 text-right">{msg.operator} · {msgTime(msg)}</p>
          </div>
        </div>
      </div>
    );
  }
  return null;
}

// ── Автодополнение шаблонов по слешу ────────────────────────────────────────
// Оператор пишет «/» в начале сообщения → список шаблонов; дальше сужает его
// набором по заголовку либо по началу текста шаблона. Логика поиска вынесена
// отдельно от компонента: её же удобно дёрнуть из проверок.

// Порядок важен: точное попадание должно оказаться первым, чтобы «/» + пара
// букв + Enter закрывали типичный случай.
function rankTemplates(templates, query) {
  const list = templates || [];
  const q = (query || "").trim().toLowerCase();
  if (!q) return list;
  const scored = [];
  for (const t of list) {
    const title = (t.title || "").toLowerCase();
    const text = (t.text || "").toLowerCase();
    let rank = -1;
    if (title.startsWith(q)) rank = 0;
    else if (title.includes(q)) rank = 1;
    // «Заголовок не помню, помню как начинается ответ».
    else if (text.startsWith(q)) rank = 2;
    else if (text.includes(q)) rank = 3;
    if (rank >= 0) scored.push({ t, rank });
  }
  // Внутри одного ранга сохраняем исходный порядок (группа, заголовок).
  return scored.map((s, i) => ({ ...s, i }))
    .sort((a, b) => a.rank - b.rank || a.i - b.i)
    .map((s) => s.t);
}

// Запрос автодополнения или null, если панель показывать не нужно: слеш ловим
// только первым символом (как в ТГ), поэтому «/home/user» внутри текста ничего
// не открывает.
function slashQueryOf(draft, mode) {
  if (mode !== "message") return null;
  if (!draft.startsWith("/")) return null;
  if (draft.includes("\n")) return null;
  return draft.slice(1);
}

function SlashTemplateList({ items, activeIndex, onPick, onHover, compact = false }) {
  const boxRef = useRefD(null);

  // Активная строка всегда в видимой области — иначе перебор стрелками
  // «уезжает» за границу списка.
  useEffectD(() => {
    const box = boxRef.current;
    const row = box && box.querySelector(`[data-idx="${activeIndex}"]`);
    if (row && row.scrollIntoView) row.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  return (
    <div className="absolute bottom-full left-0 right-0 mb-2 z-40 bg-[#13131a] border border-[#2a2a3a] rounded-xl shadow-2xl overflow-hidden">
      <div ref={boxRef} className={"overflow-y-auto scrollbar-thin py-1 " +
           (compact ? "max-h-[200px]" : "max-h-[260px]")}>
        {items.map((t, i) => (
          <button
            key={t.id}
            data-idx={i}
            onMouseDown={(e) => { e.preventDefault(); onPick(t); }}
            onClick={(e) => { e.preventDefault(); onPick(t); }}
            onMouseEnter={() => onHover(i)}
            className={"w-full px-3.5 text-left transition " +
              (compact ? "py-3 " : "py-2 ") +
              (i === activeIndex ? "bg-[#1a1a24]" : "hover:bg-[#1a1a24]/60")}
          >
            <div className="flex items-center gap-2">
              <span className={"text-sm font-medium truncate " +
                (i === activeIndex ? "text-[#7BA8F9]" : "text-[#f1f1f5]")}>{t.title}</span>
              <span className="text-[10px] text-[#6b7280] shrink-0">{t.group_name}</span>
            </div>
            <div className="text-xs text-[#6b7280] truncate mt-0.5">{(t.text || "").split("\n")[0]}</div>
          </button>
        ))}
      </div>
      <div className="px-3.5 py-1.5 border-t border-[#2a2a3a]/60 text-[10px] text-[#6b7280]">
        ↑↓ выбрать · Enter вставить · Esc закрыть
      </div>
    </div>
  );
}

function TemplatePickerModal({ onSelect, onClose, templates }) {
  // Список приходит готовым из DialogsScreen — он же питает автодополнение по
  // слешу, поэтому грузить его второй раз при открытии модалки не нужно.
  const [search, setSearch] = useStateD("");
  const [group, setGroup] = useStateD("all");

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
    <ModalOverlay onClose={onClose}>
      <div className="bg-[#13131a] border border-[#2a2a3a] rounded-xl w-full max-w-2xl flex flex-col"
           style={{ maxHeight: "70vh" }}>
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
    </ModalOverlay>
  );
}

function TransferModal({ activeDialog, operators, currentOperator, onTransfer, onClose }) {
  // Передать тикет можно только тому, у кого есть доступ к его ВПН-сервису
  // (админ обслуживает все) — иначе сервер вернёт 400.
  const candidates = (operators || []).filter(op =>
    op.name !== activeDialog?.assignedOperator &&
    (op.role === "admin" || (op.serviceIds || []).includes(activeDialog?.serviceId))
  );
  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-[#13131a] border border-[#2a2a3a] rounded-xl w-full max-w-sm">
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
              <PresenceLabel online={op.online} paused={op.paused} lastSeen={op.lastSeen}
                             className="shrink-0 max-w-[152px]" />
            </button>
          ))}
        </div>
      </div>
    </ModalOverlay>
  );
}

function DialogsScreen({
  conversations, setConversations,
  activeId, setActiveId,
  showToast,
  onReply, onToggleAI, onClose, onHandoff, onReopen, onWait,
  currentOperator, operators,
  showServiceTag = false,
  serviceId = null, folders = [],
  viewport, mobileChrome, onMobileChatOpen,
}) {
  const [searchQ, setSearchQ] = useStateD("");
  const [view,   setView]   = useStateD("my");  // "my" | "all"
  const [filter, setFilter] = useStateD("wip");
  const [draft, setDraft] = useStateD("");
  const [mode, setMode] = useStateD("message"); // "message" | "comment"
  const [aiEnabled, setAiEnabled] = useStateD(true);
  const [lightboxUrl, setLightboxUrl] = useStateD(null);
  const [pendingFile, setPendingFile] = useStateD(null);
  const [confirmClose, setConfirmClose] = useStateD(false);
  const [showTemplates, setShowTemplates] = useStateD(false);
  const [showTransfer, setShowTransfer] = useStateD(false);
  const [showFolderPick, setShowFolderPick] = useStateD(false);
  const [actionsOpen, setActionsOpen] = useStateD(false);
  // Шаблоны нужны сразу: по «/» список должен появляться мгновенно, без похода
  // в сеть. Модалка шаблонов берёт этот же массив.
  const [templates, setTemplates] = useStateD([]);
  const [slashIndex, setSlashIndex] = useStateD(0);
  const [slashDismissed, setSlashDismissed] = useStateD(false);
  // Телефон: экран показывает либо список, либо переписку.
  const [mobileView, setMobileView] = useStateD("list");
  const [showSearch, setShowSearch] = useStateD(false);
  const [showClientSheet, setShowClientSheet] = useStateD(false);
  const [showActionsSheet, setShowActionsSheet] = useStateD(false);
  const scrollRef = useRefD(null);
  const fileInputRef = useRefD(null);
  const composerRef = useRefD(null);

  const active = conversations.find((c) => c.id === activeId) || conversations[0];

  // Тикет могли открыть снаружи (клик по уведомлению, ссылка ?dialog=) — тогда
  // на телефоне сразу показываем переписку, а не список.
  useEffectD(() => { if (activeId) setMobileView("chat"); }, [activeId]);

  // Шторки принадлежат конкретному тикету: смена тикета их закрывает.
  useEffectD(() => { setShowClientSheet(false); setShowActionsSheet(false); setActionsOpen(false); }, [active?.id]);

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

  // Шаблоны пер-сервисные: при переходе на тикет другого ВПН-а подгружаем его
  // набор (плюс общие).
  useEffectD(() => {
    const sid = active?.serviceId;
    if (!sid) { setTemplates([]); return; }
    let stale = false;
    window.apiFetch("GET", `/api/templates?service_id=${sid}`)
      .then((list) => { if (!stale) setTemplates(list || []); })
      .catch(() => { if (!stale) setTemplates([]); });
    return () => { stale = true; };
  }, [active?.serviceId]);

  // ── Автодополнение по слешу ──────────────────────────────────────────────
  const slashQuery = slashQueryOf(draft, mode);
  const slashMatches = useMemoD(
    () => (slashQuery === null ? [] : rankTemplates(templates, slashQuery)),
    [templates, slashQuery]
  );
  // Нет совпадений — панель прячется: иначе она мешала бы отправить сообщение,
  // которое просто начинается со слеша.
  const slashOpen = slashQuery !== null && !slashDismissed && slashMatches.length > 0;

  // Смена запроса возвращает выделение на первую строку; уход от слеша снимает
  // ручное закрытие, чтобы следующий «/» снова открыл панель.
  useEffectD(() => { setSlashIndex(0); }, [slashQuery]);
  useEffectD(() => { if (slashQuery === null) setSlashDismissed(false); }, [slashQuery]);

  function applyTemplate(t) {
    // Слеш ловится только в начале сообщения, поэтому шаблон заменяет весь текст.
    setDraft(t.text);
    setSlashDismissed(false);
    const el = composerRef.current;
    if (el) {
      requestAnimationFrame(() => {
        el.focus();
        el.selectionStart = el.selectionEnd = el.value.length;
      });
    }
  }

  // На телефоне модалка шаблонов с боковым списком групп не помещается —
  // кнопка просто ставит «/» и открывает ту же панель автодополнения.
  function openSlashPanel() {
    setDraft("/");
    setSlashDismissed(false);
    const el = composerRef.current;
    if (el) requestAnimationFrame(() => { el.focus(); el.selectionStart = el.selectionEnd = 1; });
  }

  function onComposerKeyDown(e) {
    // Cmd/Ctrl+Enter отправляет всегда — панель при этом просто закрывается.
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      setSlashDismissed(true);
      sendMessage();
      return;
    }
    if (!slashOpen) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSlashIndex((i) => (i + 1) % slashMatches.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSlashIndex((i) => (i - 1 + slashMatches.length) % slashMatches.length);
    } else if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      applyTemplate(slashMatches[Math.min(slashIndex, slashMatches.length - 1)]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setSlashDismissed(true);   // текст остаётся как есть
    }
  }

  // Sections per view: «Все» — the whole pipeline, «Мои» — only own tickets.
  // «Все» shows 3 main tabs + an overflow menu («ещё») with ИИ and Закрытые.
  const SECTION_STATUS = { ai: "ai", queue: "queue", wip: "in_progress", waiting: "waiting", closed: "closed" };
  const SECTION_META = {
    wip:     { label: "В работе", icon: "📁" },
    waiting: { label: "Ожидание", icon: "⏸️" },
    queue:   { label: "Очередь",  icon: "⌛" },
    ai:      { label: "ИИ",       icon: "🤖" },
    closed:  { label: "Закрытые", icon: "✅" },
  };
  const MY_SECTIONS  = ["wip", "waiting", "closed"];
  const ALL_SECTIONS = ["wip", "waiting", "queue", "ai", "closed"];

  // Папки видны только при выбранном ВПН-е: они пер-сервисные, и одноимённые
  // папки двух сервисов в одном ряду читались бы как одна.
  const visibleFolders = serviceId === null ? [] : folders;
  const isFolder = (f) => String(f).startsWith("folder:");
  const folderIdOf = (f) => Number(String(f).slice(7));

  function switchView(v) {
    setView(v);
    const valid = v === "my" ? MY_SECTIONS : ALL_SECTIONS;
    if (!isFolder(filter) && !valid.includes(filter)) setFilter("wip");
  }

  const baseList = useMemoD(() =>
    view === "my"
      ? conversations.filter((c) => c.assignedOperator === currentOperator?.name)
      : conversations,
    [conversations, view, currentOperator]
  );

  const filtered = useMemoD(() => {
    // В папке показываем открытые тикеты: закрытые живут в своём разделе,
    // иначе счётчик папки и её содержимое расходились бы.
    let list = isFolder(filter)
      ? baseList.filter((c) => c.folderId === folderIdOf(filter) && c.status !== "closed")
      : baseList.filter((c) => c.status === SECTION_STATUS[filter]);
    if (searchQ.trim()) {
      const q = searchQ.toLowerCase();
      list = list.filter(
        (c) => c.name.toLowerCase().includes(q)
          || c.username.toLowerCase().includes(q)
          || c.preview.toLowerCase().includes(q)
          || String(c.chatId || "").includes(q)
      );
    }
    return [...list].sort((a, b) => {
      const ta = a.updatedAt || "";
      const tb = b.updatedAt || "";
      return tb.localeCompare(ta);
    });
  }, [baseList, filter, searchQ]);

  const counts = useMemoD(() => {
    const res = {};
    for (const id of ALL_SECTIONS) {
      res[id] = baseList.filter((c) => c.status === SECTION_STATUS[id]).length;
    }
    for (const f of visibleFolders) {
      res["folder:" + f.id] = baseList.filter(
        (c) => c.folderId === f.id && c.status !== "closed").length;
    }
    return res;
  }, [baseList, visibleFolders]);

  // Один список вкладок на обе раскладки: статусные разделы, разделитель,
  // папки. Ряд прокручивается — новые папки не ломают вёрстку.
  const sectionTabs = useMemoD(() => {
    const statuses = (view === "my" ? MY_SECTIONS : ALL_SECTIONS).map((id) => ({
      key: id, icon: SECTION_META[id].icon, label: SECTION_META[id].label,
    }));
    return statuses.concat(visibleFolders.map((f) => ({
      key: "folder:" + f.id, icon: f.emoji, label: f.name, color: f.color,
    })));
  }, [view, visibleFolders]);

  async function setDialogFolder(folderId) {
    setShowFolderPick(false);
    if (!active) return;
    try {
      await window.apiFetch("POST", `/api/dialogs/${active.id}/folder`, { folder_id: folderId });
      const f = folders.find((x) => x.id === folderId);
      showToast(f ? `Тикет в папке «${f.name}»` : "Тикет вынут из папки");
    } catch (e) {
      showToast(e?.status === 423 ? e.detail : "Не удалось изменить папку");
    }
  }

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

  function waitDialog() {
    if (!active) return;
    showToast("Тикет переведён в ожидание");
    if (onWait) onWait(active.id);
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


  // ── Раскладка ────────────────────────────────────────────────────────────
  // Куски интерфейса — список, переписка и карточка клиента — одни и те же на
  // всех ширинах; меняется только их размещение: телефон — drill-down, планшет
  // — две колонки и карточка шторкой, десктоп — три колонки как раньше.
  const vp = viewport || { isMobile: false, isTablet: false, isDesktop: true, isCompact: false };
  const compact = vp.isCompact;
  const chrome = mobileChrome || {};
  const chatVisible = vp.isMobile ? (mobileView === "chat" && !!active) : !!active;

  const STATUS_LABEL = {
    ai: "ИИ", queue: "Очередь", in_progress: "В работе", waiting: "Ожидание", closed: "Закрыт",
  };

  // Пока тикет в работе у одного оператора, второй такого же уровня его только
  // читает: двое, пишущих клиенту разное, хуже любой задержки с ответом.
  // Забрать тикет можно кнопкой «Запросить» — владелец передаёт его сам.
  // Админ не ограничен: иначе разруливать зависшие тикеты было бы некому.
  const lockedFor = (c) =>
    currentOperator?.role !== "admin" && !!c?.assignedOperator
    && c.assignedOperator !== currentOperator?.name
    && ["in_progress", "waiting"].includes(c.status);
  const locked = lockedFor(active);
  const myClaimPending = locked && active?.claimRequestedBy === currentOperator?.name;
  // Обратная сторона: у меня просят мой тикет.
  const claimOnMine = !!active?.claimRequestedBy
    && (active?.assignedOperator === currentOperator?.name || currentOperator?.role === "admin")
    && active?.claimRequestedBy !== currentOperator?.name;

  async function requestClaim() {
    if (!active) return;
    try {
      await window.apiFetch("POST", `/api/dialogs/${active.id}/claim`);
      showToast(`Запрос отправлен: ${active.assignedOperator}`);
    } catch (e) { showToast(e?.detail || "Не удалось отправить запрос"); }
  }

  async function answerClaim(approve) {
    if (!active) return;
    try {
      await window.apiFetch("POST", `/api/dialogs/${active.id}/claim/${approve ? "approve" : "decline"}`);
      showToast(approve ? `Тикет передан: ${active.claimRequestedBy}` : "Запрос отклонён");
    } catch (e) { showToast(e?.detail || "Не удалось ответить на запрос"); }
  }

  // Нижняя навигация уступает место переписке и клавиатуре.
  useEffectD(() => {
    if (onMobileChatOpen) onMobileChatOpen(!!(vp.isMobile && mobileView === "chat" && active));
  }, [vp.isMobile, mobileView, active?.id, onMobileChatOpen]);

  function openDialog(id) {
    setActiveId(id);
    setMobileView("chat");
  }

  function copyDialogLink() {
    if (!active) return;
    const url = `${window.location.origin}${window.location.pathname}?dialog=${active.id}`;
    navigator.clipboard.writeText(url)
      .then(() => showToast("Ссылка скопирована"))
      .catch(() => showToast("Не удалось скопировать ссылку"));
  }

  // Действия над тикетом: на десктопе кнопками в шапке, на узких — шторкой.
  const ticketActions = !active ? [] : locked ? [
    // Чужой тикет: только попросить его и скопировать ссылку.
    ...(myClaimPending
      ? [] : [{ icon: "handRaise", label: "Запросить тикет", run: requestClaim }]),
    { icon: "link", label: "Скопировать ссылку", run: copyDialogLink },
  ] : [
    ...(["ai", "queue"].includes(active.status)
      ? [{ icon: "user", label: "Взять в работу", run: handoffToOperator }] : []),
    ...(["in_progress", "waiting"].includes(active.status)
      ? [{ icon: "arrowLeft", label: "Вернуть в очередь", run: reopenDialog }] : []),
    ...(active.status === "in_progress"
      ? [{ icon: "clock", label: "В ожидание", run: waitDialog }] : []),
    ...(active.status !== "closed"
      ? [{ icon: "arrowRight", label: "Передать оператору", run: () => setShowTransfer(true) }] : []),
    ...(folders.length > 0
      ? [{ icon: "grid", label: active.folderId ? "Сменить папку" : "Положить в папку",
           run: () => setShowFolderPick(true) }] : []),
    { icon: "link", label: "Скопировать ссылку", run: copyDialogLink },
    ...(active.status !== "closed"
      ? [{ icon: "x", label: "Закрыть диалог", danger: true, run: () => setConfirmClose(true) }] : []),
  ];

  const searchField = (
    <div className="relative">
      <Icon name="search" className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[#6b7280]" />
      <input
        value={searchQ}
        onChange={(e) => setSearchQ(e.target.value)}
        placeholder="Поиск по диалогам..."
        className="w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg pl-9 pr-3 py-2 text-sm text-[#f1f1f5] placeholder:text-[#6b7280] focus:outline-none focus:border-[#4F8EF7]/50"
      />
    </div>
  );

  // Управление списком на десктопе и планшете: «Мои/Все», поиск, разделы.
  const listControls = (
    <div className="p-3 border-b border-[#2a2a3a] space-y-2.5">
      <div className="flex bg-[#0d0d12] rounded-lg p-0.5 gap-0.5">
        {[["my", "Мои"], ["all", "Все"]].map(([v, label]) => (
          <button key={v} onClick={() => switchView(v)}
            className={"flex-1 py-1.5 rounded-md text-xs font-medium transition " +
              (view === v ? "bg-[#4F8EF7] text-white" : "text-[#6b7280] hover:text-[#f1f1f5]")}>
            {label}
          </button>
        ))}
      </div>
      {searchField}
      {/* Ряд разделов прокручивается вправо: статусных пять, а папок сколько
          угодно, и «ещё»-меню, в которое раньше прятались ИИ и Закрытые,
          столько уже не вместит. */}
      <div className="flex gap-1 text-[11px] overflow-x-auto scrollbar-thin pb-0.5">
        {sectionTabs.map((t, i) => (
          <React.Fragment key={t.key}>
            {i > 0 && !isFolder(sectionTabs[i - 1].key) && isFolder(t.key) && (
              <div className="w-px shrink-0 my-1.5 bg-[#2a2a3a]"></div>
            )}
            <button
              onClick={() => setFilter(t.key)}
              title={t.label}
              className={
                "shrink-0 min-w-[56px] max-w-[104px] px-1.5 py-1.5 rounded-md font-medium transition flex flex-col items-center gap-0.5 " +
                (filter === t.key
                  ? "bg-[#4F8EF7]/15 text-[#7BA8F9]"
                  : "text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24]")
              }
            >
              <span className="text-sm leading-none">{t.icon}</span>
              <span className="max-w-full truncate">{t.label}</span>
              <span className="opacity-60">{counts[t.key] || 0}</span>
            </button>
          </React.Fragment>
        ))}
      </div>
    </div>
  );

  // Телефон: «Мои/Все» отдельным переключателем, разделы — прокручиваемыми
  // чипами (всё помещается, «ещё» не нужно).
  const mobileFilterBar = (
    <div className="shrink-0 flex items-center gap-2 px-2.5 py-2 bg-[#1a1a24] border-b border-[#2a2a3a] overflow-hidden">
      <div className="shrink-0 flex bg-[#0d0d12] border border-[#2a2a3a] rounded-full p-0.5">
        {[["my", "Мои"], ["all", "Все"]].map(([v, label]) => (
          <button key={v} onClick={() => switchView(v)}
            aria-label={v === "my" ? "Мои тикеты" : "Все тикеты"}
            className={"min-h-[40px] px-3.5 rounded-full text-xs font-semibold transition " +
              (view === v ? "bg-[#202030] text-[#f1f1f5]" : "text-[#9095a3]")}>
            {label}
          </button>
        ))}
      </div>
      <div className="flex gap-1.5 overflow-x-auto no-scrollbar">
        {sectionTabs.map((t) => (
          <button key={t.key} onClick={() => setFilter(t.key)}
            aria-label={"Раздел: " + t.label}
            className={"shrink-0 min-h-[44px] px-3.5 rounded-full text-[12.5px] font-medium border transition " +
              (filter === t.key
                ? "bg-[#4F8EF7] border-[#4F8EF7] text-white"
                : "bg-[#13131a] border-[#2a2a3a] text-[#9095a3]")}>
            {isFolder(t.key) && <span className="mr-1">{t.icon}</span>}
            {t.label}
            {counts[t.key] > 0 && <span className="ml-1 font-mono opacity-75">{counts[t.key]}</span>}
          </button>
        ))}
      </div>
    </div>
  );

  const listRows = (
    <div className={"flex-1 overflow-y-auto scrollbar-thin " + (vp.isMobile ? "" : "p-2 space-y-1")}>
      {filtered.length === 0 && (
        <div className="text-center text-xs text-[#6b7280] py-8">Диалоги не найдены</div>
      )}
      {filtered.map((c) => (
        <ConvCard key={c.id} conv={c} active={!vp.isMobile && c.id === activeId}
                  onClick={() => openDialog(c.id)} showServiceTag={showServiceTag}
                  flat={vp.isMobile} lockedForMe={lockedFor(c)} />
      ))}
    </div>
  );

  // Шапка переписки на десктопе. Раньше сюда выкладывались все действия сразу,
  // и ряд кнопок вытеснял имя клиента за границы шапки уже на 1440px — центр
  // это ширина окна минус две боковые колонки, её всегда меньше, чем кажется.
  // Теперь на виду главное действие и контекст (владелец, замок, папка),
  // остальное — в меню «⋯»; список тот же ticketActions, что и в шторке на
  // узких экранах.
  const primaryAction = !active ? null
    : locked ? "claim"
    : ["ai", "queue"].includes(active.status) ? "take"
    : null;
  const menuActions = ticketActions.filter((a) =>
    !(primaryAction === "take" && a.label === "Взять в работу")
    && !(primaryAction === "claim" && a.label === "Запросить тикет"));

  const chatTopBar = active && (
    <div className="h-[60px] shrink-0 px-5 border-b border-[#2a2a3a] flex items-center justify-between gap-3 bg-[#13131a]/40 relative z-20">
      <div className="flex items-center gap-3 min-w-0">
        <Avatar initials={active.initials} color={active.avatarColor} size={36} photoUrl={active.photoUrl} />
        <div className="min-w-0">
          <div className="flex items-center gap-2 min-w-0">
            <div className="font-medium text-[#f1f1f5] truncate">{active.name}</div>
            <StatusBadge status={active.status} />
            {active.status === "waiting" && <WaitingLabel reason={active.waitingReason} />}
            <SlaTimer slaSeconds={active.slaSeconds} slaStartedAt={active.slaStartedAt} />
          </div>
          <div className="text-xs text-[#6b7280] truncate">{active.username} · ID {active.tgId}</div>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {locked && (
          <span className="flex items-center gap-1.5 text-xs text-[#6b7280] px-1 max-w-[190px]">
            <Icon name="lock" className="w-3.5 h-3.5 shrink-0" />
            <span className="truncate">В работе у {active.assignedOperator}</span>
          </span>
        )}
        {!locked && ["in_progress", "waiting"].includes(active.status) && active.assignedOperator && (
          <span className="flex items-center gap-1.5 text-xs text-[#6b7280] px-1 max-w-[160px]">
            <Icon name="user" className="w-3.5 h-3.5 shrink-0" />
            <span className="truncate">{active.assignedOperator}</span>
          </span>
        )}

        {primaryAction === "take" && (
          <button
            onClick={handoffToOperator}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[#A855F7]/15 text-[#C084FC] border border-[#A855F7]/30 hover:bg-[#A855F7]/25 transition flex items-center gap-1.5 whitespace-nowrap"
          >
            <Icon name="user" className="w-3.5 h-3.5" />
            Взять в работу
          </button>
        )}
        {primaryAction === "claim" && (
          <button
            onClick={requestClaim}
            disabled={myClaimPending}
            title={myClaimPending
              ? "Владелец ещё не ответил на запрос"
              : "Попросить владельца передать тикет вам"}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-[#eab308]/15 text-[#eab308] border border-[#eab308]/30 hover:bg-[#eab308]/25 transition flex items-center gap-1.5 whitespace-nowrap disabled:opacity-50 disabled:cursor-default"
          >
            <Icon name="handRaise" className="w-3.5 h-3.5" />
            {myClaimPending ? "Запрос отправлен" : "Запросить"}
          </button>
        )}

        {!locked && folders.length > 0 && (
          <button
            onClick={() => setShowFolderPick(true)}
            title={active.folderName ? `Папка: ${active.folderName}` : "Положить в папку"}
            className={"px-2.5 py-1.5 rounded-lg text-xs font-medium border transition flex items-center gap-1.5 max-w-[150px] " +
              (active.folderId
                ? "border-[#3a3a4a] text-[#f1f1f5] bg-[#1a1a24]"
                : "border-[#2a2a3a] text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24]")}
          >
            <span className="text-sm leading-none shrink-0">{active.folderEmoji || "📁"}</span>
            <span className="truncate">{active.folderName || "Папка"}</span>
          </button>
        )}

        <div className="relative">
          <button
            onClick={() => setActionsOpen((v) => !v)}
            title="Действия над тикетом"
            className={"w-8 h-8 rounded-lg flex items-center justify-center transition " +
              (actionsOpen ? "bg-[#1a1a24] text-[#f1f1f5]" : "text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24]")}
          >
            <Icon name="dots" className="w-4 h-4" />
          </button>
          {actionsOpen && (
            <>
              <div className="fixed inset-0 z-30" onClick={() => setActionsOpen(false)}></div>
              <div className="absolute right-0 top-full mt-1 z-40 bg-[#1a1a24] border border-[#2a2a3a] rounded-lg shadow-2xl py-1 min-w-[210px]">
                {menuActions.map((a) => (
                  <button
                    key={a.label}
                    onClick={() => { setActionsOpen(false); a.run(); }}
                    className={"w-full text-left px-3 py-2 text-xs flex items-center gap-2.5 transition hover:bg-[#2a2a3a]/50 " +
                      (a.danger ? "text-[#f87171]" : "text-[#d1d1d8]")}
                  >
                    <Icon name={a.icon} className={"w-4 h-4 shrink-0 " + (a.danger ? "text-[#f87171]" : "text-[#6b7280]")} />
                    {a.label}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );

  // Шапка переписки на телефоне и планшете: «назад», имя, статус и две кнопки —
  // карточка клиента и меню действий.
  const chatTopBarCompact = active && (
    <MobileAppBar
      title={active.name}
      subtitle={`${active.username} · ${STATUS_LABEL[active.status] || ""}`}
      onBack={vp.isMobile ? () => setMobileView("list") : null}
      leading={<Avatar initials={active.initials} color={active.avatarColor} size={32}
                       photoUrl={active.photoUrl} />}
      right={
        <>
          <AppBarButton icon="info" label="Карточка клиента" onClick={() => setShowClientSheet(true)} />
          <AppBarButton icon="dots" label="Действия над тикетом" onClick={() => setShowActionsSheet(true)} />
        </>
      }
    />
  );

  // Владелец видит просьбу прямо над перепиской — иначе она утонет в системных
  // сообщениях, а второй оператор будет ждать впустую.
  const claimBanner = active && claimOnMine && (
    <div className="px-4 py-2.5 bg-[#eab308]/[.07] border-b border-[#eab308]/25 flex items-center gap-3">
      <Icon name="handRaise" className="w-4 h-4 text-[#eab308] shrink-0" />
      <span className="text-xs text-[#eab308] flex-1 min-w-0 truncate">
        {active.claimRequestedBy} просит передать этот тикет
      </span>
      <button onClick={() => answerClaim(true)}
        className="shrink-0 text-xs px-2.5 py-1 rounded-lg bg-[#eab308]/15 text-[#eab308] hover:bg-[#eab308]/25 transition font-medium">
        Передать
      </button>
      <button onClick={() => answerClaim(false)}
        className="shrink-0 text-xs px-2.5 py-1 rounded-lg text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24] transition">
        Отклонить
      </button>
    </div>
  );

  const closedBanner = active && active.status === "closed" && (
    <div className="px-4 py-2.5 bg-[#1a1a18] border-b border-[#2a2a3a] flex items-center gap-3">
      {activeDialogForSameUser ? (
        <>
          <Icon name="bellRing" className="w-4 h-4 text-[#eab308] shrink-0" />
          <span className="text-xs text-[#d1a800] flex-1">Пользователь написал в новый чат</span>
          <button
            onClick={() => openDialog(activeDialogForSameUser.id)}
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
  );

  const messagesPane = active && (
    <div ref={scrollRef}
         className={"flex-1 overflow-y-auto space-y-3 scrollbar-thin " + (compact ? "px-3 py-4" : "px-5 py-5")}>
      {(active.messages || []).length === 0 && (
        <div className="text-center text-xs text-[#6b7280] py-8">Загрузка сообщений...</div>
      )}
      {(() => {
        let lastDay = null;
        return (active.messages || []).map((m) => {
          let sep = null;
          if (m.createdAt) {
            const label = fmtDayLabel(m.createdAt);
            if (label && label !== lastDay) {
              lastDay = label;
              sep = <DaySeparator label={label} />;
            }
          }
          return (
            <React.Fragment key={m.id}>
              {sep}
              <MessageBubble msg={m} onImageClick={(url) => setLightboxUrl(url)} compact={compact} />
            </React.Fragment>
          );
        });
      })()}
    </div>
  );

  const lockedComposer = active && locked && (
    <div className="border-t border-[#2a2a3a] bg-[#13131a]/40 px-4 py-4 flex items-center gap-3"
         style={vp.isMobile ? { paddingBottom: "calc(1rem + env(safe-area-inset-bottom))" } : undefined}>
      <Icon name="lock" className="w-4 h-4 text-[#6b7280] shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="text-sm text-[#f1f1f5] truncate">
          Тикет в работе у {active.assignedOperator}
        </div>
        <div className="text-[11px] text-[#6b7280]">
          {myClaimPending
            ? "Запрос отправлен — ждём, пока владелец передаст тикет"
            : "Читать можно, отвечать — нет. Попросите передать его вам."}
        </div>
      </div>
      <button onClick={requestClaim} disabled={myClaimPending}
        className="shrink-0 px-3.5 py-2 rounded-lg text-xs font-semibold bg-[#eab308]/15 text-[#eab308] border border-[#eab308]/30 hover:bg-[#eab308]/25 transition flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-default">
        <Icon name="handRaise" className="w-3.5 h-3.5" />
        {myClaimPending ? "Запрос отправлен" : "Запросить"}
      </button>
    </div>
  );

  const composerPane = active && !locked && (
    <div className="border-t border-[#2a2a3a] bg-[#13131a]/40"
         style={vp.isMobile ? { paddingBottom: "env(safe-area-inset-bottom)" } : undefined}>
      <input ref={fileInputRef} type="file" className="hidden"
        accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.zip,.txt"
        onChange={handleFileSelect} />
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
      <div className={compact ? "p-2.5" : "p-3.5"}>
        {pendingFile && mode === "message" && (
          <div className="mb-2 flex items-center gap-2 bg-[#1a1a24] border border-[#2a2a3a] rounded-lg px-3 py-2">
            <Icon name="paperclip" className="w-4 h-4 text-[#4F8EF7] shrink-0" />
            <span className="text-xs text-[#f1f1f5] truncate flex-1">{pendingFile.name}</span>
            <button onClick={() => setPendingFile(null)} className="text-[#6b7280] hover:text-[#ef4444]"><Icon name="x" className="w-3.5 h-3.5" /></button>
          </div>
        )}
        <div className={"relative bg-[#1a1a24] border rounded-xl focus-within:border-[#4F8EF7]/50 transition " +
          (mode === "comment" ? "border-[#eab308]/30 focus-within:border-[#eab308]/50" : "border-[#2a2a3a]")}>
          {slashOpen && (
            <SlashTemplateList
              items={slashMatches}
              activeIndex={slashIndex}
              onPick={applyTemplate}
              onHover={setSlashIndex}
              compact={compact}
            />
          )}
          <textarea
            ref={composerRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onComposerKeyDown}
            placeholder={
              active.status === "closed" ? "Диалог закрыт" :
              mode === "comment" ? "Комментарий виден только операторам..." :
              "Написать сообщение..."
            }
            disabled={active.status === "closed"}
            rows={compact ? 1 : 2}
            className="w-full bg-transparent px-3.5 py-2.5 text-sm text-[#f1f1f5] placeholder:text-[#6b7280] focus:outline-none resize-none disabled:opacity-50"
          />
          <div className="flex items-center justify-between px-2 py-2 border-t border-[#2a2a3a]/60">
            <div className="flex items-center gap-1">
              {mode === "message" && (
                <>
                  <button
                    className={(compact ? "w-11 h-11 flex items-center justify-center " : "p-1.5 ") +
                      "text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#0d0d12] rounded transition"}
                    disabled={active.status === "closed"}
                    onClick={() => fileInputRef.current?.click()}
                    title="Прикрепить файл"
                  >
                    <Icon name="paperclip" />
                  </button>
                  <button
                    className={(compact ? "w-11 h-11 flex items-center justify-center " : "p-1.5 ") +
                      "text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#0d0d12] rounded transition"}
                    disabled={active.status === "closed"}
                    onClick={compact ? openSlashPanel : () => setShowTemplates(true)}
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
              className={"text-white text-xs font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-1.5 " +
                (compact ? "w-11 h-11 rounded-full " : "px-4 py-1.5 rounded-lg ") +
                (mode === "comment" ? "bg-[#eab308]/80 hover:bg-[#eab308]" : "bg-[#4F8EF7] hover:bg-[#3d7ce8]")}
              aria-label={mode === "comment" ? "Сохранить комментарий" : "Отправить"}
            >
              <Icon name="send" className={compact ? "w-4 h-4" : "w-3.5 h-3.5"} />
              {!compact && (mode === "comment" ? "Комментарий" : "Отправить")}
            </button>
          </div>
        </div>
        {!compact && (
          <div className="text-[10px] text-[#6b7280] mt-1.5 ml-1">
            Cmd/Ctrl + Enter для отправки
            {mode === "message" && <span> · <span className="font-mono text-[#7BA8F9]">/</span> — шаблоны</span>}
          </div>
        )}
      </div>
    </div>
  );

  const infoPanel = active && (
    <UserInfoPanel
      key={active.id}
      conv={active}
      showToast={showToast}
      compact={compact}
      readOnly={locked}
      isAdmin={currentOperator?.role === "admin"}
      onTicketClick={(id) => { setShowClientSheet(false); openDialog(id); }}
    />
  );

  // Экран списка на телефоне: шапка сервиса, лента ВПН-ов, фильтры, строки.
  const mobileListScreen = (
    <div className="h-full flex flex-col min-h-0">
      <MobileAppBar
        title={chrome.currentServiceId == null
          ? "Все сервисы"
          : (chrome.services || []).find((s) => s.id === chrome.currentServiceId)?.name || "Диалоги"}
        subtitle="Диалоги"
        right={
          <>
            <AppBarButton icon="search" label="Поиск"
                          tone={showSearch || searchQ ? "accent" : "muted"}
                          onClick={() => { const v = !showSearch; setShowSearch(v); if (!v) setSearchQ(""); }} />
            <AppBarButton icon="bell" label="Уведомления" badge={chrome.bellBadge} onClick={chrome.onBell} />
          </>
        }
      />
      <ServiceRail services={chrome.services} currentServiceId={chrome.currentServiceId}
                   onSelect={chrome.onSelectService} />
      {mobileFilterBar}
      {showSearch && <div className="shrink-0 px-2.5 py-2 bg-[#13131a] border-b border-[#2a2a3a]">{searchField}</div>}
      {listRows}
    </div>
  );

  const mobileChatScreen = (
    <div className="h-full flex flex-col min-h-0 bg-[#0d0d12]">
      {chatTopBarCompact}
      {claimBanner}
      {closedBanner}
      {messagesPane}
      {lockedComposer}
      {composerPane}
    </div>
  );

  return (
    <>
      {vp.isMobile ? (
        chatVisible ? mobileChatScreen : mobileListScreen
      ) : (
        <div className="flex h-full min-h-0">
          {/* Left: conversation list */}
          <aside className="w-[260px] shrink-0 bg-[#13131a] border-r border-[#2a2a3a] flex flex-col min-h-0">
            {listControls}
            {listRows}
          </aside>

          {/* Center: chat */}
          <section className="flex-1 flex flex-col bg-[#0d0d12] min-w-0 min-h-0">
            {active && (
              <>
                {compact ? chatTopBarCompact : chatTopBar}
                {claimBanner}
                {closedBanner}
                {messagesPane}
                {lockedComposer}
                {composerPane}
              </>
            )}
          </section>

          {/* Right: user info — на планшете уезжает в шторку по кнопке ⓘ */}
          {!compact && (
            <aside className="w-[320px] shrink-0 bg-[#13131a] border-l border-[#2a2a3a] overflow-y-auto scrollbar-thin">
              {infoPanel}
            </aside>
          )}
        </div>
      )}

      {/* Карточка клиента и действия над тикетом на узких экранах */}
      {compact && (
        <>
          <BottomSheet open={showClientSheet} onClose={() => setShowClientSheet(false)}
                       title={active?.name} subtitle="Карточка клиента">
            {infoPanel}
          </BottomSheet>
          <BottomSheet open={showActionsSheet} onClose={() => setShowActionsSheet(false)}
                       title={active?.name}
                       subtitle={active ? STATUS_LABEL[active.status] : null}>
            {ticketActions.map((a) => (
              <button key={a.label}
                onClick={() => { setShowActionsSheet(false); a.run(); }}
                className={"w-full min-h-[56px] px-[18px] flex items-center gap-3 text-[14.5px] text-left border-b border-[#2a2a3a]/50 last:border-0 active:bg-[#1a1a24] " +
                  (a.danger ? "text-[#f87171]" : "text-[#f1f1f5]")}>
                <Icon name={a.icon} className={"w-[19px] h-[19px] shrink-0 " + (a.danger ? "text-[#f87171]" : "text-[#9095a3]")} />
                {a.label}
              </button>
            ))}
          </BottomSheet>
        </>
      )}

      {/* Lightbox */}
      {lightboxUrl && (
        <ModalOverlay onClose={() => setLightboxUrl(null)} className="bg-black/80 p-8">
          <div className="relative max-w-4xl max-h-[90vh]">
            <img src={lightboxUrl} alt="" className="max-w-full max-h-[90vh] rounded-xl object-contain" />
            <button
              onClick={() => setLightboxUrl(null)}
              className="absolute top-3 right-3 w-8 h-8 rounded-full bg-black/60 hover:bg-black text-white flex items-center justify-center"
            >
              <Icon name="x" />
            </button>
          </div>
        </ModalOverlay>
      )}

      {/* Close confirm */}
      {confirmClose && (
        <ModalOverlay onClose={() => setConfirmClose(false)}>
          <div className="bg-[#13131a] border border-[#2a2a3a] rounded-xl p-6 w-full max-w-sm">
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
        </ModalOverlay>
      )}
      {showTemplates && <TemplatePickerModal onSelect={pickTemplate} templates={templates}
                                             onClose={() => setShowTemplates(false)} />}
      <ActionShell open={showFolderPick} onClose={() => setShowFolderPick(false)}
                   compact={compact} title="Папка тикета" subtitle={active?.name}>
        <div className="space-y-1.5">
          {folders.map((f) => (
            <button key={f.id} onClick={() => setDialogFolder(f.id)}
              className={"w-full min-h-[44px] px-3 rounded-lg flex items-center gap-2.5 text-left border transition " +
                (active?.folderId === f.id
                  ? "bg-[#1a1a24] border-[#3a3a4a] text-[#f1f1f5]"
                  : "border-[#2a2a3a] text-[#d1d1d8] hover:bg-[#1a1a24]")}>
              <span className="w-7 h-7 shrink-0 rounded-lg flex items-center justify-center text-base"
                    style={{ background: f.color + "22", border: `1px solid ${f.color}55` }}>
                {f.emoji}
              </span>
              <span className="flex-1 min-w-0 truncate text-sm">{f.name}</span>
              {active?.folderId === f.id && <Icon name="check" className="w-4 h-4 text-[#22c55e] shrink-0" />}
            </button>
          ))}
          {active?.folderId && (
            <button onClick={() => setDialogFolder(null)}
              className="w-full min-h-[44px] px-3 rounded-lg text-sm text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24] text-left">
              Убрать из папки
            </button>
          )}
        </div>
      </ActionShell>

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
      const token = localStorage.getItem("hd_token") || "";
      const res = await fetch(`/api/dialogs/${convId}/notes`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token },
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

// ── Карточка клиента ────────────────────────────────────────────────────────
// Данные и список доступных действий приходят из /api/dialogs/{id}/customer:
// какой источник за ними стоит, панель не знает (см. app/customer.py). Формы
// действий строятся по описанию полей, поэтому новое действие появляется в
// интерфейсе само, без правки этого файла.

function TrafficBar({ used, total }) {
  // Безлимит — тоже с подписью: иначе число висит без контекста, в отличие от
  // остальных строк карточки.
  if (!total) {
    return (
      <div className="flex justify-between items-center gap-3">
        <span className="text-[#6b7280]">Трафик</span>
        <span className="text-[#f1f1f5] font-medium tabular-nums">
          {used} <span className="text-[#6b7280] font-normal">ГБ · без лимита</span>
        </span>
      </div>
    );
  }
  const pct = Math.min(100, (used / total) * 100);
  const color = pct > 85 ? "#ef4444" : pct > 60 ? "#eab308" : "#22c55e";
  return (
    <>
      <div className="flex justify-between items-center mb-1.5">
        <span className="text-[#6b7280]">Трафик</span>
        <span className="text-[#f1f1f5] font-medium tabular-nums">
          {used} <span className="text-[#6b7280]">/ {total} ГБ</span>
        </span>
      </div>
      <div className="h-1.5 bg-[#0d0d12] rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: pct + "%", background: color }}></div>
      </div>
    </>
  );
}

function InfoRow({ label, children }) {
  return (
    <div className="flex justify-between items-center gap-3 py-0.5">
      <span className="text-[#6b7280] shrink-0">{label}</span>
      <span className="text-[#f1f1f5] text-right min-w-0 truncate">{children}</span>
    </div>
  );
}

const TRIAL_LABEL = { none: "не использован", active: "идёт сейчас", used: "использован" };

// Модалка на десктопе, шторка на узком экране — форма одна и та же.
function ActionShell({ open, onClose, title, subtitle, compact, children }) {
  if (compact) {
    return (
      <BottomSheet open={open} onClose={onClose} title={title} subtitle={subtitle}>
        <div className="px-[18px] pb-2">{children}</div>
      </BottomSheet>
    );
  }
  if (!open) return null;
  return (
    <ModalOverlay onClose={onClose} zIndex={60}>
      <div className="bg-[#13131a] border border-[#2a2a3a] rounded-xl w-full max-w-sm">
        <div className="px-5 py-4 border-b border-[#2a2a3a] flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="font-medium text-sm text-[#f1f1f5] truncate">{title}</div>
            {subtitle && <div className="text-[11px] text-[#6b7280] truncate">{subtitle}</div>}
          </div>
          <button onClick={onClose} className="text-[#6b7280] hover:text-[#f1f1f5] shrink-0">
            <Icon name="x" className="w-4 h-4" />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </ModalOverlay>
  );
}

// Форма действия по описанию полей из ACTIONS (app/customer.py).
function ActionForm({ spec, options, keys, devices, devicesKeyId, preset, busy, onSubmit, onCancel }) {
  // Устройства источник отдаёт не по клиенту целиком, а по одному ключу. Значит
  // в форме с выбором устройства ключ не выбирается: он тот, чьи устройства в
  // списке. Иначе оператор снял бы устройство с ключа, которому оно не
  // принадлежит, и запрос ушёл бы с несуществующей парой ключ+устройство.
  const deviceKey = spec.fields.some((f) => f.type === "device") ? (devicesKeyId || "") : "";
  const initial = {};
  for (const f of spec.fields) {
    initial[f.name] = deviceKey && f.type === "key"
      ? deviceKey
      : preset && preset[f.name] !== undefined
      ? preset[f.name]
      : (f.default !== null && f.default !== undefined ? f.default : "");
  }
  const [values, setValues] = useStateD(initial);
  const set = (name, v) => setValues((prev) => ({ ...prev, [name]: v }));
  const input = "w-full bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2.5 text-sm text-[#f1f1f5] placeholder:text-[#6b7280] focus:outline-none focus:border-[#4F8EF7]/50";

  return (
    <div className="space-y-3">
      {spec.confirm && (
        <div className="text-sm text-[#eab308] bg-[#eab308]/10 border border-[#eab308]/20 rounded-lg px-3 py-2">
          {spec.confirm}
        </div>
      )}
      {spec.fields.map((f) => {
        const lockedByDevice = !!deviceKey && f.type === "key";
        const preselected = (preset && preset[f.name] !== undefined) || lockedByDevice;
        if (f.type === "key" && preselected) {
          const k = (keys || []).find((x) => x.id === values[f.name]);
          return (
            <div key={f.name}>
              <label className="block text-xs text-[#6b7280] mb-1.5">{f.label}</label>
              <div className="text-sm text-[#f1f1f5] bg-[#0d0d12] border border-[#2a2a3a] rounded-lg px-3 py-2.5 truncate">
                {k ? `${k.name} · ${k.server || "—"}` : values[f.name]}
              </div>
              {lockedByDevice && (
                <div className="text-[10px] text-[#6b7280] mt-1">
                  Список устройств известен только по этому ключу
                </div>
              )}
            </div>
          );
        }
        const list = f.type === "key"
          ? (keys || []).map((k) => ({ value: k.id, label: `${k.name} · ${k.server || "—"}` }))
          : f.type === "device"
          ? (devices || []).map((d) => ({ value: d.id, label: d.name }))
          : (options && options[f.options]) || [];
        return (
          <div key={f.name}>
            <label className="block text-xs text-[#6b7280] mb-1.5">
              {f.label}{!f.required && <span className="text-[#3a3a4a]"> · необязательно</span>}
            </label>
            {f.type === "textarea" ? (
              <textarea rows={4} value={values[f.name]} onChange={(e) => set(f.name, e.target.value)}
                        className={input + " resize-none"} />
            ) : f.type === "bool" ? (
              <button type="button" onClick={() => set(f.name, !values[f.name])}
                      className={"w-full flex items-center justify-between px-3 py-2.5 rounded-lg border text-sm " +
                        (values[f.name] ? "border-[#4F8EF7]/50 text-[#f1f1f5]" : "border-[#2a2a3a] text-[#6b7280]")}>
                <span>{values[f.name] ? "Да" : "Нет"}</span>
                <span className={"relative w-8 h-[18px] rounded-full transition " +
                  (values[f.name] ? "bg-[#4F8EF7]" : "bg-[#2a2a3a]")}>
                  <span className={"absolute top-[2px] w-[14px] h-[14px] bg-white rounded-full transition-all " +
                    (values[f.name] ? "left-[16px]" : "left-[2px]")}></span>
                </span>
              </button>
            ) : (f.type === "select" || f.type === "key" || f.type === "device") ? (
              <select value={values[f.name]} onChange={(e) => set(f.name, e.target.value)} className={input}>
                {!f.required && <option value="">— не указывать —</option>}
                {list.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            ) : (
              <input type={f.type === "number" ? "number" : "text"} value={values[f.name]}
                     onChange={(e) => set(f.name, e.target.value)} className={input} />
            )}
            {f.hint && <div className="text-[10px] text-[#6b7280] mt-1">{f.hint}</div>}
          </div>
        );
      })}
      <div className="flex justify-end gap-2 pt-1">
        <button onClick={onCancel}
                className="px-3 py-2 rounded-lg text-sm text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24]">
          Отмена
        </button>
        <button onClick={() => onSubmit(values)} disabled={!!busy}
                className={"px-3 py-2 rounded-lg text-sm font-medium disabled:opacity-40 " +
                  (spec.danger
                    ? "bg-[#ef4444]/20 text-[#ef4444] border border-[#ef4444]/30 hover:bg-[#ef4444]/30"
                    : "bg-[#4F8EF7] text-white hover:bg-[#3d7ce8]")}>
          {busy ? "Выполняем…" : spec.label}
        </button>
      </div>
    </div>
  );
}

function ActionButton({ spec, onClick, small = false }) {
  return (
    <button onClick={onClick} title={spec.label}
            className={"rounded-lg font-medium border transition truncate " +
              (small ? "px-2.5 py-1.5 text-[11px] " : "px-3 py-2 text-xs ") +
              (spec.danger
                ? "border-[#ef4444]/30 text-[#ef4444] hover:bg-[#ef4444]/10"
                : "border-[#2a2a3a] text-[#d1d1d8] hover:bg-[#1a1a24] hover:text-[#f1f1f5]")}>
      {spec.label}
    </button>
  );
}

function KeyCard({ item, actions, onAction }) {
  const expired = item.expiresAt && new Date(item.expiresAt) < new Date();
  return (
    <div className="bg-[#1a1a24] rounded-xl p-3 border border-[#2a2a3a]/60 space-y-2">
      <div className="flex items-center gap-2">
        <span className={"w-1.5 h-1.5 rounded-full shrink-0 " +
          (item.active && !expired ? "bg-[#22c55e]" : "bg-zinc-600")}></span>
        <span className="text-sm text-[#f1f1f5] truncate flex-1">{item.name}</span>
        <span className={"text-[10px] shrink-0 " + (expired ? "text-[#ef4444]" : "text-[#6b7280]")}>
          {item.expiresAt || "—"}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-1.5 text-center">
        {[["Сервер", item.server || "—"], ["Тариф", item.plan || "—"],
          // null — источник не считал устройства по этому ключу; ноль значит ноль
          ["Устройств", item.devices ?? "—"]].map(([l, v]) => (
          <div key={l} className="bg-[#0d0d12] rounded-lg px-1.5 py-1">
            <div className="text-[9.5px] text-[#6b7280] truncate">{l}</div>
            <div className="text-[11px] text-[#f1f1f5] truncate">{v}</div>
          </div>
        ))}
      </div>
      <div className="text-[11px]">
        <TrafficBar used={item.trafficUsed} total={item.trafficLimit} />
      </div>
      {actions.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-0.5">
          {actions.map((a) => (
            <ActionButton key={a.name} spec={a} small onClick={() => onAction(a, { key_id: item.id })} />
          ))}
        </div>
      )}
    </div>
  );
}

// Лента «Действия»: всё, что случилось с аккаунтом клиента — и его руками, и
// операторскими. Данные собираются из внешней API (оплаты, журнал бота) и из
// самой панели, поэтому источник у каждой строки подписан.
const ACTIVITY_KINDS = {
  payment:  { icon: "💳", label: "Оплаты",      tone: "text-[#22c55e]" },
  deposit:  { icon: "💰", label: "Пополнения",  tone: "text-[#22c55e]" },
  key:      { icon: "🔑", label: "Ключи",       tone: "text-[#7BA8F9]" },
  device:   { icon: "📱", label: "Устройства",  tone: "text-[#7BA8F9]" },
  user:     { icon: "👤", label: "Профиль",     tone: "text-[#C084FC]" },
  message:  { icon: "✉️", label: "Сообщения",   tone: "text-[#9095a3]" },
  panel:    { icon: "🛟", label: "Панель",      tone: "text-[#eab308]" },
};

function ActivityTab({ convId, showToast }) {
  const [data, setData] = useStateD(null);     // {items, sources}
  const [loading, setLoading] = useStateD(true);
  const [kind, setKind] = useStateD("all");

  const load = React.useCallback(async () => {
    setLoading(true);
    try { setData(await window.apiFetch("GET", `/api/dialogs/${convId}/activity`)); }
    catch { setData({ items: [], sources: [] }); }
    setLoading(false);
  }, [convId]);

  // Лениво: три-четыре запроса во внешнюю API не должны тормозить открытие
  // тикета, поэтому лента грузится при первом заходе на вкладку.
  useEffectD(() => { load(); }, [load]);

  const items = data?.items || [];
  const kinds = useMemoD(() => {
    const seen = [];
    for (const e of items) if (!seen.includes(e.kind)) seen.push(e.kind);
    return seen;
  }, [items]);
  const shown = kind === "all" ? items : items.filter((e) => e.kind === kind);
  const failed = (data?.sources || []).filter((s) => !s.ok);

  if (loading && !data) return <div className="text-center text-xs text-[#6b7280] py-8">Загрузка ленты…</div>;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-wider text-[#6b7280] font-semibold flex-1">
          {items.length} событий
        </span>
        <button onClick={load} disabled={loading} title="Обновить ленту"
                className="w-7 h-7 shrink-0 rounded-lg flex items-center justify-center text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24] disabled:opacity-40">
          <Icon name="refresh" className={"w-3.5 h-3.5 " + (loading ? "animate-spin" : "")} />
        </button>
      </div>

      {failed.length > 0 && (
        <div className="rounded-lg px-2.5 py-2 text-[11px] border bg-[#f59e0b]/10 border-[#f59e0b]/30 text-[#f59e0b]">
          Часть истории недоступна: {failed.map((s) => `${s.name} — ${s.error}`).join("; ")}
        </div>
      )}

      {kinds.length > 1 && (
        <div className="flex gap-1 flex-wrap">
          {["all", ...kinds].map((k) => (
            <button key={k} onClick={() => setKind(k)}
              className={"px-2 py-1 rounded-md text-[11px] font-medium border transition " +
                (kind === k ? "bg-[#1a1a24] text-[#f1f1f5] border-[#3a3a4a]"
                            : "border-[#2a2a3a] text-[#6b7280] hover:text-[#f1f1f5]")}>
              {k === "all" ? "Все" : `${(ACTIVITY_KINDS[k] || {}).icon || "•"} ${(ACTIVITY_KINDS[k] || {}).label || k}`}
            </button>
          ))}
        </div>
      )}

      {shown.length === 0 && (
        <div className="text-center text-xs text-[#6b7280] py-6">Событий нет</div>
      )}

      <div className="space-y-1.5">
        {shown.map((e, i) => {
          const meta = ACTIVITY_KINDS[e.kind] || { icon: "•", tone: "text-[#9095a3]" };
          return (
            <div key={i} className="bg-[#1a1a24] rounded-lg px-3 py-2 border border-[#2a2a3a]/60 text-xs">
              <div className="flex items-start gap-2">
                <span className="shrink-0 text-[13px] leading-5">{meta.icon}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-[#f1f1f5] truncate">{e.title}</span>
                    {e.amount != null && e.amount !== 0 && (
                      <span className={"shrink-0 tabular-nums font-medium " + meta.tone}>
                        {e.amount} {e.currency}
                      </span>
                    )}
                  </div>
                  {e.detail && <div className="text-[10px] text-[#6b7280] mt-0.5 break-words">{e.detail}</div>}
                  <div className="flex items-center justify-between gap-2 mt-0.5 text-[10px] text-[#6b7280]">
                    <span className="truncate">{e.actor || "—"}</span>
                    <span className="shrink-0">{fmtDateTime(e.at)}</span>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {(data?.sources || []).length > 0 && (
        <div className="text-[10px] text-[#3a3a4a] pt-1">
          источники: {(data.sources || []).map((s) => s.name).join(", ")}
        </div>
      )}
    </div>
  );
}

function UserInfoPanel({ conv, showToast, onTicketClick, compact = false, isAdmin = false,
                        readOnly = false }) {
  const [tab, setTab] = useStateD("profile");
  const [data, setData] = useStateD(null);
  const [loading, setLoading] = useStateD(true);
  const [form, setForm] = useStateD(null);      // {spec, preset}
  const [busy, setBusy] = useStateD(false);

  const load = React.useCallback(async (refresh) => {
    setLoading(true);
    try {
      const d = await window.apiFetch(
        "GET", `/api/dialogs/${conv.id}/customer${refresh ? "?refresh=true" : ""}`);
      setData(d);
    } catch {
      setData(null);
    }
    setLoading(false);
  }, [conv.id]);

  useEffectD(() => { setTab("profile"); load(false); }, [load]);

  async function runAction(spec, params) {
    setBusy(true);
    try {
      const res = await window.apiFetch(
        "POST", `/api/dialogs/${conv.id}/customer/${spec.name}`, params);
      showToast && showToast(res.message || spec.label);
      setForm(null);
      await load(true);
    } catch (e) {
      showToast && showToast(e?.detail || "Не удалось выполнить действие", "warn");
    }
    setBusy(false);
  }

  function openAction(spec, preset) {
    // Действие без полей и без подтверждения выполняется сразу — лишний клик
    // оператору не нужен.
    if (spec.fields.length === 0 && !spec.confirm) { runAction(spec, {}); return; }
    setForm({ spec, preset: preset || {} });
  }

  // Чужой тикет — только чтение: продлевать подписку и банить клиента должен
  // тот, кто с ним разговаривает.
  const actions = readOnly ? [] : ((data && data.actions) || []);
  const byGroup = (g) => actions.filter((a) => a.group === g);
  // Действия над конкретным ключом рисуются на его карточке.
  const keyScoped = byGroup("keys").filter((a) => a.fields.some((f) => f.type === "key"));
  const keyGlobal = byGroup("keys").filter((a) => !a.fields.some((f) => f.type === "key"));

  const tabs = [
    { id: "profile",   label: "Профиль" },
    { id: "keys",      label: "Ключи",    count: data?.keys?.length },
    { id: "referrals", label: "Рефералы", count: data?.referrals?.length },
    // «История» разъехалась надвое: прошлые обращения — это тикеты, а
    // «Действия» — что происходило с самим аккаунтом клиента.
    { id: "tickets",   label: "Обращения", count: (conv.tickets || []).length },
    { id: "activity",  label: "Действия" },
  ];

  return (
    <div className="flex flex-col min-h-0">
      {/* Шапка: кто это и откуда данные */}
      <div className="p-4 pb-3 shrink-0">
        <div className="flex items-center gap-3">
          <Avatar initials={conv.initials} color={conv.avatarColor} size={44} photoUrl={conv.photoUrl} />
          <div className="min-w-0 flex-1">
            <div className="font-medium text-[#f1f1f5] text-sm truncate">{conv.name}</div>
            {data?.tgLink ? (
              <a href={data.tgLink} target="_blank" rel="noreferrer"
                 className="text-xs text-[#7BA8F9] hover:underline truncate block">
                {data.username || conv.username}
              </a>
            ) : (
              <div className="text-xs text-[#6b7280] truncate">{conv.username}</div>
            )}
            <div className="text-[10px] text-[#6b7280]/70 font-mono">ID {conv.tgId}</div>
          </div>
          <button onClick={() => load(true)} disabled={loading} title="Обновить профиль"
                  className="w-8 h-8 shrink-0 rounded-lg flex items-center justify-center text-[#6b7280] hover:text-[#f1f1f5] hover:bg-[#1a1a24] disabled:opacity-40">
            <Icon name="refresh" className={"w-4 h-4 " + (loading ? "animate-spin" : "")} />
          </button>
        </div>
        {data && (data.isMock || data.stale) && (
          <div className={"mt-3 flex items-start gap-2 rounded-lg px-2.5 py-2 text-[11px] border " +
            (data.stale
              ? "bg-[#ef4444]/10 border-[#ef4444]/25 text-[#ef4444]"
              : "bg-[#f59e0b]/10 border-[#f59e0b]/30 text-[#f59e0b]")}>
            <span className="shrink-0">⚠</span>
            <span>{data.message || (data.isMock ? "Тестовые данные (мок)" : "Данные могут устареть")}</span>
          </div>
        )}
      </div>

      {/* Вкладки */}
      <div className="flex px-1 border-b border-[#2a2a3a] shrink-0 overflow-x-auto no-scrollbar">
        {tabs.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
                  className={"shrink-0 px-2 py-2 text-xs font-medium border-b-2 -mb-px whitespace-nowrap transition " +
                    (tab === t.id
                      ? "border-[#4F8EF7] text-[#7BA8F9]"
                      : "border-transparent text-[#6b7280] hover:text-[#f1f1f5]")}>
            {t.label}
            {t.count > 0 && <span className="ml-1 opacity-60 font-mono">{t.count}</span>}
          </button>
        ))}
      </div>

      <div className="p-4 space-y-4 min-h-0">
        {loading && !data && (
          <div className="text-center text-xs text-[#6b7280] py-8">Загрузка профиля…</div>
        )}
        {!loading && !data && (
          <div className="text-center text-xs text-[#6b7280] py-8">Профиль недоступен</div>
        )}

        {/* ── Профиль ─────────────────────────────────────────────────────── */}
        {data && tab === "profile" && (
          <>
            <div className="bg-[#1a1a24] rounded-xl p-3.5 border border-[#2a2a3a]/60 space-y-2 text-xs">
              <InfoRow label="Тариф"><PlanBadge plan={data.plan || conv.plan} /></InfoRow>
              <InfoRow label="Подписка"><SubStatus status={data.subStatus} /></InfoRow>
              <InfoRow label="Статус">
                <span className={data.banned ? "text-[#ef4444]" : "text-[#22c55e]"}>
                  {data.banned ? "Забанен" : "Активен"}
                </span>
              </InfoRow>
              {data.group && <InfoRow label="Группа">{data.group}</InfoRow>}
              {data.language && <InfoRow label="Язык в ТГ">{data.language}</InfoRow>}
              <InfoRow label="Пробный период">{TRIAL_LABEL[data.trial] || data.trial}</InfoRow>
              <InfoRow label="След. платёж">{data.nextPayment || "—"}</InfoRow>
              <InfoRow label="Устройств">{data.devices.length || "—"}</InfoRow>
              <div className="pt-2 mt-1 border-t border-[#2a2a3a]/60">
                <TrafficBar used={data.traffic.used} total={data.traffic.total} />
              </div>
            </div>

            <div className="bg-[#1a1a24] rounded-xl p-3.5 border border-[#2a2a3a]/60 space-y-2 text-xs">
              <div className="text-[10px] uppercase tracking-wider text-[#6b7280] font-semibold mb-1">
                Партнёрка
              </div>
              <InfoRow label="Партнёр">
                <span className={data.isPartner ? "text-[#22c55e]" : "text-[#6b7280]"}>
                  {data.isPartner ? "да" : "нет"}
                </span>
              </InfoRow>
              <InfoRow label="Реф. процент">{data.refPercent}%</InfoRow>
              <InfoRow label="Реф. баланс">
                <span className="tabular-nums">{data.refBalance}</span>
              </InfoRow>
              {data.refCode && <InfoRow label="Реф. код"><span className="font-mono">{data.refCode}</span></InfoRow>}
              <InfoRow label="Рефералов">
                {data.referrals.length} <span className="text-[#6b7280]">· оплатили {data.referralsPaid}</span>
              </InfoRow>
              <InfoRow label="Депозиты рефералов">
                <span className="tabular-nums">{data.referralsDepositsTotal}</span>
              </InfoRow>
            </div>

            <div className="bg-[#1a1a24] rounded-xl p-3.5 border border-[#2a2a3a]/60 space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-wider text-[#6b7280] font-semibold">
                  Депозиты
                </span>
                <span className="text-[#f1f1f5] font-medium tabular-nums">{data.depositsTotal}</span>
              </div>
              {data.deposits.length === 0 && <div className="text-[#6b7280]">Платежей не было</div>}
              {data.deposits.slice(0, 5).map((p, i) => (
                <div key={i} className="flex justify-between gap-2">
                  <span className="text-[#6b7280] truncate">{p.date || "—"}{p.method ? ` · ${p.method}` : ""}</span>
                  <span className="text-[#f1f1f5] tabular-nums shrink-0">{p.amount} {p.currency}</span>
                </div>
              ))}
            </div>

            {byGroup("profile").length > 0 && (
              <div className="flex flex-wrap gap-2">
                {byGroup("profile").map((a) => (
                  <ActionButton key={a.name} spec={a} onClick={() => openAction(a)} />
                ))}
              </div>
            )}

            {conv.rating && (
              <section>
                <div className="text-[10px] uppercase tracking-wider text-[#6b7280] font-semibold mb-2">Оценка поддержки</div>
                <div className="bg-[#1a1a24] rounded-xl p-3.5 border border-[#2a2a3a]/60 flex items-center justify-between">
                  <StarRating rating={conv.rating} size="lg" />
                  <span className="text-[11px] text-[#6b7280]">{conv.rating} / 5</span>
                </div>
              </section>
            )}

            <section>
              <div className="text-[10px] uppercase tracking-wider text-[#6b7280] font-semibold mb-2">Заметки</div>
              <NotesEditor convId={conv.id} initialValue={conv.notes || ""} showToast={showToast} />
            </section>
          </>
        )}

        {/* ── Ключи ───────────────────────────────────────────────────────── */}
        {data && tab === "keys" && (
          <>
            {keyGlobal.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {keyGlobal.map((a) => (
                  <ActionButton key={a.name} spec={a} onClick={() => openAction(a)} />
                ))}
              </div>
            )}
            {data.keys.length === 0 && (
              <div className="text-center text-xs text-[#6b7280] py-6">Ключей нет</div>
            )}
            {data.keys.map((k) => (
              <KeyCard key={k.id} item={k} actions={keyScoped}
                       onAction={(spec, preset) => openAction(spec, preset)} />
            ))}
            {data.devices.length > 0 && (
              <section>
                <div className="text-[10px] uppercase tracking-wider text-[#6b7280] font-semibold mb-2">Устройства</div>
                <div className="space-y-1.5">
                  {data.devices.map((d) => (
                    <div key={d.id} className="bg-[#1a1a24] rounded-lg px-3 py-2 border border-[#2a2a3a]/60 flex justify-between gap-2 text-xs">
                      <span className="text-[#f1f1f5] truncate">{d.name}</span>
                      <span className="text-[#6b7280] shrink-0">{d.lastSeen}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </>
        )}

        {/* ── Рефералы ────────────────────────────────────────────────────── */}
        {data && tab === "referrals" && (
          <>
            <div className="grid grid-cols-3 gap-2">
              {[["Всего", data.referrals.length], ["Оплатили", data.referralsPaid],
                ["Депозиты", data.referralsDepositsTotal]].map(([l, v]) => (
                <div key={l} className="bg-[#1a1a24] rounded-xl px-2 py-2.5 border border-[#2a2a3a]/60 text-center">
                  <div className="text-base font-semibold text-[#f1f1f5] tabular-nums truncate">{v}</div>
                  <div className="text-[10px] text-[#6b7280]">{l}</div>
                </div>
              ))}
            </div>
            {byGroup("referrals").length > 0 && (
              <div className="flex flex-wrap gap-2">
                {byGroup("referrals").map((a) => (
                  <ActionButton key={a.name} spec={a} onClick={() => openAction(a)} />
                ))}
              </div>
            )}
            {data.referrals.length === 0 && (
              <div className="text-center text-xs text-[#6b7280] py-6">Рефералов нет</div>
            )}
            <div className="space-y-1.5">
              {data.referrals.map((r) => (
                <div key={r.tgId} className="bg-[#1a1a24] rounded-lg px-3 py-2 border border-[#2a2a3a]/60 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[#f1f1f5] truncate">{r.name}</span>
                    <span className={"shrink-0 text-[10px] " + (r.paid ? "text-[#22c55e]" : "text-[#6b7280]")}>
                      {r.paid ? "оплатил" : "без оплат"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-2 mt-0.5">
                    <span className="text-[10px] text-[#6b7280] font-mono truncate">{r.tgId}</span>
                    <span className="text-[10px] text-[#f1f1f5] tabular-nums shrink-0">{r.depositsTotal}</span>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {/* ── Действия над аккаунтом клиента ──────────────────────────────── */}
        {tab === "activity" && <ActivityTab convId={conv.id} showToast={showToast} />}

        {/* ── Прошлые обращения ───────────────────────────────────────────── */}
        {tab === "tickets" && (
          <div className="space-y-1.5">
            {(conv.tickets || []).length === 0 && (
              <div className="text-center text-xs text-[#6b7280] py-6">Нет закрытых обращений</div>
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

        {data && data.source && (
          <div className="text-[10px] text-[#3a3a4a] pt-1">источник: {data.source}</div>
        )}
      </div>

      <ActionShell open={!!form} onClose={() => setForm(null)} compact={compact}
                   title={form?.spec.label} subtitle={conv.name}>
        {form && (
          <ActionForm
            spec={form.spec}
            preset={form.preset}
            options={data?.options || {}}
            keys={data?.keys || []}
            devices={data?.devices || []}
            devicesKeyId={data?.devicesKeyId || ""}
            busy={busy}
            onSubmit={(values) => runAction(form.spec, values)}
            onCancel={() => setForm(null)}
          />
        )}
      </ActionShell>
    </div>
  );
}

Object.assign(window, { DialogsScreen });
