# Delphi V4 Endpoints - Tested Coverage and Notes

V4 is the **Delphi Developer Platform API** (`openapi: 3.1.0`, `info.version: 4.0.0`)
— a *separate product surface* from V3, not a replacement for it. Captured from
the live spec at `GET /v4/openapi.json` and grounded in real read-only tests
(2026-08-01).

Base URL: `https://api.delphi.ai/v4`
Authentication: `x-api-key` header, same as V3. **Existing V3 keys work against
V4** (verified — a `dsk-` key returned 200 on every read endpoint below).
Fetching the spec itself also requires a valid key: `GET /v4/openapi.json`
returns `401` unauthenticated (V3's returns `403`).

## READ THIS FIRST: V4 does not replace V3

V4 has **zero overlap** with V3's conversational surface. There is no `/stream`,
`/conversation`, `/voice`, `/questions`, `/search`, `/agent`, or `/clone` in V4.
Confirmed by scanning every path in the live spec.

**Do not plan a V3 → V4 migration.** They are complementary:

| Need | Use |
|------|-----|
| Chat / SSE streaming, voice, KB search, agent | **V3** — V4 has none of it |
| Contacts/CRM, custom properties, cohort filtering | **V4** — richer than V3 `/users` |
| Knowledge-base **writes** (create/update/delete content) | **V4** — V3 can only *search* content |
| Outbound SMS/email to a contact | **V4** `/send` — no V3 equivalent |
| Owner-voice text generation (no retrieval) | **V4** `/generate` |
| Raw OpenAI-compatible completions | **V4** `/llm/chat/completions` |
| Webhooks / event subscriptions | **V4** — no V3 equivalent |
| Deployed custom code (integrations platform) | **V4** — no V3 equivalent |

## Conventions that differ from V3

These bite if you assume V3 habits carry over.

1. **Response envelope.** V4 wraps successful payloads in `{"data": ...}`.
   V3 returns bare objects. **The envelope is not uniform** — always check the
   actual shape:
   - `{"data": [...]}` — `/contacts`, `/content`, `/contact-tags`, `/contact-properties/definitions`, `/integrations`, `/contacts/{id}/properties`, `/contacts/{id}/threads`
   - `{"data": {...}}` — `/profile`, `/contacts/{id}`, `/content/{id}`
   - `{"data": {"subscriptions": [...]}}` — `/webhook-subscriptions` (nested!)
   - `{"data": {"questions": [...]}}` — `/profile/questions` (nested!)
   - `{"data": "ok"}` — mutation acks (tag assign/unassign, property delete, content delete, notify-owner)
   - **No envelope at all** — `/llm/chat/completions` returns a raw OpenAI object
2. **Error shape.** V4 returns `{"type", "code", "message", "param"?, "details"?}`.
   V3 returns `{"detail": "..."}`. Code written against V3's `detail` key will
   silently fail to surface V4 errors. For `403` entitlement errors, `details`
   carries `{feature, currentPlan, upgradeTo}` (`feature_gated`) or
   `{quotaKey, used, limit, currentPlan, upgradeTo}` (`entitlement_quota_exceeded`).
   `/llm/chat/completions` is the exception — it uses the OpenAI envelope
   `{"error": {"message", "type", "code", "param"}}`.
3. **camelCase everywhere.** `nextCursor`, `lastInteractedAt`, `totalInteractionCount`,
   `accessTier`, `isSmsOptIn`. V3 is snake_case (`next_cursor`, `date_joined`).
4. **Pagination.** Cursor-based via `nextCursor` → pass back as `?cursor=`.
   `nextCursor` is `null` on the last page (V3 uses a `has_more` boolean).
   **`limit` maxes at 200**, same real cap as V3's `/users` — default 50.
5. **Vocabulary.** `clone` → **mind**, `users` → **contacts**, `tags` →
   **contact-tags**, conversations → **threads** / **thread-sessions**.

## Scopes

V4 documents a **scoped-key model** — a departure from V3, where a key is simply
valid or not. Scopes named in the live spec:

`contacts:list` · `contacts:list:pii` · `contacts:read` · `content:read` ·
`content:write` · `transcripts:read` · `llm` · `integrations:read` ·
`integrations:source:read`

`contacts:list:pii` is the one to know: **without it, `GET /contacts` returns
PII-free rows** (no `email`, no `phone`). With it, those fields appear. Tested
keys carried it — a key that suddenly returns rows without emails has not lost
data, it has lost a scope.

Note: the spec declares only `ApiKeyAuth` under `securitySchemes` and no
per-operation `security` blocks, so scopes appear **only in prose descriptions**.
You cannot enumerate a key's scopes from the spec — discover them by calling.

---

## Profiles

- `GET /v4/profile` — owner profile for the key: user summary, bio, headline,
  `settings`, `socialLinks[]`, `isVerified`, and suggested `questions`.
  Rough V4 analogue of V3's `GET /v3/clone` for identity discovery.
- `GET /v4/profile/questions` — profile-level suggested questions.
  **The v4 replacement for V3's `GET /v3/questions`.** Response nests:
  `{"data": {"questions": [...]}}`.
- `GET /v4/profiles/{username}` — public profile by username handle (e.g. `jc3`).
  Private profiles visible only to owner, collaborators, or linked contacts.

## Contacts

The V4 evolution of V3's `/users`, with a materially richer object.

- `GET /v4/contacts` — cursor-paginated cohort list. Requires `contacts:list`.
  - Query: `search`, `tagIds[]`, `accessTier[]` (`PUBLIC|PREMIUM|INTERNAL|PRIVATE`),
    `smsOptIn`, `status` (`active|invited`), `totalInteractionMin`/`Max`,
    `lastInteractedAfter`/`Before` (ISO), `cursor`, `limit` (1–200, default 50),
    `sort` (`name|messages|lastActive`, default `lastActive`),
    `direction` (`asc|desc`, default `desc`)
  - **Far more filterable than V3 `/users`**, which offered only `limit`,
    `cursor`, and `active`. Server-side cohort filtering replaces client-side
    sifting.
  - Row fields (verified): `id`, `tags[]`, `lastInteractedAt`,
    `totalInteractionCount`, `source`, `isSmsOptIn`, `isEmailOptIn`,
    `email`*, `phone`* (*PII scope only)
- `POST /v4/contacts` — **email-keyed upsert.**
  - Body: `email` (required, the upsert key), `name`, `tags[]` (created if
    needed, assigned idempotently), `accessTier` (`PUBLIC|INTERNAL`)
  - Response: `{"data": {"contactId": "...", "wasCreated": true|false}}`
  - **`wasCreated` resolves the ambiguity that V3's `/users/lookup` left open.**
    In V3 you had to sweep the audience beforehand to know whether a lookup
    inserted or matched; V4 states it outright. Prefer this for any new
    contact-management code.
- `GET /v4/contacts/{id}` — one contact. Requires `contacts:read`.
  Fields (verified): `id`, `name`, `email`, `phone`, `tags[]`, `accessTier`,
  `status`, `source`, `isAnonymous`, `isEmailOptIn`, `isSmsOptIn`,
  `totalInteractionCount`, `lastInteractedAt`, `createdAt`, `user`
- `PATCH /v4/contacts/{id}` — body `{"accessTier": "PUBLIC"|"INTERNAL"}`.
  Access tier only; this is not a general-purpose contact editor.
- `GET /v4/contacts/{id}/threads` — cursor-paginated conversations, newest-first.
  Transcript-class content requires `transcripts:read`. A contact with no linked
  visitor returns an empty page (not a 404).
  Row fields (verified): `threadId`, `summary` (full narrative summary),
  `lastMessageText`, `lastMessageSenderType`, `lastMessageAt`, `messageCount`,
  `channelType`
  - Closest V4 analogue to V3's `GET /v3/conversation/list?email=` — but keyed
    by contact ID, and it returns a summary + preview rather than a bare list.

## Contact tags

- `GET /v4/contact-tags` — all tag definitions. Color auto-assigned.
- `POST /v4/contact-tags` — body `{"name": "..."}` (1–50 chars).
  Unlike V3's `POST /v3/tags`, **color is not caller-supplied** — it is assigned
  from a fixed palette.
- `POST /v4/contacts/{id}/tags` — body `{"tagId": "..."}`. Idempotent.
  Note: **assign takes a tag ID in the body**, whereas V3 took a tag *name* in
  the path.
- `DELETE /v4/contacts/{id}/tags/{tagId}` — idempotent; removing an absent
  assignment is safe.
- `POST /v4/contacts/bulk/tags` — apply an add/remove diff across explicit
  contact IDs *or* a filter target. Body: `target` (IDs or filter), `add[]`,
  `remove[]`. No V3 equivalent — this is the bulk-segmentation primitive.

## Contact properties

Custom, owner-defined fields on a contact. **No V3 equivalent** (V3's closest
relative is the fixed-vocabulary `/users/{id}/info`).

- `GET|POST /v4/contact-properties/definitions` — list / create definitions.
  Create body: `{"name": "..."}` (1–50 chars). Color auto-assigned; allowed
  values are not exposed on v4 (free-text only).
- `GET|POST /v4/contacts/{id}/properties` — list / create values for a contact.
  Create body: `{"propertyDefinitionId": "...", "value": "..."}` (value 1–500).
- `PATCH|DELETE /v4/contacts/{id}/properties/{propertyValueId}` — update
  (`{"value": "..."}`) or delete one value.

## Content (knowledge base writes)

**The biggest genuinely new capability for most users.** V3 could only *search*
the knowledge base; V4 can create, edit, and delete it.

- `GET /v4/content` — cursor-paginated, newest-first. Requires `content:read`.
  - Query: `cursor`, `limit` (1–200), `type` / `types[]`, `status` /
    `statuses[]`, `folderId` (UUID, or the literal `"null"` for unfiled),
    `accessTier`, `search` (title, case-insensitive), `uploadId`
  - `type` vocabulary (33 values): `PDF`, `DOCX`, `EPUB`, `CSV`, `SRT`, `XLSX`,
    `TXT`, `RTF`, `HTML`, `AUDIO_FILE`, `MARKDOWN`, `IMAGE`, `PPTX`, `YOUTUBE`,
    `PODCAST`, `WEBSITE`, `EVERNOTE`, `QA`, `SLACK`, `NOTION`, `SUBSTACK`,
    `TWITTER`, `TIKTOK`, `FACEBOOK`, `INSTAGRAM`, `LINKEDIN`, `MANUAL`, `VIMEO`,
    `JSONL`, `LOOM`, `GRANOLA`, `GITHUB`, `OBSIDIAN`
  - `status` vocabulary: `START`, `QUEUED`, `PROCESSING`, `COMPLETE`, `FAILED`, `DELETING`
- `POST /v4/content` — ingest 1–100 items. Requires `content:write`.
  - Body: `items[]` (required), `folderId`, `accessTier` (`PUBLIC|INTERNAL|PRIVATE`, default `PUBLIC`)
  - Each item is one of three shapes:
    - `{"type": "qa", "question": "...", "answer": "..."}` (4,000 / 20,000 chars)
    - `{"type": "note", "text": "...", "title": "..."}` (100,000 chars; title derived if omitted)
    - `{"type": "url", "url": "https://..."}` (2,048 chars)
  - **Ingestion is asynchronous.** Each item returns a `contentId` immediately,
    then processes in the background. Poll `GET /v4/content/{id}` — or filter
    the list by the returned `uploadId` — until `status` is `COMPLETE`.
- `GET /v4/content/{id}` — one item, including `status` and (for QA/note) the
  inline `question`/`answer`/`text` body.
- `PATCH /v4/content/{id}` — update in place. Requires `content:write`.
  - Editing `question`/`answer` (QA) or `text` (note) **rewrites the body and
    re-learns it** — the item returns to `START` and is re-embedded. No
    delete-and-reupload needed.
  - Metadata editable on any type: `title`, `accessTier`, `folderId` (null to
    unfile), `context` (≤2000, shown to the mind), `publishedAt` (ISO or null),
    `createdBy` (string, or `{"kind": "self"}`), `citationUrl` (≤2048),
    `hideCitation`
- `DELETE /v4/content/{id}` — removes from the KB and unlearns asynchronously.
  **Destructive — real knowledge loss. Confirm with the user first.**

## Generate / Send / Notify

Outbound and generation primitives. None have a V3 equivalent.

- `POST /v4/generate` — one reply in the owner's mind voice.
  - Body: `prompt` (required, 1–8000), `channelId`, `includeKnowledgeBase`,
    `idempotencyKey`
  - Response: `{"data": {"text", "budgetRemaining", "replayed"}}`
  - **`includeKnowledgeBase` is accepted but explicitly IGNORED** — this path
    does *no* retrieval. It is voice, not RAG. For knowledge-grounded answers
    use V3 `/v3/search/query` or `/v3/agent/run`.
  - **Metered by a daily budget enforced per OWNER, not per key** — minting
    extra keys cannot multiply the cap. Enforced in Redis and **degrades
    CLOSED**: if Redis is unreachable the call fails `503` rather than
    generating un-metered. An exhausted budget returns `429`.
    (Observed budget on a tested account: 10,000/day.)
  - **Idempotency verified live**: repeating a call with the same
    `idempotencyKey` returned the original text verbatim with
    `"replayed": true` and `"budgetRemaining": null` — no slot reserved, model
    not re-invoked. Key may also travel as an `Idempotency-Key`,
    `X-Delivery-Id`, or `X-Step-Id` header (body wins).
- `POST /v4/send` — **deliver an SMS or email to a real contact.**
  - Body: `contactId`, `channel` (`sms|email`), `body`, `idempotencyKey`
  - **Consent is enforced server-side** against the contact's own per-channel
    opt-in flag; a caller-supplied opt-in is never trusted. An opted-out contact
    returns `422 consent_rejected`.
  - Returns `200` with a discriminated outcome — branch on `data.outcome`:
    `sent` (with `externalId`), `carrier_failed` (with `reason`), or
    `generation_failed` (with `reason`). **A 200 does not mean delivered.**
  - **NEVER call this while testing.** It messages a real person. Not covered by
    the test harness by design.
- `POST /v4/notify-owner` — freeform notification to the mind owner and editor
  collaborators via Knock. Body: `subject` (≤200), `body` (≤1000); both
  sanitized server-side. **The recipient is always the key owner** and is never
  read from the request body — it cannot be aimed at a third party.

## LLM (OpenAI-compatible)

- `POST /v4/llm/chat/completions` — raw, **voiceless** model completion.
  - Point an unmodified OpenAI client at base URL `/v4/llm` and authenticate
    with a Delphi key holding the `llm` scope.
  - Body: `messages[]` (required); `model` accepted **but ignored** — every
    request routes to the Delphi-hosted model. Response `model` is always
    `delphi-llm`.
  - **Synchronous and non-streaming**: `stream: true` is *rejected*, not
    silently coerced. **Tool/function calling is rejected.**
  - Sampling params (`temperature`, `top_p`, `seed`, `stop`, `max_tokens`, …)
    are forwarded; `max_tokens` is clamped to a server ceiling.
  - **No `data` envelope** — returns a raw OpenAI object (`id`, `object`,
    `created`, `model`, `choices[]`, `usage`). Errors use the OpenAI envelope.
  - Verified live: responses may carry a non-standard `reasoning_content` field
    alongside `content` inside `choices[].message`. Don't assume strict OpenAI
    field parity when parsing.
  - `409` if a request with the same `Idempotency-Key` is already in flight.
  - This is **not** the mind's voice — for that use `/v4/generate`.

## Thread sessions

- `GET /v4/thread-sessions/{threadSessionId}/contact` — resolve a session to its
  owner-scoped contact. Useful for turning a webhook payload into a contact.
- `GET /v4/thread-sessions/{threadSessionId}/transcript` — transcript messages
  within a completed session.

## Webhook subscriptions

No V3 equivalent. Response nests: `{"data": {"subscriptions": [...]}}`.

- `GET|POST /v4/webhook-subscriptions` — list / create.
  - Create body: `targetUrl` (required, HTTPS, **validated for SSRF safety**),
    `endpointId`, `name`, `eventType`, `trigger`, `inactivityThresholdDays`
    (1–365), `jmespathFilter` (null/empty delivers all)
  - **Creating the first subscription reveals the account signing secret once**
    if no active secret exists yet. Capture it at creation — treat it as a
    credential.
- `GET|PUT|DELETE /v4/webhook-subscriptions/{id}` — read / update / soft-delete.
  A changed `targetUrl` is re-validated for SSRF.

**Event vocabulary** (9 — shared with integration triggers and the delivery log):
`thread-session-ended`, `chat-visitor-message-sent`, `contact-created`,
`contact-updated`, `contact-deleted`, `alert-occurrence-created`,
`affiliate-product-mention-created`, `phone-number-captured`,
`contact-inactivity-threshold-crossed`

## Integrations (21 operations)

A full deploy-your-own-code platform: bundled JS runs on Cloudflare, triggered by
Delphi events or cron. **The largest single area of V4 and the highest-risk.**
No V3 equivalent.

- **Lifecycle**: `GET|POST /v4/integrations`, `GET|DELETE /v4/integrations/{id}`,
  and slug-addressed twins `GET|DELETE /v4/integrations/by-slug/{slug}`.
  `POST /v4/integrations/push` upserts by slug — a re-push of a live integration
  **hot-swaps the running bundle**.
- **Deploy state**: `POST /{id}/publish`, `POST /{id}/unpublish`,
  `POST /by-slug/{slug}/activate`, `POST /by-slug/{slug}/deactivate`
  (activate/deactivate are idempotent no-ops when already in the target state).
- **Code**: `GET|PUT /{id}/source`, `GET /by-slug/{slug}/source`
  (needs `integrations:source:read`), `PUT /{id}/build-artifact`.
  `codeBundle` is esbuild output, ≤1,000,000 chars — **bundling happens upstream
  of the API**.
- **Secrets**: `GET /{id}/secrets` (names only), `PUT|DELETE /{id}/secrets/{name}`.
  Plaintext (≤16384) is **accepted once and never returned**.
- **Triggers**: `GET|PUT /{id}/triggers` — event subscriptions + per-event
  JMESPath filters, from the 9-event vocabulary above.
- **Observability**: `GET /{id}/log` — keyset-paginated delivery log; filter by
  `eventType`, `outcome` (`skipped|delivered|failed`), `contactId`, `since`.
  Metadata is visible to any reader, but **captured request/response bodies and
  headers are editor/owner-only** and hidden from `integrations:read` API keys.
  Note this endpoint returns `{"data", "response_metadata"}` — not the usual
  `nextCursor` shape.
- **Misc**: `POST /{id}/regenerate-overview` — force a fresh async Overview.

Cross-cutting behavior worth knowing:

- Most integration endpoints accept `?ownerUserId=` — "when acting as a
  collaborator, the owner whose data to act on; omit for self."
- The advisory **audit never gates a deploy**. Findings are attached to the
  record; the spec is explicit that "the runtime is the real boundary."
  Do not read a clean audit as a safety guarantee.
- `declaredHosts` is the egress allowlist, enforced at runtime by the loader.
- **`503` is a meaningful, distinct state here**: the Cloudflare loader is
  unconfigured/unreachable and *nothing went live*. On `push` it can mean code
  was stored but not deployed. Treat `503` as "partially applied — re-check
  state", not a generic retry.
- `forceOrphan=true` on delete commits the soft-delete even if CF unpublish
  fails, deliberately orphaning the runtime tenant so an unreachable loader
  can't make an integration undeletable.

## Data deletion

- `POST /v4/data-deletion-requests` — body `{"email": "..."}`. Queues deletion of
  that contact's conversations, audience profile, and visitor memory **for this
  Delphi only** — it does not touch their platform account or their
  relationships with other Delphis. Returns `202` (queued for administrator
  execution), not `200`.
  **Destructive and effectively irreversible. Explicit user confirmation
  required before calling.**

## Common error codes

| HTTP | Meaning | V4 notes |
|------|---------|----------|
| 200 | Success | Payload under `data` (except `/llm/*`) |
| 202 | Accepted | `/data-deletion-requests` — queued, not done |
| 400 | Bad Request | Validation failed |
| 401 | Unauthorized | Missing/invalid key. **Unauthenticated `/v4/openapi.json` returns 401** (V3 returns 403) |
| 403 | Forbidden | Often a **missing scope**, not a dead key. `details` carries `feature_gated` / `entitlement_quota_exceeded` context |
| 404 | Not Found | Resource absent |
| 409 | Conflict | `/llm/*` — same `Idempotency-Key` already in flight |
| 422 | Unprocessable | `/send` — `consent_rejected` (contact not opted in) |
| 429 | Rate Limited | Also an **exhausted `/generate` daily budget** |
| 500 | Server Error | Backend failure |
| 502 | Bad Gateway | Upstream generation / model provider failed |
| 503 | Unavailable | `/generate`: budget unenforceable (fails closed). Integrations: CF loader unreachable, **nothing went live** |

**No numeric rate limit is published in the V4 spec** — unlike V3's documented
120 req/60s. Nearly every write endpoint documents `429`, but no window or
ceiling is stated. Assume conservative pacing until Delphi documents one.

## Safety rules for V4 testing

V4's write surface is materially more dangerous than V3's. In V3 the worst
accidental write renamed a user; in V4 it can message a real person, delete
knowledge, or deploy code.

**Never call while testing, without explicit per-call user confirmation:**

- `POST /v4/send` — sends a real SMS/email to a real person
- `POST /v4/data-deletion-requests` — queues irreversible deletion
- `DELETE /v4/content/{id}` — real knowledge-base loss
- Any `integrations` publish / activate / push / delete — deploys or tears down
  live code
- `PUT /v4/integrations/{id}/secrets/{name}` — writes a credential

**Metered — safe but not free:** `POST /v4/generate` (daily owner budget) and
`POST /v4/llm/chat/completions` (token spend). Use sparingly; prefer an
idempotency key so retries don't double-charge.

**Safe read-only baseline** (all verified `200` on a production key):
`GET /profile`, `/profile/questions`, `/profiles/{username}`, `/contacts`,
`/contacts/{id}`, `/contacts/{id}/threads`, `/contact-tags`,
`/contact-properties/definitions`, `/content`, `/content/{id}`,
`/integrations`, `/webhook-subscriptions`.
