# Delphi Web Embed — Capabilities and Constraints

The web embed is a **third surface**, separate from the V3 and V4 APIs. It runs
entirely in the browser, uses no API key, and is authenticated by channel ID
plus origin. Nothing in this file requires or accepts a `dsk-`/`dlph_` key.

Reach for this file when a user asks to put a clone on a web page, prefill or
auto-send a first message in an embed, restyle an embed, wire SSO into an embed,
or debug an embed that renders but won't behave.

**Verified 2026-08-05** against `https://www.delphi.ai/embed.js` and the embed
app's own client bundles, on a live channel.

## Two generations — check which one the user has

| Script tag | Generation | Iframe origin | Host page can drive the DOM? |
|---|---|---|---|
| `https://www.delphi.ai/embed.js` | **current** | `https://www.delphi.ai/embed/{channelId}` | **No** — genuinely cross-origin |
| `https://embed.delphi.ai/loader.js` | legacy | initially same-origin document | Yes |

This distinction decides every answer about embeds. Always ask for (or read) the
actual script tag before advising.

The legacy loader requires a config `<script>` tag carrying
`id="delphi-page-script"` — it calls `document.getElementById('delphi-page-script')`
and throws *"Script tag with id 'delphi-page-script' not found"* without it. It
reads `window.delphi.page`. The current `embed.js` ignores that ID entirely and
reads `data-*` attributes off its own tag.

## Current embed — `embed.js`

Minimal inline install:

```html
<div id="embed">
  <script src="https://www.delphi.ai/embed.js"
          data-channel="CHANNEL_UUID"
          data-mode="inline" data-width="100%" data-height="600" async></script>
</div>
```

`embed.js` inserts the iframe as its **own previous sibling** (`insertBefore`),
so the iframe lands wherever the script tag sits. To control placement, move the
script tag.

### Script tag attributes — the complete set

| Attribute | Values | Notes |
|---|---|---|
| `data-channel` | channel UUID | Required. Warns to console if absent. |
| `data-mode` | `inline` \| `bubble` | Anything other than `inline` is treated as `bubble`. |
| `data-width` | CSS width | `inline` only. A bare number gets `px`. Default `100%`. |
| `data-height` | CSS height | `inline` only. Bare number gets `px`. Default `600`. |
| `data-position` | `bottom-right` \| `bottom-left` | `bubble` only. Default `bottom-right`. |
| `data-landing-page` | `CHAT` \| `VOICE` \| `OVERVIEW` | Validated against that set; invalid values are dropped. |
| `data-reset-disclaimer` | `1` | Re-shows the disclaimer. |

⚠️ **There is no `data-` attribute for a first message, and no supported
JavaScript call to send one.** If a user wants an embed to open with a question
already asked, the only path is the URL param below.

### Legacy `window.delphi` overrides still honored

`embed.js` reads `window.delphi.page.overrides` (or `window.delphi.bubble.overrides`
in bubble mode) for backward compatibility, then forwards a validated subset onto
the iframe URL:

| Override | Validation |
|---|---|
| `landingPage` | must be `CHAT`/`VOICE`/`OVERVIEW` |
| `primaryColor`, `secondaryColor` | must match `^#[0-9a-fA-F]{6}$` — 3-digit hex and named colors are silently dropped |
| `overrideHeadline` | trimmed, truncated to 120 chars |
| `resetEmbedDisclaimer`, `resetEmbedSession` | booleans; only `true` is forwarded |

`data-landing-page` wins over `overrides.landingPage`.

### Iframe URL parameters

The embed app reads these from its **own** URL. This is the real extension point.

| Param | Set by | Notes |
|---|---|---|
| `q` or `message` | **the host page** | Initial prompt. Also forces the CHAT view. |
| `landingPage` | `data-landing-page` / overrides | Starting view. |
| `theme` | `embed.js` | Hardcoded `light` as of 2026-08-05. |
| `parentOrigin` | `embed.js` | Omitted when `window.location.origin === "null"`. |
| `userOrigin` | `embed.js` | `hostname + pathname`. |
| `primaryColor`, `secondaryColor`, `overrideHeadline` | overrides | See validation above. |
| `resetEmbedDisclaimer`, `resetEmbedSession` | overrides / `data-reset-disclaimer` | `1`. |
| `question_source`, `autoLoadRecent` | — | Present in the app's param-cleanup path but never set by `embed.js`. Undocumented; treat as unsupported. |

The app consumes `q`/`message` into an **entry intent** and strips `message`,
`q`, `question_source`, and `autoLoadRecent` via `history.replaceState`, so the
prompt fires exactly once and won't re-fire on client-side navigation.

Server-side confirmation that a prompt was accepted — the RSC payload carries it:

