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
    welcomeEyebrow: "Practical support for Filipino workers abroad",
    welcomeTitle: "Is your work following your contract?",
    welcomeBody: "Talk to us about what is happening. We will help you see what may not match and who you can call.",
    welcomeStepOne: "Talk to us in your own words",
    welcomeStepTwo: "See what may not match",
    welcomeStepThree: "Find the right person to call",
    signIn: "Continue with Google",
    privacyNote: "Your records are private to your account. Gabay OFW never stores passwords.",
    owwaAlways: "OWWA's free 24/7 hotline is available to OFWs and their families.",
    languageLabel: "Language",
    accountControls: "Account controls",
    serviceOverview: "Service overview",
    homeLabel: "Gabay OFW home",
    countries: ["Saudi Arabia", "United Arab Emirates", "Qatar", "Kuwait", "Bahrain", "Oman"],
    profile: "Profile",
    signOut: "Sign out",
    needHelp: "I Need Help Now",
    modeNavigation: "Choose a service",
    helpTab: "Help now",
    disclaimerTitle: "Before you begin",
    disclaimerBody: "Gabay OFW offers practical guidance and connects you with official support.",
    notLegalTitle: "Not legal advice.",
    notLegalBody: "Findings identify possible conflicts with standard rules. Verify them with DMW, OWWA, or a lawyer.",
    notEmergencyTitle: "Not an emergency service.",
    notEmergencyBody: "If you are in immediate danger, contact local emergency services or the nearest Philippine Embassy.",
    understand: "I understand",
    greeting: (name) => `Welcome, ${name}.`,
    dashboardTitle: "What do you need?",
    dashboardBody: "Choose a service. Gabay OFW will never guess which kind of help you need.",
    crisisKicker: "Short, calm, and direct",
    crisisTitle: "Crisis Help",
    crisisBody: "Tell us what is happening and we will connect you with the right official support.",
    crisisCta: "Get help now",
    crisisTime: "Straight to the right number",
    privacyTitle: "Built for privacy",
    privacyBody: "This preview does not save conversations. Stored Crisis Sessions are designed to expire automatically.",
    backDashboard: "Back to dashboard",
    continue: "Continue",
    done: "Done",
    crisisStep: "Crisis Help",
    crisisAsideKicker: "Official help stays close",
    crisisAsideTitle: "You do not have to explain everything.",
    crisisAsideBody: "Share only what feels safe. We use this to show official contacts and do not save this conversation in the preview.",
    crisisHotlineLabel: "OWWA, any hour",
    crisisQuestionTitle: "Are you in physical danger right now?",
    crisisQuestionBody: "Choose what feels closest to your situation. We will give contact information without asking for details we do not need.",
    dangerYes: "Yes, or I cannot leave safely",
    dangerNo: "No, I can safely use my phone",
    countryTitle: "Which country are you in?",
    countryLabel: "Country",
    chooseCountry: "Choose a country",
    situationTitle: "What kind of help do you need?",
    situationBody: "A short description is enough. Do not share passport numbers, addresses, or other sensitive details.",
    situationLabel: "One-line description",
    situationPlaceholder: "Example: My employer is keeping my passport.",
    showHelp: "Show official help",
    routeTitle: "Call one of these now. All are free.",
    routeBody: "For a safety threat, confinement, or trafficking concern, these free services can help.",
    mwoRouteTitle: "Contact your Migrant Workers Office",
    mwoRouteBody: (country) => `For a concern without immediate danger in ${country}, contact the official MWO or OWWA.`,
    actionline: "Actionline Against Human Trafficking",
    owwa: "OWWA 24/7 Hotline",
    embassy: "Find the nearest Philippine Embassy or MWO",
    officialDirectory: "Open the official DMW directory",
    reassurance: "You are not alone. These offices exist specifically to help OFWs in your situation, and reaching out does not cost you anything.",
    call: (number) => `Call ${number}`,
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
    otherCountry: "Other",
    signInFailed: (message) => `Sign-in failed: ${message}`,
    notConfigured: "Firebase sign-in is not configured yet.",
    chatCardTitle: "Talk to Gabay",
    chatCardBody: "Tell your story in any order, in any language. Gabay listens and builds your case with you.",
    chatTitle: "Tell me what's happening",
    chatBody: "Any language, any order. Office names like DOLE-SEnA, MWO, and OWWA stay as they are so you can match them against a sign or a website.",
    chatStep: "Your conversation",
    chatPlaceholder: "Type in any language...",
    chatSend: "Send",
    chatOpenersLabel: "You can start with one of these:",
    chatError: "Something went wrong on our side. Nothing you wrote was lost - please send it again.",
    caseTitle: "What Gabay has understood",
    caseEmpty: "Facts you share will appear here so you never have to repeat yourself.",
    caseFlagsTitle: "Safety notes",
  },
  tl: {
    languageName: "Filipino",
    loading: "Binubuksan ang iyong pribadong espasyo...",
    welcomeEyebrow: "Praktikal na suporta para sa Pilipinong manggagawa sa abroad",
    welcomeTitle: "Sinusunod ba ng trabaho mo ang kontrata?",
    welcomeBody: "Kuwento mo sa amin ang nangyayari. Tutulungan ka naming makita ang posibleng hindi tugma at kung sino ang puwedeng tawagan.",
    welcomeStepOne: "Magkuwento sa sarili mong salita",
    welcomeStepTwo: "Tingnan ang posibleng hindi tugma",
    welcomeStepThree: "Hanapin ang tamang taong tatawagan",
    signIn: "Magpatuloy gamit ang Google",
    privacyNote: "Pribado sa account mo ang mga record. Hindi nag-iimbak ng password ang Gabay OFW.",
    owwaAlways: "Laging bukas at libre ang OWWA 24/7 hotline para sa OFW at pamilya.",
    languageLabel: "Wika",
    accountControls: "Mga control ng account",
    serviceOverview: "Buod ng serbisyo",
    homeLabel: "Home ng Gabay OFW",
    countries: ["Saudi Arabia", "United Arab Emirates", "Qatar", "Kuwait", "Bahrain", "Oman"],
    profile: "Profile",
    signOut: "Mag-sign out",
    needHelp: "Kailangan Ko ng Tulong Ngayon",
    modeNavigation: "Pumili ng serbisyo",
    helpTab: "Tulong ngayon",
    disclaimerTitle: "Bago magsimula",
    disclaimerBody: "Nagbibigay ang Gabay OFW ng praktikal na gabay at koneksiyon sa opisyal na suporta.",
    notLegalTitle: "Hindi legal na payo.",
    notLegalBody: "Posibleng paglabag lamang ang findings. I-verify sa DMW, OWWA, o abogado.",
    notEmergencyTitle: "Hindi emergency service.",
    notEmergencyBody: "Kung may agarang panganib, tumawag sa local emergency services o pinakamalapit na Philippine Embassy.",
    understand: "Naiintindihan ko",
    greeting: (name) => `Maligayang pagdating, ${name}.`,
    dashboardTitle: "Ano ang kailangan mo?",
    dashboardBody: "Pumili ng serbisyo. Hindi huhulaan ng Gabay OFW kung anong tulong ang kailangan mo.",
    crisisKicker: "Maikli, kalmado, at direkta",
    crisisTitle: "Crisis Help",
    crisisBody: "Kuwento mo ang nangyayari at ituturo ka namin sa tamang opisyal na suporta.",
    crisisCta: "Humingi ng tulong",
    crisisTime: "Diretso sa tamang numero",
    privacyTitle: "Dinisenyo para sa privacy",
    privacyBody: "Hindi sine-save ng preview na ito ang usapan. Dinisenyong awtomatikong mabura ang stored Crisis Sessions.",
    backDashboard: "Bumalik sa dashboard",
    continue: "Magpatuloy",
    done: "Tapos",
    crisisStep: "Crisis Help",
    crisisAsideKicker: "Malapit lang ang opisyal na tulong",
    crisisAsideTitle: "Hindi mo kailangang ikuwento ang lahat.",
    crisisAsideBody: "Ibahagi lang ang ligtas para sa iyo. Ginagamit ito para ipakita ang opisyal na contact at hindi sine-save ang usapan sa preview.",
    crisisHotlineLabel: "OWWA, anumang oras",
    crisisQuestionTitle: "Nasa pisikal na panganib ka ba ngayon?",
    crisisQuestionBody: "Piliin ang pinakamalapit sa sitwasyon mo. Ibibigay agad ang contact information nang hindi humihingi ng detalyeng hindi kailangan.",
    dangerYes: "Oo, o hindi ako ligtas na makaalis",
    dangerNo: "Hindi, ligtas kong magagamit ang phone",
    countryTitle: "Saang bansa ka naroon?",
    countryLabel: "Bansa",
    chooseCountry: "Pumili ng bansa",
    situationTitle: "Anong uri ng tulong ang kailangan mo?",
    situationBody: "Maikling paglalarawan lang. Huwag magbahagi ng passport number, address, o sensitibong detalye.",
    situationLabel: "Isang linyang paglalarawan",
    situationPlaceholder: "Halimbawa: Hawak ng employer ko ang passport ko.",
    showHelp: "Ipakita ang opisyal na tulong",
    routeTitle: "Tumawag sa isa sa mga ito ngayon. Libre lahat.",
    routeBody: "Para sa banta sa kaligtasan, pagkakulong, o trafficking concern, makakatulong ang libreng serbisyong ito.",
    mwoRouteTitle: "Makipag-ugnayan sa Migrant Workers Office",
    mwoRouteBody: (country) => `Para sa concern na walang agarang panganib sa ${country}, kontakin ang opisyal na MWO o OWWA.`,
    actionline: "Actionline Against Human Trafficking",
    owwa: "OWWA 24/7 Hotline",
    embassy: "Hanapin ang pinakamalapit na Philippine Embassy o MWO",
    officialDirectory: "Buksan ang opisyal na DMW directory",
    reassurance: "Hindi ka nag-iisa. Nariyan ang mga opisinang ito para tulungan ang OFW sa ganitong sitwasyon, at walang bayad ang paglapit.",
    call: (number) => `Tumawag sa ${number}`,
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
    otherCountry: "Ibang bansa",
    signInFailed: (message) => `Hindi nagtagumpay ang sign-in: ${message}`,
    notConfigured: "Hindi pa naka-configure ang Firebase sign-in.",
    chatCardTitle: "Kausapin si Gabay",
    chatCardBody: "Ikuwento mo sa kahit anong ayos, sa kahit anong wika. Nakikinig si Gabay at binubuo ninyo ang kaso mo.",
    chatTitle: "Ikuwento mo kung ano ang nangyayari",
    chatBody: "Kahit anong wika, kahit anong ayos. Mananatili ang mga pangalan ng opisina tulad ng DOLE-SEnA, MWO, at OWWA para maitugma mo sa karatula o website.",
    chatStep: "Ang usapan ninyo",
    chatPlaceholder: "Mag-type sa kahit anong wika...",
    chatSend: "Ipadala",
    chatOpenersLabel: "Puwede kang magsimula sa isa sa mga ito:",
    chatError: "May nangyaring mali sa amin. Hindi nawala ang isinulat mo - pakisend ulit.",
    caseTitle: "Ang naiintindihan ni Gabay",
    caseEmpty: "Lalabas dito ang mga detalyeng ibinahagi mo para hindi mo na kailangang ulitin.",
    caseFlagsTitle: "Mga paalala sa kaligtasan",
  },
  ceb: {
    languageName: "Bisaya",
    loading: "Giablihan ang imong pribadong luna...",
    welcomeEyebrow: "Praktikal nga suporta para sa Pilipinong trabahante sa abroad",
    welcomeTitle: "Nagsunod ba ang imong trabaho sa kontrata?",
    welcomeBody: "Isulti kanamo unsay nahitabo. Tabangan ka namo nga makita ang posibleng dili motakdo ug kinsa ang tawagan.",
    welcomeStepOne: "Isulti sa imong kaugalingong mga pulong",
    welcomeStepTwo: "Tan-awa ang posibleng dili motakdo",
    welcomeStepThree: "Pangitaa ang hustong tawagan",
    signIn: "Padayon gamit ang Google",
    privacyNote: "Pribado sa imong account ang records. Dili magtipig og password ang Gabay OFW.",
    owwaAlways: "Libre ug abli 24/7 ang OWWA hotline para sa OFW ug pamilya.",
    languageLabel: "Pinulongan",
    accountControls: "Mga control sa account",
    serviceOverview: "Kinatibuk-ang serbisyo",
    homeLabel: "Home sa Gabay OFW",
    countries: ["Saudi Arabia", "United Arab Emirates", "Qatar", "Kuwait", "Bahrain", "Oman"],
    profile: "Profile",
    signOut: "Sign out",
    needHelp: "Kinahanglan Ko og Tabang Karon",
    modeNavigation: "Pilia ang serbisyo",
    helpTab: "Tabang karon",
    disclaimerTitle: "Sa dili pa magsugod",
    disclaimerBody: "Naghatag ang Gabay OFW og praktikal nga giya ug koneksiyon sa opisyal nga suporta.",
    notLegalTitle: "Dili legal nga tambag.",
    notLegalBody: "Posibleng conflict lang ang findings. I-verify sa DMW, OWWA, o abogado.",
    notEmergencyTitle: "Dili emergency service.",
    notEmergencyBody: "Kung naa sa diha-diha nga peligro, kontaka ang local emergency services o duol nga Philippine Embassy.",
    understand: "Nasabtan nako",
    greeting: (name) => `Maayong pag-abot, ${name}.`,
    dashboardTitle: "Unsay imong kinahanglan?",
    dashboardBody: "Pilia ang serbisyo. Dili tag-anon sa Gabay OFW ang tabang nga imong kinahanglan.",
    crisisKicker: "Mubo, kalmado, ug direkta",
    crisisTitle: "Crisis Help",
    crisisBody: "Isulti unsay nahitabo ug itudlo ka namo sa hustong opisyal nga suporta.",
    crisisCta: "Pangayo og tabang",
    crisisTime: "Diretso sa hustong numero",
    privacyTitle: "Gidisenyo para sa privacy",
    privacyBody: "Dili i-save sa preview ang panag-istorya. Gidisenyo nga awtomatikong mapapas ang stored Crisis Sessions.",
    backDashboard: "Balik sa dashboard",
    continue: "Padayon",
    done: "Human",
    crisisStep: "Crisis Help",
    crisisAsideKicker: "Duol ra ang opisyal nga tabang",
    crisisAsideTitle: "Dili kinahanglan isulti ang tanan.",
    crisisAsideBody: "Ipaambit lang ang luwas para nimo. Gamiton kini sa pagpakita sa opisyal nga contact ug dili i-save ang panag-istorya sa preview.",
    crisisHotlineLabel: "OWWA, bisan unsang orasa",
    crisisQuestionTitle: "Naa ka ba sa pisikal nga peligro karon?",
    crisisQuestionBody: "Pilia ang labing duol sa imong kahimtang. Ihatag dayon ang contact information nga dili mangayo og detalye nga wala namo kinahanglana.",
    dangerYes: "Oo, o dili ko luwas nga makagawas",
    dangerNo: "Dili, luwas nakong magamit ang phone",
    countryTitle: "Asang nasod ka karon?",
    countryLabel: "Nasod",
    chooseCountry: "Pilia ang nasod",
    situationTitle: "Unsang tabang ang imong kinahanglan?",
    situationBody: "Mubo nga paghulagway lang. Ayaw paghatag og passport number, address, o sensitibong detalye.",
    situationLabel: "Usa ka linya nga paghulagway",
    situationPlaceholder: "Pananglitan: Gikuptan sa employer ang akong passport.",
    showHelp: "Ipakita ang opisyal nga tabang",
    routeTitle: "Tawag sa usa niini karon. Libre ang tanan.",
    routeBody: "Para sa hulga sa kaluwasan, pagkabilanggo, o trafficking concern, makatabang kining libre nga serbisyo.",
    mwoRouteTitle: "Kontaka ang Migrant Workers Office",
    mwoRouteBody: (country) => `Para sa concern nga walay diha-diha nga peligro sa ${country}, kontaka ang opisyal nga MWO o OWWA.`,
    actionline: "Actionline Against Human Trafficking",
    owwa: "OWWA 24/7 Hotline",
    embassy: "Pangitaa ang duol nga Philippine Embassy o MWO",
    officialDirectory: "Ablihi ang opisyal nga DMW directory",
    reassurance: "Dili ka nag-inusara. Anaa kining mga opisina para motabang sa OFW sa imong kahimtang, ug walay bayad ang pagpangayo og tabang.",
    call: (number) => `Tawag sa ${number}`,
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
    otherCountry: "Ubang nasod",
    signInFailed: (message) => `Wala molampos ang sign-in: ${message}`,
    notConfigured: "Wala pa ma-configure ang Firebase sign-in.",
    chatCardTitle: "Istoryahi si Gabay",
    chatCardBody: "Isulti sa bisan unsang han-ay, sa bisan unsang pinulongan. Maminaw si Gabay ug tukoron ninyo ang imong kaso.",
    chatTitle: "Isulti unsay nahitabo",
    chatBody: "Bisan unsang pinulongan, bisan unsang han-ay. Magpabilin ang ngalan sa opisina sama sa DOLE-SEnA, MWO, ug OWWA aron imong ikatandi sa karatula o website.",
    chatStep: "Ang inyong istorya",
    chatPlaceholder: "Pag-type sa bisan unsang pinulongan...",
    chatSend: "Ipadala",
    chatOpenersLabel: "Mahimo kang magsugod sa usa niini:",
    chatError: "Adunay sayop sa among bahin. Wala mawala ang imong gisulat - palihug isend pag-usab.",
    caseTitle: "Ang nasabtan ni Gabay",
    caseEmpty: "Mogawas dinhi ang mga detalye nga imong gipaambit aron dili na nimo balikon.",
    caseFlagsTitle: "Mga pahinumdom sa kaluwasan",
  },
};

