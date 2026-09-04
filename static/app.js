import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
  onAuthStateChanged,
} from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";

const copy = {
  en: {
    languageName: "English",
    loading: "Loading your private space...",
    welcomeTitle: "Is your work following your contract?",
    welcomeBody: "Talk to us about what is happening. We will help you see what may not match and who you can call.",
    welcomeStepOne: "Talk to us in your own words",
    welcomeStepTwo: "See what may not match",
    welcomeStepThree: "Find the right person to call",
    signIn: "Sign in with Google",
    languageLabel: "Language",
    homeLabel: "Gabay OFW home",
    profile: "Profile",
    signOut: "Sign out",
    disclaimerTitle: "Before you begin",
    disclaimerBody: "Gabay OFW offers practical guidance and connects you with official support.",
    notLegalTitle: "Not legal advice.",
    notLegalBody: "Findings identify possible conflicts with standard rules. Verify them with DMW, OWWA, or a lawyer.",
    notEmergencyTitle: "Not an emergency service.",
    notEmergencyBody: "If you are in immediate danger, contact local emergency services or the nearest Philippine Embassy.",
    understand: "I understand",
    greeting: (name) => `${name}, what do you need?`,
    conversationsHeading: "Conversations",
    conversationsNavigation: "Conversations",
    thisConversation: "Your conversation",
    backHome: "Back",
    profileTitle: "Your profile",
    profileKicker: "Optional and private",
    profileBody: "Optional details help keep future conversations relevant. Any destination country is accepted.",
    countryOptional: "Destination country (optional)",
    occupationOptional: "Occupation (optional)",
    countryPlaceholder: "Any country",
    occupationPlaceholder: "Example: Domestic worker",
    saveProfile: "Save profile",
    profileSaved: "Profile saved on this device.",
    deleteData: "Delete local profile",
    localProfileDeleted: "Local profile deleted.",
    wipeTitle: "Delete everything",
    wipeBody: "One tap permanently deletes your conversations and case from Gabay OFW. Nothing is kept anywhere, and it cannot be undone.",
    wipeEverything: "Delete everything now",
    wipeDone: "Everything was deleted.",
    wipeFailed: "Could not delete right now. Try again.",
    signInFailed: (message) => `Sign-in failed: ${message}`,
    notConfigured: "Firebase sign-in is not configured yet.",
    chatBody: "Any language, any order. Office names like DOLE-SEnA, MWO, and OWWA stay as they are so you can match them against a sign or a website.",
    chatPlaceholder: "Type in any language...",
    chatSend: "Send",
    chatOpenersLabel: "You can start with one of these:",
    chatError: "Something went wrong on our side. Nothing you wrote was lost - please send it again.",
    caseTitle: "What Gabay has understood",
    caseEmpty: "Facts you share will appear here so you never have to repeat yourself.",
    caseFlagsTitle: "Safety notes",
    caseConflictPrompt: "You and a document don't agree. Which is right?",
    caseCorrectLabel: "Correct this",
    caseConfirm: "Confirm",
    caseCancel: "Cancel",
    caseSourceUser: "you confirmed",
    caseSourceExtraction: "you said",
    caseSourceDocument: "a document said",
    caseSourceDebunker: "checked",
    caseUpdateFailed: "Could not save your correction. Try again.",
    emergencyButton: "EMERGENCY",
    emergencyFailed: "Could not reach the emergency card right now. Try again.",
    markSafeButton: "I'm safe now",
    markSafeConfirmTitle: "Confirm you are safe",
    markSafeConfirmBody: "This clears the emergency alert on your account, but keeps what you already disclosed on record. Only confirm if you can tap freely right now and no one is watching your phone.",
    markSafeConfirm: "Yes, I am safe",
    markSafeCancel: "Cancel",
    markSafeDone: "Marked safe. The emergency alert is cleared.",
    markSafeFailed: "Could not confirm right now. Try again.",
  },
  tl: {
    languageName: "Filipino",
    loading: "Binubuksan ang iyong pribadong espasyo...",
    welcomeTitle: "Sinusunod ba ng trabaho mo ang kontrata?",
    welcomeBody: "Kuwento mo sa amin ang nangyayari. Tutulungan ka naming makita ang posibleng hindi tugma at kung sino ang puwedeng tawagan.",
    welcomeStepOne: "Magkuwento sa sarili mong salita",
    welcomeStepTwo: "Tingnan ang posibleng hindi tugma",
    welcomeStepThree: "Hanapin ang tamang taong tatawagan",
    signIn: "Mag-sign in gamit ang Google",
    languageLabel: "Wika",
    homeLabel: "Home ng Gabay OFW",
    profile: "Profile",
    signOut: "Mag-sign out",
    disclaimerTitle: "Bago magsimula",
    disclaimerBody: "Nagbibigay ang Gabay OFW ng praktikal na gabay at koneksiyon sa opisyal na suporta.",
    notLegalTitle: "Hindi legal na payo.",
    notLegalBody: "Posibleng paglabag lamang ang findings. I-verify sa DMW, OWWA, o abogado.",
    notEmergencyTitle: "Hindi emergency service.",
    notEmergencyBody: "Kung may agarang panganib, tumawag sa local emergency services o pinakamalapit na Philippine Embassy.",
    understand: "Naiintindihan ko",
    greeting: (name) => `${name}, ano ang kailangan mo?`,
    conversationsHeading: "Mga Usapan",
    conversationsNavigation: "Mga Usapan",
    thisConversation: "Ang usapan mo",
    backHome: "Bumalik",
    profileTitle: "Iyong profile",
    profileKicker: "Opsiyonal at pribado",
    profileBody: "Opsiyonal ang detalye at makakatulong sa susunod na usapan. Tinatanggap ang anumang destination country.",
    countryOptional: "Destination country (opsiyonal)",
    occupationOptional: "Trabaho (opsiyonal)",
    countryPlaceholder: "Anumang bansa",
    occupationPlaceholder: "Halimbawa: Domestic worker",
    saveProfile: "I-save ang profile",
    profileSaved: "Na-save ang profile sa device na ito.",
    deleteData: "Burahin ang local profile",
    localProfileDeleted: "Nabura ang local profile.",
    wipeTitle: "Burahin ang lahat",
    wipeBody: "Isang tap ang permanenteng bubura sa lahat ng usapan at case mo sa Gabay OFW. Walang matitira kahit saan, at hindi na ito maibabalik.",
    wipeEverything: "Burahin lahat ngayon",
    wipeDone: "Nabura na ang lahat.",
    wipeFailed: "Hindi nabura ngayon. Subukan muli.",
    signInFailed: (message) => `Hindi nagtagumpay ang sign-in: ${message}`,
    notConfigured: "Hindi pa naka-configure ang Firebase sign-in.",
    chatBody: "Kahit anong wika, kahit anong ayos. Mananatili ang mga pangalan ng opisina tulad ng DOLE-SEnA, MWO, at OWWA para maitugma mo sa karatula o website.",
    chatPlaceholder: "Mag-type sa kahit anong wika...",
    chatSend: "Ipadala",
    chatOpenersLabel: "Puwede kang magsimula sa isa sa mga ito:",
    chatError: "May nangyaring mali sa amin. Hindi nawala ang isinulat mo - pakisend ulit.",
    caseTitle: "Ang naiintindihan ni Gabay",
    caseEmpty: "Lalabas dito ang mga detalyeng ibinahagi mo para hindi mo na kailangang ulitin.",
    caseFlagsTitle: "Mga paalala sa kaligtasan",
    caseConflictPrompt: "Hindi magkatugma ang sinabi mo at ang isang dokumento. Alin ang tama?",
    caseCorrectLabel: "Itama ito",
    caseConfirm: "Kumpirmahin",
    caseCancel: "Kanselahin",
    caseSourceUser: "kinumpirma mo",
    caseSourceExtraction: "sinabi mo",
    caseSourceDocument: "sinabi ng dokumento",
    caseSourceDebunker: "na-check",
    caseUpdateFailed: "Hindi na-save ang pagtatama mo. Subukan muli.",
    emergencyButton: "EMERGENCY",
    emergencyFailed: "Hindi naabot ang emergency card ngayon. Subukan muli.",
    markSafeButton: "Ligtas na ako ngayon",
    markSafeConfirmTitle: "Kumpirmahin na ligtas ka na",
    markSafeConfirmBody: "Aalisin nito ang emergency alert sa account mo, pero mananatiling nakatala ang naibahagi mo na. Kumpirma lamang kung malaya kang makaka-tap ngayon at walang nagbabantay sa phone mo.",
    markSafeConfirm: "Oo, ligtas na ako",
    markSafeCancel: "Kanselahin",
    markSafeDone: "Na-mark na ligtas. Naalis na ang emergency alert.",
    markSafeFailed: "Hindi na-kumpirma ngayon. Subukan muli.",
  },
  ceb: {
    languageName: "Bisaya",
    loading: "Giablihan ang imong pribadong luna...",
    welcomeTitle: "Nagsunod ba ang imong trabaho sa kontrata?",
    welcomeBody: "Isulti kanamo unsay nahitabo. Tabangan ka namo nga makita ang posibleng dili motakdo ug kinsa ang tawagan.",
    welcomeStepOne: "Isulti sa imong kaugalingong mga pulong",
    welcomeStepTwo: "Tan-awa ang posibleng dili motakdo",
    welcomeStepThree: "Pangitaa ang hustong tawagan",
    signIn: "Padayon gamit ang Google",
    languageLabel: "Pinulongan",
    homeLabel: "Home sa Gabay OFW",
    profile: "Profile",
    signOut: "Sign out",
    disclaimerTitle: "Sa dili pa magsugod",
    disclaimerBody: "Naghatag ang Gabay OFW og praktikal nga giya ug koneksiyon sa opisyal nga suporta.",
    notLegalTitle: "Dili legal nga tambag.",
    notLegalBody: "Posibleng conflict lang ang findings. I-verify sa DMW, OWWA, o abogado.",
    notEmergencyTitle: "Dili emergency service.",
    notEmergencyBody: "Kung naa sa diha-diha nga peligro, kontaka ang local emergency services o duol nga Philippine Embassy.",
    understand: "Nasabtan nako",
    greeting: (name) => `${name}, unsay imong kinahanglan?`,
    conversationsHeading: "Mga Panag-istorya",
    conversationsNavigation: "Mga Panag-istorya",
    thisConversation: "Imong panag-istorya",
    backHome: "Balik",
    profileTitle: "Imong profile",
    profileKicker: "Opsiyonal ug pribado",
    profileBody: "Opsiyonal ang detalye ug makatabang sa umaabot nga panag-istorya. Dawaton ang bisan unsang destination country.",
    countryOptional: "Destination country (opsiyonal)",
    occupationOptional: "Trabaho (opsiyonal)",
    countryPlaceholder: "Bisan unsang nasod",
    occupationPlaceholder: "Pananglitan: Domestic worker",
    saveProfile: "I-save ang profile",
    profileSaved: "Na-save ang profile sa device.",
    deleteData: "Papasa ang local profile",
    localProfileDeleted: "Napapas ang local profile.",
    wipeTitle: "Papasa ang tanan",
    wipeBody: "Usa ka tap mopapas sa tanan nimong panag-istorya ug case sa Gabay OFW. Walay mabilin bisan asa, ug dili na kini mabalik.",
    wipeEverything: "Papasa tanan karon",
    wipeDone: "Napapas na ang tanan.",
    wipeFailed: "Wala mapapas karon. Sulayi pag-usab.",
    signInFailed: (message) => `Wala molampos ang sign-in: ${message}`,
    notConfigured: "Wala pa ma-configure ang Firebase sign-in.",
    chatBody: "Bisan unsang pinulongan, bisan unsang han-ay. Magpabilin ang ngalan sa opisina sama sa DOLE-SEnA, MWO, ug OWWA aron imong ikatandi sa karatula o website.",
    chatPlaceholder: "Pag-type sa bisan unsang pinulongan...",
    chatSend: "Ipadala",
    chatOpenersLabel: "Mahimo kang magsugod sa usa niini:",
    chatError: "Adunay sayop sa among bahin. Wala mawala ang imong gisulat - palihug isend pag-usab.",
    caseTitle: "Ang nasabtan ni Gabay",
    caseEmpty: "Mogawas dinhi ang mga detalye nga imong gipaambit aron dili na nimo balikon.",
    caseFlagsTitle: "Mga pahinumdom sa kaluwasan",
    caseConflictPrompt: "Wala magtugma ang imong gisulti ug ang usa ka dokumento. Hain ang husto?",
    caseCorrectLabel: "Tul-ira kini",
    caseConfirm: "Kumpirma",
    caseCancel: "Kanselaha",
    caseSourceUser: "imong gikumpirma",
    caseSourceExtraction: "imong gisulti",
    caseSourceDocument: "gisulti sa dokumento",
    caseSourceDebunker: "gi-check",
    caseUpdateFailed: "Wala ma-save ang imong pagtul-id. Sulayi pag-usab.",
    emergencyButton: "EMERGENCY",
    emergencyFailed: "Wala naabot ang emergency card karon. Sulayi pag-usab.",
    markSafeButton: "Luwas na ko karon",
    markSafeConfirmTitle: "Kumpirmaha nga luwas ka na",
    markSafeConfirmBody: "Kini mopapas sa emergency alert sa imong account, apan magpabilin nga naka-record ang imong gipaambit na. Kumpirma lang kung gawasnon kang maka-tap karon ug walay nagbantay sa imong phone.",
    markSafeConfirm: "Oo, luwas na ko",
    markSafeCancel: "Kanselaha",
    markSafeDone: "Na-mark nga luwas. Napapas na ang emergency alert.",
    markSafeFailed: "Wala na-kumpirma karon. Sulayi pag-usab.",
  },
};

