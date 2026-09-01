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
    welcomeTitle: "Know your rights. Find the right help.",
    welcomeBody: "Compare your working conditions with standard OFW contract rules, or get routed to trusted help when you need it.",
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
    disclaimerTitle: "Before you begin",
    disclaimerBody: "Gabay OFW offers practical guidance and connects you with official support.",
    notLegalTitle: "Not legal advice.",
    notLegalBody: "Findings identify possible conflicts with standard rules. Verify them with DMW, OWWA, or a lawyer.",
    notEmergencyTitle: "Not an emergency service.",
    notEmergencyBody: "If you are in immediate danger, contact local emergency services or the nearest Philippine Embassy.",
    understand: "I understand",
    greeting: (name) => `Welcome, ${name}.`,
    dashboardTitle: "How can we help?",
    dashboardBody: "Choose a service. Gabay OFW will never guess which kind of help you need.",
    contractKicker: "Understand your working conditions",
    contractTitle: "Contract Check",
    contractBody: "Tell us what your contract says and what is happening at work. Receive a clear Findings Report.",
    contractCta: "Start Contract Check",
    crisisKicker: "Short, calm, and direct",
    crisisTitle: "Crisis Help",
    crisisBody: "Answer a few questions and get routed to the right official support.",
    crisisCta: "Get help now",
    recentTitle: "Your Contract Checks",
    recentEmpty: "No saved checks yet. Start a Contract Check when you are ready.",
    privacyTitle: "Built for privacy",
    privacyBody: "This preview does not save conversations. Stored Crisis Sessions are designed to expire automatically.",
    backDashboard: "Back to dashboard",
    contractIntroTitle: "Start with what changed",
    contractIntroBody: "Describe one concern at a time. You can use English, Tagalog, Taglish, or Bisaya.",
    contractPrompt: "What does your contract say, and what is actually happening?",
    contractPlaceholder: "Example: My contract says one rest day each week, but I have worked every day this month.",
    continue: "Continue",
    contractStep: "Contract Check",
    interviewerName: "Gabay Interviewer",
    sampleAssistant: "Salamat. To understand clearly, does your contract state that overtime or work on your rest day should be paid?",
    sampleUser: "Yes, it says overtime should be paid, but I have not received overtime pay.",
    viewReport: "View sample Findings Report",
    findingsTitle: "Your Findings Report",
    findingsIntro: "These findings appear to conflict with standard POEA/DMW contract rules. Verify them with DMW, OWWA, or a licensed lawyer.",
    urgent: "Urgent",
    concerning: "Concerning",
    informational: "Informational",
    restDayFinding: "Missing weekly rest day",
    restDayRule: "Standard OFW contracts require at least one rest day each week, with premium pay if worked.",
    overtimeFinding: "Unpaid overtime",
    overtimeRule: "Overtime should be paid at the POEA SEC rate or host-country rate, whichever is higher.",
    reportInfoTitle: "Keep your records",
    reportInfoRule: "Save copies of your verified contract, payslips, schedules, and messages where it is safe to do so.",
    done: "Done",
    crisisStep: "Crisis Help",
    crisisQuestionTitle: "Are you in physical danger right now?",
    crisisQuestionBody: "Choose the closest answer. We will give contact information without asking for unnecessary details.",
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
    routeTitle: "Contact trained support now",
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
    profileBody: "Optional details help keep future conversations relevant. Any destination country is accepted.",
    countryOptional: "Destination country (optional)",
    occupationOptional: "Occupation (optional)",
    countryPlaceholder: "Any country",
    occupationPlaceholder: "Example: Domestic worker",
    saveProfile: "Save profile",
    profileSaved: "Profile saved on this device.",
    deleteData: "Delete local profile",
    localProfileDeleted: "Local profile deleted.",
    otherCountry: "Other",
    signInFailed: (message) => `Sign-in failed: ${message}`,
    notConfigured: "Firebase sign-in is not configured yet.",
  },
  tl: {
    languageName: "Tagalog",
    loading: "Binubuksan ang iyong pribadong espasyo...",
    welcomeEyebrow: "Praktikal na suporta para sa Pilipinong manggagawa sa abroad",
    welcomeTitle: "Alamin ang karapatan. Hanapin ang tamang tulong.",
    welcomeBody: "Ihambing ang aktuwal na trabaho sa standard OFW contract rules, o magpaturo sa mapagkakatiwalaang tulong.",
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
    disclaimerTitle: "Bago magsimula",
    disclaimerBody: "Nagbibigay ang Gabay OFW ng praktikal na gabay at koneksiyon sa opisyal na suporta.",
    notLegalTitle: "Hindi legal na payo.",
    notLegalBody: "Posibleng paglabag lamang ang findings. I-verify sa DMW, OWWA, o abogado.",
    notEmergencyTitle: "Hindi emergency service.",
    notEmergencyBody: "Kung may agarang panganib, tumawag sa local emergency services o pinakamalapit na Philippine Embassy.",
    understand: "Naiintindihan ko",
    greeting: (name) => `Maligayang pagdating, ${name}.`,
    dashboardTitle: "Paano kami makakatulong?",
    dashboardBody: "Pumili ng serbisyo. Hindi huhulaan ng Gabay OFW kung anong tulong ang kailangan mo.",
    contractKicker: "Unawain ang iyong working conditions",
    contractTitle: "Contract Check",
    contractBody: "Ikuwento ang nasa kontrata at ang aktuwal na nangyayari. Makakuha ng malinaw na Findings Report.",
    contractCta: "Simulan ang Contract Check",
    crisisKicker: "Maikli, kalmado, at direkta",
    crisisTitle: "Crisis Help",
    crisisBody: "Sagutin ang ilang tanong at ituturo ka sa tamang opisyal na suporta.",
    crisisCta: "Humingi ng tulong",
    recentTitle: "Iyong mga Contract Check",
    recentEmpty: "Wala pang naka-save na check. Magsimula kapag handa ka na.",
    privacyTitle: "Dinisenyo para sa privacy",
    privacyBody: "Hindi sine-save ng preview na ito ang usapan. Dinisenyong awtomatikong mabura ang stored Crisis Sessions.",
    backDashboard: "Bumalik sa dashboard",
    contractIntroTitle: "Magsimula sa nagbago",
    contractIntroBody: "Isang concern muna. Puwede ang English, Tagalog, Taglish, o Bisaya.",
    contractPrompt: "Ano ang nasa kontrata, at ano ang aktuwal na nangyayari?",
    contractPlaceholder: "Halimbawa: May isang rest day bawat linggo sa kontrata, pero araw-araw akong nagtatrabaho ngayong buwan.",
    continue: "Magpatuloy",
    contractStep: "Contract Check",
    interviewerName: "Gabay Interviewer",
    sampleAssistant: "Salamat. Nakasaad ba sa kontrata na dapat bayaran ang overtime o trabaho sa rest day?",
    sampleUser: "Oo, dapat bayad ang overtime, pero wala akong natatanggap na overtime pay.",
    viewReport: "Tingnan ang sample Findings Report",
    findingsTitle: "Iyong Findings Report",
    findingsIntro: "Ang findings ay posibleng salungat sa standard POEA/DMW contract rules. I-verify sa DMW, OWWA, o lisensiyadong abogado.",
    urgent: "Agarang pansin",
    concerning: "Nakababahala",
    informational: "Impormasyon",
    restDayFinding: "Walang lingguhang rest day",
    restDayRule: "Nangangailangan ang standard OFW contract ng isang rest day bawat linggo at premium pay kung magtatrabaho.",
    overtimeFinding: "Hindi bayad na overtime",
    overtimeRule: "Dapat bayaran ang overtime sa POEA SEC rate o host-country rate, kung alin ang mas mataas.",
    reportInfoTitle: "Itago ang mga record",
    reportInfoRule: "Magtago ng kopya ng verified contract, payslip, schedule, at mensahe kung ligtas gawin.",
    done: "Tapos",
    crisisStep: "Crisis Help",
    crisisQuestionTitle: "Nasa pisikal na panganib ka ba ngayon?",
    crisisQuestionBody: "Piliin ang pinakamalapit na sagot. Ibibigay agad ang contact information nang hindi humihingi ng di-kailangang detalye.",
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
    routeTitle: "Makipag-ugnayan sa trained support ngayon",
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
    profileBody: "Opsiyonal ang detalye at makakatulong sa susunod na usapan. Tinatanggap ang anumang destination country.",
    countryOptional: "Destination country (opsiyonal)",
    occupationOptional: "Trabaho (opsiyonal)",
    countryPlaceholder: "Anumang bansa",
    occupationPlaceholder: "Halimbawa: Domestic worker",
    saveProfile: "I-save ang profile",
    profileSaved: "Na-save ang profile sa device na ito.",
    deleteData: "Burahin ang local profile",
    localProfileDeleted: "Nabura ang local profile.",
    otherCountry: "Ibang bansa",
    signInFailed: (message) => `Hindi nagtagumpay ang sign-in: ${message}`,
    notConfigured: "Hindi pa naka-configure ang Firebase sign-in.",
  },
  taglish: {
    languageName: "Taglish",
    loading: "Binubuksan ang private space mo...",
    welcomeEyebrow: "Practical support para sa Filipino workers abroad",
    welcomeTitle: "Know your rights. Hanapin ang tamang help.",
    welcomeBody: "I-compare ang actual work sa standard OFW contract rules, o magpa-route sa trusted help.",
    signIn: "Continue with Google",
    privacyNote: "Private sa account mo ang records. Never nagse-save ng password ang Gabay OFW.",
    owwaAlways: "Free at open 24/7 ang OWWA hotline para sa OFWs at families.",
    languageLabel: "Language",
    accountControls: "Account controls",
    serviceOverview: "Service overview",
    homeLabel: "Gabay OFW home",
    countries: ["Saudi Arabia", "United Arab Emirates", "Qatar", "Kuwait", "Bahrain", "Oman"],
    profile: "Profile",
    signOut: "Sign out",
    needHelp: "I Need Help Now",
    disclaimerTitle: "Bago tayo magsimula",
    disclaimerBody: "Practical guidance at official support links ang binibigay ng Gabay OFW.",
    notLegalTitle: "Hindi legal advice.",
    notLegalBody: "Possible conflicts lang ang findings. I-verify sa DMW, OWWA, or lawyer.",
    notEmergencyTitle: "Hindi emergency service.",
    notEmergencyBody: "Kung immediate danger, contact local emergency services or nearest Philippine Embassy.",
    understand: "Gets ko",
    greeting: (name) => `Welcome, ${name}.`,
    dashboardTitle: "How can we help?",
    dashboardBody: "Pumili ng service. Hindi huhulaan ng Gabay OFW kung anong help ang kailangan mo.",
    contractKicker: "Understand your working conditions",
    contractTitle: "Contract Check",
    contractBody: "Sabihin ang nasa contract at actual na nangyayari. Get a clear Findings Report.",
    contractCta: "Start Contract Check",
    crisisKicker: "Short, calm, and direct",
    crisisTitle: "Crisis Help",
    crisisBody: "Answer a few questions para ma-route sa tamang official support.",
    crisisCta: "Get help now",
    recentTitle: "Your Contract Checks",
    recentEmpty: "Wala pang saved checks. Start when ready.",
    privacyTitle: "Built for privacy",
    privacyBody: "Hindi nagsa-save ng conversations ang preview. Designed to expire automatically ang stored Crisis Sessions.",
    backDashboard: "Back to dashboard",
    contractIntroTitle: "Start with what changed",
    contractIntroBody: "One concern at a time. Puwede ang English, Tagalog, Taglish, or Bisaya.",
    contractPrompt: "Ano ang nasa contract, at ano ang actual na nangyayari?",
    contractPlaceholder: "Example: One rest day weekly ang contract, pero everyday akong working this month.",
    continue: "Continue",
    contractStep: "Contract Check",
    interviewerName: "Gabay Interviewer",
    sampleAssistant: "Salamat. Nakalagay ba sa contract na paid ang overtime or work on rest day?",
    sampleUser: "Yes, paid dapat ang overtime, pero wala akong overtime pay.",
    viewReport: "View sample Findings Report",
    findingsTitle: "Your Findings Report",
    findingsIntro: "These findings may conflict with standard POEA/DMW contract rules. I-verify sa DMW, OWWA, or licensed lawyer.",
    urgent: "Urgent",
    concerning: "Concerning",
    informational: "Informational",
    restDayFinding: "Missing weekly rest day",
    restDayRule: "Standard OFW contracts require one rest day weekly, with premium pay if worked.",
    overtimeFinding: "Unpaid overtime",
    overtimeRule: "Overtime should use the higher of the POEA SEC rate or host-country rate.",
    reportInfoTitle: "Keep your records",
    reportInfoRule: "Save copies of your verified contract, payslips, schedules, and messages if safe.",
    done: "Done",
    crisisStep: "Crisis Help",
    crisisQuestionTitle: "Nasa physical danger ka ba ngayon?",
    crisisQuestionBody: "Choose the closest answer. Ibibigay agad ang contact details without unnecessary questions.",
    dangerYes: "Yes, or hindi ako safe na makaalis",
    dangerNo: "No, safe kong magagamit ang phone",
    countryTitle: "Which country are you in?",
    countryLabel: "Country",
    chooseCountry: "Choose a country",
    situationTitle: "What kind of help do you need?",
    situationBody: "Short description lang. Huwag mag-share ng passport number, address, or sensitive details.",
    situationLabel: "One-line description",
    situationPlaceholder: "Example: Hawak ng employer ko ang passport ko.",
    showHelp: "Show official help",
    routeTitle: "Contact trained support now",
    routeBody: "For safety threats, confinement, or trafficking concerns, these free services can help.",
    mwoRouteTitle: "Contact your Migrant Workers Office",
    mwoRouteBody: (country) => `For a concern without immediate danger in ${country}, contact the official MWO or OWWA.`,
    actionline: "Actionline Against Human Trafficking",
    owwa: "OWWA 24/7 Hotline",
    embassy: "Find the nearest Philippine Embassy or MWO",
    officialDirectory: "Open official DMW directory",
    reassurance: "Hindi ka nag-iisa. These offices exist to help OFWs in your situation, at free ang pag-reach out.",
    call: (number) => `Call ${number}`,
    profileTitle: "Your profile",
    profileBody: "Optional details help future conversations. Any destination country is accepted.",
    countryOptional: "Destination country (optional)",
    occupationOptional: "Occupation (optional)",
    countryPlaceholder: "Any country",
    occupationPlaceholder: "Example: Domestic worker",
    saveProfile: "Save profile",
    profileSaved: "Saved ang profile sa device na ito.",
    deleteData: "Delete local profile",
    localProfileDeleted: "Deleted ang local profile.",
    otherCountry: "Other",
    signInFailed: (message) => `Sign-in failed: ${message}`,
    notConfigured: "Hindi pa configured ang Firebase sign-in.",
  },
  ceb: {
    languageName: "Bisaya",
    loading: "Giablihan ang imong pribadong luna...",
    welcomeEyebrow: "Praktikal nga suporta para sa Pilipinong trabahante sa abroad",
    welcomeTitle: "Hibaloa ang katungod. Pangitaa ang hustong tabang.",
    welcomeBody: "Itandi ang aktuwal nga trabaho sa standard OFW contract rules, o magpatudlo sa kasaligan nga tabang.",
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
    disclaimerTitle: "Sa dili pa magsugod",
    disclaimerBody: "Naghatag ang Gabay OFW og praktikal nga giya ug koneksiyon sa opisyal nga suporta.",
    notLegalTitle: "Dili legal nga tambag.",
    notLegalBody: "Posibleng conflict lang ang findings. I-verify sa DMW, OWWA, o abogado.",
    notEmergencyTitle: "Dili emergency service.",
    notEmergencyBody: "Kung naa sa diha-diha nga peligro, kontaka ang local emergency services o duol nga Philippine Embassy.",
    understand: "Nasabtan nako",
    greeting: (name) => `Maayong pag-abot, ${name}.`,
    dashboardTitle: "Unsaon namo pagtabang?",
    dashboardBody: "Pilia ang serbisyo. Dili tag-anon sa Gabay OFW ang tabang nga imong kinahanglan.",
    contractKicker: "Sabta ang imong working conditions",
    contractTitle: "Contract Check",
    contractBody: "Isulti ang naa sa kontrata ug ang aktuwal nga nahitabo. Dawata ang klarong Findings Report.",
    contractCta: "Sugdi ang Contract Check",
    crisisKicker: "Mubo, kalmado, ug direkta",
    crisisTitle: "Crisis Help",
    crisisBody: "Tubaga ang pipila ka pangutana ug itudlo ka sa hustong opisyal nga suporta.",
    crisisCta: "Pangayo og tabang",
    recentTitle: "Imong mga Contract Check",
    recentEmpty: "Wala pay na-save nga check. Sugdi kung andam na.",
    privacyTitle: "Gidisenyo para sa privacy",
    privacyBody: "Dili i-save sa preview ang panag-istorya. Gidisenyo nga awtomatikong mapapas ang stored Crisis Sessions.",
    backDashboard: "Balik sa dashboard",
    contractIntroTitle: "Sugdi sa nausab",
    contractIntroBody: "Usa ka concern matag higayon. Puwede English, Tagalog, Taglish, o Bisaya.",
    contractPrompt: "Unsa ang giingon sa kontrata, ug unsa ang aktuwal nga nahitabo?",
    contractPlaceholder: "Pananglitan: Usa ka rest day kada semana ang kontrata, pero adlaw-adlaw ko nagtrabaho karong buwana.",
    continue: "Padayon",
    contractStep: "Contract Check",
    interviewerName: "Gabay Interviewer",
    sampleAssistant: "Salamat. Naa ba sa kontrata nga bayran ang overtime o trabaho sa rest day?",
    sampleUser: "Oo, bayran unta ang overtime, pero wala koy nadawat nga overtime pay.",
    viewReport: "Tan-awa ang sample Findings Report",
    findingsTitle: "Imong Findings Report",
    findingsIntro: "Posibleng supak ang findings sa standard POEA/DMW contract rules. I-verify sa DMW, OWWA, o lisensiyadong abogado.",
    urgent: "Dinalian",
    concerning: "Makapabalaka",
    informational: "Impormasyon",
    restDayFinding: "Walay senemanang rest day",
    restDayRule: "Ang standard OFW contract nanginahanglan og usa ka rest day kada semana ug premium pay kung motrabaho.",
    overtimeFinding: "Wala nabayrang overtime",
    overtimeRule: "Bayran ang overtime sa POEA SEC rate o host-country rate, kung asa ang mas taas.",
    reportInfoTitle: "Tipigi ang records",
    reportInfoRule: "Tipigi ang kopya sa verified contract, payslip, schedule, ug mensahe kung luwas.",
    done: "Human",
    crisisStep: "Crisis Help",
    crisisQuestionTitle: "Naa ka ba sa pisikal nga peligro karon?",
    crisisQuestionBody: "Pilia ang pinakaduol nga tubag. Ihatag dayon ang contact information nga walay dili kinahanglan nga pangutana.",
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
    routeTitle: "Kontaka ang trained support karon",
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
    profileBody: "Opsiyonal ang detalye ug makatabang sa umaabot nga panag-istorya. Dawaton ang bisan unsang destination country.",
    countryOptional: "Destination country (opsiyonal)",
    occupationOptional: "Trabaho (opsiyonal)",
    countryPlaceholder: "Bisan unsang nasod",
    occupationPlaceholder: "Pananglitan: Domestic worker",
    saveProfile: "I-save ang profile",
    profileSaved: "Na-save ang profile sa device.",
    deleteData: "Papasa ang local profile",
    localProfileDeleted: "Napapas ang local profile.",
    otherCountry: "Ubang nasod",
    signInFailed: (message) => `Wala molampos ang sign-in: ${message}`,
    notConfigured: "Wala pa ma-configure ang Firebase sign-in.",
  },
};