Object.assign(copy.en, {
  howItWorks: "How it works",
  privacyLink: "Your privacy",
  callOwwa: "Call OWWA 1348",
  startNow: "Start now",
  signInBody: "Signing in keeps your conversation private to you. Nobody at your work is told.",
  signIn: "Sign in with Google",
  trustFree: "Free",
  trustPrivate: "Private to you",
  trustNoAds: "No ads",
  dangerTonight: "In danger tonight? Call OWWA, any hour. Free from any phone.",
  greeting: (name) => `${name}, what do you need?`,
  dashboardBody: "Choose where to begin. You can move between both kinds of support at any time.",
  crisisTitle: "I need help now",
  crisisBody: "Tell us what is happening, then see the numbers that can help tonight.",
  topicPrompt: "Or start with what is happening",
  topicLeave: "I cannot go out",
});

Object.assign(copy.tl, {
  howItWorks: "Paano ito gumagana",
  privacyLink: "Ang privacy mo",
  callOwwa: "Tumawag sa OWWA 1348",
  startNow: "Magsimula",
  signInBody: "Ang pag-sign in ay nagpapanatiling pribado sa iyo ang usapan. Walang sasabihin sa pinagtatrabahuhan mo.",
  signIn: "Mag-sign in gamit ang Google",
  trustFree: "Libre",
  trustPrivate: "Pribado sa iyo",
  trustNoAds: "Walang ads",
  dangerTonight: "Nasa panganib ngayong gabi? Tumawag sa OWWA anumang oras. Libre mula sa kahit anong telepono.",
  greeting: (name) => `${name}, ano ang kailangan mo?`,
  dashboardBody: "Piliin kung saan magsisimula. Puwede kang lumipat sa dalawang uri ng suporta anumang oras.",
  crisisTitle: "Kailangan ko ng tulong ngayon",
  crisisBody: "Kuwento mo ang nangyayari, pagkatapos ay tingnan ang mga numerong makakatulong ngayong gabi.",
  topicPrompt: "O magsimula sa nangyayari",
  topicLeave: "Hindi ako makalabas",
});