Object.assign(copy.en, {
  howItWorks: "How it works",
  privacyLink: "Your privacy",
  startNow: "Start now",
  signInBody: "Signing in keeps your conversation private to you. Nobody at your work is told.",
  trustFree: "Free",
  trustPrivate: "Private to you",
  trustNoAds: "No ads",
});

Object.assign(copy.tl, {
  howItWorks: "Paano ito gumagana",
  privacyLink: "Ang privacy mo",
  startNow: "Magsimula",
  signInBody: "Ang pag-sign in ay nagpapanatiling pribado sa iyo ang usapan. Walang sasabihin sa pinagtatrabahuhan mo.",
  trustFree: "Libre",
  trustPrivate: "Pribado sa iyo",
  trustNoAds: "Walang ads",
});

Object.assign(copy.ceb, {
  howItWorks: "Giunsa kini pagtrabaho",
  privacyLink: "Imong privacy",
  startNow: "Pagsugod",
  signInBody: "Ang pag-sign in magpabiling pribado sa imo ang panag-istorya. Walay sultihan sa imong trabaho.",
  trustFree: "Libre",
  trustPrivate: "Pribado sa imo",
  trustNoAds: "Walay ads",
});

const screen = document.getElementById("screen");
const screenLoading = document.getElementById("screen-loading");
const app = document.getElementById("signed-in");
const signedOut = document.getElementById("signed-out");
const authLoading = document.getElementById("auth-loading");
const dialog = document.getElementById("first-run-dialog");
const languageSelects = document.querySelectorAll(".language-select");
const markSafeButton = document.getElementById("mark-safe-button");
const markSafeDialog = document.getElementById("mark-safe-dialog");
const status = document.getElementById("status");

