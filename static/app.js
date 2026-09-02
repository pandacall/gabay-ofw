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
    contractTab: "My contract",
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
    contractKicker: "Understand your working conditions",
    contractTitle: "Contract Check",
    contractBody: "Tell us what your contract says and what is happening at work. Receive a clear Findings Report.",
    contractCta: "Start Contract Check",
    crisisKicker: "Short, calm, and direct",
    crisisTitle: "Crisis Help",
    crisisBody: "Tell us what is happening and we will connect you with the right official support.",
    crisisCta: "Get help now",
    contractTime: "About five minutes",
    crisisTime: "Straight to the right number",
    recentTitle: "Your Contract Checks",
    recentEmpty: "No saved checks yet. Start a Contract Check when you are ready.",
    privacyTitle: "Built for privacy",
    privacyBody: "This preview does not save conversations. Stored Crisis Sessions are designed to expire automatically.",
    backDashboard: "Back to dashboard",
    contractIntroBody: "Talk to us about what is happening. You can use English, Tagalog, Taglish, or Bisaya.",
    contractPrompt: "Talk to us about what your contract says and what is actually happening.",
    contractPlaceholder: "Example: My contract says one rest day each week, but I have worked every day this month.",
    continue: "Continue",
    contractStep: "Contract Check",
    conversationHint: "Take your time. Talk to us in your own words.",
    typeAnswer: "Type your message",
    voiceInput: "Use voice",
    photoContract: "Photograph my contract",
    voicePrototype: "Voice input is a prototype for now. Nothing is being recorded.",
    photoPrototype: "Contract photography is a prototype for now. Nothing was opened or uploaded.",
    sampleAssistant: "Salamat. Tell us whether your contract says overtime or work on your rest day should be paid.",
    viewReport: "View sample Findings Report",
    findingsTitle: "Two of these are serious.",
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
    contractTab: "Kontrata ko",
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
    contractKicker: "Unawain ang iyong working conditions",
    contractTitle: "Contract Check",
    contractBody: "Ikuwento ang nasa kontrata at ang aktuwal na nangyayari. Makakuha ng malinaw na Findings Report.",
    contractCta: "Simulan ang Contract Check",
    crisisKicker: "Maikli, kalmado, at direkta",
    crisisTitle: "Crisis Help",
    crisisBody: "Kuwento mo ang nangyayari at ituturo ka namin sa tamang opisyal na suporta.",
    crisisCta: "Humingi ng tulong",
    contractTime: "Mga limang minuto",
    crisisTime: "Diretso sa tamang numero",
    recentTitle: "Iyong mga Contract Check",
    recentEmpty: "Wala pang naka-save na check. Magsimula kapag handa ka na.",
    privacyTitle: "Dinisenyo para sa privacy",
    privacyBody: "Hindi sine-save ng preview na ito ang usapan. Dinisenyong awtomatikong mabura ang stored Crisis Sessions.",
    backDashboard: "Bumalik sa dashboard",
    contractIntroBody: "Kuwento mo sa amin ang nangyayari. Puwede ang English, Tagalog, Taglish, o Bisaya.",
    contractPrompt: "Kuwento mo kung ano ang nasa kontrata at kung ano ang aktuwal na nangyayari.",
    contractPlaceholder: "Halimbawa: May isang rest day bawat linggo sa kontrata, pero araw-araw akong nagtatrabaho ngayong buwan.",
    continue: "Magpatuloy",
    contractStep: "Contract Check",
    conversationHint: "Dahan-dahan lang. Magkuwento sa sarili mong salita.",
    typeAnswer: "I-type ang mensahe",
    voiceInput: "Gamitin ang boses",
    photoContract: "Kunan ng litrato ang kontrata",
    voicePrototype: "Prototype pa ang voice input. Walang nire-record.",
    photoPrototype: "Prototype pa ang contract photo. Walang camera o upload na binuksan.",
    sampleAssistant: "Salamat. Kuwento mo kung nakasaad sa kontrata na dapat bayaran ang overtime o trabaho sa rest day.",
    viewReport: "Tingnan ang sample Findings Report",
    findingsTitle: "Dalawa rito ay seryoso.",
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
    welcomeTitle: "Following ba ng work mo ang contract?",
    welcomeBody: "Tell us what's happening. Tutulungan ka naming makita ang hindi match at kung sino ang puwedeng tawagan.",
    welcomeStepOne: "Tell us in your own words",
    welcomeStepTwo: "See what may not match",
    welcomeStepThree: "Find the right person to call",
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
    modeNavigation: "Choose a service",
    contractTab: "My contract",
    helpTab: "Help now",
    disclaimerTitle: "Bago tayo magsimula",
    disclaimerBody: "Practical guidance at official support links ang binibigay ng Gabay OFW.",
    notLegalTitle: "Hindi legal advice.",
    notLegalBody: "Possible conflicts lang ang findings. I-verify sa DMW, OWWA, or lawyer.",
    notEmergencyTitle: "Hindi emergency service.",
    notEmergencyBody: "Kung immediate danger, contact local emergency services or nearest Philippine Embassy.",
    understand: "Gets ko",
    greeting: (name) => `Welcome, ${name}.`,
    dashboardTitle: "What do you need?",
    dashboardBody: "Pumili ng service. Hindi huhulaan ng Gabay OFW kung anong help ang kailangan mo.",
    contractKicker: "Understand your working conditions",
    contractTitle: "Contract Check",
    contractBody: "Sabihin ang nasa contract at actual na nangyayari. Get a clear Findings Report.",
    contractCta: "Start Contract Check",
    crisisKicker: "Short, calm, and direct",
    crisisTitle: "Crisis Help",
    crisisBody: "Tell us what's happening para ma-connect ka sa tamang official support.",
    crisisCta: "Get help now",
    contractTime: "About five minutes",
    crisisTime: "Straight to the right number",
    recentTitle: "Your Contract Checks",
    recentEmpty: "Wala pang saved checks. Start when ready.",
    privacyTitle: "Built for privacy",
    privacyBody: "Hindi nagsa-save ng conversations ang preview. Designed to expire automatically ang stored Crisis Sessions.",
    backDashboard: "Back to dashboard",
    contractIntroBody: "Tell us what's happening. Puwede ang English, Tagalog, Taglish, or Bisaya.",
    contractPrompt: "Tell us what your contract says and what's actually happening.",
    contractPlaceholder: "Example: One rest day weekly ang contract, pero everyday akong working this month.",
    continue: "Continue",
    contractStep: "Contract Check",
    conversationHint: "Take your time. Tell us in your own words.",
    typeAnswer: "Type your message",
    voiceInput: "Use voice",
    photoContract: "Photograph my contract",
    voicePrototype: "Prototype pa ang voice input. Nothing is being recorded.",
    photoPrototype: "Prototype pa ang contract photo. Walang camera or upload na binuksan.",
    sampleAssistant: "Salamat. Tell us kung nakalagay sa contract na paid ang overtime or work on rest day.",
    viewReport: "View sample Findings Report",
    findingsTitle: "Two of these are serious.",
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
    crisisQuestionBody: "Choose what feels closest sa situation mo. Ibibigay agad ang contact details without asking for details we do not need.",
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
    routeTitle: "Call one of these now. All are free.",
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
    contractTab: "Akong kontrata",
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
    contractKicker: "Sabta ang imong working conditions",
    contractTitle: "Contract Check",
    contractBody: "Isulti ang naa sa kontrata ug ang aktuwal nga nahitabo. Dawata ang klarong Findings Report.",
    contractCta: "Sugdi ang Contract Check",
    crisisKicker: "Mubo, kalmado, ug direkta",
    crisisTitle: "Crisis Help",
    crisisBody: "Isulti unsay nahitabo ug itudlo ka namo sa hustong opisyal nga suporta.",
    crisisCta: "Pangayo og tabang",
    contractTime: "Mga lima ka minuto",
    crisisTime: "Diretso sa hustong numero",
    recentTitle: "Imong mga Contract Check",
    recentEmpty: "Wala pay na-save nga check. Sugdi kung andam na.",
    privacyTitle: "Gidisenyo para sa privacy",
    privacyBody: "Dili i-save sa preview ang panag-istorya. Gidisenyo nga awtomatikong mapapas ang stored Crisis Sessions.",
    backDashboard: "Balik sa dashboard",
    contractIntroBody: "Isulti kanamo unsay nahitabo. Puwede English, Tagalog, Taglish, o Bisaya.",
    contractPrompt: "Isulti kanamo unsay giingon sa kontrata ug unsay aktuwal nga nahitabo.",
    contractPlaceholder: "Pananglitan: Usa ka rest day kada semana ang kontrata, pero adlaw-adlaw ko nagtrabaho karong buwana.",
    continue: "Padayon",
    contractStep: "Contract Check",
    conversationHint: "Ayaw pagdali. Isulti sa imong kaugalingong mga pulong.",
    typeAnswer: "I-type ang mensahe",
    voiceInput: "Gamita ang tingog",
    photoContract: "Litrati ang akong kontrata",
    voicePrototype: "Prototype pa ang voice input. Walay gi-record.",
    photoPrototype: "Prototype pa ang contract photo. Walay camera o upload nga giablihan.",
    sampleAssistant: "Salamat. Isulti kung naa sa kontrata nga bayran ang overtime o trabaho sa rest day.",
    viewReport: "Tan-awa ang sample Findings Report",
    findingsTitle: "Duha niini seryoso.",
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
  contractTitle: "Check my contract",
  contractBody: "A calm conversation about your hours, pay, rest days, and papers. Stop and come back whenever you like.",
  contractCta: "Start talking",
  crisisTitle: "I need help now",
  crisisBody: "Tell us what is happening, then see the numbers that can help tonight.",
  topicPrompt: "Or start with what is happening",
  topicPassport: "They keep my passport",
  topicPay: "I am not paid",
  topicRest: "No rest day",
  topicLeave: "I cannot go out",
  switchAnytime: "You can move between the two at any time.",
  currentTopic: "Now talking about your contract and work",
  summaryTitle: "What you have told us",
  summaryConcern: "Your concern",
  summaryActive: "Talking now",
  summaryEdit: "Anything here can be changed before we make your list.",
  verifyTitle: "Verify the details",
  verifyRule: "Bring this list to DMW, OWWA, or a licensed lawyer. They decide, not Gabay OFW.",
  resultCount: (current) => `${current} of 4`,
  youSaid: "You said",
  contractSays: "Standard contract",
  restDaySaid: "You said you work every day.",
  restDayContract: "Standard contracts include a weekly rest day.",
  overtimeSaid: "You said overtime has not been paid.",
  overtimeContract: "Extra hours should be paid under the applicable contract.",
  recordsSaid: "Your records can support what you shared.",
  recordsContract: "Keep copies only where it is safe.",
  verifySaid: "This list reflects only what you told us.",
  verifyContract: "An official adviser can verify each item.",
  takeToPerson: "Take this to a person",
  takeToPersonBody: "We will show you OWWA, the Actionline, and the official Migrant Workers Office directory.",
  saveCopy: "Save a copy",
  readToMe: "Read it to me",
  reportPrivacy: "This list is built only from what you told us. It is not a legal decision, and nothing has been sent anywhere.",
  savePrototype: "Saving a report is a prototype for now. Nothing was downloaded.",
  readPrototype: "Read-aloud is a prototype for now. No audio was started.",
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
  contractTitle: "Suriin ang kontrata ko",
  contractBody: "Isang kalmadong usapan tungkol sa oras, sahod, rest day, at papeles mo. Huminto at bumalik anumang oras.",
  contractCta: "Magsimulang magkuwento",
  crisisTitle: "Kailangan ko ng tulong ngayon",
  crisisBody: "Kuwento mo ang nangyayari, pagkatapos ay tingnan ang mga numerong makakatulong ngayong gabi.",
  topicPrompt: "O magsimula sa nangyayari",
  topicPassport: "Hawak nila ang passport ko",
  topicPay: "Hindi ako binabayaran",
  topicRest: "Walang rest day",
  topicLeave: "Hindi ako makalabas",
  switchAnytime: "Puwede kang lumipat sa dalawa anumang oras.",
  currentTopic: "Pinag-uusapan ngayon ang kontrata at trabaho mo",
  summaryTitle: "Ang naikuwento mo",
  summaryConcern: "Concern mo",
  summaryActive: "Pinag-uusapan ngayon",
  summaryEdit: "Puwedeng baguhin ang anumang narito bago namin buuin ang listahan mo.",
  verifyTitle: "Ipa-verify ang detalye",
  verifyRule: "Dalhin ang listahang ito sa DMW, OWWA, o lisensiyadong abogado. Sila ang magpapasya, hindi ang Gabay OFW.",
  resultCount: (current) => `${current} sa 4`,
  youSaid: "Sinabi mo",
  contractSays: "Standard contract",
  restDaySaid: "Sinabi mong araw-araw kang nagtatrabaho.",
  restDayContract: "May lingguhang rest day sa standard contracts.",
  overtimeSaid: "Sinabi mong hindi binayaran ang overtime.",
  overtimeContract: "Dapat bayaran ang extra hours ayon sa naaangkop na kontrata.",
  recordsSaid: "Makakatulong ang records sa naikuwento mo.",
  recordsContract: "Magtago lamang ng kopya kung ligtas.",
  verifySaid: "Ang listahang ito ay mula lamang sa sinabi mo.",
  verifyContract: "Maaaring i-verify ng opisyal na adviser ang bawat item.",
  takeToPerson: "Dalhin ito sa isang tao",
  takeToPersonBody: "Ipapakita namin ang OWWA, Actionline, at opisyal na Migrant Workers Office directory.",
  saveCopy: "Mag-save ng kopya",
  readToMe: "Basahin sa akin",
  reportPrivacy: "Mula lamang sa sinabi mo ang listahang ito. Hindi ito legal na desisyon, at walang ipinadala kahit saan.",
  savePrototype: "Prototype pa ang pag-save ng report. Walang na-download.",
  readPrototype: "Prototype pa ang pagbasa nang malakas. Walang audio na nagsimula.",
});

