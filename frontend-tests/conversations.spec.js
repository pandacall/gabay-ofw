const { test, expect } = require("@playwright/test");
const {
  openAsSignedInUser,
  SAMPLE_CONTACTS,
  openRailIfDrawer,
  expandCasePanel,
} = require("./test-helpers");

// issue #72 (ADR-0008): many Conversations she can leave and return to,
// sharing one Case. These drive the rail + transcript UI with every
// endpoint stubbed at the network edge (the test-helpers pattern).

const DAY = 24 * 60 * 60;
const NOW = 1_757_000_000; // fixed epoch seconds for deterministic labels

// Replace the helper's default empty-list stub with a scripted list plus
// per-session transcripts, then reload so the rail re-fetches. Routes
// added here win over the helper's (Playwright matches last-added first).
async function useConversations(page, { list = [], transcripts = {} } = {}) {
  await page.unroute("**/api/conversations");
  await page.route("**/api/conversations", (route) =>
    route.fulfill({ json: { conversations: list } }),
  );
  await page.route(/\/api\/conversations\/[^/]+$/, (route) => {
    const id = decodeURIComponent(route.request().url().split("/").pop());
    if (route.request().method() === "DELETE") {
      return route.fulfill({ json: { deleted: true } });
    }
    route.fulfill({
      contentType: "application/x-ndjson",
      body: (transcripts[id] || []).map((line) => JSON.stringify(line)).join("\n") + "\n",
    });
  });
  await page.reload();
}

test("the rail lists every conversation, most-recent first, with a date label", async ({
  page,
}) => {
  await openAsSignedInUser(page);
  await useConversations(page, {
    list: [
      { session_id: "s-sep", last_update_time: NOW },
      { session_id: "s-aug", last_update_time: NOW - 20 * DAY },
    ],
  });

  const rows = page.locator(".rail-conversation");
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0)).toHaveAttribute("data-session-id", "s-sep");
  await expect(rows.nth(1)).toHaveAttribute("data-session-id", "s-aug");
});

test("tapping 'new conversation' clears the thread and leaves no row until she sends a message", async ({
  page,
}) => {
  await openAsSignedInUser(page);
  await useConversations(page, { list: [] });

  await openRailIfDrawer(page);
  await page.getByRole("button", { name: "New conversation" }).click();
  await expect(page.locator(".rail-conversation")).toHaveCount(0);
  await expect(page.locator("#home-greeting")).toBeVisible();

  // Her first message is what brings the Conversation into existence.
  await page.unroute("**/api/conversations");
  await page.route("**/api/conversations", (route) =>
    route.fulfill({ json: { conversations: [{ session_id: "s1", last_update_time: NOW }] } }),
  );
  await page.route("**/api/chat", (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      body:
        [
          JSON.stringify({ type: "ack", text: "I hear you.", session_id: "s1" }),
          JSON.stringify({ type: "reply", text: "Thank you for telling me.", session_id: "s1" }),
          JSON.stringify({ type: "case", case: {}, session_id: "s1" }),
        ].join("\n") + "\n",
    }),
  );
  await page.locator("#chat-input").fill("They took my passport");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.locator(".chat-message.agent").last()).toContainText("Thank you");
  await expect(page.locator(".rail-conversation")).toHaveCount(1);
});

test("opening a conversation from the rail restores its transcript and cards", async ({
  page,
}) => {
  await openAsSignedInUser(page);
  await useConversations(page, {
    list: [{ session_id: "s-wages", last_update_time: NOW }],
    transcripts: {
      "s-wages": [
        { type: "user", text: "I have not been paid for three months" },
        {
          type: "card",
          card: {
            type: "safe_floor",
            country: "SA",
            title: "Real offices that can help",
            reason_line: "I don't have a verified plan yet.",
            contacts: SAMPLE_CONTACTS,
          },
        },
        { type: "reply", text: "These offices can help you." },
        {
          type: "case",
          case: {
            claims: { months_unpaid: { value: "3", source: "extraction" } },
            safety_flags: {},
          },
        },
      ],
    },
  });

  await openRailIfDrawer(page);
  await page.locator(".rail-conversation .rail-conversation-open").first().click();

  await expect(page.locator(".chat-message.user")).toContainText("not been paid");
  await expect(page.locator(".contact-card")).toContainText("Real offices that can help");
  await expect(page.locator(".chat-message.agent").last()).toContainText("These offices can help");
  await expandCasePanel(page);
  await expect(page.locator(".case-panel-body")).toContainText("months unpaid");
});