const supportedLanguages = Object.keys(copy);
const savedLanguage = localStorage.getItem("gabay-language");
let language = supportedLanguages.includes(savedLanguage) ? savedLanguage : "en";
// The rail's rewrite (issue #71) collapses the old dashboard+chat screens
// into one "home" screen — a single conversation, matching CONTEXT.md's
// Conversation vocabulary. "profile" is the only other screen left.
let currentScreen = "home";
let userName = "";
let userId = "";

// Paired bilingual openers: showing both languages work is the point
// ("Hindi ako nababayaran / I'm not being paid").
const CHAT_OPENERS = [
  "Hindi ako nababayaran / I'm not being paid",
  "Kinuha nila ang passport ko / They took my passport",
  "Gusto ko nang umuwi / I want to go home",
  "Natatakot ako sa amo ko / I'm afraid of my employer",
];
let chatSessionId = null;
let chatMessages = [];
let chatCase = {};
let chatBusy = false;
let editingCaseField = null;
// The Progress Trail (issue #75, ADR-0010): fixed, code-owned labels
// shown while a turn runs, never part of chatMessages/the transcript —
// cleared as soon as the "reply" line lands (see handleChatLine) and
// again defensively in sendChatTurn's finally block.
let chatTrail = [];

const t = (key, ...args) => {
  const value = copy[language][key] ?? copy.en[key];
  return typeof value === "function" ? value(...args) : value;
};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function applyCopy(root = document) {
  document.documentElement.lang = language;
  root.querySelectorAll("[data-copy]").forEach((element) => {
    element.textContent = t(element.dataset.copy);
  });
  root.querySelectorAll("[data-copy-aria]").forEach((element) => {
    element.setAttribute("aria-label", t(element.dataset.copyAria));
  });
}

