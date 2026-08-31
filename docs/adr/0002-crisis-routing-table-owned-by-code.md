---
status: accepted
date: 2026-09-01
---

# Crisis Help: LLM triages to a category; code owns the routing table

The Crisis Help agent outputs only a structured triage result (`category`, `country`, calm reply in the user's language). Application code maps the category to escalation resources via a hardcoded table (1343 Actionline, OWWA 1348, DMW directory link), and the UI renders the contact card outside the LLM text as tappable links. The draft v1 prompt had the LLM emit routing (numbers included) directly; we rejected that because a hallucinated phone number in a crisis is the app's worst failure mode — "the model never fabricates a contact" must be a structural guarantee, not a prompt instruction.