Object.assign(copy.ceb, {
  howItWorks: "Giunsa kini pagtrabaho",
  privacyLink: "Imong privacy",
  callOwwa: "Tawag sa OWWA 1348",
  startNow: "Pagsugod",
  signInBody: "Ang pag-sign in magpabiling pribado sa imo ang panag-istorya. Walay sultihan sa imong trabaho.",
  signIn: "Sign in gamit ang Google",
  trustFree: "Libre",
  trustPrivate: "Pribado sa imo",
  trustNoAds: "Walay ads",
  dangerTonight: "Naa sa peligro karong gabii? Tawag sa OWWA bisan unsang oras. Libre sa bisan unsang phone.",
  greeting: (name) => `${name}, unsay imong kinahanglan?`,
  dashboardBody: "Pilia asa magsugod. Makabalhin ka sa duha ka klase sa suporta bisan kanus-a.",
  crisisTitle: "Kinahanglan ko og tabang karon",
  crisisBody: "Isulti unsay nahitabo, dayon tan-awa ang mga numero nga makatabang karong gabii.",
  topicPrompt: "O sugdi sa unsay nahitabo",
  topicLeave: "Dili ko makagawas",
});

const screen = document.getElementById("screen");
const screenLoading = document.getElementById("screen-loading");
const app = document.getElementById("signed-in");
const signedOut = document.getElementById("signed-out");
const authLoading = document.getElementById("auth-loading");
const dialog = document.getElementById("first-run-dialog");
const languageSelects = document.querySelectorAll(".language-select");
const modeSwitcher = document.querySelector(".mode-switcher");
const globalHelp = document.getElementById("global-help");
const status = document.getElementById("status");