function renderLanguageOptions() {
  languageSelects.forEach((select) => {
    select.replaceChildren(
      ...supportedLanguages.map((key) => {
        const option = document.createElement("option");
        option.value = key;
        option.textContent = copy[key].languageName;
        option.selected = key === language;
        return option;
      }),
    );
  });
}

function flowNav(label) {
  return `<nav class="flow-nav" aria-label="${escapeHtml(label)}">
    <button class="back-button" type="button" data-action="home">${t("backHome")}</button>
    <span class="step-label">${label}</span>
  </nav>`;
}

function profileTemplate() {
  const profile = JSON.parse(localStorage.getItem(`gabay-profile:${userId}`) || "{}");
  return `<section class="flow-shell profile-shell">
    ${flowNav(t("profile"))}
    <div class="profile-layout">
      <header class="profile-intro">
        <p class="eyebrow">${t("profileKicker")}</p>
        <h1>${t("profileTitle")}</h1>
        <p>${t("profileBody")}</p>
      </header>
      <form class="profile-form" data-form="profile">
      <h2 class="profile-form-title">${t("profile")}</h2>
      <div class="field">
        <label for="profile-country">${t("countryOptional")}</label>
        <input id="profile-country" name="country" value="${escapeHtml(profile.country || "")}" placeholder="${escapeHtml(t("countryPlaceholder"))}">
      </div>
      <div class="field">
        <label for="profile-occupation">${t("occupationOptional")}</label>
        <input id="profile-occupation" name="occupation" value="${escapeHtml(profile.occupation || "")}" placeholder="${escapeHtml(t("occupationPlaceholder"))}">
      </div>
      <div class="button-row">
        <button class="button ink-button" type="submit">${t("saveProfile")}</button>
        <button class="button" type="button" data-action="delete-profile">${t("deleteData")}</button>
      </div>
      </form>
      <section class="profile-form wipe-zone">
        <h2 class="profile-form-title">${t("wipeTitle")}</h2>
        <p>${t("wipeBody")}</p>
        <button class="button urgent-button" type="button" data-action="panic-wipe">${t("wipeEverything")}</button>
      </section>
    </div>
  </section>`;
}