test("a re-opened turn with a past plan card shows one 'view current plan' line, not an actionable card", async ({
  page,
}) => {
  await openAsSignedInUser(page);
  await useConversations(page, {
    list: [{ session_id: "s-plan", last_update_time: NOW }],
    transcripts: {
      "s-plan": [
        { type: "user", text: "What is my filing order?" },
        { type: "stale_plan_ref" },
        { type: "reply", text: "Here is the order to file in." },
        { type: "case", case: {} },
      ],
    },
  });

  await openRailIfDrawer(page);
  await page.locator(".rail-conversation .rail-conversation-open").first().click();

  await expect(page.locator(".chat-message.stale-plan")).toHaveCount(1);
  await expect(page.locator(".chat-message.stale-plan")).toContainText("current plan");
  await expect(page.locator('[data-card-type="plan"]')).toHaveCount(0);
});

test("deleting a conversation shows the plain-language line, then removes the row", async ({
  page,
}) => {
  await openAsSignedInUser(page);
  await useConversations(page, {
    list: [
      { session_id: "s-keep", last_update_time: NOW },
      { session_id: "s-drop", last_update_time: NOW - DAY },
    ],
  });

  await openRailIfDrawer(page);
  await page
    .locator('.rail-conversation[data-session-id="s-drop"]')
    .locator("[data-action='delete-conversation']")
    .click();

  const dialog = page.getByRole("dialog", { name: /remove this conversation/i });
  await expect(dialog).toContainText("What you told Gabay about your situation stays");
  await expect(dialog).toContainText("Delete everything");

  await page.unroute("**/api/conversations");
  await page.route("**/api/conversations", (route) =>
    route.fulfill({ json: { conversations: [{ session_id: "s-keep", last_update_time: NOW }] } }),
  );
  await dialog.getByRole("button", { name: "Remove conversation" }).click();

  await expect(page.locator('[data-session-id="s-drop"]')).toHaveCount(0);
  await expect(page.locator('[data-session-id="s-keep"]')).toHaveCount(1);
});

test("the rail shows the derived topic label, with the date kept as a subline", async ({
  page,
}) => {
  await openAsSignedInUser(page);
  await useConversations(page, {
    list: [
      { session_id: "s-a", last_update_time: NOW, label: "passport", label_source: "derived" },
      { session_id: "s-b", last_update_time: NOW - DAY, label: "wages", label_source: "derived" },
    ],
  });

  const rows = page.locator(".rail-conversation");
  await expect(rows.nth(0).locator(".rail-conversation-label")).toHaveText("Passport and papers");
  await expect(rows.nth(0).locator(".rail-conversation-date")).toHaveCount(1);
  await expect(rows.nth(1).locator(".rail-conversation-label")).toHaveText("Wages");
});

// spec 2026-09-05-llm-conversation-titles: an "llm" label renders
// verbatim, exactly like her own rename, never localised as a key.
test("the rail shows a generated LLM title verbatim, not localised", async ({
  page,
}) => {
  await openAsSignedInUser(page);
  await useConversations(page, {
    list: [
      {
        session_id: "s-a",
        last_update_time: NOW,
        label: "Unpaid wages, several months",
        label_source: "llm",
      },
    ],
  });

  const rows = page.locator(".rail-conversation");
  await expect(rows.nth(0).locator(".rail-conversation-label")).toHaveText(
    "Unpaid wages, several months",
  );
});

test("she can rename a conversation and her name is shown verbatim", async ({ page }) => {
  await openAsSignedInUser(page);
  await useConversations(page, {
    list: [{ session_id: "s-a", last_update_time: NOW, label: "passport", label_source: "derived" }],
  });

  let patched = null;
  await page.route(/\/api\/conversations\/[^/]+$/, (route) => {
    if (route.request().method() === "PATCH") {
      patched = JSON.parse(route.request().postData());
      return route.fulfill({ json: { label: patched.label } });
    }
    return route.fallback();
  });

  await openRailIfDrawer(page);
  await page
    .locator('.rail-conversation[data-session-id="s-a"]')
    .locator("[data-action='rename-conversation']")
    .click();

  const dialog = page.getByRole("dialog", { name: /rename this conversation/i });
  await dialog.locator("#rename-conversation-input").fill("the passport one");

  await page.unroute("**/api/conversations");
  await page.route("**/api/conversations", (route) =>
    route.fulfill({
      json: {
        conversations: [
          { session_id: "s-a", last_update_time: NOW, label: "the passport one", label_source: "user" },
        ],
      },
    }),
  );
  await dialog.getByRole("button", { name: "Save name" }).click();

  await expect.poll(() => patched && patched.label).toBe("the passport one");
  await expect(page.locator(".rail-conversation-label")).toHaveText("the passport one");
});

test("delete-everything is still one tap in the profile screen", async ({ page }) => {
  await openAsSignedInUser(page);
  await openRailIfDrawer(page);
  await page.getByRole("button", { name: "Profile" }).click();
  await expect(page.getByRole("button", { name: "Delete everything now" })).toBeVisible();
});
