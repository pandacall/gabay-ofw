# Gabay OFW

A Gemini-powered web app for Filipino Overseas Foreign Workers (OFWs) in the
Gulf corridor, with two explicitly chosen modes:

- **Contract Check** — describe your contract and your actual conditions; get a
  structured findings report grounded in the six non-negotiable POEA/DMW rules.
  Guidance, never legal advice.
- **Crisis Help ("I Need Help Now")** — a short, calm triage that routes you to
  real resources (1343 Actionline, OWWA 1348, your country's MWO via the
  official DMW directory). Contact cards are rendered by application code,
  never composed by the AI.

Built for the Hack2skill GenAI Academy APAC **Cloud Run AI Challenge**.

## Status

Walking skeleton (issue #2): Firebase Auth (Google Sign-In), user-isolated
Firestore round-trip, Secret Manager key retrieval, Cloud Run deploy.

## Stack

Python 3.11 · FastAPI · `google-adk >= 2.0` · Firebase Authentication ·
Cloud Firestore · Gemini (AI Studio) · Google Cloud Secret Manager · Cloud Run.

## Local development

```bash
pip install -r requirements-dev.txt
python -m pytest tests            # backend tests (HTTP seam, no cloud needed)
```

Run the server locally (needs Application Default Credentials for Firestore):

```bash
set GOOGLE_CLOUD_PROJECT=<project-id>
set FIREBASE_WEB_CONFIG={"apiKey":"...","authDomain":"...","projectId":"..."}
uvicorn --factory app.main:production_app --port 8000
```

### Firestore security-rules tests

Rules are tested directly against the Firestore emulator (requires Node 18+
and Java 11+ on PATH):

```bash
cd rules-tests
npm install
npm test
```

## Configuration

| Name | Where | Purpose |
| --- | --- | --- |
| `gemini-api-key` | Secret Manager secret | Gemini API key; fetched at runtime, never in source or env files |
| `GOOGLE_CLOUD_PROJECT` | env (set by Cloud Run) | project for Firestore/Secret Manager |
| `FIREBASE_WEB_CONFIG` | env (JSON) | public Firebase web-app config served to the sign-in page |

## Firestore security rules

`firestore.rules` enforces `request.auth.uid == uid` on **every** path under
`users/{uid}/...` (profile, contractChecks + messages, crisisSessions +
messages). Everything outside the user tree is denied by default. Deploy with:

```bash
firebase deploy --only firestore:rules --project <project-id>
```

## Deploy to Cloud Run

```bash
gcloud run deploy gabay-ofw \
  --source . \
  --project <project-id> \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --labels dev-tutorial=cloud-run-ai-challenge \
  --set-env-vars GOOGLE_CLOUD_PROJECT=<project-id> \
  --set-env-vars ^@^FIREBASE_WEB_CONFIG={"apiKey":"..."}
```

One-time project setup:

1. Enable APIs: `run`, `firestore`, `secretmanager`, `identitytoolkit`,
   `cloudbuild`, `artifactregistry`, `firebase`, `firebaserules`.
2. Add Firebase to the GCP project; enable the **Google** sign-in provider and
   add the Cloud Run domain to Authentication → Authorized domains.
3. Create the Firestore database (native mode).
4. Create the secret and grant the runtime service account access:

   ```bash
   echo -n "<GEMINI_API_KEY>" | gcloud secrets create gemini-api-key --data-file=-
   gcloud secrets add-iam-policy-binding gemini-api-key \
     --member serviceAccount:<runtime-sa> --role roles/secretmanager.secretAccessor
   ```

5. Deploy Firestore rules (see above).

## Privacy & security design

- Per-user isolation enforced by Firestore security rules, not client filtering.
- Crisis sessions carry an `expireAt` field with a Firestore TTL policy
  (48–72 h auto-delete); users can also delete any session manually.
- The Gemini key lives only in Secret Manager.
- All model output is schema-validated before being trusted or rendered.
