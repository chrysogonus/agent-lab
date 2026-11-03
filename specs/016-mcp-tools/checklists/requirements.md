# Specification Quality Checklist: M16 — Tools over MCP

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-03
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- MCP is the subject of the milestone, so the spec names the protocol, its servers and its two
  transports (a local program, an address over HTTP). It leaves message formats, file formats,
  modules and the protocol revision to the plan.
- SC-005 and SC-006 are manual checks: an outside client, and a real model
  (`openai/gpt-6-luna` while the local model is off).
- Defaults chosen without asking, listed under Assumptions: tools only; the servers file is the
  grant; up to 6 tools per model-call block; 10 s to connect, 30 s per call; results cut at
  20,000 characters; no OAuth.
