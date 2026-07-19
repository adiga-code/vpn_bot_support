// Демо-данные для автономной демонстрации хелпдеска (без бэкенда).
// Собирает свежий набор состояния при каждой загрузке страницы — все
// временные метки вычисляются относительно текущего момента.
(function () {
  "use strict";

  // ── Помощники времени ──────────────────────────────────────────────────────

  function minAgo(n) {
    return new Date(Date.now() - n * 60 * 1000);
  }

  function dayAgo(n) {
    return new Date(Date.now() - n * 24 * 60 * 60 * 1000);
  }

  function fmtTime(dt) {
    if (!dt) return "";
    const now = new Date();
    const diffDays = Math.floor((now - dt) / 86400000);
    const sameDay = dt.getDate() === now.getDate() && dt.getMonth() === now.getMonth() && dt.getFullYear() === now.getFullYear();
    if (sameDay) return dt.toTimeString().slice(0, 5);
    if (diffDays <= 1) return "Вчера";
    const dd = String(dt.getDate()).padStart(2, "0");
    const mm = String(dt.getMonth() + 1).padStart(2, "0");
    return dd + "." + mm;
  }

  function fmtDate(dt) {
    const dd = String(dt.getDate()).padStart(2, "0");
    const mm = String(dt.getMonth() + 1).padStart(2, "0");
    return dd + "." + mm + "." + dt.getFullYear();
  }

  let _msgId = 1000;
  function msg(kind, text, minutesAgo, extra) {
    const created = minAgo(minutesAgo);
    return Object.assign({
      id: "m-" + (++_msgId),
      kind: kind,
      text: text || "",
      fileId: null,
      fileType: null,
      fileUrl: null,
      operator: null,
      time: fmtTime(created),
      createdAt: created.toISOString(),
      deliveryStatus: kind === "operator" ? "delivered" : null,
      deliveryError: null,
    }, extra || {});
  }

  // Небольшая инлайновая картинка для сообщения с фото (работает офлайн)
  const DEMO_PHOTO =
    "data:image/svg+xml;charset=utf-8," + encodeURIComponent(
      '<svg xmlns="http://www.w3.org/2000/svg" width="520" height="360">' +
      '<rect width="520" height="360" fill="#1a1a24"/>' +
      '<rect x="40" y="40" width="440" height="230" rx="12" fill="#0d0d12" stroke="#2a2a3a"/>' +
      '<text x="60" y="80" fill="#7BA8F9" font-family="monospace" font-size="16">WireGuard · Настройки</text>' +
      '<text x="60" y="120" fill="#f1f1f5" font-family="monospace" font-size="14">Статус: Handshake failed</text>' +
      '<text x="60" y="150" fill="#ef4444" font-family="monospace" font-size="14">Ошибка: peer timeout (код 110)</text>' +
      '<text x="60" y="190" fill="#6b7280" font-family="monospace" font-size="13">Endpoint: nl-ams-2.vpn.example:51820</text>' +
      '<text x="60" y="220" fill="#6b7280" font-family="monospace" font-size="13">Последний хендшейк: никогда</text>' +
      '<text x="40" y="320" fill="#6b7280" font-family="sans-serif" font-size="13">Скриншот клиента (демо)</text>' +
      "</svg>"
    );

  function dialog(o) {
    return Object.assign({
      chatId: o.tgId,
      tgId: o.tgId,
      initials: o.name.split(/\s+/).map(function (w) { return w[0]; }).join("").slice(0, 2).toUpperCase(),
      operatorCalled: false,
      unread: 0,
      aiEnabled: false,
      plan: "Basic",
      subStatus: "active",
      nextPayment: fmtDate(dayAgo(-21)),
      traffic: { used: 24, total: 100 },
      lastPayment: { amount: "299 ₽", date: fmtDate(dayAgo(9)) },
      assignedOperator: null,
      rating: null,
      notes: "",
      photoUrl: null,
      waitingReason: null,
      slaSeconds: 0,
      slaStartedAt: null,
      returnRequested: false,
      tickets: [],
    }, o);
  }

  // ── Сборка состояния ───────────────────────────────────────────────────────

  window.buildDemoData = function () {
    const operators = [
      { id: 1, name: "Алексей Петров", tg: "@alex_petrov", tgId: 100200301, role: "admin", initials: "АП", color: "#4F8EF7", online: true, paused: false,
        notifPrefs: { new_dialog: true, operator_called: true, server_down: true, sound_enabled: true } },
      { id: 2, name: "Мария Иванова", tg: "@maria_iv", tgId: 100200302, role: "agent", initials: "МИ", color: "#A855F7", online: true, paused: false,
        notifPrefs: { new_dialog: true, operator_called: true, server_down: true, sound_enabled: true } },
      { id: 3, name: "Дмитрий Соколов", tg: "@d_sokolov", tgId: 100200303, role: "agent", initials: "ДС", color: "#22c55e", online: false, paused: false,
        notifPrefs: { new_dialog: true, operator_called: true, server_down: false, sound_enabled: false } },
    ];

    const dialogs = [
      dialog({
        id: "dlg-1024", tgId: 562304178, name: "Игорь Савченко", username: "@igor_sav",
        avatarColor: "#f97316", status: "in_progress", assignedOperator: "Алексей Петров",
        plan: "Pro", traffic: { used: 61, total: 200 },
        lastPayment: { amount: "499 ₽", date: fmtDate(dayAgo(4)) },
        preview: "Вот скриншот с ошибкой", time: fmtTime(minAgo(6)),
        updatedAt: minAgo(6).toISOString(),
        slaSeconds: 540, slaStartedAt: minAgo(9).toISOString(),
        notes: "Windows 11, обновился до клиента 2.4.1 — после этого пропало подключение.",
        tickets: [
          { id: "T-0871", dialogId: "dlg-0871", title: "Не приходил ключ после оплаты", date: fmtTime(dayAgo(12)), solved: true, rating: 5 },
          { id: "T-0640", dialogId: "dlg-0640", title: "Настройка на роутере Keenetic", date: fmtTime(dayAgo(34)), solved: true, rating: 4 },
        ],
      }),
      dialog({
        id: "dlg-1023", tgId: 918273645, name: "Ольга Крылова", username: "@olga_kr",
        avatarColor: "#ec4899", status: "in_progress", assignedOperator: "Мария Иванова",
        plan: "Premium", traffic: { used: 132, total: 500 },
        lastPayment: { amount: "899 ₽", date: fmtDate(dayAgo(1)) },
        preview: "Списание прошло два раза, вот выписка", time: fmtTime(minAgo(18)),
        updatedAt: minAgo(18).toISOString(),
        slaSeconds: 1260, slaStartedAt: minAgo(21).toISOString(),
        unread: 2,
      }),
      dialog({
        id: "dlg-1021", tgId: 736451920, name: "Денис Мороз", username: "@denis_moroz",
        avatarColor: "#22c55e", status: "waiting", waitingReason: "operator_replied",
        assignedOperator: "Алексей Петров",
        preview: "Хорошо, попробую вечером и напишу", time: fmtTime(minAgo(47)),
        updatedAt: minAgo(47).toISOString(),
        slaSeconds: 320, slaStartedAt: null,
      }),
      dialog({
        id: "dlg-1019", tgId: 845102937, name: "Артём Волков", username: "@artem_v",
        avatarColor: "#eab308", status: "waiting", waitingReason: "manual",
        assignedOperator: "Мария Иванова", plan: "Pro",
        preview: "И сколько ждать ответа?", time: fmtTime(minAgo(64)),
        updatedAt: minAgo(64).toISOString(),
        slaSeconds: 780, slaStartedAt: minAgo(13).toISOString(),
        notes: "Ждём ответа от биллинга по возврату — тикет BIL-2214.",
      }),
      dialog({
        id: "dlg-1025", tgId: 654908712, name: "Сергей Панов", username: "@sergey_p",
        avatarColor: "#ef4444", status: "queue", operatorCalled: true, unread: 3,
        subStatus: "expired", nextPayment: fmtDate(dayAgo(2)),
        traffic: { used: 100, total: 100 },
        preview: "Оператора позовите пожалуйста!!", time: fmtTime(minAgo(3)),
        updatedAt: minAgo(3).toISOString(),
        slaSeconds: 0, slaStartedAt: minAgo(3).toISOString(),
      }),
      dialog({
        id: "dlg-1026", tgId: 190283746, name: "Наталья Ким", username: "@nat_travel",
        avatarColor: "#A855F7", status: "ai", aiEnabled: true,
        preview: "Спасибо! А на планшет тоже можно?", time: fmtTime(minAgo(11)),
        updatedAt: minAgo(11).toISOString(),
      }),
      dialog({
        id: "dlg-1027", tgId: 573829104, name: "Марк Гордеев", username: "@mark_dev",
        avatarColor: "#06b6d4", status: "ai", aiEnabled: true, plan: "Pro",
        preview: "Какой протокол лучше для мобильного интернета?", time: fmtTime(minAgo(28)),
        updatedAt: minAgo(28).toISOString(),
      }),
      dialog({
        id: "dlg-1014", tgId: 428190573, name: "Виктор Лебедев", username: "@viktor_l",
        avatarColor: "#4F8EF7", status: "closed", rating: 5,
        assignedOperator: "Алексей Петров",
        preview: "Всё заработало, спасибо большое!", time: fmtTime(dayAgo(1)),
        updatedAt: dayAgo(1).toISOString(),
      }),
      dialog({
        id: "dlg-1009", tgId: 309284756, name: "Anna Skvortsova", username: "@anna_sky",
        avatarColor: "#8b5cf6", status: "closed", rating: 4,
        assignedOperator: "Мария Иванова", plan: "Premium",
        preview: "Ок, поняла, спасибо", time: fmtTime(dayAgo(3)),
        updatedAt: dayAgo(3).toISOString(),
      }),
    ];

    const messages = {
      "dlg-1024": [
        msg("user", "Здравствуйте! После обновления клиента VPN перестал подключаться. Крутится «подключение» и всё.", 42),
        msg("ai", "Здравствуйте, Игорь! Попробуйте, пожалуйста: 1) перезапустить приложение; 2) переключить протокол на WireGuard в настройках; 3) выбрать другой сервер. Помогло?", 41),
        msg("user", "Пробовал всё, не помогает. Позовите живого человека", 38),
        msg("system", "Диалог передан оператору", 38),
        msg("system", "Оператор Алексей Петров подключился к диалогу", 35),
        msg("operator", "Игорь, добрый день! Посмотрю вашу проблему. Пришлите, пожалуйста, скриншот экрана с ошибкой из клиента.", 34, { operator: "Алексей Петров" }),
        msg("user", "Вот скриншот с ошибкой", 6, { fileType: "photo", fileUrl: DEMO_PHOTO }),
      ],
      "dlg-1023": [
        msg("user", "Добрый день! Оплатила подписку, а деньги списались два раза 😡", 25),
        msg("system", "Диалог передан оператору", 24),
        msg("system", "Оператор Мария Иванова подключилась к диалогу", 23),
        msg("operator", "Ольга, здравствуйте! Сейчас проверю платежи по вашему аккаунту. Одну минуту.", 22, { operator: "Мария Иванова" }),
        msg("comment", "Вижу в биллинге два платежа с разницей 30 сек — похоже на дабл-клик на форме. Оформляю возврат второго.", 20, { operator: "Мария Иванова" }),
        msg("user", "Списание прошло два раза, вот выписка", 18),
      ],
      "dlg-1021": [
        msg("user", "Скорость очень низкая по вечерам, что делать?", 95),
        msg("system", "Оператор Алексей Петров подключился к диалогу", 90),
        msg("operator", "Денис, добрый день! Вечером сервер Амстердам-1 бывает загружен. Переключитесь на Амстердам-2 или Стокгольм — в клиенте это пункт «Выбор сервера». Напишите, как результат.", 50, { operator: "Алексей Петров" }),
        msg("user", "Хорошо, попробую вечером и напишу", 47),
        msg("system", "Тикет в ожидании ответа клиента", 47),
      ],
      "dlg-1019": [
        msg("user", "Оформил возврат неделю назад, деньги так и не пришли", 130),
        msg("system", "Оператор Мария Иванова подключилась к диалогу", 120),
        msg("operator", "Артём, здравствуйте! Проверяю статус возврата в платёжной системе, уточню у коллег и вернусь с ответом.", 70, { operator: "Мария Иванова" }),
        msg("user", "И сколько ждать ответа?", 64),
        msg("system", "Тикет поставлен в ожидание оператором", 60),
      ],
      "dlg-1025": [
        msg("user", "Подписка кончилась а я оплатил вчера!", 9),
        msg("ai", "Сергей, вижу, что последний платёж не привязался к аккаунту. Уточните, пожалуйста, каким способом вы оплачивали?", 8),
        msg("user", "Картой как обычно. Ничего не поменялось", 5),
        msg("user", "Оператора позовите пожалуйста!!", 3),
        msg("system", "Клиент вызвал оператора", 3),
      ],
      "dlg-1026": [
        msg("user", "Привет! Еду в отпуск, VPN будет работать за границей?", 15),
        msg("ai", "Здравствуйте, Наталья! Да, сервис работает из любой страны. Рекомендуем заранее включить протокол WireGuard — он стабильнее в роуминге.", 14),
        msg("user", "Спасибо! А на планшет тоже можно?", 11),
        msg("ai", "Конечно! По одной подписке можно подключить до 5 устройств. Установите приложение на планшет и войдите с тем же ключом.", 10),
      ],
      "dlg-1027": [
        msg("user", "Какой протокол лучше для мобильного интернета?", 28),
        msg("ai", "Марк, для мобильных сетей обычно лучше WireGuard: быстрее восстанавливает соединение при смене сети. Если провайдер блокирует — попробуйте наш обфусцированный режим.", 27),
      ],
      "dlg-1014": [
        msg("user", "Не работает VPN на макбуке, ошибка DNS", 1500),
        msg("system", "Оператор Алексей Петров подключился к диалогу", 1495),
        msg("operator", "Виктор, добрый день! Откройте настройки клиента → «Сеть» → включите «Использовать DNS сервиса». После этого переподключитесь.", 1490, { operator: "Алексей Петров" }),
        msg("user", "Всё заработало, спасибо большое!", 1450),
        msg("system", "Диалог закрыт", 1448),
        msg("system", "Клиент оценил поддержку: 5/5", 1440),
      ],
      "dlg-1009": [
        msg("user", "Можно ли сменить тариф без потери оплаченных дней?", 4400),
        msg("system", "Оператор Мария Иванова подключилась к диалогу", 4390),
        msg("operator", "Anna, да! При переходе на старший тариф остаток дней пересчитывается пропорционально. Готова оформить переход — подтвердите тариф Premium.", 4380, { operator: "Мария Иванова" }),
        msg("user", "Ок, поняла, спасибо", 4320),
        msg("system", "Диалог закрыт", 4315),
      ],
    };

    const templates = [
      { id: 1, group_name: "Приветствие", title: "Приветствие", text: "Здравствуйте! Меня зовут {name}, я специалист поддержки. Уже разбираюсь с вашим вопросом 🙂" },
      { id: 2, group_name: "Приветствие", title: "Взял в работу", text: "Добрый день! Ваше обращение у меня в работе, отвечу в течение нескольких минут." },
      { id: 3, group_name: "Подключение", title: "Смена протокола", text: "Откройте настройки приложения → «Протокол» → выберите WireGuard, затем переподключитесь. Если не поможет — пришлите скриншот ошибки." },
      { id: 4, group_name: "Подключение", title: "Другой сервер", text: "Попробуйте выбрать другой сервер из списка — ближайший к вам по расположению обычно даёт лучшую скорость." },
      { id: 5, group_name: "Оплата", title: "Проверка платежа", text: "Проверяю ваш платёж в системе. Уточните, пожалуйста, дату оплаты и последние 4 цифры карты." },
      { id: 6, group_name: "Оплата", title: "Возврат оформлен", text: "Возврат оформлен ✅ Деньги вернутся на карту в течение 3–5 рабочих дней в зависимости от банка." },
      { id: 7, group_name: "Завершение", title: "Закрытие диалога", text: "Рад был помочь! Если появятся вопросы — просто напишите в этот чат. Хорошего дня! 🙌" },
    ];

    const kbArticles = [
      { id: "kb-001", title: "Настройка WireGuard на iPhone и iPad", category: "Подключение",
        keywords: ["ios", "iphone", "wireguard", "настройка", "конфиг"],
        content: "1. Установите приложение из App Store.\n2. Войдите по ключу из письма или скопируйте конфигурацию из личного кабинета.\n3. Разрешите добавление VPN-профиля в настройках iOS.\n4. Включите переключатель подключения. При проблемах — смените сервер на ближайший.",
        created_at: dayAgo(20).toISOString() },
      { id: "kb-002", title: "Оплата, автопродление и смена тарифа", category: "Оплата",
        keywords: ["оплата", "тариф", "автопродление", "карта", "подписка"],
        content: "Подписка продлевается автоматически за сутки до окончания. Отключить автопродление можно в личном кабинете → «Подписка». При переходе на старший тариф остаток дней пересчитывается пропорционально стоимости.",
        created_at: dayAgo(20).toISOString() },
      { id: "kb-003", title: "Низкая скорость: чек-лист диагностики", category: "Скорость",
        keywords: ["скорость", "медленно", "лагает", "пинг"],
        content: "1. Смените сервер на менее загруженный (индикатор нагрузки в списке).\n2. Переключите протокол на WireGuard.\n3. Проверьте скорость без VPN — если она тоже низкая, проблема у провайдера.\n4. На роутерах старше 5 лет шифрование может упираться в CPU.",
        created_at: dayAgo(14).toISOString() },
      { id: "kb-004", title: "Возврат средств", category: "Оплата",
        keywords: ["возврат", "деньги", "refund"],
        content: "Возврат возможен в течение 30 дней с момента оплаты, если использовано менее 10 ГБ трафика. Оформляется оператором через биллинг-панель, зачисление на карту — 3–5 рабочих дней.",
        created_at: dayAgo(7).toISOString() },
      { id: "kb-005", title: "Двойное списание при оплате", category: "Оплата",
        keywords: ["двойное", "списание", "дубль", "платеж"],
        content: "Причина почти всегда — повторное нажатие кнопки оплаты. Найдите в биллинге два платежа с интервалом менее минуты и оформите возврат второго. Клиенту сообщите срок возврата 3–5 рабочих дней.",
        created_at: dayAgo(2).toISOString() },
    ];

    const servers = [
      { name: "Амстердам-1", status: "ok", location: "Нидерланды, Амстердам", ping: 34, load: 41, uptime: 99.98 },
      { name: "Амстердам-2", status: "ok", location: "Нидерланды, Амстердам", ping: 36, load: 27, uptime: 99.95 },
      { name: "Франкфурт", status: "ok", location: "Германия, Франкфурт", ping: 41, load: 52, uptime: 99.99 },
      { name: "Стокгольм", status: "high", location: "Швеция, Стокгольм", ping: 48, load: 88, uptime: 99.91 },
      { name: "Алматы", status: "ok", location: "Казахстан, Алматы", ping: 21, load: 33, uptime: 99.86 },
      { name: "Нью-Йорк", status: "down", location: "США, Нью-Йорк", ping: null, load: null, uptime: 97.24 },
    ];

    const settings = {
      ai: {
        prompt: "Ты — дружелюбный ассистент поддержки VPN-сервиса. Отвечай кратко, на русском. Если не знаешь ответ — предложи передать диалог оператору.",
        model: "gpt-4o-mini",
        temperature: 0.7,
        auto_reply: true,
        handoff_enabled: true,
        classification_enabled: true,
      },
      schedule: {
        mon: { enabled: true, from: "09:00", to: "21:00" },
        tue: { enabled: true, from: "09:00", to: "21:00" },
        wed: { enabled: true, from: "09:00", to: "21:00" },
        thu: { enabled: true, from: "09:00", to: "21:00" },
        fri: { enabled: true, from: "09:00", to: "21:00" },
        sat: { enabled: false, from: "10:00", to: "18:00" },
        sun: { enabled: false, from: "10:00", to: "18:00" },
      },
      automation: {
        operator_button_enabled: true,
        operator_button_after_msgs: 3,
        auto_handoff_enabled: true,
        rating_enabled: true,
        rating_message_text: "Оцените качество поддержки:",
        rating_thanks_text: "Спасибо за оценку! 🙏",
        close_message_enabled: true,
        close_message_text: "Спасибо за обращение! Если появятся вопросы — просто напишите нам.",
        max_tickets_per_operator: 10,
        offline_grace_seconds: 60,
        handoff_instruction_text: "Если вопрос сложный или пользователь просит живого человека — добавь [HANDOFF] в начало ответа.",
      },
      sounds: {},
      notifications: { new_dialog: true, operator_called: true, server_down: true, sound_enabled: true },
    };

    // ── Статистика ────────────────────────────────────────────────────────────

    function buildStats(days) {
      const base = [31, 24, 28, 35, 41, 22, 18, 27, 33, 38, 29, 25, 36, 44, 30, 26, 21, 34, 39, 28, 23, 32, 37, 42, 27, 19, 31, 40, 33, 26];
      const daily = [];
      for (let i = 0; i < days; i++) daily.unshift(base[i % base.length]);
      daily[daily.length - 1] = 17; // «сегодня» — день ещё не кончился
      const hourly = [1, 0, 0, 0, 1, 2, 4, 8, 14, 21, 26, 29, 31, 28, 25, 27, 30, 33, 36, 31, 24, 15, 8, 3];
      return {
        today_total: 17,
        today_closed: 12,
        ai_pct: 58,
        daily: daily,
        hourly: hourly,
        operators: operators.map(function (op, i) {
          return {
            id: op.id, name: op.name, tg: op.tg, role: op.role, online: op.online,
            initials: op.initials, color: op.color,
            closed: [7, 4, 1][i] || 0, avgTime: "—",
          };
        }),
        top_questions: [
          { q: "Подключение", count: 46 },
          { q: "Оплата и продление", count: 38 },
          { q: "Низкая скорость", count: 29 },
          { q: "Настройка на iOS", count: 21 },
          { q: "Настройка на Android", count: 18 },
          { q: "Ключ не работает", count: 14 },
          { q: "Смена сервера", count: 11 },
          { q: "Возврат средств", count: 7 },
        ],
      };
    }

    function buildTimeStats(days) {
      return {
        period_days: days,
        team: { first_response_avg: 94, next_response_avg: 51, close_time_avg: 8640 },
        operators: operators.map(function (op, i) {
          return {
            id: op.id, name: op.name, online: op.online, initials: op.initials,
            color: op.color, role: op.role, tg: op.tg,
            first_response_avg: [76, 102, 143][i] || null,
            next_response_avg: [44, 57, 81][i] || null,
            dialogs_count: [124, 98, 31][i] || 0,
          };
        }),
      };
    }

    return {
      operators: operators,
      dialogs: dialogs,
      messages: messages,
      templates: templates,
      kbArticles: kbArticles,
      servers: servers,
      settings: settings,
      buildStats: buildStats,
      buildTimeStats: buildTimeStats,
      fmtTime: fmtTime,
      fmtDate: fmtDate,
      demoPhoto: DEMO_PHOTO,
      makeMsg: msg,
    };
  };
})();
