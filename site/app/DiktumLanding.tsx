"use client";

/* eslint-disable @next/next/no-img-element */

import { FormEvent, useMemo, useState } from "react";

type Lang = "ru" | "en";
type SubmitState = "idle" | "submitting" | "success" | "error";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const copy = {
  ru: {
    brand: "Диктум",
    nav: ["Как работает", "Приватность", "Установка"],
    navDownload: "Скачать",
    heroEyebrow: "Локально на Mac · Точно на русском · Альфа",
    heroTitle: "Длинные записи — в точные протоколы обсуждений.",
    heroText:
      "Точное распознавание русской речи с пунктуацией, разделение реплик по спикерам и готовый протокол. На вашем Mac, без облака, без подписки, без установки или работы через Terminal.",
    heroCta: "Скачать для Mac",
    heroSecondary: "Как это работает",
    heroNote: "Бесплатно на условии обратной связи · Apple Silicon · .m4a .mp3 .wav .mp4",
    cardLong: "Длинная запись · обработка по частям",
    speakers: ["Анна", "Игорь", "Ведущая"],
    lines: [
      "Давайте начнем с целей модуля и зафиксируем ожидания группы.",
      "У меня вопрос по практике: где будем разбирать кейсы?",
      "Кейсы во второй день, сейчас — теория и разбор примеров.",
    ],
    cardCaption: "Реплики разложены по спикерам, с таймкодами и пунктуацией",
    stats: [
      ["2–3 мин", "на час записи на M4/M5"],
      ["≈30×", "быстрее длины записи"],
      ["0", "аудиофайлов в облаке"],
    ],
    storyEyebrow: "Зачем это",
    storyTitle: "Не просто текст — точный протокол, с которым можно работать",
    storyText: [
      "Интервью, многочасовые обучения, голосовые заметки. Важно не просто получить текст, а получить точный протокол: с пунктуацией, разделением по спикерам и таймкодами.",
      "Диктум работает на ресурсах самого Mac и использует локальные модели, сильные именно на русском. Поэтому инструмент остается понятным для людей, которые не хотят жить в Terminal.",
    ],
    storyQuote:
      "По нашим тестам на русских записях точность и пунктуация заметно лучше, чем у популярного Whisper.",
    howEyebrow: "Как это работает",
    howTitle: "Четыре шага от записи к протоколу",
    how: [
      ["Положите записи", "Перетащите аудио в папку Inbox или загрузите через локальный браузер. Диктофон, iPhone, петличка."],
      ["Распознавание на Mac", "Речь расшифровывается локально, моделью, сильной на русском. Часы аудио обрабатываются по частям."],
      ["Разделение по спикерам", "Прослушайте семплы голосов, впишите имена, и реплики разложатся по говорящим."],
      ["Готовый протокол", "Откройте результат кликом и выгрузите чистый Markdown или TXT для людей и AI-агентов."],
    ],
    privacyEyebrow: "Приватность",
    privacyTitle: "Ваши записи остаются у вас",
    privacyText:
      "Аудио, промежуточные файлы и готовые тексты хранятся на вашем компьютере. Ничего не уходит в облако без вашего явного выбора.",
    privacy: [
      ["Локально по умолчанию", "Обработка идет на вашем Mac."],
      ["Без облака", "Аудио не отправляется на чужие серверы."],
      ["Без подписки", "Построен на бесплатных компонентах."],
    ],
    whomEyebrow: "Кому это нужно",
    whomTitle: "Для тех, кто работает с записями людей",
    whom: [
      "Консультанты",
      "Методологи образовательных программ",
      "Исследователи и интервьюеры",
      "Коучи и психологи",
      "Организаторы обучений и вебинаров",
      "Те, кто кормит расшифровками AI-агентов",
    ],
    featuresEyebrow: "Что внутри",
    featuresTitle: "Сделано для повторяемой работы с файлами",
    features: [
      ["Точность и пунктуация", "Точный результат на русском, со знаками препинания."],
      ["Длинные записи", "Часы аудио, без практического лимита."],
      ["Русская речь", "Модели, сильные именно на русском."],
      ["Спикеры", "Разделение и переименование голосов."],
      ["Скорость", "Час записи за 2–3 минуты на M4/M5."],
      ["Очередь", "Пакетная обработка папок."],
      ["Экспорт", "Markdown и TXT для людей и агентов."],
      ["Локально", "Все на вашем Mac, без облака."],
    ],
    installEyebrow: "Установка и требования",
    installTitle: "Маленькая загрузка — локальная мощь",
    installSteps: [
      "Скачайте и распакуйте ZIP",
      "Откройте START_HERE",
      "Настройте один раз",
      "Запустите локальный web UI",
    ],
    installCards: [
      ["Как это устроено", "Дистрибутив маленький. При первой настройке программа скачивает нужные AI-модели, поэтому потребуется интернет. После установки папка занимает примерно 1.5-2 ГБ."],
      ["Скорость", "На MacBook с M4 или M5 и 32 ГБ час записи обрабатывается примерно за 2-3 минуты: около 30 раз быстрее длины записи."],
      ["Что нужно", "Mac на Apple Silicon, 16 ГБ RAM, 20-30 ГБ свободного места и интернет при первой настройке."],
    ],
    alphaTitle: "Это альфа-версия",
    alphaText:
      "Диктум распространяется бесплатно на условии обратной связи. Качество не идеально и продолжает улучшаться. Это не приложение из App Store — вы запускаете локальную папку.",
    ctaEyebrow: "Альфа-доступ",
    ctaTitle: "Попробуйте Диктум на своих записях",
    ctaText:
      "Скачивайте бесплатно, а взамен поделитесь обратной связью. Новые версии и заметки о развитии будут в Telegram.",
    ctaButton: "Скачать и попробовать",
    tg: "Telegram-канал",
    github: "GitHub",
    footerAuthor: "Личный проект методолога изменений Андрея Майера",
    footerFeedback: "Буду рад обратной связи и идеям развития через Тг-канал проекта.",
    modalTitle: "Скачать Диктум",
    modalText: "Укажите email. Мы сохраним заявку, а скачивание ZIP начнется сразу после отправки формы.",
    placeholder: "you@email.com",
    modalButton: "Получить ZIP",
    modalBusy: "Сохраняем...",
    modalPrivacy: "Email нужен для ссылки, обновлений и обратной связи. Аудио и тексты не загружаются.",
    emailError: "Проверьте адрес электронной почты.",
    submitError: "Не получилось сохранить email. Попробуйте еще раз.",
    okTitle: "Готово, скачивание начинается",
    okText: "Если браузер не начал загрузку автоматически, нажмите кнопку ниже.",
    okButton: "Скачать ZIP для Mac",
    okNote: "После распаковки откройте START_HERE внутри папки.",
  },
  en: {
    brand: "Diktum",
    nav: ["How it works", "Privacy", "Install"],
    navDownload: "Download",
    heroEyebrow: "Local on Mac · Accurate in Russian · Alpha",
    heroTitle: "Long recordings into accurate discussion protocols.",
    heroText:
      "Accurate Russian speech recognition with punctuation, speaker separation, and a ready protocol. On your Mac, with no cloud, no subscription, and no Terminal install or Terminal workflow.",
    heroCta: "Download for Mac",
    heroSecondary: "How it works",
    heroNote: "Free in exchange for feedback · Apple Silicon · .m4a .mp3 .wav .mp4",
    cardLong: "Long recording · processed in chunks",
    speakers: ["Anna", "Igor", "Host"],
    lines: [
      "Let's start with the module goals and capture the group's expectations.",
      "I have a question about practice: where will we review the cases?",
      "Cases are on day two; for now, theory and worked examples.",
    ],
    cardCaption: "Lines split by speaker, with timecodes and punctuation",
    stats: [
      ["2-3 min", "per hour of audio on M4/M5"],
      ["about 30x", "faster than real time"],
      ["0", "audio files in the cloud"],
    ],
    storyEyebrow: "Why",
    storyTitle: "Not just text, but an accurate protocol you can work with",
    storyText: [
      "Interviews, multi-hour trainings, voice notes. What matters is not raw text, but a useful protocol with punctuation, speakers, and timecodes.",
      "Diktum runs on your Mac and uses local models that are strong in Russian, so the tool stays approachable for people who do not want to live in Terminal.",
    ],
    storyQuote:
      "In our tests on Russian recordings, accuracy and punctuation are noticeably better than the popular Whisper.",
    howEyebrow: "How it works",
    howTitle: "Four steps from recording to protocol",
    how: [
      ["Add recordings", "Drop audio into Inbox or upload via the local browser. Voice recorder, iPhone, lavalier."],
      ["Recognition on Mac", "Speech is transcribed locally with a model strong in Russian. Hours of audio are processed in chunks."],
      ["Separate speakers", "Listen to voice samples, type names, and lines are assigned to speakers."],
      ["Ready protocol", "Open the result with one click and export clean Markdown or TXT for people and AI agents."],
    ],
    privacyEyebrow: "Privacy",
    privacyTitle: "Your recordings stay with you",
    privacyText:
      "Audio, intermediate files, and finished texts stay on your computer. Nothing leaves for the cloud without your explicit choice.",
    privacy: [
      ["Local by default", "Processing runs on your Mac."],
      ["No cloud", "Audio is not sent to someone else's servers."],
      ["No subscription", "Built on free components."],
    ],
    whomEyebrow: "Who it is for",
    whomTitle: "For people who work with recordings of people",
    whom: [
      "Consultants",
      "Learning designers",
      "Researchers and interviewers",
      "Coaches and therapists",
      "Training and webinar hosts",
      "People feeding transcripts to AI agents",
    ],
    featuresEyebrow: "What's inside",
    featuresTitle: "Built for repeatable work with files",
    features: [
      ["Accuracy and punctuation", "Accurate Russian output, with punctuation."],
      ["Long recordings", "Hours of audio, with no practical limit."],
      ["Russian speech", "Models strong specifically in Russian."],
      ["Speakers", "Separate and rename voices."],
      ["Speed", "An hour in 2-3 minutes on M4/M5."],
      ["Queue", "Batch-process folders."],
      ["Export", "Markdown and TXT for people and agents."],
      ["Local", "Everything on your Mac, no cloud."],
    ],
    installEyebrow: "Install and requirements",
    installTitle: "Tiny download, local power",
    installSteps: [
      "Download and unzip",
      "Open START_HERE",
      "Set up once",
      "Launch the local web UI",
    ],
    installCards: [
      ["How it works", "The distribution is small. On first setup the app downloads the required AI models, so internet is needed. After setup the folder takes about 1.5-2 GB."],
      ["Speed", "On a MacBook with M4 or M5 and 32 GB, an hour of audio is processed in about 2-3 minutes: around 30 times faster than real time."],
      ["Requirements", "Apple Silicon Mac, 16 GB RAM, 20-30 GB of free space, and internet for first setup."],
    ],
    alphaTitle: "This is an alpha",
    alphaText:
      "Diktum is free in exchange for feedback. Quality is not perfect and keeps improving. It is not an App Store app: you run a local folder.",
    ctaEyebrow: "Alpha access",
    ctaTitle: "Try Diktum on your own recordings",
    ctaText:
      "Download for free and share feedback in return. New versions and development notes will be posted on Telegram.",
    ctaButton: "Download and try",
    tg: "Telegram channel",
    github: "GitHub",
    footerAuthor: "A personal project by change methodologist Andrey Mayer",
    footerFeedback: "Feedback and development ideas are welcome via the project Telegram channel.",
    modalTitle: "Download Diktum",
    modalText: "Enter your email. We will save the request, and the ZIP download starts right after the form is sent.",
    placeholder: "you@email.com",
    modalButton: "Get the ZIP",
    modalBusy: "Saving...",
    modalPrivacy: "Email is used for the link, updates, and feedback. Audio and transcripts are not uploaded.",
    emailError: "Please check the email address.",
    submitError: "Could not save the email. Please try again.",
    okTitle: "Done, download is starting",
    okText: "If your browser did not start downloading automatically, use the button below.",
    okButton: "Download ZIP for Mac",
    okNote: "After unzipping, open START_HERE inside the folder.",
  },
} as const;

