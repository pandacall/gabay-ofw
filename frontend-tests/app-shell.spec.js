const { test, expect } = require("@playwright/test");
const { openAsSignedInUser } = require("./test-helpers");

const openApp = openAsSignedInUser;

test("signed-in user reaches Crisis Help from the dashboard", async ({
  page,
}) => {
  await openAsSignedInUser(page);

  await expect(page.getByRole("heading", { name: "Alice, what do you need?" })).toBeVisible();
  await expect(page.locator(".crisis-card")).toBeVisible();
  await expect(page.locator(".crisis-card")).toHaveCSS("background-color", "rgb(168, 67, 31)");
  await expect(page.getByRole("button", { name: "I cannot go out" })).toBeVisible();
});

test("signed-out user can choose a language before sign-in", async ({ page }) => {
  await openApp(page, { signedIn: false });

  await expect(page.locator("#signed-out .language-select option")).toHaveText([
    "English",
    "Filipino",
    "Bisaya",
  ]);
  await page.locator("#signed-out").getByLabel("Language").selectOption("tl");
  await expect(
    page.getByRole("heading", { name: "Sinusunod ba ng trabaho mo ang kontrata?" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Mag-sign in gamit ang Google" })).toBeVisible();
});

test("first-time user sees the service limits before using the app", async ({
  page,
}) => {
  await openAsSignedInUser(page, { acceptedDisclaimer: false });

  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Before you begin" })).toBeVisible();
  await expect(dialog).toContainText("Not legal advice.");
  await expect(dialog).toContainText("Not an emergency service.");
  await dialog.getByRole("button", { name: "I understand" }).click();
  await expect(dialog).not.toBeVisible();
});

test("user can click through Crisis Help to code-owned contact cards", async ({
  page,
}) => {
  await openAsSignedInUser(page);

  await page.locator(".crisis-card").click();
  await page.getByRole("button", { name: "Yes, or I cannot leave safely" }).click();
  await page.getByLabel("Country").selectOption("Qatar");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("One-line description").fill("My employer will not let me leave.");
  await page.getByRole("button", { name: "Show official help" }).click();

  await expect(page.getByRole("heading", { name: "Call one of these now. All are free." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Call 1343" })).toHaveAttribute("href", "tel:1343");
  await expect(page.getByRole("link", { name: "Call 1348" })).toHaveAttribute("href", "tel:1348");
  await expect(page.getByRole("link", { name: "Open the official DMW directory" })).toHaveAttribute(
    "href",
    "https://dmw.gov.ph/",
  );
});

test("language choice updates every flow and persists", async ({ page }) => {
  await openAsSignedInUser(page);

  await page.locator("#signed-in").getByLabel("Language").selectOption("ceb");
  await expect(page.getByRole("heading", { name: "Alice, unsay imong kinahanglan?" })).toBeVisible();
  await expect(page.locator(".crisis-card")).toContainText("Kinahanglan ko og tabang karon");

  await page.reload();
  await expect(page.getByRole("heading", { name: "Alice, unsay imong kinahanglan?" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "ceb");
});

test("optional profile accepts and retains any destination country", async ({
  page,
}) => {
  await openAsSignedInUser(page);

  await page.getByRole("button", { name: "Profile" }).click();
  await page.getByLabel("Destination country (optional)").fill("Iceland");
  await page.getByLabel("Occupation (optional)").fill("");
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByRole("status")).toContainText("Profile saved");

  await page.getByRole("button", { name: "Back to dashboard" }).click();
  await page.getByRole("button", { name: "Profile" }).click();
  await expect(page.getByLabel("Destination country (optional)")).toHaveValue("Iceland");
});

test("one tap wipes everything through the nonce-gated backend", async ({
  page,
}) => {
  const requests = [];
  await page.route("**/api/panic-wipe/nonce", (route) => {
    requests.push({
      url: "nonce",
      auth: route.request().headers()["authorization"],
    });
    route.fulfill({ json: { nonce: "one-time-nonce" } });
  });
  await page.route("**/api/panic-wipe", (route) => {
    requests.push({
      url: "wipe",
      auth: route.request().headers()["authorization"],
      body: route.request().postDataJSON(),
    });
    route.fulfill({ json: { wiped: true, documents_deleted: 4 } });
  });
  await openAsSignedInUser(page);

  await page.getByRole("button", { name: "Profile" }).click();
  await page.getByRole("button", { name: "Delete everything now" }).click();

  await expect(page.getByRole("status")).toContainText("Everything was deleted.");
  expect(requests).toEqual([
    { url: "nonce", auth: "Bearer valid-alice" },
    { url: "wipe", auth: "Bearer valid-alice", body: { nonce: "one-time-nonce" } },
  ]);
});

test("a failed wipe is reported, never silently swallowed", async ({ page }) => {
  await page.route("**/api/panic-wipe/nonce", (route) =>
    route.fulfill({ status: 503, json: { detail: "down" } }),
  );
  await openAsSignedInUser(page);

  await page.getByRole("button", { name: "Profile" }).click();
  await page.getByRole("button", { name: "Delete everything now" }).click();

  await expect(page.getByRole("status")).toContainText("Could not delete right now.");
});

test("non-danger Crisis Help path omits the trafficking hotline", async ({
  page,
}) => {
  await openAsSignedInUser(page);

  await page.locator(".crisis-card").click();
  await page.getByRole("button", { name: "No, I can safely use my phone" }).click();
  await page.getByLabel("Country").selectOption("Kuwait");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("One-line description").fill("My wages have not been paid.");
  await page.getByRole("button", { name: "Show official help" }).click();

  await expect(page.getByRole("heading", { name: "Contact your Migrant Workers Office" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Call 1343" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Call 1348" })).toBeVisible();
});

test("user can open the conversation from a paired bilingual opener", async ({
  page,
}) => {
  await openAsSignedInUser(page);
  await page.route("**/api/chat", (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      body:
        [
          JSON.stringify({ type: "ack", text: "I hear you. I'm reading what you wrote — one moment.", session_id: "s1" }),
          JSON.stringify({ type: "reply", text: "Nandito ako para tumulong. Ilang buwan ka nang hindi nababayaran?", session_id: "s1" }),
          JSON.stringify({
            type: "case",
            case: {
              claims: { months_unpaid: { value: "3", source: "extraction" } },
              safety_flags: { PASSPORT_WITHHELD: { source: "extraction" } },
              language: "taglish",
            },
            session_id: "s1",
          }),
        ].join("\n") + "\n",
    }),
  );

  await page.locator(".chat-card").click();
  const opener = page.getByRole("button", { name: "Hindi ako nababayaran / I'm not being paid" });
  await expect(opener).toBeVisible();
  await opener.click();
  await expect(page.locator("#chat-input")).toHaveValue("Hindi ako nababayaran / I'm not being paid");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.locator(".chat-message.agent.ack")).toContainText("I hear you");
  await expect(page.locator(".chat-message.agent").last()).toContainText("Nandito ako para tumulong");
  await expect(page.locator(".chat-case")).toContainText("months unpaid");
  await expect(page.locator(".chat-case")).toContainText("passport withheld");
});

test("a Safe Floor card line renders as tappable contacts outside the LLM text", async ({
  page,
}) => {
  await openAsSignedInUser(page);
  await page.route("**/api/chat", (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      body:
        [
          JSON.stringify({ type: "ack", text: "I hear you. I'm reading what you wrote — one moment.", session_id: "s1" }),
          JSON.stringify({
            type: "card",
            card: {
              type: "safe_floor",
              country: "SA",
              title: "Saudi Arabia — Mga totoong opisina na makakatulong / Real offices that can help",
              reason: "NO_VERIFIED_PLAN",
              reason_line: "Wala pa akong verified na plano para sa sitwasyon mo. / I don't have a verified plan yet.",
              contacts: [
                { key: "mwo_riyadh", channel: "MWO", label: "MWO Riyadh (Migrant Workers Office)", phone: "+966 50 285 0944", dial_mode: "dialable", note: "" },
                { key: "owwa_1348", channel: "OWWA_1348", label: "OWWA / DMW Hotline 1348", phone: "1348", dial_mode: "manila_relay", note: "for someone in the Philippines to call for you" },
              ],
              hold_line: "Huwag kang umalis sa amo mo bago ka makausap ang MWO. / Do not leave before speaking to the MWO.",
            },
            session_id: "s1",
          }),
          JSON.stringify({ type: "reply", text: "Narito ang mga totoong opisina na makakatulong sa iyo.", session_id: "s1" }),
          JSON.stringify({ type: "case", case: {}, session_id: "s1" }),
        ].join("\n") + "\n",
    }),
  );

  await page.locator(".chat-card").click();
  await page.locator("#chat-input").fill("Ano ang unang hakbang ko?");
  await page.getByRole("button", { name: "Send" }).click();

  const card = page.locator(".contact-card");
  await expect(card).toBeVisible();
  await expect(card.locator(".card-reason")).toContainText("verified na plano");
  const dialable = card.locator(".card-contact.dialable a.card-contact-phone");
  await expect(dialable).toHaveAttribute("href", "tel:+966502850944");
  await expect(card.locator(".card-contact.relay")).toContainText("1348");
  await expect(card.locator(".card-hold-line")).toContainText("Do not leave before speaking to the MWO");
});

test("profile and crisis entry remain available on a small screen", async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await openAsSignedInUser(page);

  await expect(page.getByRole("button", { name: "Profile" })).toBeVisible();
  await expect(page.locator(".crisis-card")).toBeVisible();
});

test("a Case conflict is shown with both values and resolved by one tap", async ({
  page,
}) => {
  // Demoable fixture (PRD #34, issue #44): payslip says 14 months, she
  // said 11 — both shown with provenance, her tap resolves it.
  await openAsSignedInUser(page);
  await page.route("**/api/chat", (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      body:
        [
          JSON.stringify({ type: "ack", text: "I hear you. I'm reading what you wrote — one moment.", session_id: "s1" }),
          JSON.stringify({ type: "reply", text: "Salamat sa pagsabi.", session_id: "s1" }),
          JSON.stringify({
            type: "case",
            case: {
              claims: {
                months_unpaid: {
                  value: "11",
                  source: "extraction",
                  confidence: "high",
                  conflicts: [
                    { value: "14", source: "document", confidence: "high", at: "2026-09-03T00:00:00Z" },
                  ],
                },
              },
              safety_flags: {},
              language: "en",
            },
            session_id: "s1",
          }),
        ].join("\n") + "\n",
    }),
  );

  await page.locator(".chat-card").click();
  await page.locator("#chat-input").fill("Hindi ako nababayaran ng 11 months");
  await page.getByRole("button", { name: "Send" }).click();

  const conflict = page.locator(".case-claim.has-conflict");
  await expect(conflict).toBeVisible();
  await expect(conflict).toContainText("11");
  await expect(conflict).toContainText("14");

  let correctBody;
  await page.route("**/api/case/correct", (route) => {
    correctBody = route.request().postDataJSON();
    route.fulfill({
      json: {
        case: {
          claims: {
            months_unpaid: {
              value: "11",
              source: "user",
              confidence: "high",
              user_confirmed: true,
              conflicts: [],
            },
          },
          safety_flags: {},
          language: "en",
        },
      },
    });
  });

  await conflict.locator(".case-option", { hasText: "11" }).click();

  await expect(page.locator(".case-claim.has-conflict")).toHaveCount(0);
  await expect(page.locator(".case-claims")).toContainText("11");
  expect(correctBody).toMatchObject({
    session_id: "s1",
    field: "months_unpaid",
    value: "11",
  });
});