const supportedLanguages = Object.keys(copy);
const savedLanguage = localStorage.getItem("gabay-language");
let language = supportedLanguages.includes(savedLanguage) ? savedLanguage : "en";
let currentScreen = "dashboard";
let userName = "";
let userId = "";
let crisisDanger = false;
let crisisCountry = "";

// Paired bilingual openers: showing both languages work is the point
// ("Hindi ako nababayaran / I'm not being paid").
const CHAT_OPENERS = [
  "Hindi ako nababayaran / I'm not being paid",
  "Kinuha nila ang passport ko / They took my passport",
  "Gusto ko nang umuwi / I want to go home",
  "Natatakot ako sa amo ko / I'm afraid of my employer",
];
let chatSessionId = null;
let chatThread = [];
let chatCase = {};
let chatBusy = false;

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

function dashboardTemplate() {
  const firstName = userName.split(" ")[0] || "friend";
  return `
    <section class="dashboard-shell">
      <header class="dashboard-heading">
        <h1>${escapeHtml(t("greeting", firstName))}</h1>
      </header>
      <div class="service-grid">
        <button class="mode-card chat-card" type="button" data-action="chat">
          <svg class="service-icon" viewBox="0 0 48 48" aria-hidden="true">
            <path d="M10 14h28v18H22l-8 7v-7h-4z"></path>
            <path d="M17 21h14M17 26h9"></path>
          </svg>
          <span>
            <h2>${t("chatCardTitle")}</h2>
            <p>${t("chatCardBody")}</p>
          </span>
        </button>
        <button class="mode-card crisis-card" type="button" data-action="crisis">
          <svg class="service-icon" viewBox="0 0 48 48" aria-hidden="true">
            <circle cx="24" cy="24" r="18"></circle>
            <path d="M18 16c1 8 6 13 14 16M19 14l5 7-4 3M34 29l-7-4-3 4"></path>
          </svg>
          <span>
            <h2>${t("crisisTitle")}</h2>
            <p>${t("crisisBody")}</p>
          </span>
        </button>
      </div>
      <div class="topic-starters">
        <p>${t("topicPrompt")}</p>
        <div class="topic-chips">
          <button type="button" data-action="crisis">${t("topicLeave")}</button>
        </div>
      </div>
    </section>`;
}

