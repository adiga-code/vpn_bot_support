// Reusable UI components

const { useState, useEffect, useRef, useMemo } = React;

// Generic avatar circle with initials
function Avatar({ initials, color, size = 36, ring = false }) {
  return (
    <div
      className={"flex items-center justify-center rounded-full text-white font-medium shrink-0 " + (ring ? "ring-2 ring-[#13131a]" : "")}
      style={{
        width: size,
        height: size,
        background: color,
        fontSize: size * 0.38,
      }}
    >
      {initials}
    </div>
  );
}

function StatusBadge({ status }) {
  const map = {
    new: { label: "Новый", cls: "bg-[#4F8EF7]/15 text-[#7BA8F9] border-[#4F8EF7]/30" },
    in_progress: { label: "В работе", cls: "bg-[#eab308]/15 text-[#eab308] border-[#eab308]/30" },
    closed: { label: "Закрыт", cls: "bg-zinc-500/15 text-zinc-400 border-zinc-600/40" },
  };
  const cfg = map[status] || map.new;
  return (
    <span className={"inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium border " + cfg.cls}>
      {cfg.label}
    </span>
  );
}

function PlanBadge({ plan }) {
  const map = {
    Pro: "bg-gradient-to-r from-[#A855F7] to-[#4F8EF7] text-white",
    Basic: "bg-[#1f2a44] text-[#7BA8F9] border border-[#4F8EF7]/30",
    Trial: "bg-[#3d3320] text-[#eab308] border border-[#eab308]/30",
  };
  return (
    <span className={"inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold " + (map[plan] || map.Basic)}>
      {plan}
    </span>
  );
}

function SubStatus({ status }) {
  const map = {
    active: { label: "Активна", color: "text-[#22c55e]", dot: "bg-[#22c55e]" },
    expiring: { label: "Истекает", color: "text-[#eab308]", dot: "bg-[#eab308]" },
    blocked: { label: "Заблокирована", color: "text-[#ef4444]", dot: "bg-[#ef4444]" },
  };
  const cfg = map[status] || map.active;
  return (
    <span className={"inline-flex items-center gap-1.5 text-xs font-medium " + cfg.color}>
      <span className={"w-1.5 h-1.5 rounded-full " + cfg.dot}></span>
      {cfg.label}
    </span>
  );
}

// Icons (inline SVG, stroke-based)
function Icon({ name, className = "w-4 h-4", strokeWidth = 1.75 }) {
  const paths = {
    search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3-3" /></>,
    bell: <><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10 21a2 2 0 0 0 4 0" /></>,
    menu: <><path d="M3 6h18M3 12h18M3 18h18" /></>,
    send: <><path d="m22 2-7 20-4-9-9-4Z" /><path d="M22 2 11 13" /></>,
    paperclip: <><path d="m21 12-9.5 9.5a5 5 0 0 1-7-7L13 5a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L15 7" /></>,
    chevronDown: <><path d="m6 9 6 6 6-6" /></>,
    chevronRight: <><path d="m9 6 6 6-6 6" /></>,
    x: <><path d="M18 6 6 18M6 6l12 12" /></>,
    check: <><path d="M20 6 9 17l-5-5" /></>,
    plus: <><path d="M12 5v14M5 12h14" /></>,
    edit: <><path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z" /></>,
    trash: <><path d="M3 6h18" /><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /><path d="m19 6-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /></>,
    chat: <><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></>,
    chart: <><path d="M3 3v18h18" /><path d="m7 14 4-4 4 4 5-6" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></>,
    bellRing: <><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10 21a2 2 0 0 0 4 0" /></>,
    image: <><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="9" cy="9" r="2" /><path d="m21 15-5-5L5 21" /></>,
    sparkles: <><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" /></>,
    user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
    refresh: <><path d="M3 12a9 9 0 0 1 15-6.7L21 8" /><path d="M21 3v5h-5" /><path d="M21 12a9 9 0 0 1-15 6.7L3 16" /><path d="M3 21v-5h5" /></>,
    key: <><circle cx="7.5" cy="15.5" r="4.5" /><path d="m21 2-9.6 9.6" /><path d="m15.5 7.5 3 3L22 7l-3-3" /></>,
    plus2: <><path d="M12 5v14M5 12h14" /></>,
    arrowLeft: <><path d="M19 12H5" /><path d="m12 19-7-7 7-7" /></>,
    arrowRight: <><path d="M5 12h14" /><path d="m12 5 7 7-7 7" /></>,
    calendar: <><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></>,
    operators: <><circle cx="9" cy="8" r="4" /><path d="M3 21a6 6 0 0 1 12 0" /><circle cx="17" cy="9" r="3" /><path d="M21 19a4 4 0 0 0-4-4" /></>,
    book: <><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    server:    <><rect x="2" y="2" width="20" height="8" rx="2" /><rect x="2" y="14" width="20" height="8" rx="2" /><path d="M6 6h.01M6 18h.01" /></>,
    zap:       <><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" /></>,
    megaphone: <><path d="M3 11v2" /><path d="M11.5 5.5L19 3v18l-7.5-2.5" /><path d="M11.5 5.5v13" /><path d="M3 11a2 2 0 0 0 0 4v-4z" /></>,
    template:  <><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" /><rect x="9" y="3" width="6" height="4" rx="1" /><path d="M9 12h6M9 16h4" /></>,
    link:      <><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" /><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" /></>,
  };
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" className={className}>
      {paths[name]}
    </svg>
  );
}

function Toast({ msg }) {
  if (!msg) return null;
  return (
    <div className="fixed bottom-6 right-6 z-50 animate-[slideUp_.2s_ease-out]">
      <div className="bg-[#1a1a24] border border-[#2a2a3a] rounded-lg px-4 py-3 shadow-2xl flex items-center gap-2.5 text-sm text-[#f1f1f5]">
        <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e]"></span>
        {msg}
      </div>
    </div>
  );
}

Object.assign(window, { Avatar, StatusBadge, PlanBadge, SubStatus, Icon, Toast });