function contactCardHtml(card) {
  const contacts = (card.contacts || [])
    .map((contact) => {
      const phone = escapeHtml(contact.phone || "");
      const label = escapeHtml(contact.label || "");
      if (contact.dial_mode === "dialable") {
        return `<li class="card-contact dialable">
          <span class="card-contact-label">${label}</span>
          <a class="card-contact-phone" href="tel:${phone.replaceAll(" ", "")}">${phone}</a>
        </li>`;
      }
      return `<li class="card-contact relay">
        <span class="card-contact-label">${label}</span>
        <span class="card-contact-phone">${phone}</span>
        <span class="card-contact-note">${escapeHtml(contact.note || "")}</span>
      </li>`;
    })
    .join("");
  const holdLine = card.hold_line
    ? `<p class="card-hold-line">${escapeHtml(card.hold_line)}</p>`
    : "";
  return `<div class="chat-message agent contact-card" data-card-type="${escapeHtml(card.type || "")}">
    ${card.title ? `<h3 class="card-title">${escapeHtml(card.title)}</h3>` : ""}
    ${card.reason_line ? `<p class="card-reason">${escapeHtml(card.reason_line)}</p>` : ""}
    <ul class="card-contacts">${contacts}</ul>
    ${holdLine}
  </div>`;
}

function chatMessageHtml(message) {
  if (message.kind === "card") {
    return contactCardHtml(message.card || {});
  }
  if (message.role === "user") {
    return `<div class="chat-message user">${escapeHtml(message.text)}</div>`;
  }
  const extra = message.kind === "ack" ? " ack" : message.kind === "error" ? " error" : "";
  return `<div class="chat-message agent${extra}">${escapeHtml(message.text)}</div>`;
}

function chatMessagesHtml() {
  const bubbles = chatMessages.map(chatMessageHtml).join("");
  // The Progress Trail replaces the meaningless typing animation with
  // fixed, code-owned labels of what the app is actually doing (issue
  // #75, ADR-0010) — shown only while busy, and only in the DOM, never
  // added to chatMessages, so it can never become part of the transcript.
  const trail = chatBusy
    ? chatTrail
        .map(
          (label) => `<div class="chat-message agent trail">${escapeHtml(label)}</div>`,
        )
        .join("")
    : "";
  const typing = chatBusy && !chatTrail.length
    ? '<div class="chat-message agent typing" aria-hidden="true"><span></span><span></span><span></span></div>'
    : "";
  return bubbles + trail + typing;
}

function caseFieldLabel(field) {
  return field.replaceAll("_", " ");
}

function caseProvenanceLabel(source) {
  const key = {
    user: "caseSourceUser",
    extraction: "caseSourceExtraction",
    document: "caseSourceDocument",
    debunker: "caseSourceDebunker",
  }[source];
  return key ? t(key) : source;
}

// One-tap correction (issue #44): a claim with unresolved conflicts[] is
// rendered as a first-class choice between every candidate value with its
// provenance, never silently resolved — her tap is the only thing that
// resolves it (POST /api/case/correct, source="user"). An uncontested
// claim gets a lightweight edit affordance so ANY fact stays correctable
// in one tap, not only a contested one.
function caseClaimHtml(field, claim) {
  const conflicts = Array.isArray(claim.conflicts) ? claim.conflicts : [];
  if (conflicts.length) {
    const candidates = [
      { value: claim.value, source: claim.source },
      ...conflicts.map((conflict) => ({ value: conflict.value, source: conflict.source })),
    ];
    const options = candidates
      .map(
        (candidate) => `<button type="button" class="case-option" data-action="correct-case" data-field="${escapeHtml(field)}" data-value="${escapeHtml(String(candidate.value))}">
          <span class="case-option-value">${escapeHtml(String(candidate.value))}</span>
          <small class="case-option-source">${escapeHtml(caseProvenanceLabel(candidate.source))}</small>
        </button>`,
      )
      .join("");
    return `<li class="case-claim has-conflict">
      <span class="case-field">${escapeHtml(caseFieldLabel(field))}</span>
      <p class="case-conflict-prompt">${t("caseConflictPrompt")}</p>
      <div class="case-conflict-options">${options}</div>
    </li>`;
  }
  if (editingCaseField === field) {
    return `<li class="case-claim">
      <span class="case-field">${escapeHtml(caseFieldLabel(field))}</span>
      <form class="case-edit-form" data-form="case-edit" data-field="${escapeHtml(field)}">
        <input type="text" class="case-edit-input" value="${escapeHtml(String(claim.value))}" maxlength="2000" required />
        <button type="submit" class="button ink-button case-edit-confirm">${t("caseConfirm")}</button>
        <button type="button" class="case-edit-cancel" data-action="cancel-case-edit">${t("caseCancel")}</button>
      </form>
    </li>`;
  }
  return `<li class="case-claim">
    <span class="case-field">${escapeHtml(caseFieldLabel(field))}</span>
    <span class="case-value">${escapeHtml(String(claim.value))}
      <button type="button" class="case-edit-trigger" data-action="edit-case-claim" data-field="${escapeHtml(field)}" aria-label="${escapeHtml(t("caseCorrectLabel"))}">&#9998;</button>
    </span>
  </li>`;
}

function chatCaseHtml() {
  const claims = Object.entries(chatCase.claims || {});
  const flags = Object.keys(chatCase.safety_flags || {});
  if (!claims.length && !flags.length) {
    return `<p class="case-empty">${t("caseEmpty")}</p>`;
  }
  const rows = claims.map(([field, claim]) => caseClaimHtml(field, claim)).join("");
  const flagRows = flags
    .map((flag) => `<li class="case-flag">${escapeHtml(flag.replaceAll("_", " ").toLowerCase())}</li>`)
    .join("");
  return `${claims.length ? `<ul class="case-claims">${rows}</ul>` : ""}
    ${flags.length ? `<h3>${t("caseFlagsTitle")}</h3><ul class="case-flags">${flagRows}</ul>` : ""}`;
}