function flowNav(label) {
  return `<nav class="flow-nav" aria-label="${escapeHtml(label)}">
    <button class="back-button" type="button" data-action="dashboard">${t("backDashboard")}</button>
    <span class="step-label">${label}</span>
  </nav>`;
}

function crisisContext() {
  return `<aside class="crisis-context">
    <p class="eyebrow">${t("crisisAsideKicker")}</p>
    <h2>${t("crisisAsideTitle")}</h2>
    <p>${t("crisisAsideBody")}</p>
    <a class="crisis-hotline" href="tel:1348">
      <span>${t("crisisHotlineLabel")}</span>
      <strong>1348</strong>
    </a>
  </aside>`;
}

function crisisFrame(content, extraClass = "", showContext = true) {
  return `<section class="flow-shell crisis-shell ${extraClass}">
    ${flowNav(t("crisisStep"))}
    <div class="crisis-layout">
      <div class="crisis-main">${content}</div>
      ${showContext ? crisisContext() : ""}
    </div>
  </section>`;
}

function crisisQuestionTemplate() {
  return crisisFrame(`<div class="question-card">
      <p class="eyebrow">${t("crisisStep")}</p>
      <h1>${t("crisisQuestionTitle")}</h1>
      <p>${t("crisisQuestionBody")}</p>
      <div class="choice-stack">
        <button class="choice" type="button" data-action="crisis-country" data-danger="true">${t("dangerYes")}</button>
        <button class="choice" type="button" data-action="crisis-country" data-danger="false">${t("dangerNo")}</button>
      </div>
    </div>`);
}

