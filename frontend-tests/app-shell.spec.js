const { test, expect } = require("@playwright/test");
const { openAsSignedInUser, SAMPLE_CONTACTS } = require("./test-helpers");

const openApp = openAsSignedInUser;

test("signed-in user lands directly on the home screen: a centred greeting, the rail, and the floating composer", async ({
  page,
}) => {
  await openAsSignedInUser(page);

  await expect(page.getByRole("heading", { name: "Alice, what do you need?" })).toBeVisible();
  await expect(page.locator(".rail")).toBeVisible();
  await expect(page.locator(".rail-conversation.active")).toBeVisible();
  await expect(page.locator("#chat-input")).toBeVisible();
  await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
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

test("language choice updates the home screen and persists", async ({ page }) => {
  await openAsSignedInUser(page);

  await page.locator("#signed-in").getByLabel("Language").selectOption("ceb");
  await expect(page.getByRole("heading", { name: "Alice, unsay imong kinahanglan?" })).toBeVisible();

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

  await page.getByRole("button", { name: "Back" }).click();
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

  // The device is the threat model (issue #71): a wipe that leaves local
  // traces behind is not a wipe. Seed both device-local keys so we can
  // prove the wipe clears them, not just the server-side subtree.
  await page.evaluate(() => {
    localStorage.setItem("gabay-profile:alice", JSON.stringify({ country: "Qatar" }));
    localStorage.setItem("gabay-disclaimer-accepted:alice", "true");
  });

  await page.getByRole("button", { name: "Profile" }).click();
  await page.getByRole("button", { name: "Delete everything now" }).click();

  await expect(page.getByRole("status")).toContainText("Everything was deleted.");
  expect(requests).toEqual([
    { url: "nonce", auth: "Bearer valid-alice" },
    { url: "wipe", auth: "Bearer valid-alice", body: { nonce: "one-time-nonce" } },
  ]);
  const remainingKeys = await page.evaluate(() => ({
    profile: localStorage.getItem("gabay-profile:alice"),
    disclaimer: localStorage.getItem("gabay-disclaimer-accepted:alice"),
  }));
  expect(remainingKeys).toEqual({ profile: null, disclaimer: null });
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

  const opener = page.getByRole("button", { name: "Hindi ako nababayaran / I'm not being paid" });
  await expect(opener).toBeVisible();
  await opener.click();
  await expect(page.locator("#chat-input")).toHaveValue("Hindi ako nababayaran / I'm not being paid");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.locator(".chat-message.agent.ack")).toContainText("I hear you");
  await expect(page.locator(".chat-message.agent").last()).toContainText("Nandito ako para tumulong");
  await expect(page.locator(".case-panel")).toContainText("months unpaid");
  await expect(page.locator(".case-panel")).toContainText("passport withheld");
  // The greeting and openers retire once the conversation starts, but the
  // composer never does (issue #71: "a floating pill composer that never
  // leaves the screen").
  await expect(page.locator("#home-greeting")).toBeHidden();
  await expect(page.locator("#chat-input")).toBeVisible();
});

test("a Safe Floor card line renders as a message in the conversation, with the composer still visible", async ({
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
              contacts: SAMPLE_CONTACTS,
              hold_line: "Huwag kang umalis sa amo mo bago ka makausap ang MWO. / Do not leave before speaking to the MWO.",
            },
            session_id: "s1",
          }),
          JSON.stringify({ type: "reply", text: "Narito ang mga totoong opisina na makakatulong sa iyo.", session_id: "s1" }),
          JSON.stringify({ type: "case", case: {}, session_id: "s1" }),
        ].join("\n") + "\n",
    }),
  );

  await page.locator("#chat-input").fill("Ano ang unang hakbang ko?");
  await page.getByRole("button", { name: "Send" }).click();

  // The finding arrives as Gabay's reply in the conversation — never a
  // separate screen (issue #71's structural move) — and the composer
  // stays put.
  const card = page.locator(".contact-card");
  await expect(card).toBeVisible();
  await expect(page.locator(".messages")).toContainText("Real offices that can help");
  await expect(card.locator(".card-reason")).toContainText("verified na plano");
  const dialable = card.locator(".card-contact.dialable a.card-contact-phone");
  await expect(dialable).toHaveAttribute("href", "tel:+966502850944");
  await expect(card.locator(".card-contact.relay")).toContainText("1348");
  await expect(card.locator(".card-hold-line")).toContainText("Do not leave before speaking to the MWO");
  await expect(page.locator("#chat-input")).toBeVisible();
  await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
});

test("profile stays reachable, and the composer stays visible, on a small screen", async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await openAsSignedInUser(page);

  await expect(page.getByRole("button", { name: "Profile" })).toBeVisible();
  await expect(page.locator("#chat-input")).toBeVisible();
  await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
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

test("the retired Crisis Help wizard is gone: no danger question, country picker, situation form, or routing screen is reachable", async ({
  page,
}) => {
  await openAsSignedInUser(page);

  await expect(page.locator("[data-action='crisis']")).toHaveCount(0);
  await expect(page.locator("[data-form='crisis-country']")).toHaveCount(0);
  await expect(page.locator("[data-form='crisis-situation']")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Are you in physical danger right now?" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Profile" })).toBeVisible();
});

test("an unrecognised stream line type is ignored without breaking the render (ADR-0010)", async ({
  page,
}) => {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error));
  await openAsSignedInUser(page);
  await page.route("**/api/chat", (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      body:
        [
          JSON.stringify({ type: "ack", text: "I hear you.", session_id: "s1" }),
          // A future slice's line type (e.g. the Progress Trail, ADR-0010)
          // this build does not know about yet.
          JSON.stringify({ type: "progress", label: "Looking up your agency", session_id: "s1" }),
          JSON.stringify({ type: "reply", text: "Salamat.", session_id: "s1" }),
          JSON.stringify({ type: "case", case: {}, session_id: "s1" }),
        ].join("\n") + "\n",
    }),
  );

  await page.locator("#chat-input").fill("Hello");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.locator(".chat-message.agent.ack")).toContainText("I hear you");
  await expect(page.locator(".chat-message.agent").last()).toContainText("Salamat");
  expect(pageErrors).toEqual([]);
});

test("no hotline or office phone number appears anywhere in client-side code (ADR-0002)", async ({
  page,
}) => {
  const fs = require("fs");
  const path = require("path");
  const html = fs.readFileSync(path.join(__dirname, "..", "static", "index.html"), "utf-8");
  const js = fs.readFileSync(path.join(__dirname, "..", "static", "app.js"), "utf-8");
  for (const forbidden of ["1343", "1348"]) {
    expect(html).not.toContain(forbidden);
    expect(js).not.toContain(forbidden);
  }
});