// home (issue #71): the whole conversation surface — a centred greeting,
// the message list, and the floating composer pill that never leaves
// the screen. The greeting and openers are always in the DOM and simply
// toggled hidden once she has sent her first message (see
// refreshChatScreen), so the composer never re-renders and never loses
// focus mid-stream. This is the structural move that matters: findings
// (cards, verdicts, anything DISPATCHER's tools return) arrive as
// messages in THIS Conversation, never a separate screen.
function homeTemplate() {
  const isEmpty = chatMessages.length === 0;
  const firstName = userName.split(" ")[0] || "friend";
  const openers = CHAT_OPENERS.map(
    (opener) => `<button type="button" class="chat-opener" data-opener="${escapeHtml(opener)}">${escapeHtml(opener)}</button>`,
  ).join("");
  return `<section class="home-shell">
    <div class="ph-glow" aria-hidden="true"></div>
    <div class="home-main">
      <div class="home-greeting${isEmpty ? "" : " hidden"}" id="home-greeting">
        <h1>${escapeHtml(t("greeting", firstName))}</h1>
        <p>${t("chatBody")}</p>
      </div>
      <div class="messages" id="chat-messages" aria-live="polite">${chatMessagesHtml()}</div>
      <div class="chat-openers${isEmpty ? "" : " hidden"}" id="chat-openers">
        <p>${t("chatOpenersLabel")}</p>
        <div class="opener-chips">${openers}</div>
      </div>
      <form class="composer-pill" data-form="chat">
        <textarea id="chat-input" rows="1" maxlength="4000" required placeholder="${escapeHtml(t("chatPlaceholder"))}"></textarea>
        <button class="button ink-button composer-send" type="submit" ${chatBusy ? "disabled" : ""}>${t("chatSend")}</button>
      </form>
    </div>
    <aside class="case-panel" id="chat-case-panel">
      <h2>${t("caseTitle")}</h2>
      <div id="chat-case">${chatCaseHtml()}</div>
    </aside>
  </section>`;
}

function refreshChatScreen() {
  refreshEmergencyControls();
  if (currentScreen !== "home") return;
  const greeting = document.getElementById("home-greeting");
  if (greeting) greeting.classList.toggle("hidden", chatMessages.length > 0);
  const openersBlock = document.getElementById("chat-openers");
  if (openersBlock) openersBlock.classList.toggle("hidden", chatMessages.length > 0);
  const messagesEl = document.getElementById("chat-messages");
  if (messagesEl) {
    messagesEl.innerHTML = chatMessagesHtml();
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
  const casePanel = document.getElementById("chat-case");
  if (casePanel) casePanel.innerHTML = chatCaseHtml();
  const sendButton = document.querySelector('.composer-pill button[type="submit"]');
  if (sendButton) sendButton.disabled = chatBusy;
}

// The Imminent Danger predicate (case.emergency.active) is global app
// state, not screen state — the "mark safe" affordance must show or hide
// no matter which screen she is looking at (issue #64).
function refreshEmergencyControls() {
  if (markSafeButton) {
    markSafeButton.classList.toggle("hidden", !chatCase?.emergency?.active);
  }
}

// Shared NDJSON line-delimited stream reader for both /api/chat and the
// EMERGENCY button's one-shot response — same wire format, same handling.
async function readNdjsonLines(response, onLine) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (value) buffer += decoder.decode(value, { stream: true });
    let newline;
    while ((newline = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (line) onLine(JSON.parse(line));
    }
    if (done) break;
  }
}

async function sendChatTurn(text) {
  if (chatBusy || !auth?.currentUser) return;
  chatBusy = true;
  chatMessages.push({ role: "user", text });
  chatTrail = [];
  refreshChatScreen();
  try {
    const token = await auth.currentUser.getIdToken();
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ text, session_id: chatSessionId }),
    });
    if (!response.ok || !response.body) throw new Error(`chat failed: ${response.status}`);
    await readNdjsonLines(response, handleChatLine);
  } catch {
    chatMessages.push({ role: "agent", kind: "error", text: t("chatError") });
  } finally {
    chatBusy = false;
    // Defensive: the trail is transient and must never outlive the turn
    // even if the stream broke before a "reply" line ever arrived.
    chatTrail = [];
    refreshChatScreen();
  }
}