function crisisCountryTemplate() {
  return crisisFrame(`<form class="question-card" data-form="crisis-country">
      <p class="eyebrow">${t("crisisStep")}</p>
      <h1>${t("countryTitle")}</h1>
      <div class="field">
        <label for="crisis-country">${t("countryLabel")}</label>
        <select id="crisis-country" required>
          <option value="">${t("chooseCountry")}</option>
          ${t("countries").map((country) => `<option${country === crisisCountry ? " selected" : ""}>${country}</option>`).join("")}
          <option value="Other"${crisisCountry === "Other" ? " selected" : ""}>${t("otherCountry")}</option>
        </select>
      </div>
      <button class="button ink-button" type="submit">${t("continue")}</button>
    </form>`);
}

function crisisSituationTemplate() {
  return crisisFrame(`<form class="question-card" data-form="crisis-situation">
      <p class="eyebrow">${t("crisisStep")}</p>
      <h1>${t("situationTitle")}</h1>
      <p>${t("situationBody")}</p>
      <div class="field">
        <label for="crisis-situation">${t("situationLabel")}</label>
        <textarea id="crisis-situation" required maxlength="500" placeholder="${escapeHtml(t("situationPlaceholder"))}"></textarea>
      </div>
      <button class="button ink-button" type="submit">${t("showHelp")}</button>
    </form>`);
}