const screen = document.getElementById("screen");
const screenLoading = document.getElementById("screen-loading");
const app = document.getElementById("signed-in");
const signedOut = document.getElementById("signed-out");
const authLoading = document.getElementById("auth-loading");
const dialog = document.getElementById("first-run-dialog");
const languageSelects = document.querySelectorAll(".language-select");
const status = document.getElementById("status");

let language = localStorage.getItem("gabay-language") || "en";
let currentScreen = "dashboard";
let userName = "";
let userId = "";
let contractDraft = "";
let crisisDanger = false;
let crisisCountry = "";

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
  document.documentElement.lang = language === "tl" || language === "taglish" ? "tl" : language;
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
      ...Object.keys(copy).map((key) => {
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
  return `
    <section>
      <header class="screen-header">
        <div>
          <p class="user-greeting">${escapeHtml(t("greeting", userName))}</p>
          <h1>${t("dashboardTitle")}</h1>
          <p>${t("dashboardBody")}</p>
        </div>
      </header>
      <div class="mode-grid">
        <button class="mode-card" type="button" data-action="contract-intro">
          <span class="mode-kicker">${t("contractKicker")}</span>
          <span>
            <h2>${t("contractTitle")}</h2>
            <p>${t("contractBody")}</p>
            <span class="mode-cta">${t("contractCta")}</span>
          </span>
        </button>
        <button class="mode-card crisis-card" type="button" data-action="crisis">
          <span class="mode-kicker">${t("crisisKicker")}</span>
          <span>
            <h2>${t("crisisTitle")}</h2>
            <p>${t("crisisBody")}</p>
            <span class="mode-cta">${t("crisisCta")}</span>
          </span>
        </button>
      </div>
      <div class="dashboard-lower">
        <section class="plain-section">
          <h3>${t("recentTitle")}</h3>
          <p class="empty-state">${t("recentEmpty")}</p>
        </section>
        <section class="plain-section">
          <h3>${t("privacyTitle")}</h3>
          <p>${t("privacyBody")}</p>
        </section>
      </div>
    </section>`;
}

function flowNav(label) {
  return `<nav class="flow-nav" aria-label="${escapeHtml(label)}">
    <button class="button quiet" type="button" data-action="dashboard">${t("backDashboard")}</button>
    <span class="step-label">${label}</span>
  </nav>`;
}

function contractIntroTemplate() {
  return `<section class="flow-shell">
    ${flowNav(t("contractStep"))}
    <form class="question-card" data-form="contract-intro">
      <h1>${t("contractIntroTitle")}</h1>
      <p>${t("contractIntroBody")}</p>
      <div class="field">
        <label for="contract-message">${t("contractPrompt")}</label>
        <textarea id="contract-message" required maxlength="4000" placeholder="${escapeHtml(t("contractPlaceholder"))}">${escapeHtml(contractDraft)}</textarea>
      </div>
      <button class="button primary" type="submit">${t("continue")}</button>
    </form>
  </section>`;
}

function contractChatTemplate() {
  return `<section class="flow-shell">
    ${flowNav(t("contractStep"))}
    <h1>${t("interviewerName")}</h1>
    <div class="chat-thread" aria-live="polite">
      <div class="message user">${escapeHtml(contractDraft || t("contractPlaceholder"))}</div>
      <div class="message assistant">${t("sampleAssistant")}</div>
      <div class="message user">${t("sampleUser")}</div>
    </div>
    <button class="button primary" type="button" data-action="findings">${t("viewReport")}</button>
  </section>`;
}

function findingsTemplate() {
  return `<section class="flow-shell">
    ${flowNav(t("contractStep"))}
    <article class="report">
      <h1>${t("findingsTitle")}</h1>
      <p class="report-intro">${t("findingsIntro")}</p>
      <div class="finding-list">
        <section class="finding urgent">
          <span class="severity">${t("urgent")}</span>
          <h3>${t("restDayFinding")}</h3>
          <p>${t("restDayRule")}</p>
        </section>
        <section class="finding concerning">
          <span class="severity">${t("concerning")}</span>
          <h3>${t("overtimeFinding")}</h3>
          <p>${t("overtimeRule")}</p>
        </section>
        <section class="finding informational">
          <span class="severity">${t("informational")}</span>
          <h3>${t("reportInfoTitle")}</h3>
          <p>${t("reportInfoRule")}</p>
        </section>
      </div>
      <div class="button-row" style="margin-top: 1.5rem">
        <button class="button primary" type="button" data-action="dashboard">${t("done")}</button>
      </div>
    </article>
  </section>`;
}

function crisisQuestionTemplate() {
  return `<section class="flow-shell">
    ${flowNav(t("crisisStep"))}
    <div class="question-card">
      <h1>${t("crisisQuestionTitle")}</h1>
      <p>${t("crisisQuestionBody")}</p>
      <div class="choice-stack">
        <button class="choice" type="button" data-action="crisis-country" data-danger="true">${t("dangerYes")}</button>
        <button class="choice" type="button" data-action="crisis-country" data-danger="false">${t("dangerNo")}</button>
      </div>
    </div>
  </section>`;
}

function crisisCountryTemplate() {
  return `<section class="flow-shell">
    ${flowNav(t("crisisStep"))}
    <form class="question-card" data-form="crisis-country">
      <h1>${t("countryTitle")}</h1>
      <div class="field">
        <label for="crisis-country">${t("countryLabel")}</label>
        <select id="crisis-country" required>
          <option value="">${t("chooseCountry")}</option>
          ${t("countries").map((country) => `<option${country === crisisCountry ? " selected" : ""}>${country}</option>`).join("")}
          <option value="Other"${crisisCountry === "Other" ? " selected" : ""}>${t("otherCountry")}</option>
        </select>
      </div>
      <button class="button primary" type="submit">${t("continue")}</button>
    </form>
  </section>`;
}

function crisisSituationTemplate() {
  return `<section class="flow-shell">
    ${flowNav(t("crisisStep"))}
    <form class="question-card" data-form="crisis-situation">
      <h1>${t("situationTitle")}</h1>
      <p>${t("situationBody")}</p>
      <div class="field">
        <label for="crisis-situation">${t("situationLabel")}</label>
        <textarea id="crisis-situation" required maxlength="500" placeholder="${escapeHtml(t("situationPlaceholder"))}"></textarea>
      </div>
      <button class="button primary" type="submit">${t("showHelp")}</button>
    </form>
  </section>`;
}

function crisisRouteTemplate() {
  const routeTitle = crisisDanger ? t("routeTitle") : t("mwoRouteTitle");
  const routeBody = crisisDanger
    ? t("routeBody")
    : t("mwoRouteBody", crisisCountry || t("otherCountry"));
  return `<section class="flow-shell">
    ${flowNav(t("crisisStep"))}
    <article class="report">
      <h1>${routeTitle}</h1>
      <p class="report-intro">${routeBody}</p>
      ${crisisDanger ? `<section class="route-card">
        <h3>${t("actionline")}</h3>
        <p class="route-number">1343</p>
        <a href="tel:1343">${t("call", "1343")}</a>
      </section>` : ""}
      <section class="route-card">
        <h3>${t("owwa")}</h3>
        <p class="route-number">1348</p>
        <a href="tel:1348">${t("call", "1348")}</a>
      </section>
      <section class="route-card">
        <h3>${t("embassy")}</h3>
        <a href="https://dmw.gov.ph/" target="_blank" rel="noopener noreferrer">${t("officialDirectory")}</a>
      </section>
      <p class="reassurance">${t("reassurance")}</p>
      <button class="button" type="button" data-action="dashboard">${t("done")}</button>
    </article>
  </section>`;
}

function profileTemplate() {
  const profile = JSON.parse(localStorage.getItem(`gabay-profile:${userId}`) || "{}");
  return `<section class="flow-shell">
    ${flowNav(t("profile"))}
    <form class="profile-form" data-form="profile">
      <h1>${t("profileTitle")}</h1>
      <p>${t("profileBody")}</p>
      <div class="field">
        <label for="profile-country">${t("countryOptional")}</label>
        <input id="profile-country" name="country" value="${escapeHtml(profile.country || "")}" placeholder="${escapeHtml(t("countryPlaceholder"))}">
      </div>
      <div class="field">
        <label for="profile-occupation">${t("occupationOptional")}</label>
        <input id="profile-occupation" name="occupation" value="${escapeHtml(profile.occupation || "")}" placeholder="${escapeHtml(t("occupationPlaceholder"))}">
      </div>
      <div class="button-row">
        <button class="button primary" type="submit">${t("saveProfile")}</button>
        <button class="button danger" type="button" data-action="delete-profile">${t("deleteData")}</button>
      </div>
    </form>
  </section>`;
}

const templates = {
  dashboard: dashboardTemplate,
  "contract-intro": contractIntroTemplate,
  "contract-chat": contractChatTemplate,
  findings: findingsTemplate,
  crisis: crisisQuestionTemplate,
  "crisis-country": crisisCountryTemplate,
  "crisis-situation": crisisSituationTemplate,
  "crisis-route": crisisRouteTemplate,
  profile: profileTemplate,
};

function renderScreen(name = currentScreen) {
  currentScreen = name;
  screen.innerHTML = templates[name]();
  screen.focus({ preventScroll: true });
}

function navigate(name) {
  screen.classList.add("hidden");
  screenLoading.classList.remove("hidden");
  window.setTimeout(() => {
    renderScreen(name);
    screenLoading.classList.add("hidden");
    screen.classList.remove("hidden");
  }, 120);
}

function showStatus(message) {
  status.textContent = message;
  status.classList.remove("hidden");
  window.setTimeout(() => status.classList.add("hidden"), 2600);
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const action = button.dataset.action;
  if (action === "crisis-country") {
    crisisDanger = button.dataset.danger === "true";
  }
  if (action === "delete-profile") {
    localStorage.removeItem(`gabay-profile:${userId}`);
    renderScreen("profile");
    showStatus(t("localProfileDeleted"));
    return;
  }
  navigate(action);
});

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!form.dataset.form) return;
  event.preventDefault();
  if (form.dataset.form === "contract-intro") {
    contractDraft = document.getElementById("contract-message").value.trim();
    navigate("contract-chat");
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
    if (!user) return;
    userName = user.displayName || user.email || "";
    userId = user.uid || user.email || "signed-in-user";
    renderScreen("dashboard");
    if (!localStorage.getItem(`gabay-disclaimer-accepted:${userId}`)) {
      dialog.showModal();
    }
  });
}