// The stream line handler is the load-bearing seam between backend and
// frontend slices shipping independently: a line type this build does
// not yet know about is ignored, silently and without throwing, so the
// rest of the turn still renders (issue #71, ADR-0010). Never replace
// this if/else chain with anything that warns or throws on an unknown
// type.
function handleChatLine(line) {
  if (line.session_id) chatSessionId = line.session_id;
  if (line.type === "ack") {
    chatMessages.push({ role: "agent", kind: "ack", text: line.text });
  } else if (line.type === "trail") {
    // The Progress Trail (issue #75, ADR-0010): fixed, code-owned labels
    // of what the app is doing, transient — never pushed to
    // chatMessages, so it never becomes part of the transcript.
    if (line.text) chatTrail.push(line.text);
  } else if (line.type === "reply") {
    // Cleared the moment the reply lands (ADR-0010): the trail's job is
    // done once she has something to read.
    chatTrail = [];
    if (line.text) chatMessages.push({ role: "agent", text: line.text });
  } else if (line.type === "card") {
    // The card is fixed app data rendered outside the LLM text (ADR-0002).
    if (line.card) chatMessages.push({ role: "agent", kind: "card", card: line.card });
  } else if (line.type === "case") {
    chatCase = line.case || {};
  } else if (line.type === "error") {
    chatMessages.push({ role: "agent", kind: "error", text: t("chatError") });
  }
  refreshChatScreen();
}

// One-tap correction (issue #44): POST /api/case/correct, source="user" —
// wins outright, sets user_confirmed, and resolves any Conflict a prior
// turn raised on this field. Never a conversation turn, never an agent
// tool; an authenticated per-user write like every other endpoint here.
async function correctCaseField(field, value) {
  if (!auth?.currentUser || !chatSessionId) return;
  try {
    const token = await auth.currentUser.getIdToken();
    const response = await fetch("/api/case/correct", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: chatSessionId, field, value }),
    });
    if (!response.ok) throw new Error(`correct failed: ${response.status}`);
    const data = await response.json();
    chatCase = data.case || chatCase;
  } catch {
    showStatus(t("caseUpdateFailed"));
  } finally {
    editingCaseField = null;
    refreshChatScreen();
  }
}

const templates = {
  home: homeTemplate,
  profile: profileTemplate,
};

function renderScreen(name = currentScreen) {
  currentScreen = name;
  screen.dataset.screen = name;
  screen.innerHTML = templates[name]();
  screen.focus({ preventScroll: true });
}

function navigate(name) {
  screen.classList.add("hidden");
  screenLoading.classList.remove("hidden");
  window.setTimeout(() => {
    renderScreen(name);
    window.scrollTo(0, 0);
    screenLoading.classList.add("hidden");
    screen.classList.remove("hidden");
  }, 120);
}

function showStatus(message) {
  status.textContent = message;
  status.classList.remove("hidden");
  window.setTimeout(() => status.classList.add("hidden"), 2600);
}

// panic_wipe: nonce-gated backend endpoint. One tap deletes the entire
// server-side subtree; local traces are cleared and the session ends so
// the next visit starts clean. The device is the threat model: clearing
// only the server subtree and leaving either local key behind is not a
// wipe.
async function panicWipe() {
  try {
    const token = await auth.currentUser.getIdToken();
    const headers = {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    };
    const nonceResponse = await fetch("/api/panic-wipe/nonce", { method: "POST", headers });
    if (!nonceResponse.ok) throw new Error("nonce");
    const { nonce } = await nonceResponse.json();
    const wipeResponse = await fetch("/api/panic-wipe", {
      method: "POST",
      headers,
      body: JSON.stringify({ nonce }),
    });
    if (!wipeResponse.ok) throw new Error("wipe");
    localStorage.removeItem(`gabay-profile:${userId}`);
    localStorage.removeItem(`gabay-disclaimer-accepted:${userId}`);
    showStatus(t("wipeDone"));
    await signOut(auth);
  } catch {
    showStatus(t("wipeFailed"));
  }
}

// EMERGENCY (issue #41, #64): the hardcoded exit. POST /api/emergency/button
// renders the cached action card with ZERO model turns, so it is reachable
// even when the model or chat path is down (PRD #34 user story 28) — a
// dedicated one-shot renderer, not a /api/chat turn, sharing only the NDJSON
// card/case line handling with sendChatTurn via handleChatLine. Switches to
// the home screen synchronously (never navigate()'s animated transition —
// an emergency exit does not wait on a decorative delay) so the rendered
// card is visible immediately, before the network call even resolves.
async function pressEmergencyButton() {
  if (!auth?.currentUser) return;
  if (currentScreen !== "home") renderScreen("home");
  try {
    const token = await auth.currentUser.getIdToken();
    const response = await fetch("/api/emergency/button", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok || !response.body) throw new Error(`emergency failed: ${response.status}`);
    await readNdjsonLines(response, handleChatLine);
  } catch {
    chatMessages.push({ role: "agent", kind: "error", text: t("emergencyFailed") });
    refreshChatScreen();
  }
}