function crisisRouteTemplate() {
  const routeTitle = crisisDanger ? t("routeTitle") : t("mwoRouteTitle");
  const routeBody = crisisDanger
    ? t("routeBody")
    : t("mwoRouteBody", crisisCountry || t("otherCountry"));
  return crisisFrame(`<article class="report">
      <p class="eyebrow">${t("crisisStep")}</p>
      <h1>${routeTitle}</h1>
      <p class="report-intro">${routeBody}</p>
      <div class="route-grid">
      ${crisisDanger ? `<section class="route-card">
        <h3>${t("actionline")}</h3>
        <p class="route-number">1343</p>
        <a href="tel:1343">${t("call", "1343")}</a>
      </section>` : ""}
      <section class="route-card${crisisDanger ? " primary-route" : ""}">
        <h3>${t("owwa")}</h3>
        <p class="route-number">1348</p>
        <a href="tel:1348">${t("call", "1348")}</a>
      </section>
      <section class="route-card">
        <h3>${t("embassy")}</h3>
        <a href="https://dmw.gov.ph/" target="_blank" rel="noopener noreferrer">${t("officialDirectory")}</a>
      </section>
      </div>
      <p class="reassurance">${t("reassurance")}</p>
      <button class="button" type="button" data-action="dashboard">${t("done")}</button>
    </article>`, "crisis-route-shell", false);
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
        <button class="profile-help-link" type="button" data-action="crisis">
          <span class="urgent-dot" aria-hidden="true"></span>
          ${t("needHelp")}
        </button>
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

function chatMessageHtml(message) {
  if (message.role === "user") {
    return `<div class="chat-message user">${escapeHtml(message.text)}</div>`;
  }
  const extra = message.kind === "ack" ? " ack" : message.kind === "error" ? " error" : "";
  return `<div class="chat-message agent${extra}">${escapeHtml(message.text)}</div>`;
}

function chatThreadHtml() {
  const bubbles = chatThread.map(chatMessageHtml).join("");
  const typing = chatBusy ? '<div class="chat-message agent typing" aria-hidden="true"><span></span><span></span><span></span></div>' : "";
  return bubbles + typing;
}

function caseFieldLabel(field) {
  return field.replaceAll("_", " ");
}

function chatCaseHtml() {
  const claims = Object.entries(chatCase.claims || {});
  const flags = Object.keys(chatCase.safety_flags || {});
  if (!claims.length && !flags.length) {
    return `<p class="case-empty">${t("caseEmpty")}</p>`;
  }
  const rows = claims
    .map(
      ([field, claim]) => `<li>
        <span class="case-field">${escapeHtml(caseFieldLabel(field))}</span>
        <span class="case-value">${escapeHtml(String(claim.value))}</span>
      </li>`,
    )
    .join("");
  const flagRows = flags
    .map((flag) => `<li class="case-flag">${escapeHtml(flag.replaceAll("_", " ").toLowerCase())}</li>`)
    .join("");
  return `${claims.length ? `<ul class="case-claims">${rows}</ul>` : ""}
    ${flags.length ? `<h3>${t("caseFlagsTitle")}</h3><ul class="case-flags">${flagRows}</ul>` : ""}`;
}

function chatTemplate() {
  const openers = CHAT_OPENERS.map(
    (opener) => `<button type="button" class="chat-opener" data-opener="${escapeHtml(opener)}">${escapeHtml(opener)}</button>`,
  ).join("");
  return `<section class="flow-shell chat-shell">
    ${flowNav(t("chatStep"))}
    <div class="chat-layout">
      <div class="chat-main">
        <header class="chat-heading">
          <h1>${t("chatTitle")}</h1>
          <p>${t("chatBody")}</p>
        </header>
        <div class="chat-thread" id="chat-thread" aria-live="polite">${chatThreadHtml()}</div>
        ${chatThread.length ? "" : `<div class="chat-openers" id="chat-openers">
          <p>${t("chatOpenersLabel")}</p>
          <div class="opener-chips">${openers}</div>
        </div>`}
        <form class="chat-composer" data-form="chat">
          <textarea id="chat-input" rows="2" maxlength="4000" required placeholder="${escapeHtml(t("chatPlaceholder"))}"></textarea>
          <button class="button ink-button" type="submit" ${chatBusy ? "disabled" : ""}>${t("chatSend")}</button>
        </form>
      </div>
      <aside class="chat-case" id="chat-case-panel">
        <h2>${t("caseTitle")}</h2>
        <div id="chat-case">${chatCaseHtml()}</div>
      </aside>
    </div>
  </section>`;
}

function refreshChatScreen() {
  if (currentScreen !== "chat") return;
  const thread = document.getElementById("chat-thread");
  if (thread) {
    thread.innerHTML = chatThreadHtml();
    thread.scrollTop = thread.scrollHeight;
  }
  const casePanel = document.getElementById("chat-case");
  if (casePanel) casePanel.innerHTML = chatCaseHtml();
  const openersBlock = document.getElementById("chat-openers");
  if (openersBlock && chatThread.length) openersBlock.remove();
  const sendButton = document.querySelector('.chat-composer button[type="submit"]');
  if (sendButton) sendButton.disabled = chatBusy;
}

async function sendChatTurn(text) {
  if (chatBusy || !auth?.currentUser) return;
  chatBusy = true;
  chatThread.push({ role: "user", text });
  refreshChatScreen();
  try {
    const token = await auth.currentUser.getIdToken();
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ text, session_id: chatSessionId }),
    });
    if (!response.ok || !response.body) throw new Error(`chat failed: ${response.status}`);
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
        if (line) handleChatLine(JSON.parse(line));
      }
      if (done) break;
    }
  } catch {
    chatThread.push({ role: "agent", kind: "error", text: t("chatError") });
  } finally {
    chatBusy = false;
    refreshChatScreen();
  }
}

