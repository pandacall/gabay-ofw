const { test, expect } = require("@playwright/test");

async function openApp(
  page,
  { acceptedDisclaimer = true, signedIn = true } = {},
) {
  if (acceptedDisclaimer) {
    await page.addInitScript(() =>
      localStorage.setItem("gabay-disclaimer-accepted:alice", "true"),
    );
  }
  await page.route("**/firebase-app.js", (route) =>
    route.fulfill({
      contentType: "text/javascript",
      body: "export const initializeApp = config => config;",
    }),
  );
  await page.route("**/firebase-auth.js", (route) =>
    route.fulfill({
      contentType: "text/javascript",
      body: `
        export class GoogleAuthProvider {}
        export const getAuth = () => ({ currentUser: { getIdToken: async () => "valid-alice" } });
        export const signInWithPopup = async () => {};
        export const signOut = async () => {};
        export const onAuthStateChanged = (_auth, callback) =>
          callback(${signedIn ? '{ uid: "alice", displayName: "Alice", email: "alice@example.com" }' : "null"});
      `,
    }),
  );
  await page.route("**/api/firebase-config", (route) =>
    route.fulfill({ json: { apiKey: "test", projectId: "test" } }),
  );
  await page.route("**/api/notes", (route) =>
    route.fulfill({ json: { notes: [] } }),
  );
  await page.goto("/");
}

const openAsSignedInUser = (page, options) => openApp(page, options);

test("signed-in user explicitly chooses either mode from the dashboard", async ({
  page,
}) => {
  await openAsSignedInUser(page);

  await expect(page.getByRole("heading", { name: "What do you need?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Start Contract Check" })).toBeVisible();
  await expect(page.locator(".crisis-card")).toBeVisible();
  await expect(page.locator(".crisis-card")).toHaveCSS("background-color", "rgb(168, 67, 31)");
  await expect(page.locator(".mode-card").first()).toHaveCSS("background-color", "rgb(255, 255, 255)");
});

test("signed-out user can choose a language before sign-in", async ({ page }) => {
  await openApp(page, { signedIn: false });

  await page.locator("#signed-out").getByLabel("Language").selectOption("tl");
  await expect(
    page.getByRole("heading", { name: "Sinusunod ba ng trabaho mo ang kontrata?" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Magpatuloy gamit ang Google" })).toBeVisible();
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

test("user can click through the static Contract Check flow", async ({ page }) => {
  await openAsSignedInUser(page);

  await page.getByRole("button", { name: /Start Contract Check/ }).click();
  await page.getByLabel("What does your contract say, and what is actually happening?").fill(
    "My contract promises a weekly rest day, but I work every day.",
  );
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("4 of 9")).toBeVisible();
  await expect(page.getByRole("button", { name: "Answer by voice" })).toBeVisible();
  await expect(page.getByRole("button", { name: "I Need Help Now" })).toBeVisible();

  await page.getByRole("button", { name: "Answer by voice" }).click();
  await expect(page.getByRole("status")).toContainText("Nothing is being recorded");
  await page.getByRole("button", { name: "Photograph my contract" }).click();
  await expect(page.getByRole("status")).toContainText("Nothing was opened or uploaded");

  await page.getByRole("button", { name: "View sample Findings Report" }).click();
  await expect(page.getByRole("heading", { name: "Two of these are serious." })).toBeVisible();
  await expect(page.getByText("Missing weekly rest day")).toBeVisible();
  await expect(page.getByText("Unpaid overtime")).toBeVisible();
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
  await expect(page.getByRole("heading", { name: "Unsay imong kinahanglan?" })).toBeVisible();
  await expect(page.locator(".crisis-card")).toContainText("Pangayo og tabang");

  await page.reload();
  await expect(page.getByRole("heading", { name: "Unsay imong kinahanglan?" })).toBeVisible();
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

test("profile and crisis entry remain available on a small screen", async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await openAsSignedInUser(page);

  await expect(page.getByRole("button", { name: "Profile" })).toBeVisible();
  await expect(page.locator(".crisis-card")).toBeVisible();
});
