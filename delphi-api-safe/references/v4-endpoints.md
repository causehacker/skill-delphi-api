# Delphi V4 Endpoints - Tested Coverage and Notes

V4 is the **Delphi Developer Platform API** (`openapi: 3.1.0`, `info.version: 4.0.0`).
Captured from the live spec at `GET /v4/openapi.json` and grounded in real tests.

**Last cross-checked 2026-08-02: 47 paths / 65 operations** (up from 40 / 58 the
previous day — Delphi added a conversational surface plus attachments; see
"Conversations" below).

Base URL: `https://api.delphi.ai/v4`
Authentication: `x-api-key` header, same as V3. **Existing V3 keys work against
V4** (verified — a `dsk-` key returned 200 on every read endpoint below).
Fetching the spec itself also requires a valid key: `GET /v4/openapi.json`
returns `401` unauthenticated (V3's returns `403`).

## READ THIS FIRST: how V4 relates to V3

**This changed on 2026-08-02.** V4 gained a full conversational surface —
`POST /v4/conversations`, `/messages`, `/messages/stream`, `/ask`, and
conversation insights. An earlier version of this document said V4 had "zero
overlap" with V3 and told readers not to plan a migration. **That is no longer
true.** If you are following older notes, re-read this section.

What V4 still does **not** have: `/voice/*`, `/search/*`, `/agent/run`, and
`/clone` (its nearest equivalent is `GET /v4/profile`). Everything else in V3's
chat path now has a V4 counterpart.

| Need | Use | Notes |
|------|-----|-------|
| Chat — create a conversation and send messages | **either** | V4 additionally offers a **synchronous** send (no SSE parsing). See the comparison below. |
| SSE token streaming | **either** | V4's `/messages/stream` reuses V3's exact `CloneResponse` frame contract — existing parsers port unchanged |
| One-shot Q&A with no conversation state | **either** | V3 `/conversation/ask`, V4 `/ask` — ⚠️ **both currently return 502**, see below |
| Voice audio / TTS | **V3 only** | no V4 equivalent |
| Knowledge-base search & the KB agent | **V3 only** | `/v3/search/*`, `/v3/agent/run` |
| Audience sizing & retention analytics | **V3** | `/v3/users` + `/v3/conversation/list` |
| Contacts/CRM, custom properties, cohort filtering | **V4** | far richer than V3 `/users` |
| Knowledge-base **writes** (create/update/delete) | **V4** | V3 can only *search* content |
| Outbound SMS/email to a contact | **V4** `/send` | no V3 equivalent |
| Owner-voice generation (no retrieval) | **V4** `/generate` | |
| Raw OpenAI-compatible completions | **V4** `/llm/chat/completions` | |
| Webhooks, integrations platform | **V4** | no V3 equivalent |

### Choosing a chat surface now that both have one

| | V3 | V4 |
|---|---|---|
| Create | `POST /v3/conversation` | `POST /v4/conversations` |
| Send (streaming) | `POST /v3/stream` | `POST /v4/conversations/{id}/messages/stream` |
| Send (synchronous) | — | `POST /v4/conversations/{id}/messages` ✅ |
| Idempotent create | — | `externalId` (409 on reuse with different input) ✅ |
| Attachments | ✅ (new) | ✅ (new) |
| Scope required | none (legacy keys unscoped) | **`conversations:write`** — see Scopes |

**Prefer V4 for new chat integrations** when you want the synchronous send or
idempotent conversation creation, *and* your key carries `conversations:write`.
**Stay on V3** if you need voice or knowledge-base search in the same flow, or if
your key lacks the scope — which is the common case today (see Scopes).

There is still no reason to migrate working V3 chat code purely for its own sake.

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

## Scopes — read this before choosing which key to use

V4 uses a **scoped-key model**; V3 keys are simply valid or not. This has a
counter-intuitive consequence verified on 2026-08-02:

> **Legacy `dsk-` keys work on more of V4 than the newer `dlph_` App-Launch keys
> do.** Legacy keys appear unscoped/full-access and returned `200` on every V4
> endpoint tested (25/25 across five clones). Most App-Launch keys are missing
> `conversations:write` and `insights:read`, so they get `403` on the entire
> conversational surface.

**Do not assume "newer key = more access."** The App-Launch advantage is the
10k req/min rate limit, not breadth. On the newest V4 endpoints it is *narrower*.

The full scope vocabulary observed on a fully-provisioned key (21 scopes):

```
profile:read        content:read          content:write       contacts:read
contacts:write      contacts:delete       contacts:list       contacts:list:pii
transcripts:read    webhooks:read         webhooks:write      integrations:read
integrations:source:read                  integrations:write  subscriptions:write
send                notify-owner          generate:text       llm
insights:read       conversations:write
```

Two to know:

- **`conversations:write`** gates `POST /v4/conversations`,
  `/messages`, and `/messages/stream`. Without it: `403`.
  Measured across the App-Launch keys on hand, only **2 of 16** had it.
- **`contacts:list:pii`** — without it, `GET /contacts` returns rows with **no
  `email` or `phone`**. That looks like missing data but is a scope difference.

A missing scope produces an unambiguous error that names it:

```json
{"type":"forbidden","code":"insufficient_permissions",
 "message":"API key is missing required scope: conversations:write",
 "details":{"scope":"conversations:write"}}
```

**Use this to tell scope problems apart from outages.** A `403
insufficient_permissions` is a provisioning issue — ask Delphi to add the scope.
A `502 dependency_failure` is a backend fault and no amount of scope will fix it.

**Migration trap:** switching a clone from its legacy `dsk-` key to a `dlph_`
App-Launch key can silently *remove* access to the V4 conversational endpoints.
Verify with `POST /v4/conversations` before cutting over.

Note: the spec declares only `ApiKeyAuth` under `securitySchemes` and no
per-operation `security` blocks, so scopes appear **only in prose descriptions**.
You cannot enumerate a key's scopes from the spec — discover them by calling
(the `scripts/test_delphi_v4.py` harness reports the ones it can infer).

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

## Conversations — added 2026-08-02

The newest V4 surface. All of these require **`conversations:write`** (insights
require `insights:read`) — see Scopes; most App-Launch keys lack both.

- `POST /v4/conversations` — create a conversation.
  - Body (all optional): `channelId` (defaults to the owner's API channel),
    `contactId` (omit for an anonymous conversation), `externalId`
    (caller-supplied idempotency key, 1–512), `overrides` (see below)
  - **`overrides`** — conversation-level experience overrides. Merge chain is
    `experience_config → channel → conversation`, so these win over both.

    | Field | Type | Description |
    |---|---|---|
    | `purpose` | string | Override the Mind's purpose for this conversation. Max 10,000 chars. |
    | `defaultLanguage` | string | BCP-47 code to respond in (`"es"`, `"fr"`, `"pt-BR"`). |
    | `multipleLanguages` | boolean | When `false` **and** `defaultLanguage` is set, always respond in that language regardless of what the user writes. |

    ```bash
    curl -sS -X POST "https://api.delphi.ai/v4/conversations" \
      -H "x-api-key: $DELPHI_API_KEY" -H "Content-Type: application/json" \
      -d '{"overrides":{"defaultLanguage":"es","multipleLanguages":false}}'
    ```

    ⚠️ **Language enforcement is advisory, not guaranteed** — same behavior as
    the V3 equivalent. Measured 2 of 5 trials complied; the Mind sometimes
    narrates the directive in English instead of obeying it, and with `"fr"` it
    refused outright as off-voice for the persona. See the V3 note in
    `v3-endpoints.md` for the full findings. Setting the language inside
    `overrides.purpose` as well is a stronger lever, since it edits the persona
    rather than competing with it.
  - Response: `{"data": {"conversationId": "...", "existed": false}}`
  - **`externalId` makes creation idempotent** — a second call with the same
    value returns the existing conversation (`existed: true`). Reusing it with a
    *different* contact, channel, or settings returns `409`. V3 has no equivalent;
    this is the clean way to avoid duplicate conversations on retry.
  - ⚠️ **Creation is eventually consistent — you cannot send a message
    immediately.** The call returns a `conversationId` before the underlying
    thread exists. Posting to `/messages` right away fails with:

    ```json
    {"type":"not_found","code":"resource_not_found","message":"Thread not found"}
    ```

    Measured 2026-08-02: ready after **~2–6 seconds** (`insights` is readable
    instantly, so only the *thread* lags). **Retry on `404` with ~1s backoff**
    rather than sleeping a fixed amount — treat a 404 immediately after create
    as "not ready yet", not "wrong id". This bites the obvious
    create-then-send integration on the very first call.
- `POST /v4/conversations/{conversationId}/messages` — **send and wait**.
  - Body: `text` (required, 1–50,000), `attachmentIds[]`
  - Response: `{"data": {"userMessageId", "assistantMessageId", "text",
    "citations": [], "parts": [{"type":"text","text":"..."}]}}`
  - **Synchronous — no SSE parsing.** This is the single biggest ergonomic win
    over V3, where every reply requires consuming a stream. Verified live:
    returns the complete assistant reply in one JSON round-trip.
- `POST /v4/conversations/{conversationId}/messages/stream` — SSE stream.
  - Same body as above; response is `text/event-stream`.
  - The spec states it "uses the v3 CloneResponse SSE frame contract" — verified:
    frames carry `current_token`, and the stream terminates with `[DONE]`, exactly
    like `/v3/stream`. **Existing V3 SSE parsers work unchanged.**
  - Observed ~59–65 frames and ~5s for a short answer.
- `GET /v4/conversations/{conversationId}/insights` — cursor-paginated insight
  cards (`limit` 1–200, default 50). Requires `insights:read`.
  - **Returns existing cards only; it does not trigger synthesis.** Insights are
    generated asynchronously, so a freshly created conversation returns
    `{"data": [], "nextCursor": null}` — that is normal, not an error.
- `POST /v4/ask` — stateless Q&A. **⚠️ Currently returns `502` for all callers —
  see the note below.**
  - Body: `question` (required, 1–50,000), `contactId` (informs the answer with
    that contact's identity and access tier), `idempotencyKey` (1–512)
  - Answers from the knowledge base **without creating** a conversation, session,
    message, attachment, preview, or insight.
  - `409` if an idempotency key is reused with different input.

### ⚠️ `/v4/ask` and `/v3/conversation/ask` are currently broken

Both stateless "ask" endpoints return `502` on every request:

```json
{"type":"bad_gateway","code":"dependency_failure",
 "message":"The response service failed. Please try again.",
 "details":{"failureKind":"experience_stream_incomplete","attemptCount":1,"status":200}}
```

Verified deterministic — 0 successes in 24+ attempts across 5 clones, both key
styles, both API versions, and keys with the complete scope set. **Not a scope
issue** (that would be `403`, not `502`), and not transient (unlike the known
intermittent `500` on `/v3/stream`, retries never clear it). It fails in ~0.4s
while a real generation takes ~5s, so it is failing at stream open rather than
timing out.

**Workaround** — two calls instead of one:

```
POST /v4/conversations                 -> conversationId
POST /v4/conversations/{id}/messages   -> answer
```

This leaves behind conversation state that `ask` exists to avoid, and doubles
request count. Reported to Delphi 2026-08-02; re-test before relying on `ask`.

## Attachments (V4) — added 2026-08-02

Two-step upload, mirroring the V3 flow with camelCase fields.

1. `POST /v4/conversations/{conversationId}/attachments/presign`
   - Body: `fileName` (1–255), `contentType` (≤255), `fileSize` (**≤10,485,760
     bytes / 10 MB**)
   - Response carries a presigned **S3 PUT URL** — upload the bytes directly to it
2. `POST /v4/conversations/{conversationId}/attachments/{attachmentId}/complete`
   - Verifies and indexes the uploaded file

Then pass the attachment id in `attachmentIds[]` on a `/messages` call. The V3
equivalent returns `status: indexed | skipped`, with `reason` one of
`no_extractable_content`, `indexing_unavailable`, `unsupported_media_type` —
**a `skipped` result is a success response, so check `status`, not just the HTTP
code.**

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

**Metered — safe but not free:** `POST /v4/generate` (daily owner budget),
`POST /v4/llm/chat/completions` (token spend), and the conversation endpoints
(`/messages`, `/messages/stream`) which invoke the model per call. Use sparingly;
prefer an idempotency key so retries don't double-charge.

**Note on `/generate` budgets:** the daily cap is **per owner and varies by
account** — observed 9,999/day on one account and 494/day on another. Read
`budgetRemaining` from the response rather than assuming a fixed ceiling.

**Safe read-only baseline** (all verified `200` on a production key):
`GET /profile`, `/profile/questions`, `/profiles/{username}`, `/contacts`,
`/contacts/{id}`, `/contacts/{id}/threads`, `/contact-tags`,
`/contact-properties/definitions`, `/content`, `/content/{id}`,
`/integrations`, `/webhook-subscriptions`,
`/conversations/{id}/insights` (needs `insights:read`).

Creating a conversation (`POST /v4/conversations`) is technically a write but is
cheap and side-effect-light — it allocates an id and nothing else. It is the
right first call when checking whether a key holds `conversations:write`.