function handleChatLine(line) {
  if (line.session_id) chatSessionId = line.session_id;
  if (line.type === "ack") {
    chatThread.push({ role: "agent", kind: "ack", text: line.text });
  } else if (line.type === "reply") {
    if (line.text) chatThread.push({ role: "agent", text: line.text });
  } else if (line.type === "case") {
    chatCase = line.case || {};
  } else if (line.type === "error") {
    chatThread.push({ role: "agent", kind: "error", text: t("chatError") });
  }
  refreshChatScreen();
}

const templates = {
  dashboard: dashboardTemplate,
  chat: chatTemplate,
  crisis: crisisQuestionTemplate,
  "crisis-country": crisisCountryTemplate,
  "crisis-situation": crisisSituationTemplate,
  "crisis-route": crisisRouteTemplate,
  profile: profileTemplate,
};

function renderScreen(name = currentScreen) {
  currentScreen = name;
  screen.dataset.screen = name;
  screen.innerHTML = templates[name]();
  const isCrisis = name.startsWith("crisis");
  modeSwitcher.classList.toggle("hidden", name === "dashboard" || name === "profile");
  globalHelp.classList.toggle("hidden", name === "dashboard" || name === "profile" || isCrisis);
  modeSwitcher.querySelector('[data-mode-link="crisis"]').classList.toggle("active", isCrisis);
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
// the next visit starts clean.
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
  if (action === "crisis-country") {
    crisisDanger = button.dataset.danger === "true";
  }
  if (action === "panic-wipe") {
    button.disabled = true;
    panicWipe().finally(() => {
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
  } else if (form.dataset.form === "crisis-country") {
    crisisCountry = document.getElementById("crisis-country").value;
    navigate("crisis-situation");
  } else if (form.dataset.form === "crisis-situation") {
    navigate("crisis-route");
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
document.getElementById("disclaimer-help").addEventListener("click", () => navigate("crisis"));

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
      chatThread = [];
      chatCase = {};
      return;
    }
    userName = user.displayName || user.email || "";
    userId = user.uid || user.email || "signed-in-user";
    document.getElementById("account-name").textContent = userName;
    document.getElementById("avatar-initial").textContent = userName.trim().charAt(0).toUpperCase() || "G";
    renderScreen("dashboard");
    if (!localStorage.getItem(`gabay-disclaimer-accepted:${userId}`)) {
      dialog.showModal();
    }
  });
}