Object.assign(copy.taglish, {
  howItWorks: "How it works",
  privacyLink: "Your privacy",
  callOwwa: "Call OWWA 1348",
  startNow: "Start now",
  signInBody: "Signing in keeps the conversation private to you. Walang sasabihin sa work mo.",
  signIn: "Sign in with Google",
  trustFree: "Free",
  trustPrivate: "Private to you",
  trustNoAds: "No ads",
  dangerTonight: "In danger tonight? Call OWWA anytime. Free from any phone.",
  greeting: (name) => `${name}, what do you need?`,
  dashboardBody: "Choose where to begin. Puwede kang lumipat sa both kinds of support anytime.",
  contractTitle: "Check my contract",
  contractBody: "A calm conversation about your hours, pay, rest days, and papers. Stop and come back anytime.",
  contractCta: "Start talking",
  crisisTitle: "I need help now",
  crisisBody: "Tell us what is happening, then see the numbers that can help tonight.",
  topicPrompt: "Or start with what is happening",
  topicPassport: "Hawak nila ang passport ko",
  topicPay: "Hindi ako binabayaran",
  topicRest: "No rest day",
  topicLeave: "Hindi ako makalabas",
  switchAnytime: "Puwede kang lumipat sa dalawa anytime.",
  currentTopic: "Now talking about your contract and work",
  summaryTitle: "What you have told us",
  summaryConcern: "Your concern",
  summaryActive: "Talking now",
  summaryEdit: "Anything here can be changed before we make your list.",
  verifyTitle: "Verify the details",
  verifyRule: "Bring this list to DMW, OWWA, or a licensed lawyer. Sila ang magde-decide, not Gabay OFW.",
  resultCount: (current) => `${current} of 4`,
  youSaid: "You said",
  contractSays: "Standard contract",
  restDaySaid: "You said you work every day.",
  restDayContract: "Standard contracts include a weekly rest day.",
  overtimeSaid: "You said hindi paid ang overtime.",
  overtimeContract: "Extra hours should be paid under the applicable contract.",
  recordsSaid: "Your records can support what you shared.",
  recordsContract: "Keep copies only where it is safe.",
  verifySaid: "This list reflects only what you told us.",
  verifyContract: "An official adviser can verify each item.",
  takeToPerson: "Take this to a person",
  takeToPersonBody: "We will show you OWWA, the Actionline, and the official Migrant Workers Office directory.",
  saveCopy: "Save a copy",
  readToMe: "Read it to me",
  reportPrivacy: "Built only from what you told us. Hindi ito legal decision, at nothing was sent anywhere.",
  savePrototype: "Prototype pa ang saving. Nothing was downloaded.",
  readPrototype: "Prototype pa ang read-aloud. No audio was started.",
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
  contractTitle: "Susiha ang akong kontrata",
  contractBody: "Kalmadong panag-istorya bahin sa oras, sweldo, rest day, ug papeles. Hunong ug balik bisan kanus-a.",
  contractCta: "Sugdi ang pag-istorya",
  crisisTitle: "Kinahanglan ko og tabang karon",
  crisisBody: "Isulti unsay nahitabo, dayon tan-awa ang mga numero nga makatabang karong gabii.",
  topicPrompt: "O sugdi sa unsay nahitabo",
  topicPassport: "Gikuptan nila akong passport",
  topicPay: "Wala ko bayri",
  topicRest: "Walay rest day",
  topicLeave: "Dili ko makagawas",
  switchAnytime: "Makabalhin ka sa duha bisan kanus-a.",
  currentTopic: "Gihisgutan karon ang imong kontrata ug trabaho",
  summaryTitle: "Ang imong gisulti",
  summaryConcern: "Imong concern",
  summaryActive: "Gihisgutan karon",
  summaryEdit: "Mahimong usbon ang bisan unsa dinhi sa dili pa buhaton ang imong lista.",
  verifyTitle: "Ipa-verify ang detalye",
  verifyRule: "Dad-a kini sa DMW, OWWA, o lisensiyadong abogado. Sila ang mohukom, dili ang Gabay OFW.",
  resultCount: (current) => `${current} sa 4`,
  youSaid: "Imong gisulti",
  contractSays: "Standard contract",
  restDaySaid: "Miingon ka nga kada adlaw ka nagtrabaho.",
  restDayContract: "Ang standard contracts adunay senemanang rest day.",
  overtimeSaid: "Miingon ka nga wala bayri ang overtime.",
  overtimeContract: "Ang extra hours kinahanglan bayran sumala sa angay nga kontrata.",
  recordsSaid: "Makatabang ang records sa imong gisulti.",
  recordsContract: "Tipigi lang ang kopya kung luwas.",
  verifySaid: "Gikan lamang sa imong gisulti kining listaha.",
  verifyContract: "Mahimong i-verify sa opisyal nga adviser ang matag item.",
  takeToPerson: "Dad-a kini sa usa ka tawo",
  takeToPersonBody: "Ipakita namo ang OWWA, Actionline, ug opisyal nga Migrant Workers Office directory.",
  saveCopy: "I-save ang kopya",
  readToMe: "Basaha para nako",
  reportPrivacy: "Gikan lamang sa imong gisulti kining listaha. Dili kini legal nga desisyon, ug walay gipadala.",
  savePrototype: "Prototype pa ang pag-save. Walay na-download.",
  readPrototype: "Prototype pa ang read-aloud. Walay audio nga gisugdan.",
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
  const firstName = userName.split(" ")[0] || "friend";
  return `
    <section class="dashboard-shell">
      <header class="dashboard-heading">
        <h1>${escapeHtml(t("greeting", firstName))}</h1>
        <p>${t("dashboardBody")}</p>
      </header>
      <div class="service-grid">
        <button class="mode-card contract-card" type="button" data-action="contract-chat">
          <svg class="service-icon" viewBox="0 0 48 48" aria-hidden="true">
            <rect x="11" y="7" width="26" height="34" rx="4"></rect>
            <path d="M17 17h14M17 24h14M17 31h9"></path>
          </svg>
          <span>
            <h2>${t("contractTitle")}</h2>
            <p>${t("contractBody")}</p>
            <span class="mode-cta">${t("contractCta")} →</span>
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
            <span class="mode-cta">${t("crisisCta")} →</span>
          </span>
        </button>
      </div>
      <div class="topic-starters">
        <p>${t("topicPrompt")}</p>
        <div class="topic-chips">
          <button type="button" data-action="contract-chat">${t("topicPassport")}</button>
          <button type="button" data-action="contract-chat">${t("topicPay")}</button>
          <button type="button" data-action="contract-chat">${t("topicRest")}</button>
          <button type="button" data-action="crisis">${t("topicLeave")}</button>
        </div>
      </div>
      <p class="switch-note"><span aria-hidden="true">↔</span> ${t("switchAnytime")}</p>
    </section>`;
}

function flowNav(label) {
  return `<nav class="flow-nav" aria-label="${escapeHtml(label)}">
    <button class="back-button" type="button" data-action="dashboard">${t("backDashboard")}</button>
    <span class="step-label">${label}</span>
  </nav>`;
}

function contractChatTemplate() {
  const hasStarted = Boolean(contractDraft);
  return `<section class="contract-workspace">
    <div class="conversation-pane">
      <div class="conversation-inner">
        <p class="conversation-topic"><span aria-hidden="true">✦</span> ${t("currentTopic")}</p>
        <div class="chat-thread" aria-live="polite">
          <div class="message assistant">${t("contractPrompt")}</div>
          ${hasStarted ? `
            <div class="message user">${escapeHtml(contractDraft)}</div>
            <div class="message assistant">${t("sampleAssistant")}</div>
          ` : ""}
        </div>
        <form class="composer" data-form="contract-chat">
          <button class="voice-button" type="button" data-action="prototype-voice" aria-label="${escapeHtml(t("voiceInput"))}">⌁</button>
          <input id="contract-message" required maxlength="4000" aria-label="${escapeHtml(t("contractPrompt"))}" placeholder="${escapeHtml(hasStarted ? t("typeAnswer") : t("contractPlaceholder"))}">
          <button class="photo-button" type="button" data-action="prototype-photo" aria-label="${escapeHtml(t("photoContract"))}">▣</button>
          <button class="send-button" type="submit" aria-label="${escapeHtml(hasStarted ? t("viewReport") : t("continue"))}">↑</button>
        </form>
        <p class="composer-hint">${t("conversationHint")}</p>
      </div>
    </div>
    <aside class="conversation-summary">
      <header>
        <p class="eyebrow">${t("contractStep")}</p>
        <h2>${t("summaryTitle")}</h2>
      </header>
      <article class="summary-card active">
        <span>${t("summaryActive")}</span>
        <strong>${t("contractTitle")}</strong>
      </article>
      ${hasStarted ? `
        <article class="summary-card">
          <span>${t("summaryConcern")}</span>
          <p>${escapeHtml(contractDraft)}</p>
        </article>
      ` : ""}
      <p class="summary-note">${t("summaryEdit")}</p>
    </aside>
  </section>`;
}

function findingsTemplate() {
  const findings = [
    ["urgent", "urgent", "restDayFinding", "restDaySaid", "restDayContract"],
    ["urgent", "urgent", "overtimeFinding", "overtimeSaid", "overtimeContract"],
    ["concerning", "informational", "reportInfoTitle", "recordsSaid", "recordsContract"],
    ["concerning", "informational", "verifyTitle", "verifySaid", "verifyContract"],
  ];
  return `<section class="report-workspace">
    <div class="report-main">
      <header class="report-heading">
        <p class="eyebrow">${t("contractStep")}</p>
        <h1>${t("findingsTitle")}</h1>
        <p>${t("findingsIntro")}</p>
      </header>
      <div class="findings-grid">
        ${findings.map(([tone, severity, title, said, rule], index) => `
          <article class="finding ${tone}">
            <div class="finding-meta">
              <span>${t(severity)}</span>
              <small>${t("resultCount", index + 1)}</small>
            </div>
            <h2>${t(title)}</h2>
            <dl>
              <div><dt>${t("youSaid")}</dt><dd>${t(said)}</dd></div>
              <div><dt>${t("contractSays")}</dt><dd>${t(rule)}</dd></div>
            </dl>
          </article>
        `).join("")}
      </div>
    </div>
    <aside class="report-actions">
      <div>
        <p class="eyebrow">${t("takeToPerson")}</p>
        <h2>${t("takeToPerson")}</h2>
        <p>${t("takeToPersonBody")}</p>
        <button class="button ink-button" type="button" data-action="crisis">${t("showHelp")} <span aria-hidden="true">→</span></button>
      </div>
      <div class="report-tools">
        <button type="button" data-action="prototype-save">${t("saveCopy")} <span aria-hidden="true">↓</span></button>
        <button type="button" data-action="prototype-read">${t("readToMe")} <span aria-hidden="true">◖</span></button>
      </div>
      <p class="report-privacy">${t("reportPrivacy")}</p>
      <button class="back-button" type="button" data-action="dashboard">← ${t("done")}</button>
    </aside>
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
      <button class="button ink-button" type="submit">${t("continue")}</button>
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
      <button class="button ink-button" type="submit">${t("showHelp")}</button>
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
        <button class="button ink-button" type="submit">${t("saveProfile")}</button>
        <button class="button" type="button" data-action="delete-profile">${t("deleteData")}</button>
      </div>
    </form>
  </section>`;
}

const templates = {
  dashboard: dashboardTemplate,
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
  screen.dataset.screen = name;
  screen.innerHTML = templates[name]();
  const isContract = name.startsWith("contract") || name === "findings";
  const isCrisis = name.startsWith("crisis");
  modeSwitcher.classList.toggle("hidden", name === "dashboard" || name === "profile");
  globalHelp.classList.toggle("hidden", name === "dashboard" || isContract || isCrisis);
  modeSwitcher.querySelector('[data-mode-link="contract"]').classList.toggle("active", isContract);
  modeSwitcher.querySelector('[data-mode-link="crisis"]').classList.toggle("active", isCrisis);
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
  if (action === "prototype-voice") {
    showStatus(t("voicePrototype"));
    return;
  }
  if (action === "prototype-photo") {
    showStatus(t("photoPrototype"));
    return;
  }
  if (action === "prototype-save") {
    showStatus(t("savePrototype"));
    return;
  }
  if (action === "prototype-read") {
    showStatus(t("readPrototype"));
    return;
  }
  navigate(action);
});

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!form.dataset.form) return;
  event.preventDefault();
  if (form.dataset.form === "contract-chat") {
    if (contractDraft) {
      navigate("findings");
    } else {
      contractDraft = document.getElementById("contract-message").value.trim();
      renderScreen("contract-chat");
    }
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
    document.getElementById("account-name").textContent = userName;
    document.getElementById("avatar-initial").textContent = userName.trim().charAt(0).toUpperCase() || "G";
    renderScreen("dashboard");
    if (!localStorage.getItem(`gabay-disclaimer-accepted:${userId}`)) {
      dialog.showModal();
    }
  });
}
