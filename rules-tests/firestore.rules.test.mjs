// Secondary test seam (PRD): Firestore security rules tested directly against
// the emulator. Cross-user reads/writes must fail on every users/{uid}/... path.
import { readFileSync } from "node:fs";
import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} from "@firebase/rules-unit-testing";

let env;

before(async () => {
  env = await initializeTestEnvironment({
    projectId: "gabay-ofw-rules-test",
    firestore: { rules: readFileSync("../firestore.rules", "utf8") },
  });
});

after(async () => {
  await env.cleanup();
});

beforeEach(async () => {
  await env.clearFirestore();
});

const alice = () => env.authenticatedContext("alice").firestore();
const bob = () => env.authenticatedContext("bob").firestore();
const anon = () => env.unauthenticatedContext().firestore();

// Every user-scoped path family from the PRD data model, with a payload
// valid for that path (crisisSessions requires an expireAt timestamp).
const writes = (uid) => [
  [`users/${uid}`, { ok: true }],
  [`users/${uid}/notes/n1`, { ok: true }],
  [`users/${uid}/crisisSessions/s1`, { expireAt: new Date(Date.now() + 48 * 3600 * 1000) }],
  [`users/${uid}/crisisSessions/s1/messages/m1`, { ok: true }],
];
// v6 session paths (ADR-0003): backend-written via the Admin SDK, which
// bypasses rules. Clients may only read their own; never write.
const readOnlyPaths = (uid) => [
  `users/${uid}/sessions/v6s1`,
  `users/${uid}/sessions/v6s1/events/e1`,
  `users/${uid}/adkUserState/gabay-ofw`,
];
const paths = (uid) => [...writes(uid).map(([p]) => p), ...readOnlyPaths(uid)];

const seedSessionPaths = async (uid) => {
  await env.withSecurityRulesDisabled(async (ctx) => {
    const db = ctx.firestore();
    await db.doc(`users/${uid}/sessions/v6s1`).set({
      appName: "gabay-ofw",
      state: { case_country: "SA" },
      revision: 1,
      lastUpdateTime: 1,
    });
    await db.doc(`users/${uid}/sessions/v6s1/events/e1`).set({ timestamp: 1 });
    await db.doc(`users/${uid}/adkUserState/gabay-ofw`).set({ preferred_language: "tl" });
  });
};

describe("owner access", () => {
  it("allows the owner to write and read every user-scoped path", async () => {
    for (const [p, data] of writes("alice")) {
      await assertSucceeds(alice().doc(p).set(data));
      await assertSucceeds(alice().doc(p).get());
    }
  });
});

describe("crisis session TTL invariant", () => {
  it("denies creating a crisis session without expireAt, even for the owner", async () => {
    await assertFails(alice().doc("users/alice/crisisSessions/s2").set({ country: "SA" }));
  });

  it("denies updating a crisis session to drop expireAt", async () => {
    await env.withSecurityRulesDisabled(async (ctx) => {
      await ctx.firestore().doc("users/alice/crisisSessions/s3").set({ expireAt: new Date() });
    });
    await assertFails(
      alice().doc("users/alice/crisisSessions/s3").set({ country: "SA" })
    );
  });

  it("denies a non-timestamp expireAt", async () => {
    await assertFails(
      alice().doc("users/alice/crisisSessions/s4").set({ expireAt: "never" })
    );
  });
});

describe("v6 session paths", () => {
  beforeEach(() => seedSessionPaths("alice"));

  it("allows the owner to read the session doc, events, and user state", async () => {
    for (const p of readOnlyPaths("alice")) {
      await assertSucceeds(alice().doc(p).get());
    }
  });

  it("denies the owner writing any session path (backend-only writes)", async () => {
    for (const p of readOnlyPaths("alice")) {
      await assertFails(alice().doc(p).set({ hacked: true }));
      await assertFails(alice().doc(p).set({ revision: 999 }, { merge: true }));
    }
  });

  it("denies the owner deleting session documents from the client", async () => {
    for (const p of readOnlyPaths("alice")) {
      await assertFails(alice().doc(p).delete());
    }
  });

  it("denies a session state update that would clear a safety flag", async () => {
    await assertFails(
      alice().doc("users/alice/sessions/v6s1").set(
        { state: { case_country: "SA", safety_flag: null } },
        { merge: true }
      )
    );
  });

  it("denies another user reading the session paths", async () => {
    for (const p of readOnlyPaths("alice")) {
      await assertFails(bob().doc(p).get());
    }
  });

  it("denies all client access to app-scoped state", async () => {
    await env.withSecurityRulesDisabled(async (ctx) => {
      await ctx.firestore().doc("adkAppState/gabay-ofw").set({ config: 1 });
    });
    await assertFails(alice().doc("adkAppState/gabay-ofw").get());
    await assertFails(alice().doc("adkAppState/gabay-ofw").set({ x: 1 }));
  });
});

describe("retention field (ADR-0007)", () => {
  it("denies the owner creating their profile with an expireAt", async () => {
    await assertFails(
      alice().doc("users/alice").set({ ok: true, expireAt: new Date() })
    );
  });

  it("denies the owner changing the backend-managed expireAt", async () => {
    await env.withSecurityRulesDisabled(async (ctx) => {
      await ctx.firestore().doc("users/alice").set({ expireAt: new Date() });
    });
    await assertFails(
      alice()
        .doc("users/alice")
        .set({ expireAt: new Date(Date.now() + 1e10) }, { merge: true })
    );
    // A full overwrite would drop expireAt — also denied.
    await assertFails(alice().doc("users/alice").set({ ok: true }));
  });

  it("allows owner profile writes that leave expireAt untouched", async () => {
    await env.withSecurityRulesDisabled(async (ctx) => {
      await ctx.firestore().doc("users/alice").set({ expireAt: new Date() });
    });
    await assertSucceeds(
      alice().doc("users/alice").set({ ok: true }, { merge: true })
    );
  });

  it("denies the owner deleting the profile document from the client", async () => {
    await env.withSecurityRulesDisabled(async (ctx) => {
      await ctx.firestore().doc("users/alice").set({ expireAt: new Date() });
    });
    await assertFails(alice().doc("users/alice").delete());
  });
});

describe("cross-user isolation", () => {
  it("denies another user reading any of the owner's paths", async () => {
    for (const p of paths("alice")) {
      await assertFails(bob().doc(p).get());
    }
  });

  it("denies another user writing any of the owner's paths", async () => {
    for (const p of paths("alice")) {
      await assertFails(bob().doc(p).set({ hacked: true }));
    }
  });

  it("denies another user deleting the owner's documents", async () => {
    await env.withSecurityRulesDisabled(async (ctx) => {
      await ctx.firestore().doc("users/alice/crisisSessions/s1").set({ x: 1 });
    });
    await assertFails(bob().doc("users/alice/crisisSessions/s1").delete());
  });

  it("denies listing another user's collections", async () => {
    await assertFails(bob().collection("users/alice/notes").get());
  });
});

describe("unauthenticated access", () => {
  it("denies all reads and writes when signed out", async () => {
    for (const p of paths("alice")) {
      await assertFails(anon().doc(p).get());
      await assertFails(anon().doc(p).set({ anon: true }));
    }
  });
});

describe("outside user tree", () => {
  it("denies access to non-user collections by default", async () => {
    await assertFails(alice().doc("admin/config").get());
    await assertFails(alice().doc("admin/config").set({ x: 1 }));
  });

  it("denies user-scoped paths outside the data model, even for the owner", async () => {
    await assertFails(alice().doc("users/alice/random/x1").set({ x: 1 }));
  });
});
