# Streaming Voice Audio from the Delphi V3 API

How to send a message to a Delphi clone and play back the voice response as it streams, using only the browser's Web Audio API. No dependencies.

Working reference implementation: [`voice-tester.html`](voice-tester.html) (standalone) and the Voice Chat widget in [`api-reference.html`](api-reference.html).

---

## Audio Format

`POST /v3/voice/stream` returns raw PCM audio:

| Property    | Value                    |
|-------------|--------------------------|
| Sample rate | 24,000 Hz                |
| Bit depth   | 16-bit signed, little-endian |
| Channels    | 1 (mono)                 |
| Byte rate   | 48,000 bytes/sec         |
| Content-Type| `application/octet-stream` |

No WAV header, no container — just raw samples.

---

## End-to-End Flow

### 1. Create a conversation

```js
const r = await fetch("https://api.delphi.ai/v3/conversation", {
  method: "POST",
  headers: { "x-api-key": API_KEY, "Content-Type": "application/json" },
  body: JSON.stringify({}),
});
const { conversation_id } = await r.json();
```

### 2. Fetch the voice stream

```js
const response = await fetch("https://api.delphi.ai/v3/voice/stream", {
  method: "POST",
  headers: { "x-api-key": API_KEY, "Content-Type": "application/json" },
  body: JSON.stringify({ conversation_id, message: "Tell me a story." }),
});
```

The response body is a readable stream of raw PCM bytes, delivered incrementally.

### 3. Set up the AudioContext at 24 kHz

```js
const ctx = new AudioContext({ sampleRate: 24000 });
```

The `sampleRate: 24000` is critical — it must match the PCM data. If the browser doesn't honor this (check `ctx.sampleRate`), you'll need to resample.

### 4. Register an AudioWorklet for click-free streaming

Playing each network chunk as a separate `AudioBufferSourceNode` causes audible clicks at chunk boundaries. Instead, use an AudioWorklet that maintains a continuous FIFO queue:

```js
const WORKLET_CODE = `
class PCMStreamProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];      // Float32Array chunks waiting to play
    this.current = null;  // chunk currently being read
    this.pos = 0;         // read position in current chunk
    this.live = true;

    this.port.onmessage = (e) => {
      if (e.data === 'stop') {
        this.live = false;
        this.queue = [];
        this.current = null;
      } else {
        this.queue.push(e.data); // e.data is a Float32Array
      }
    };
  }

  process(inputs, outputs) {
    if (!this.live) return false; // remove node from graph

    const output = outputs[0][0]; // mono output buffer (128 samples)
    let written = 0;

    while (written < output.length) {
      // Advance to next queued chunk if current is exhausted
      if (!this.current || this.pos >= this.current.length) {
        if (!this.queue.length) {
          // Underrun — fill remainder with silence
          for (; written < output.length; written++) output[written] = 0;
          return true;
        }
        this.current = this.queue.shift();
        this.pos = 0;
      }

      const n = Math.min(this.current.length - this.pos, output.length - written);
      output.set(this.current.subarray(this.pos, this.pos + n), written);
      written += n;
      this.pos += n;
    }
    return true;
  }
}
registerProcessor('pcm-stream', PCMStreamProcessor);
`;

// Register once (inline via Blob URL — no separate file needed)
const blob = new Blob([WORKLET_CODE], { type: 'application/javascript' });
const url = URL.createObjectURL(blob);
await ctx.audioWorklet.addModule(url);
URL.revokeObjectURL(url);
```

### 5. Stream chunks into the worklet

```js
const worklet = new AudioWorkletNode(ctx, 'pcm-stream');
worklet.connect(ctx.destination);

const reader = response.body.getReader();
const allChunks = [];       // keep raw bytes for replay later
let leftover = new Uint8Array(0);

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  // Combine with any leftover byte from previous chunk (PCM = 2 bytes per sample)
  let combined;
  if (leftover.length > 0) {
    combined = new Uint8Array(leftover.length + value.length);
    combined.set(leftover);
    combined.set(value, leftover.length);
  } else {
    combined = value;
  }

  const usable = combined.length - (combined.length % 2); // keep even
  leftover = combined.length % 2 ? combined.slice(usable) : new Uint8Array(0);
  if (usable === 0) continue;

  const pcm = combined.slice(0, usable);
  allChunks.push(pcm);

  // Convert Int16 PCM → Float32 and push to worklet
  const int16 = new Int16Array(pcm.buffer, pcm.byteOffset, pcm.byteLength / 2);
  const f32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) f32[i] = int16[i] / 32768;

  worklet.port.postMessage(f32);
}
```