```bash
curl -s "https://www.delphi.ai/embed/CHANNEL_UUID?theme=light&q=test+question" \
  | grep -o 'entryIntent[^}]*}'
# -> entryIntent\":{\"initialPrompt\":\"test question\"}
```

This is the fastest way to prove the param works for a given channel without a
browser. A missing `entryIntent` means the param never landed.

### First message — the only working technique

Because the iframe is cross-origin, `iframe.contentDocument` is permanently
unreachable and typing into the chat input from the host page is impossible. Any
script that retries `contentDocument` will loop and give up. The fix is to put
the message on the iframe URL:

```js
const iframe = document.querySelector('iframe[src*="delphi.ai"]');
const url = new URL(iframe.src);
url.searchParams.set('q', 'What can you help me with?');
iframe.src = url.toString();
```

Two caveats worth stating up front:

- **The embed loads twice.** `embed.js` sets `src` and inserts the iframe in one
  synchronous pass, so the first load is already in flight before a
  `MutationObserver` can react. Rewriting `src` triggers a second load. There is
  no host-side way around this; a `data-first-message` attribute in `embed.js`
  is the real fix and is worth requesting from Delphi.
- **Guard against observer loops.** Check whether `q` already equals the target
  value before assigning `src`, or the mutation your own write causes will
  retrigger the observer.

A packaged implementation of exactly this (with landing-page support, legacy
loader fallback, and a watch timeout) lives in the `delphi-first-message` repo.

### JavaScript API

`embed.js` sets `window.Delphi` in both modes:

| Method | Inline | Bubble |
|---|---|---|
| `open()` | no-op + console warning | opens the panel |
| `close()` | no-op + console warning | closes the panel |
| `destroy()` | removes the iframe | removes iframe + bubble button |
| `login(token)` | posts `delphi:sso-login` | same, queued until iframe load |
| `logout()` | posts `delphi:sso-logout` | same |

In bubble mode the panel iframe is created lazily on first open, and messages
sent before load are queued and flushed on the `load` event.

### postMessage bridge — SSO only

Inbound messages from the host page are forwarded into the iframe **only** if
they parse as one of `platform_sso_login`, `sso_login`, `sso_logout`,
`platform_sso_logout` (a login also requires a string `token`). Both raw objects
and JSON strings are accepted. Everything else is dropped.

**You cannot send a chat message, change views, or set a prompt over
`postMessage`.** If a user asks for a runtime "send this message now" API, the
honest answer is that it doesn't exist yet — reloading the iframe with `q` is
the workaround.

Outbound, from the embed: `delphi_expand` (bubble fullscreen toggle,
origin-checked and source-checked), `delphi:new-message` (drives the unread
dot), and `delphi:text-exhausted`.

## Debugging checklist

Work top to bottom; each step rules out a whole class of failure.

1. **Is the page on `http(s)://`?** `file://` blocks the embed outright and
   makes `window.location.origin` the string `"null"`, so `parentOrigin` is
   omitted.
2. **Did `embed.js` run?** Look for the `[delphi-embed] host_init` console line.
   It reports `mode`, `channelId`, and the resolved landing page — enough to
   confirm the attributes parsed as intended.
3. **Does an iframe exist with a `delphi.ai` src?** If not, `data-channel` is
   missing or the script 404'd.
4. **Is a host-page script throwing before it runs?** A `SyntaxError:
   Unexpected end of input` from a bundled helper means the bundle is corrupt
   and never executed — verify with `node --check FILE`. Symptom looks identical
   to "the feature doesn't work."
5. **Expecting a prompt?** Read the iframe's `src` and confirm `q=` is on it,
   then confirm the server echoes `entryIntent` (curl above).
6. **`contentDocument` is null** — this is correct and permanent on the current
   embed, not a bug to fix. Switch to the URL-param approach.

Console noise that is **not** an embed problem: a `favicon.ico` 404, and
`[delphi-embed] session_bootstrap_end` / `panel_view` telemetry lines (those are
healthy).

## Embed vs API — routing

| The user wants to… | Surface |
|---|---|
| Put a chat UI on a web page | **embed** |
| Open that UI with a question already asked | **embed** + `q` on the iframe URL |
| Brand colors / headline / starting view | **embed** attributes and overrides |
| Log a known user into the embed | **embed** `window.Delphi.login(token)` |
| Programmatic chat from a server or script | **API** — V3 `/v3/stream` or V4 `/v4/conversations/{id}/messages` |
| Read conversation history or transcripts | **API** — the embed exposes none |
| Audience, retention, contacts, KB writes | **API** |

The embed and the API do not share conversation state in any way the host page
can observe. If a user wants to read what someone said in an embed, that's an
API question (`/v3/conversation/list`, `/v4/contacts/{id}/threads`), not an
embed one.