// mark_safe (issue #41, #64): clears the Imminent Danger PREDICATE only —
// never the safety flag itself (PRD #34 user story 33). Nonce-gated
// backend endpoint, same shape as panic_wipe. The confirmation dialog
// (#mark-safe-dialog) is the deliberate second tap: a coerced pocket-tap
// on the visible button alone can't clear the predicate (user story 32).
async function applyMarkSafe() {
  if (!auth?.currentUser) return;
  try {
    const token = await auth.currentUser.getIdToken();
    const headers = {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    };
    const nonceResponse = await fetch("/api/mark-safe/nonce", { method: "POST", headers });
    if (!nonceResponse.ok) throw new Error("nonce");
    const { nonce } = await nonceResponse.json();
    const response = await fetch("/api/mark-safe", {
      method: "POST",
      headers,
      body: JSON.stringify({ nonce }),
    });
    if (!response.ok) throw new Error("mark-safe");
    const data = await response.json();
    chatCase = data.case || chatCase;
    showStatus(t("markSafeDone"));
  } catch {
    showStatus(t("markSafeFailed"));
  } finally {
    refreshChatScreen();
  }
}

document.addEventListener("click", (event) => {
  const opener = event.target.closest("[data-opener]");
  if (opener) {
    const input = document.getElementById("chat-input");
    if (input) {
      input.value = opener.dataset.opener;
      input.focus();
    }
    return;
  }
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const action = button.dataset.action;
  if (action === "panic-wipe") {
    button.disabled = true;
    panicWipe().finally(() => {
      button.disabled = false;
    });
    return;
  }
  if (action === "emergency-button") {
    if (dialog.open) dialog.close();
    button.disabled = true;
    pressEmergencyButton().finally(() => {
      button.disabled = false;
    });
    return;
  }
  if (action === "mark-safe") {
    markSafeDialog.showModal();
    return;
  }
  if (action === "mark-safe-cancel") {
    markSafeDialog.close();
    return;
  }
  if (action === "mark-safe-confirm") {
    markSafeDialog.close();
    button.disabled = true;
    applyMarkSafe().finally(() => {
      button.disabled = false;
    });
    return;
  }
  if (action === "delete-profile") {
    localStorage.removeItem(`gabay-profile:${userId}`);
    renderScreen("profile");
    showStatus(t("localProfileDeleted"));
    return;
  }
  if (action === "edit-case-claim") {
    editingCaseField = button.dataset.field;
    refreshChatScreen();
    return;
  }
  if (action === "cancel-case-edit") {
    editingCaseField = null;
    refreshChatScreen();
    return;
  }
  if (action === "correct-case") {
    button.disabled = true;
    correctCaseField(button.dataset.field, button.dataset.value).finally(() => {
      button.disabled = false;
    });
    return;
  }
  if (action === "home" && currentScreen === "home") return;
  navigate(action);
});

document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!form.dataset.form) return;
  event.preventDefault();
  if (form.dataset.form === "chat") {
    const input = document.getElementById("chat-input");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    sendChatTurn(text);
  } else if (form.dataset.form === "case-edit") {
    const field = form.dataset.field;
    const value = form.querySelector(".case-edit-input").value.trim();
    if (!value) return;
    correctCaseField(field, value);
  } else if (form.dataset.form === "profile") {
    localStorage.setItem(`gabay-profile:${userId}`, JSON.stringify({
      country: document.getElementById("profile-country").value.trim(),
      occupation: document.getElementById("profile-occupation").value.trim(),
    }));
    showStatus(t("profileSaved"));
  }
});

languageSelects.forEach((select) => {
  select.addEventListener("change", () => {
    language = select.value;
    localStorage.setItem("gabay-language", language);
    renderLanguageOptions();
    applyCopy();
    if (!app.classList.contains("hidden")) renderScreen();
  });
});

document.getElementById("accept-disclaimer").addEventListener("click", () => {
  localStorage.setItem(`gabay-disclaimer-accepted:${userId}`, "true");
});

applyCopy();
renderLanguageOptions();

let auth;
try {
  const configResponse = await fetch("/api/firebase-config");
  if (!configResponse.ok) throw new Error(t("notConfigured"));
  auth = getAuth(initializeApp(await configResponse.json()));
} catch (error) {
  authLoading.classList.add("hidden");
  signedOut.classList.remove("hidden");
  showStatus(error.message || t("notConfigured"));
}

document.getElementById("signin").addEventListener("click", () => {
  signInWithPopup(auth, new GoogleAuthProvider()).catch((error) => {
    showStatus(t("signInFailed", error.message));
  });
});

document.getElementById("signout").addEventListener("click", () => signOut(auth));

if (auth) {
  onAuthStateChanged(auth, (user) => {
    authLoading.classList.add("hidden");
    signedOut.classList.toggle("hidden", Boolean(user));
    app.classList.toggle("hidden", !user);
    if (!user) {
      chatSessionId = null;
      chatMessages = [];
      chatCase = {};
      editingCaseField = null;
      if (markSafeDialog.open) markSafeDialog.close();
      refreshEmergencyControls();
      return;
    }
    userName = user.displayName || user.email || "";
    userId = user.uid || user.email || "signed-in-user";
    document.getElementById("account-name").textContent = userName;
    document.getElementById("avatar-initial").textContent = userName.trim().charAt(0).toUpperCase() || "G";
    renderScreen("home");
    if (!localStorage.getItem(`gabay-disclaimer-accepted:${userId}`)) {
      dialog.showModal();
    }
  });
}