export default function DiktumLanding() {
  const [lang, setLang] = useState<Lang>("ru");
  const [modalOpen, setModalOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [state, setState] = useState<SubmitState>("idle");
  const [error, setError] = useState("");
  const [downloadUrl, setDownloadUrl] = useState("");
  const t = copy[lang];

  const rows = useMemo(
    () => [
      { time: "00:14", speaker: t.speakers[0], text: t.lines[0], tone: "green" },
      { time: "00:31", speaker: t.speakers[1], text: t.lines[1], tone: "blue" },
      { time: "00:48", speaker: t.speakers[2], text: t.lines[2], tone: "rust" },
    ],
    [t]
  );

  function openGate() {
    setModalOpen(true);
    setError("");
  }

  function closeGate() {
    if (state === "submitting") return;
    setModalOpen(false);
  }

  async function submitEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedEmail = email.trim().toLowerCase();

    if (!EMAIL_RE.test(normalizedEmail)) {
      setError(t.emailError);
      setState("error");
      return;
    }

    setState("submitting");
    setError("");

    try {
      const response = await fetch("/api/leads", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          email: normalizedEmail,
          locale: lang,
          source: "landing-modal",
          company,
        }),
      });
      const payload = (await response.json()) as {
        downloadUrl?: string;
        error?: string;
      };

      if (!response.ok || !payload.downloadUrl) {
        throw new Error(payload.error || "lead submit failed");
      }

      try {
        localStorage.setItem("diktum_email", normalizedEmail);
      } catch {
        // Browser storage is only a convenience; D1 is the source of truth.
      }

      setDownloadUrl(payload.downloadUrl);
      setState("success");
      window.setTimeout(() => {
        window.location.assign(payload.downloadUrl as string);
      }, 650);
    } catch {
      setError(t.submitError);
      setState("error");
    }
  }

  return (
    <main className="site-shell" data-lang={lang}>
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="#top" aria-label={t.brand}>
            <span className="brand-mark">{lang === "ru" ? "Д" : "D"}</span>
            <span>{t.brand}</span>
          </a>
          <nav className="nav-links" aria-label="Main navigation">
            <a href="#how">{t.nav[0]}</a>
            <a href="#privacy">{t.nav[1]}</a>
            <a href="#install">{t.nav[2]}</a>
          </nav>
          <div className="topbar-actions">
            <div className="lang-switch" aria-label="Language">
              <button type="button" className={lang === "ru" ? "active" : ""} onClick={() => setLang("ru")}>
                РУС
              </button>
              <button type="button" className={lang === "en" ? "active" : ""} onClick={() => setLang("en")}>
                ENG
              </button>
            </div>
            <button type="button" className="button button-dark button-small" onClick={openGate}>
              {t.navDownload}
            </button>
          </div>
        </div>
      </header>

      <section id="top" className="section hero-section">
        <div className="hero-grid">
          <div className="hero-copy">
            <p className="eyebrow">{t.heroEyebrow}</p>
            <h1>{t.heroTitle}</h1>
            <p className="lead">{t.heroText}</p>
            <div className="hero-actions">
              <button type="button" className="button button-primary" onClick={openGate}>
                {t.heroCta}
              </button>
              <a className="text-link" href="#how">
                {t.heroSecondary}
              </a>
            </div>
            <p className="hero-note">{t.heroNote}</p>
          </div>

          <div className="transcript-panel" aria-label="Transcript preview">
            <div className="audio-row">
              <div className="play-dot" aria-hidden="true" />
              <div className="audio-main">
                <div className="audio-title">Обучение · день 1.m4a</div>
                <div className="progress">
                  <span />
                </div>
              </div>
              <span className="audio-time">5:02:11</span>
            </div>
            <p className="panel-kicker">{t.cardLong}</p>
            <div className="speaker-lines">
              {rows.map((row) => (
                <div className="speaker-row" key={row.time}>
                  <span className="timestamp">{row.time}</span>
                  <div>
                    <span className={`speaker-label ${row.tone}`}>
                      <i />
                      {row.speaker}
                    </span>
                    <p>{row.text}</p>
                  </div>
                </div>
              ))}
            </div>
            <p className="panel-caption">{t.cardCaption}</p>
          </div>
        </div>
      </section>

      <section className="stats-band" aria-label="Product stats">
        <div className="stats-grid">
          {t.stats.map(([value, label]) => (
            <div className="stat" key={label}>
              <strong>{value}</strong>
              <span>{label}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="story-section">
        <div className="section">
          <p className="eyebrow">{t.storyEyebrow}</p>
          <h2>{t.storyTitle}</h2>
          <div className="story-columns">
            {t.storyText.map((item) => (
              <p key={item}>{item}</p>
            ))}
          </div>
          <blockquote>{t.storyQuote}</blockquote>
        </div>
      </section>

      <section id="how" className="section">
        <p className="eyebrow">{t.howEyebrow}</p>
        <h2>{t.howTitle}</h2>
        <div className="steps-grid">
          {t.how.map(([title, text], index) => (
            <article className="plain-step" key={title}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <h3>{title}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="privacy" className="privacy-band">
        <div className="section">
          <p className="eyebrow">{t.privacyEyebrow}</p>
          <h2>{t.privacyTitle}</h2>
          <p className="privacy-lead">{t.privacyText}</p>
          <div className="privacy-grid">
            {t.privacy.map(([title, text]) => (
              <article key={title}>
                <h3>{title}</h3>
                <p>{text}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section">
        <p className="eyebrow">{t.whomEyebrow}</p>
        <h2>{t.whomTitle}</h2>
        <div className="audience-list">
          {t.whom.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      </section>

      <section className="features-band">
        <div className="section">
          <p className="eyebrow">{t.featuresEyebrow}</p>
          <h2>{t.featuresTitle}</h2>
          <div className="feature-grid">
            {t.features.map(([title, text]) => (
              <article key={title}>
                <h3>{title}</h3>
                <p>{text}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="install" className="section">
        <p className="eyebrow">{t.installEyebrow}</p>
        <h2>{t.installTitle}</h2>
        <div className="install-steps">
          {t.installSteps.map((step, index) => (
            <article key={step}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <p>{step}</p>
            </article>
          ))}
        </div>
        <div className="product-visuals">
          <img src="/screenshots/install.jpg" alt="Диктум setup screen" />
          <img src="/screenshots/modal.jpg" alt="Диктум speaker naming screen" />
        </div>
        <div className="install-grid">
          {t.installCards.map(([title, text]) => (
            <article key={title}>
              <h3>{title}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
        <aside className="alpha-note">
          <h3>{t.alphaTitle}</h3>
          <p>{t.alphaText}</p>
        </aside>
      </section>

      <section className="download-band">
        <div>
          <p className="eyebrow">{t.ctaEyebrow}</p>
          <h2>{t.ctaTitle}</h2>
          <p>{t.ctaText}</p>
          <button type="button" className="button button-light" onClick={openGate}>
            {t.ctaButton}
          </button>
          <div className="download-links">
            <a href="https://t.me/+ByvsbIefhtkyZGIy" target="_blank" rel="noreferrer">
              {t.tg}
            </a>
            <a href="https://github.com/biztrackru/diktum" target="_blank" rel="noreferrer">
              {t.github}
            </a>
          </div>
        </div>
      </section>

      <footer className="footer">
        <a className="footer-brand" href="#top" aria-label={t.brand}>
          <span className="footer-brand-mark">{lang === "ru" ? "Д" : "D"}</span>
          <span>{t.brand}</span>
        </a>
        <p>
          {t.footerAuthor}{" "}
          <a href="https://biztrack.ru/am" target="_blank" rel="noreferrer">
            biztrack.ru/am
          </a>
          . {t.footerFeedback}{" "}
          <a href="https://t.me/+ByvsbIefhtkyZGIy" target="_blank" rel="noreferrer">
            Telegram
          </a>
          .
        </p>
        <div>
          <a href="https://t.me/+ByvsbIefhtkyZGIy" target="_blank" rel="noreferrer">
            Telegram
          </a>
          <a href="https://github.com/biztrackru/diktum" target="_blank" rel="noreferrer">
            GitHub
          </a>
          <span>2026</span>
        </div>
      </footer>

      {modalOpen ? (
        <div className="modal-backdrop" onClick={closeGate} role="presentation">
          <div className="modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
            <button type="button" className="modal-close" onClick={closeGate} aria-label="Close">
              ×
            </button>
            {state === "success" ? (
              <div className="success-state">
                <div className="success-mark">✓</div>
                <h3>{t.okTitle}</h3>
                <p>{t.okText}</p>
                <a className="button button-dark" href={downloadUrl}>
                  {t.okButton}
                </a>
                <p className="tiny-note">{t.okNote}</p>
              </div>
            ) : (
              <form onSubmit={submitEmail}>
                <h3>{t.modalTitle}</h3>
                <p>{t.modalText}</p>
                <label className="sr-only" htmlFor="lead-email">
                  Email
                </label>
                <input
                  id="lead-email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder={t.placeholder}
                  required
                />
                <input
                  className="company-field"
                  tabIndex={-1}
                  autoComplete="off"
                  value={company}
                  onChange={(event) => setCompany(event.target.value)}
                  aria-hidden="true"
                />
                {error ? <p className="form-error">{error}</p> : null}
                <button className="button button-primary modal-submit" type="submit" disabled={state === "submitting"}>
                  {state === "submitting" ? t.modalBusy : t.modalButton}
                </button>
                <p className="tiny-note">{t.modalPrivacy}</p>
              </form>
            )}
          </div>
        </div>
      ) : null}
    </main>
  );
}