Audio starts playing as soon as the first chunk is pushed. The worklet outputs silence during any brief gaps between chunks, keeping the audio graph continuous.

### 6. Build a full AudioBuffer for replay

After the stream ends, merge all chunks into one buffer for seek/replay:

```js
const totalLen = allChunks.reduce((s, c) => s + c.length, 0);
const merged = new Uint8Array(totalLen);
let offset = 0;
for (const c of allChunks) { merged.set(c, offset); offset += c.length; }

const int16 = new Int16Array(merged.buffer);
const float32 = new Float32Array(int16.length);
for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768;

const buffer = ctx.createBuffer(1, float32.length, 24000);
buffer.copyToChannel(float32, 0);

// Play via standard AudioBufferSourceNode
const source = ctx.createBufferSource();
source.buffer = buffer;
source.connect(ctx.destination);
source.start(0);
```

### 7. Clean up the worklet

After the streamed audio finishes playing, disconnect:

```js
const remainingSeconds = buffer.duration - (ctx.currentTime - streamStartTime);
setTimeout(() => {
  worklet.port.postMessage('stop');
  worklet.disconnect();
}, Math.max(0, remainingSeconds) * 1000 + 500);
```

---

## CORS Proxy for Browser Use

The Delphi API doesn't serve CORS headers, so browser `fetch()` calls are blocked. The included `serve.py` proxies `/api/*` to `https://api.delphi.ai/*`:

```bash
python3 docs/serve.py          # http://localhost:8787
```

Key detail for the binary voice proxy: **do not use HTTP chunked transfer encoding with Python's `http.server`**. It defaults to HTTP/1.0, which means browsers won't decode the chunked framing — the chunk size headers and terminators end up mixed into the PCM data as audible clicks.

Instead, write raw bytes and flush after each chunk. With HTTP/1.0, connection close signals end-of-body:

```python
# In serve.py _proxy_binary():
while True:
    chunk = resp.read(8192)
    if not chunk:
        break
    self.wfile.write(chunk)
    self.wfile.flush()
```

The browser's `ReadableStream` from `fetch()` delivers each flushed chunk to `reader.read()` as it arrives.

---

## Pitfalls We Hit (So You Don't Have To)

### Chunked encoding framing in PCM data

**Symptom**: Clicking/popping multiple times per second. Debug panel shows alternating ~8194-byte and ~6-byte chunks.

**Cause**: Manual HTTP chunked encoding (`Transfer-Encoding: chunked` header + `size\r\n...data...\r\n` framing) on an HTTP/1.0 server. The browser doesn't decode the framing, so chunk headers like `"2000\r\n"` (6 bytes) get interpreted as audio samples.

**Fix**: Don't write chunked framing. Write raw bytes + flush. See proxy section above.

### Per-chunk AudioBufferSourceNode clicking

**Symptom**: Clicking at regular intervals during playback, even with clean data.

**Cause**: Creating a separate `AudioBufferSourceNode` for each network chunk and scheduling them back-to-back. Tiny timing gaps between nodes produce discontinuities.

**Fix**: Use an AudioWorklet with a continuous FIFO queue (step 4 above). One node, one continuous output stream.

### Odd byte at chunk boundary

**Symptom**: Corrupted audio, pops, or `RangeError` from `Int16Array`.

**Cause**: Network chunks don't align to 2-byte PCM sample boundaries. A chunk might end with one byte of a sample, and the next byte arrives in the next chunk.

**Fix**: Track leftover bytes across chunks (step 5 above). Only convert complete 2-byte pairs.

### AudioContext sample rate ignored

**Symptom**: Audio plays too fast/slow, wrong pitch.

**Cause**: Some browsers don't honor `{ sampleRate: 24000 }` and create the context at the system rate (44100 or 48000).

**Fix**: Check `ctx.sampleRate` after creation. If it doesn't match 24000, create `AudioBuffer` objects at 24000 Hz — the browser will resample automatically when playing through a higher-rate context.

---

## File Reference

| File | What it does |
|------|-------------|
| [`voice-tester.html`](voice-tester.html) | Standalone voice conversation page with full chat UI, mic input, and debug panel |
| [`api-reference.html`](api-reference.html) | API reference with embedded "Try Voice Chat" widget in the Voice section |
| [`serve.py`](serve.py) | Local proxy server — binary streaming, SSE streaming, and standard REST proxying |
