// Демо-режим: подменяет fetch("/api/...") и WebSocket("/ws") браузерным
// моком с данными из demo-data.js. Бэкенд, n8n, Redis и Postgres не нужны —
// страница полностью автономна. Состояние живёт в памяти вкладки и
// сбрасывается при перезагрузке.
(function () {
  "use strict";

  const D = window.buildDemoData();
  window.__demoState = D; // для отладки и e2e-проверок
  const fmtTime = D.fmtTime;

  // Текущий оператор (после «входа»); по умолчанию — админ
  let currentOp = D.operators[0];

  let _liveId = 0;
  function newMsg(kind, text, extra) {
    const now = new Date();
    return Object.assign({
      id: "m-live-" + (++_liveId),
      kind: kind,
      text: text || "",
      fileId: null,
      fileType: null,
      fileUrl: null,
      operator: null,
      time: fmtTime(now),
      createdAt: now.toISOString(),
      deliveryStatus: null,
      deliveryError: null,
    }, extra || {});
  }

  function findDialog(id) {
    return D.dialogs.find(function (d) { return d.id === id; });
  }

  function pushMsg(dialogId, m) {
    (D.messages[dialogId] = D.messages[dialogId] || []).push(m);
    const d = findDialog(dialogId);
    if (d) {
      d.preview = m.text || (m.fileType ? "[" + m.fileType + "]" : "—");
      d.time = m.time;
      d.updatedAt = m.createdAt;
    }
    broadcast({ type: "new_message", dialog_id: dialogId, message: m });
  }

  function dialogUpdated(d) {
    broadcast({ type: "dialog_updated", dialog: stripMessages(d) });
  }

  function stripMessages(d) {
    // диалог в API-форме — без массива messages (его фронт хранит отдельно)
    return Object.assign({}, d);
  }

  // ── Фейковый WebSocket ─────────────────────────────────────────────────────

  const sockets = new Set();

  function broadcast(obj) {
    const data = JSON.stringify(obj);
    sockets.forEach(function (ws) {
      if (ws.readyState === 1 && ws.onmessage) {
        try { ws.onmessage({ data: data }); } catch (e) { console.error(e); }
      }
    });
  }

  const RealWebSocket = window.WebSocket;

  function DemoWebSocket(url, protocols) {
    if (!/\/ws(\?|$)/.test(String(url))) {
      return new RealWebSocket(url, protocols);
    }
    const ws = this;
    ws.url = String(url);
    ws.readyState = 0;
    ws.onopen = null;
    ws.onmessage = null;
    ws.onclose = null;
    ws.onerror = null;
    ws.send = function (text) {
      if (text === "ping") {
        setTimeout(function () {
          if (ws.readyState === 1 && ws.onmessage) ws.onmessage({ data: "pong" });
        }, 30);
      }
    };
    ws.close = function () {
      if (ws.readyState === 3) return;
      ws.readyState = 3;
      sockets.delete(ws);
      if (ws.onclose) ws.onclose({ code: 1000 });
    };
    setTimeout(function () {
      ws.readyState = 1;
      sockets.add(ws);
      if (ws.onopen) ws.onopen({});
      startAmbient();
    }, 60);
  }
  DemoWebSocket.CONNECTING = 0;
  DemoWebSocket.OPEN = 1;
  DemoWebSocket.CLOSING = 2;
  DemoWebSocket.CLOSED = 3;
  window.WebSocket = DemoWebSocket;

  // ── «Жизнь» в демо: клиенты отвечают, приходят новые обращения ────────────

  const clientReplies = [
    "Понял, сейчас попробую",
    "Секунду, проверяю…",
    "Да, так работает! Спасибо огромное 🙏",
    "Хм, а если через мобильный интернет?",
    "Получилось! Вы лучшие",
  ];
  let replyIdx = 0;

  function scheduleClientReply(dialogId) {
    const delay = 8000 + Math.random() * 6000;
    setTimeout(function () {
      const d = findDialog(dialogId);
      if (!d || d.status === "closed") return;
      const text = clientReplies[replyIdx++ % clientReplies.length];
      if (d.status === "waiting") {
        d.status = "in_progress";
        d.waitingReason = null;
        d.slaStartedAt = new Date().toISOString();
      }
      d.unread = (d.unread || 0) + 1;
      pushMsg(dialogId, newMsg("user", text));
      dialogUpdated(d);
    }, delay);
  }

  let ambientStarted = false;
  function startAmbient() {
    if (ambientStarted) return;
    ambientStarted = true;

    // Клиент из тикета «в ожидании» возвращается с ответом
    setTimeout(function () {
      const d = findDialog("dlg-1021");
      if (!d || d.status !== "waiting") return;
      d.status = "in_progress";
      d.waitingReason = null;
      d.unread = (d.unread || 0) + 1;
      d.slaStartedAt = new Date().toISOString();
      pushMsg(d.id, newMsg("user", "Переключился на Стокгольм — скорость поднялась до 240 Мбит! Спасибо"));
      dialogUpdated(d);
    }, 25000);

    // Новое обращение появляется в разделе ИИ, бот отвечает сам
    setTimeout(function () {
      const now = new Date();
      const nd = {
        id: "dlg-1028", chatId: 481203957, tgId: 481203957,
        name: "Павел Юдин", username: "@pavel_u", initials: "ПЮ",
        avatarColor: "#f59e0b", status: "ai", operatorCalled: false,
        unread: 1, aiEnabled: true, plan: "Basic", subStatus: "active",
        nextPayment: D.fmtDate(new Date(Date.now() + 19 * 864e5)),
        traffic: { used: 3, total: 100 },
        lastPayment: { amount: "299 ₽", date: D.fmtDate(new Date(Date.now() - 11 * 864e5)) },
        preview: "Здравствуйте, как подключить второе устройство?",
        time: fmtTime(now), assignedOperator: null,
        updatedAt: now.toISOString(), rating: null, notes: "", photoUrl: null,
        waitingReason: null, slaSeconds: 0, slaStartedAt: null,
        returnRequested: false, tickets: [],
      };
      D.dialogs.unshift(nd);
      D.messages[nd.id] = [];
      broadcast({ type: "new_dialog", dialog: stripMessages(nd) });
      pushMsg(nd.id, newMsg("user", "Здравствуйте, как подключить второе устройство?"));
      setTimeout(function () {
        pushMsg(nd.id, newMsg("ai", "Здравствуйте, Павел! По вашей подписке доступно до 5 устройств. Установите приложение на второе устройство и войдите с тем же ключом доступа — он в личном кабинете, раздел «Мои устройства»."));
      }, 4500);
    }, 45000);

    // …а через минуту этот клиент зовёт живого оператора (уведомление + звук)
    setTimeout(function () {
      const d = findDialog("dlg-1028");
      if (!d || d.status === "closed" || d.assignedOperator) return;
      d.unread = (d.unread || 0) + 1;
      pushMsg(d.id, newMsg("user", "А можно с человеком поговорить? Не получается найти ключ"));
      d.status = "queue";
      d.aiEnabled = false;
      d.operatorCalled = true;
      d.slaStartedAt = new Date().toISOString();
      pushMsg(d.id, newMsg("system", "Клиент вызвал оператора"));
      dialogUpdated(d);
    }, 80000);
  }

  // ── Мини-биллинг демо-операций ─────────────────────────────────────────────

  function billingAction(d, action) {
    if (action === "renew") {
      const next = new Date(Date.now() + 30 * 864e5);
      d.nextPayment = D.fmtDate(next);
      d.subStatus = "active";
      d.lastPayment = { amount: d.plan === "Premium" ? "899 ₽" : d.plan === "Pro" ? "499 ₽" : "299 ₽", date: D.fmtDate(new Date()) };
      return "Подписка продлена на 30 дней";
    }
    if (action === "buy_traffic") {
      d.traffic = { used: d.traffic.used, total: d.traffic.total + 50 };
      return "Добавлено 50 ГБ трафика";
    }
    if (action === "reset_key") {
      return "Ключ доступа сброшен, клиенту отправлен новый";
    }
    return "Готово";
  }

  // ── Роутер API ─────────────────────────────────────────────────────────────

  function json(data, status) {
    return new Response(JSON.stringify(data === undefined ? null : data), {
      status: status || 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  function parseBody(init) {
    if (!init || !init.body || typeof init.body !== "string") return {};
    try { return JSON.parse(init.body); } catch (e) { return {}; }
  }

  function fileUrlFrom(init) {
    // FormData c полем file → object URL (для превью загруженных картинок)
    try {
      if (init && init.body && typeof FormData !== "undefined" && init.body instanceof FormData) {
        const f = init.body.get("file");
        if (f) return { url: URL.createObjectURL(f), name: (f.name || "file") };
      }
    } catch (e) {}
    return { url: "about:blank", name: "file" };
  }

  function route(method, path, query, init) {
    let m;

    // ── Auth ──
    if (path === "/api/auth/status") return json({ setup_needed: false });
    if (path === "/api/auth/login" || path === "/api/auth/setup") {
      const body = parseBody(init);
      const tg = (body.tg || "").toLowerCase();
      currentOp = D.operators.find(function (o) { return o.tg.toLowerCase() === tg; }) || D.operators[0];
      currentOp.online = true;
      return json({ token: "demo-token", operator: currentOp });
    }
    if (path === "/api/auth/me") return json(currentOp);
    if (path === "/api/auth/logout") return json({ ok: true });
    if (path === "/api/auth/password") return json({ ok: true });

    // ── Dialogs ──
    if (path === "/api/dialogs" && method === "GET") {
      return json(D.dialogs.map(stripMessages));
    }
    if ((m = path.match(/^\/api\/dialogs\/([^\/]+)$/)) && method === "GET") {
      const d = findDialog(m[1]);
      return d ? json(stripMessages(d)) : json({ detail: "Not found" }, 404);
    }
    if ((m = path.match(/^\/api\/dialogs\/([^\/]+)\/history$/))) {
      const d = findDialog(m[1]);
      return json(d ? d.tickets || [] : []);
    }
    if ((m = path.match(/^\/api\/dialogs\/([^\/]+)\/messages$/))) {
      const d = findDialog(m[1]);
      if (d && d.unread) { d.unread = 0; dialogUpdated(d); }
      return json(D.messages[m[1]] || []);
    }
    if ((m = path.match(/^\/api\/dialogs\/([^\/]+)\/reply$/))) {
      const d = findDialog(m[1]);
      if (!d) return json({ detail: "Not found" }, 404);
      const body = parseBody(init);
      const mm = newMsg("operator", body.text || "", {
        operator: body.operator_name || currentOp.name,
        fileType: body.file_type || null,
        fileUrl: body.file_url || null,
      });
      pushMsg(d.id, mm);
      // подтверждение доставки чуть позже — как в живой системе
      setTimeout(function () {
        mm.deliveryStatus = "delivered";
        broadcast({ type: "message_status", dialog_id: d.id, message_id: mm.id, status: "delivered" });
      }, 900);
      // отвеченный тикет уходит в «ждём ответа», слот освобождается
      if (d.status === "in_progress") {
        d.status = "waiting";
        d.waitingReason = "operator_replied";
        d.slaStartedAt = null;
        dialogUpdated(d);
      }
      scheduleClientReply(d.id);
      return json({ ok: true, delivered: true });
    }
    if ((m = path.match(/^\/api\/dialogs\/([^\/]+)\/comment$/))) {
      const d = findDialog(m[1]);
      if (!d) return json({ detail: "Not found" }, 404);
      const body = parseBody(init);
      pushMsg(d.id, newMsg("comment", (body.text || "").trim(), { operator: currentOp.name }));
      return json({ ok: true });
    }
    if ((m = path.match(/^\/api\/dialogs\/([^\/]+)\/notes$/))) {
      const d = findDialog(m[1]);
      if (!d) return json({ detail: "Not found" }, 404);
      d.notes = parseBody(init).text || "";
      dialogUpdated(d);
      return json({ ok: true });
    }
    if ((m = path.match(/^\/api\/dialogs\/([^\/]+)\/dismiss_called$/))) {
      const d = findDialog(m[1]);
      if (d) { d.operatorCalled = false; dialogUpdated(d); }
      return json({ ok: true });
    }
    if ((m = path.match(/^\/api\/dialogs\/([^\/]+)\/toggle_ai$/))) {
      const d = findDialog(m[1]);
      if (!d) return json({ detail: "Not found" }, 404);
      d.aiEnabled = !d.aiEnabled;
      if (d.aiEnabled && d.status === "queue") d.status = "ai";
      else if (!d.aiEnabled && d.status === "ai") d.status = "queue";
      dialogUpdated(d);
      return json({ ai_enabled: d.aiEnabled });
    }
    if ((m = path.match(/^\/api\/dialogs\/([^\/]+)\/handoff$/))) {
      const d = findDialog(m[1]);
      if (!d) return json({ detail: "Not found" }, 404);
      if (d.status === "closed") return json({ detail: "Dialog is closed" }, 400);
      const opName = parseBody(init).operator_name || currentOp.name;
      d.status = "in_progress";
      d.assignedOperator = opName;
      d.aiEnabled = false;
      d.operatorCalled = false;
      d.slaStartedAt = new Date().toISOString();
      pushMsg(d.id, newMsg("system", "Оператор " + opName + " подключился к диалогу"));
      dialogUpdated(d);
      return json({ ok: true });
    }
    if ((m = path.match(/^\/api\/dialogs\/([^\/]+)\/reopen-closed$/))) {
      const d = findDialog(m[1]);
      if (!d) return json({ detail: "Not found" }, 404);
      d.status = "queue";
      d.assignedOperator = null;
      d.rating = null;
      d.slaStartedAt = new Date().toISOString();
      pushMsg(d.id, newMsg("system", "Диалог открыт повторно"));
      dialogUpdated(d);
      return json({ ok: true });
    }
    if ((m = path.match(/^\/api\/dialogs\/([^\/]+)\/reopen$/))) {
      const d = findDialog(m[1]);
      if (!d) return json({ detail: "Not found" }, 404);
      d.status = "queue";
      d.assignedOperator = null;
      d.waitingReason = null;
      pushMsg(d.id, newMsg("system", "Тикет возвращён в очередь"));
      dialogUpdated(d);
      return json({ ok: true });
    }
    if ((m = path.match(/^\/api\/dialogs\/([^\/]+)\/wait$/))) {
      const d = findDialog(m[1]);
      if (!d) return json({ detail: "Not found" }, 404);
      if (d.status !== "in_progress") return json({ detail: "Only in_progress tickets can be paused" }, 400);
      d.status = "waiting";
      d.waitingReason = "manual";
      pushMsg(d.id, newMsg("system", "Тикет поставлен в ожидание оператором"));
      dialogUpdated(d);
      return json({ ok: true });
    }
    if ((m = path.match(/^\/api\/dialogs\/([^\/]+)\/transfer$/))) {
      const d = findDialog(m[1]);
      if (!d) return json({ detail: "Not found" }, 404);
      const target = parseBody(init).operator_name;
      d.assignedOperator = target;
      pushMsg(d.id, newMsg("system", "Диалог передан оператору " + target));
      dialogUpdated(d);
      return json({ ok: true });
    }
    if ((m = path.match(/^\/api\/dialogs\/([^\/]+)\/close$/))) {
      const d = findDialog(m[1]);
      if (!d) return json({ detail: "Not found" }, 404);
      d.status = "closed";
      d.operatorCalled = false;
      d.waitingReason = null;
      d.slaStartedAt = null;
      pushMsg(d.id, newMsg("system", "Диалог закрыт"));
      dialogUpdated(d);
      // клиент ставит оценку через несколько секунд
      setTimeout(function () {
        if (d.status !== "closed" || d.rating) return;
        d.rating = 5;
        pushMsg(d.id, newMsg("system", "Клиент оценил поддержку: 5/5"));
        dialogUpdated(d);
      }, 7000);
      return json({ ok: true });
    }
    if ((m = path.match(/^\/api\/dialogs\/([^\/]+)\/billing\/([a-z_]+)$/))) {
      const d = findDialog(m[1]);
      if (!d) return json({ detail: "Not found" }, 404);
      const message = billingAction(d, m[2]);
      dialogUpdated(d);
      return json({ ok: true, message: message });
    }

    // ── Файлы ──
    if (path === "/api/upload") {
      const f = fileUrlFrom(init);
      return json({ url: f.url, filename: f.name });
    }

    // ── Серверы ──
    if (path === "/api/servers") {
      const servers = D.servers.map(function (s) {
        if (s.status === "down") return s;
        return Object.assign({}, s, {
          ping: s.ping + Math.round(Math.random() * 6 - 3),
          load: Math.max(5, Math.min(97, s.load + Math.round(Math.random() * 8 - 4))),
        });
      });
      return json({ servers: servers, last_updated: new Date().toTimeString().slice(0, 8), is_stub: false });
    }

    // ── Статистика ──
    if (path === "/api/stats") {
      return json(D.buildStats(parseInt(query.get("days") || "14", 10)));
    }
    if (path === "/api/stats/times") {
      return json(D.buildTimeStats(parseInt(query.get("days") || "30", 10)));
    }

    // ── Операторы ──
    if (path === "/api/operators" && method === "GET") return json(D.operators);
    if (path === "/api/operators" && method === "POST") {
      const body = parseBody(init);
      const op = {
        id: Math.max.apply(null, D.operators.map(function (o) { return o.id; })) + 1,
        name: body.name, tg: body.tg, tgId: body.tg_id || null,
        role: body.role || "agent",
        initials: (body.name || "??").split(/\s+/).map(function (w) { return w[0]; }).join("").slice(0, 2).toUpperCase(),
        color: ["#f97316", "#06b6d4", "#ec4899", "#8b5cf6"][D.operators.length % 4],
        online: false, paused: false,
        notifPrefs: { new_dialog: true, operator_called: true, server_down: true, sound_enabled: true },
      };
      D.operators.push(op);
      return json(op);
    }
    if (path === "/api/operators/me/notifications" && method === "GET") {
      return json(currentOp.notifPrefs);
    }
    if (path === "/api/operators/me/notifications" && method === "PUT") {
      currentOp.notifPrefs = Object.assign({}, currentOp.notifPrefs, parseBody(init));
      return json({ ok: true });
    }
    if (path === "/api/operators/me/pause") {
      const paused = !!parseBody(init).paused;
      currentOp.paused = paused;
      broadcast({ type: "operator_status", op_id: currentOp.id, online: true, paused: paused });
      return json({ ok: true, paused: paused });
    }
    if ((m = path.match(/^\/api\/operators\/(\d+)$/))) {
      const op = D.operators.find(function (o) { return o.id === +m[1]; });
      if (!op) return json({ detail: "Not found" }, 404);
      if (method === "PUT") {
        const body = parseBody(init);
        op.name = body.name; op.tg = body.tg; op.role = body.role;
        if (body.tg_id !== undefined) op.tgId = body.tg_id;
        return json(op);
      }
      if (method === "DELETE") {
        if (op.id === currentOp.id) return json({ detail: "Cannot delete yourself" }, 400);
        D.operators = D.operators.filter(function (o) { return o !== op; });
        return json({ ok: true });
      }
    }

    // ── Настройки ──
    if ((m = path.match(/^\/api\/settings\/(ai|schedule|automation|notifications|sounds)$/))) {
      const key = m[1];
      if (method === "GET") return json(D.settings[key]);
      const body = parseBody(init);
      D.settings[key] = key === "schedule" && body.schedule ? body.schedule : Object.assign({}, D.settings[key], body);
      return json({ ok: true });
    }
    if (path === "/api/settings/sounds/upload") {
      const event = query.get("event") || "new_message";
      const f = fileUrlFrom(init);
      D.settings.sounds[event + "_url"] = f.url;
      return json({ url: f.url });
    }

    // ── База знаний ──
    if (path === "/api/kb" && method === "GET") return json(D.kbArticles);
    if (path === "/api/kb" && method === "DELETE") {
      D.kbArticles = [];
      return json({ ok: true });
    }
    if (path === "/api/kb/upload") {
      // имитация чанкинга загруженного документа
      const created = new Date().toISOString();
      const ids = ["kb-new-1", "kb-new-2"].map(function (id, i) {
        const a = {
          id: id + "-" + Date.now(),
          title: i === 0 ? "Новый документ — часть 1" : "Новый документ — часть 2",
          category: "Общее",
          keywords: ["демо", "документ"],
          content: "Содержимое загруженного документа (в демо-режиме файл не обрабатывается моделью).",
          created_at: created,
        };
        D.kbArticles.unshift(a);
        return a.id;
      });
      return json({ chunks_created: ids.length, ids: ids });
    }
    if ((m = path.match(/^\/api\/kb\/(.+)$/)) && method === "DELETE") {
      D.kbArticles = D.kbArticles.filter(function (a) { return a.id !== decodeURIComponent(m[1]); });
      return json({ ok: true });
    }

    // ── Шаблоны ──
    if (path === "/api/templates" && method === "GET") return json(D.templates);
    if (path === "/api/templates" && method === "POST") {
      const body = parseBody(init);
      const t = {
        id: Math.max.apply(null, D.templates.map(function (x) { return x.id; }).concat([0])) + 1,
        group_name: (body.group_name || "Общие").trim() || "Общие",
        title: body.title, text: body.text,
      };
      D.templates.push(t);
      return json(t);
    }
    if (path === "/api/templates/group") {
      const body = parseBody(init);
      D.templates.forEach(function (t) {
        if (t.group_name === body.old_name) t.group_name = body.new_name;
      });
      return json({ ok: true });
    }
    if ((m = path.match(/^\/api\/templates\/(\d+)$/))) {
      const t = D.templates.find(function (x) { return x.id === +m[1]; });
      if (!t) return json({ detail: "Not found" }, 404);
      if (method === "PUT") {
        const body = parseBody(init);
        t.group_name = (body.group_name || "Общие").trim() || "Общие";
        t.title = body.title; t.text = body.text;
        return json(t);
      }
      if (method === "DELETE") {
        D.templates = D.templates.filter(function (x) { return x !== t; });
        return json({ ok: true });
      }
    }

    // ── Рассылка ──
    if (path === "/api/broadcast") {
      const total = D.dialogs.length;
      return json({ sent: total, failed: 0, total: total });
    }

    console.warn("[demo] незамоканный endpoint:", method, path);
    return json({ detail: "Not implemented in demo" }, 404);
  }

  // ── Патч fetch ─────────────────────────────────────────────────────────────

  const realFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    const raw = typeof input === "string" ? input : (input && input.url) || "";
    let path = raw, queryStr = "";
    const qi = raw.indexOf("?");
    if (qi >= 0) { path = raw.slice(0, qi); queryStr = raw.slice(qi + 1); }
    if (!path.startsWith("/api")) return realFetch(input, init);
    const method = ((init && init.method) || (typeof input === "object" && input.method) || "GET").toUpperCase();
    const query = new URLSearchParams(queryStr);
    return new Promise(function (resolve) {
      setTimeout(function () {
        try {
          resolve(route(method, path, query, init || {}));
        } catch (e) {
          console.error("[demo] ошибка мока:", e);
          resolve(json({ detail: String(e) }, 500));
        }
      }, 120 + Math.random() * 200); // лёгкая «сетевая» задержка
    });
  };

  // ── Бейдж демо-режима ──────────────────────────────────────────────────────

  function addBadge() {
    const el = document.createElement("div");
    el.textContent = "🎭 Демо-режим · вход с любыми логином и паролем · данные сбросятся при обновлении страницы";
    el.style.cssText =
      "position:fixed;bottom:10px;left:10px;z-index:9999;background:#1a1a24;color:#a1a1b3;" +
      "border:1px solid #2a2a3a;border-radius:10px;padding:6px 12px;font-size:11px;" +
      "font-family:Inter,system-ui,sans-serif;opacity:.92;pointer-events:none;max-width:60vw";
    document.body.appendChild(el);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", addBadge);
  } else {
    addBadge();
  }
})();
