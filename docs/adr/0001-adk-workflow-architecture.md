---
status: accepted
date: 2026-09-01
---

# ADK 2.0 Workflow graph for Contract Check; single agent for Crisis Help

Contract Check is built as an ADK 2.0 graph `Workflow` — an Interviewer `LlmAgent` looping with the user via HITL (`ResumabilityConfig` + `RequestInput`/`resume_inputs`), a deterministic completeness-check function node deciding the route, and a Rule-Matcher `LlmAgent` invoked exactly once when claims are complete. Crisis Help is a single `LlmAgent`, never a pipeline. Mode routing between the two is an explicit UI choice, never LLM classification, because misclassifying a crisis message is a safety failure.

## Considered options

- **Single Gemini call per mode (no ADK)** — lowest risk, satisfies all mandatory hackathon requirements, but forfeits demonstrating the ADK patterns taught by the GenAI Academy, which we judge relevant to the Authenticity criterion.
- **ADK 1.x-style `SequentialAgent(Interviewer, RuleMatcher)`** — rejected: it runs both sub-agents per invocation, so the Rule-Matcher would fire on every user turn against incomplete claims; human-in-the-loop across HTTP requests fights the composite-agent model.
- **ADK agents with hand-rolled orchestration in app code** — viable and is the designated fallback, but less legible as idiomatic ADK.

The Workflow graph won because it gives both: idiomatic ADK for graders *and* deterministic control logic in plain, unit-testable function nodes (routed edges).

## Consequences

- Requires `google-adk >= 2.0` and Python >= 3.11.
- ADK session services (`InMemory`/`VertexAi`/`Database`) have no Firestore TTL support, so the custom Firestore session layer in ADR-0003 must preserve user-scoped storage and the `expireAt` TTL policy.
- HITL footguns to respect: unique `interrupt_id` per loop iteration; `rerun_on_resume` semantics per node type.
- The Tue 2 Sep spike must prove, outside the real UI: (1) pause/resume across HTTP requests on Cloud Run, (2) session persistence coexisting with the TTL design, (3) Rule-Matcher firing exactly once per case.
- **Fallback ladder**: if the real Contract Check screen isn't cleanly working end-to-end by **Wed 3 Sep 6pm**, collapse to the same two agents with explicit orchestration calls in app code; only in catastrophe collapse further to a single structured Gemini call per mode.
