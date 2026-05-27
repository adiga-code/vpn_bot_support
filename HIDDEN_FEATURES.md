# Скрытые функции (v1 → доп. опции)

Временно убраны из интерфейса. Код не удалён — всё работает в бэкенде.

---

## 1. Вкладка «Серверы» (`servers.jsx`)

Мониторинг VPN-серверов (статус, нагрузка, пинг, uptime).

**Как вернуть** → `app/static/index.html`, функция `TopBar`:
- В массив `screens` добавить: `{ id: "servers", label: "Серверы", icon: "server" }`
- В `breadcrumbMap` добавить: `servers: ["Серверы VPN"]`
- В рендере `<main>` добавить: `{screen === "servers" && <ServersScreen />}`

---

## 2. Биллинг в панели пользователя (`dialogs.jsx`)

Кнопки действий прямо из диалога: продлить подписку, докупить трафик, сбросить ключ.

**Как вернуть** → `app/static/dialogs.jsx`, компонент `UserInfoPanel`:
- Вернуть состояния: `billingOpen`, `months`, `gb`
- Вернуть функции: `billingAction()`, `toggleBilling()`
- Добавить секцию `{/* Billing */}` после секции пользователя (была до секции «История»)
- Убрать строку «Последний платёж» из блока пользователя (она была только в биллинге)

---

## 3. Статистика — расширенная (`statistics.jsx`)

Убрано из `StatisticsScreen`:
- **Переключатель периода** (Сегодня / 7д / 14д / 30д)
- **График по дням** (`LineChart`)
- **Тепловая карта по часам** (`HeatmapChart`)
- **Топ-10 частых вопросов** (`TopQuestionsChart`)
- **Колонки операторов**: «Закрыто» и «Ср. время» (таблица стала только онлайн/офлайн)
- **Карточки**: «Среднее время ответа» и «ИИ решил без оператора»

**Как вернуть** → заменить `StatisticsScreen` на версию из git-истории:
```
git show HEAD~2:app/static/statistics.jsx
```

---

## 4. Настройки → «Расписание» (`settings.jsx`)

Рабочие часы по дням недели. Связано с фичей «Кнопка вызова оператора» (вне рабочего времени бот сообщает о режиме работы).

**Как вернуть** → `app/static/settings.jsx`, компонент `SettingsScreen`:
- В `allSections` добавить: `{ id: "schedule", label: "Расписание", icon: "clock", adminOnly: true }`
- В рендере добавить: `{section === "schedule" && <ScheduleSection showToast={showToast} />}`

---

## 5. Настройки → ИИ: «Передавать при низкой уверенности» (`settings.jsx`)

Авто-вызов оператора когда ИИ не уверен в ответе.

**Как вернуть** → `app/static/settings.jsx`, компонент `AISection`, в блок `div` с настройками добавить:
```jsx
<SettingsRow
  title="Передавать при низкой уверенности"
  desc="Если ИИ не уверен — зовёт оператора"
  control={<Switch on={settings.handoff_enabled} onChange={() => setSettings((s) => ({ ...s, handoff_enabled: !s.handoff_enabled }))} />}
/>
```
Также вернуть хинт под промптом:
```jsx
{settings.handoff_enabled && (
  <div className="mt-2 flex items-start gap-2 text-xs text-[#6b7280] bg-[#4F8EF7]/5 border border-[#4F8EF7]/15 rounded-lg px-3 py-2">
    <span className="text-[#4F8EF7] mt-0.5 shrink-0">+</span>
    <span>К промпту автоматически добавляется инструкция про <span className="font-mono text-[#7BA8F9]">[HANDOFF]</span> — ИИ будет знать когда звать оператора. В редакторе не отображается.</span>
  </div>
)}
```

---

## 6. Настройки → ИИ: «Классификация вопросов» (`settings.jsx`)

Автоматическое определение темы сообщений через OpenAI. Питает «Топ-10 частых вопросов» в Статистике.

**Как вернуть** → `app/static/settings.jsx`, компонент `AISection`:
```jsx
<SettingsRow
  title="Классификация вопросов"
  desc="Автоматически определять тему каждого сообщения через OpenAI. Требует OPENAI_API_KEY."
  control={<Switch on={!!settings.classification_enabled} onChange={() => setSettings((s) => ({ ...s, classification_enabled: !s.classification_enabled }))} />}
/>
```

---

## 7. Настройки → Профиль: уведомление «Сервер недоступен» (`settings.jsx`)

Telegram-уведомление оператору при падении VPN-сервера. Связано с вкладкой «Серверы».

**Как вернуть** → `app/static/settings.jsx`, компонент `ProfileSection`, в массив уведомлений добавить:
```js
["server_down", "Сервер недоступен", "VPN-сервер перестал отвечать"],
```
