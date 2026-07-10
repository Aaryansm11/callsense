# CallSense — Every Concept Explained From Scratch
### Companion to the 0→1 Plan. Format: What it is → How it works → Example.

---

# PART 1 · AUDIO & SPEECH

### 1.1 Speech-to-Text (STT / ASR / Transcription)
**What:** Converting spoken audio into written text. ASR = Automatic Speech Recognition.
**How:** A neural network takes the audio waveform, converts it into a spectrogram (a picture of
which frequencies occur at which times), and a sequence model (today, a Transformer) maps those
frequency patterns to text tokens, using both the sound AND language context ("I scream" vs
"ice cream" sound identical — context decides).
**Example:** Input: 30s WAV of "haan sir, course ki fees fifty thousand hai" → Output: that exact
text, plus (with Whisper) a timestamp for every word.

### 1.2 Whisper
**What:** OpenAI's open-source ASR model, the default choice for multilingual transcription.
**How:** An encoder-decoder Transformer trained on 680,000 hours of audio from the internet.
The encoder ingests 30-second chunks of audio-as-spectrogram; the decoder generates text like an
LLM generates words. Because training data included dozens of languages and code-switched speech,
it handles Hinglish natively. It comes in sizes: tiny/base/small/medium/large — bigger = more
accurate = slower.
**Example:** `model.transcribe("call.wav")` → `{"language": "hi", "segments": [{"start": 0.0,
"end": 3.2, "text": "Hello, am I speaking with Rahul?"}, ...]}`

### 1.3 faster-whisper
**What:** A reimplementation of Whisper that runs 4× faster using less memory. Same model
weights, faster engine.
**How:** Original Whisper runs on PyTorch (a general-purpose framework, lots of overhead).
faster-whisper runs the same weights on CTranslate2, an inference engine hand-optimized for
Transformer decoding (fused operations, better memory layout, batching).
**Example:** A 10-minute call: openai-whisper `medium` ≈ 4 min on CPU; faster-whisper `medium`
int8 ≈ 1 min. Same transcript.

### 1.4 int8 Quantization
**What:** Storing model weights as 8-bit integers instead of 32-bit floats → 4× smaller, faster
on CPU, ~negligible accuracy loss.
**How:** Every weight is a number like 0.02731. Quantization maps the range of weights in each
layer onto 256 integer buckets (−128..127) plus a scale factor. At inference, integer math is
much faster on CPUs (SIMD instructions), and 4× less data moves through memory — memory bandwidth
is usually the real bottleneck.
**Example:** weight 0.500 with scale 0.004 → stored as int 125. Reconstructed: 125 × 0.004 = 0.500.
Small rounding errors average out across millions of weights.

### 1.5 Spectrogram
**What:** A 2D image of audio: x = time, y = frequency, brightness = loudness of that frequency
at that moment. It's what audio models actually "look at."
**How:** The raw waveform is chopped into tiny overlapping windows (~25ms); a Fourier transform
decomposes each window into its component frequencies (like splitting a chord into its notes);
stacking the windows over time gives the image. Whisper uses a "mel" spectrogram — frequencies
warped to match human hearing sensitivity.
**Example:** A man's voice shows bright bands low in the image (~120 Hz fundamental); a woman's
sits higher (~210 Hz). That difference is also what diarization exploits.

### 1.6 Diarization ("who spoke when")
**What:** Splitting a recording into speaker-labeled segments: SPEAKER_A 0–8s, SPEAKER_B 8–15s...
It does NOT know names or roles — just "these chunks are the same voice."
**How (pipeline):** (1) Voice Activity Detection finds speech vs silence. (2) Each speech chunk
is converted into a **speaker embedding** — a vector (list of ~256 numbers) that captures voice
characteristics (pitch, timbre, accent) such that the same person's chunks produce nearby vectors.
(3) Clustering groups nearby vectors → each cluster = one speaker. (4) Segments get cluster labels.
**Example:** 100 chunks → embeddings → 2 clusters found → chunks 1,3,5.. labeled A; 2,4,6.. labeled B.

### 1.7 Embeddings (the core idea — used for voices here, for text everywhere in ML)
**What:** A learned mapping from a complex object (a voice clip, a word, a sentence) to a vector
of numbers, arranged so that **similar things get nearby vectors**.
**How:** A neural network is trained with a contrastive objective: pull embeddings of the same
speaker (or same meaning) together, push different ones apart. After training, "similarity"
becomes simple geometry: measure the distance/angle between two vectors.
**Similarity measure — cosine similarity:** the cosine of the angle between two vectors.
`cos(a,b) = (a·b)/(|a||b|)`. 1.0 = identical direction (very similar), 0 = unrelated,
−1 = opposite. Angle, not length, so a loud and quiet clip of the same voice still match.
**Example (voices):** advisor chunk → [0.12, −0.88, 0.45, ...]; another advisor chunk → cosine 0.93
(same person); customer chunk → cosine 0.31 (different person).
**Example (text, same principle):** embed("price of the course") and embed("how much does it
cost") land close together even with zero shared words — that's what semantic search exploits.

### 1.8 pyannote
**What:** The leading open-source diarization toolkit (a pretrained pipeline on Hugging Face).
**How:** Bundles the VAD → embedding → clustering pipeline (1.6) into one call, with models trained
on large annotated meeting/phone datasets. It's "gated": you must accept its license and pass a
HuggingFace token — which is exactly why the plan includes a fallback (graders might not have one).
**Example:** `Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")(audio)` → speaker turns.

### 1.9 Mono vs Stereo & Channel-Split Diarization
**What:** Stereo audio has 2 channels (left/right). Call systems often record advisor on one
channel and customer on the other — which makes diarization trivial.
**How:** If the file is stereo and channels differ, split it: left channel = advisor speech,
right = customer. 100% accurate, zero ML. If mono (both voices mixed in one channel), you must
fall back to real diarization (1.6) or turn-taking heuristics (long pauses usually mark speaker
changes on phone calls).
**Example:** ffprobe says `channels=2` → split → done. `channels=1` → run pyannote/fallback.

### 1.10 VAD (Voice Activity Detection)
**What:** Classifying each moment of audio as speech / not-speech (silence, hold music, noise).
**How:** A small neural net (or an energy threshold in the crude version) scores 10–30ms frames.
Used to skip silence (faster transcription) and to segment speech for diarization.
**Example:** 60s of hold music in the middle of a call → VAD marks it non-speech → Whisper never
wastes time on it and doesn't hallucinate lyrics.

### 1.11 WER (Word Error Rate)
**What:** The standard metric for transcription accuracy: what fraction of words the STT got wrong.
**How:** `WER = (substitutions + insertions + deletions) / total words in the correct reference`,
computed via edit distance. Lower is better; phone-quality Hinglish might sit at 15–25%.
**Example:** Reference "book the trial for Monday" → hypothesis "book a trail for Monday" =
1 substitution (the→a) + 1 substitution (trial→trail) over 5 words → WER 40%.
In the plan, `wer_estimate` is stored per transcript so low-quality transcripts can be flagged
(you estimate it from Whisper's own token confidence, since you have no reference in production).

### 1.12 Code-Switching (Hinglish)
**What:** Mixing languages within one conversation or even one sentence — the norm on Indian
sales calls.
**How it affects the system:** English-only STT butchers it; Whisper handles it because its
training data included mixed speech. The plan stores a `code_switch_ratio` (fraction of tokens
that are non-English) so heavily mixed calls can be monitored for quality, and the LLM prompt says
"quote verbatim in the original language" so evidence quotes aren't silently translated (which
would break quote verification).
**Example:** "Sir, honestly bolun toh, is course ke baad placement guaranteed hai" — the flag's
quote must be exactly this string, and it should trigger `over_promising`.

### 1.13 TTS (Text-to-Speech) — for demo data
**What:** The reverse of STT: text in, spoken audio out. Used to synthesize the demo call
recordings from your scripted dialogues.
**How:** Modern TTS (edge-tts uses Microsoft's neural voices, Coqui is open-source) generates a
spectrogram from text with a Transformer, then a vocoder converts it to a waveform. Different
"voices" = different learned speaker embeddings.
**Example:** Script line by line → advisor lines rendered with voice A into the left channel,
customer lines with voice B into the right → concatenated → a realistic stereo "call recording."

### 1.14 ffprobe / ffmpeg
**What:** The Swiss-army command-line tools for audio/video. ffprobe inspects (codec, duration,
channels, sample rate); ffmpeg converts/manipulates.
**How:** They parse the container format headers and decode streams. The pipeline uses ffprobe at
ingest as a validation gate: is this actually audio, is duration > 0, how many channels?
**Example:** `ffprobe -show_streams call.wav` → `channels=2, duration=312.4` → accepted, routed
to channel-split diarization. A renamed .txt file → ffprobe errors → rejected into the audit log.

---

# PART 2 · LLM & ANALYSIS CONCEPTS

### 2.1 LLM (Large Language Model)
**What:** A Transformer trained to predict the next token over internet-scale text; at scale this
yields general language competence — including "judge this sales call against a rubric."
**How (one breath):** Text → tokens → each token becomes an embedding → attention layers let
every token look at every other token to build contextual meaning → output layer predicts the
next token → repeat. "Understanding a rubric" is pattern completion over that machinery.
**Example:** Given transcript + rubric + "return JSON", the model continues with the most probable
tokens — which, prompted well, is a valid, well-reasoned JSON assessment.

### 2.2 Token
**What:** The unit LLMs read/write — usually a word-piece, not a word.
**How:** A tokenizer (BPE) learned frequent character sequences: common words = 1 token, rare
words split. Costs and context limits are measured in tokens. Rough rule: 1 token ≈ ¾ of an
English word; Hindi transliterated text often tokenizes worse (more tokens per word).
**Example:** "transcription" → ["transcri", "ption"] (2 tokens). A 30-min call transcript ≈
6–9k tokens — comfortably inside modern context windows.

### 2.3 Context Window / Context Limit
**What:** The maximum number of tokens the model can consider at once (prompt + its own answer).
**How:** Attention is computed across all tokens in the window; beyond the limit, text simply
can't be included. Plan implication: nearly all sales calls fit in one shot; the rare 2-hour call
gets a documented map-reduce path.
**Example:** 200k-token window vs a 9k-token transcript + 2k-token prompt → single call, no chunking.

### 2.4 Map-Reduce Summarization (the long-call fallback)
**What:** Handling text longer than the context window by processing chunks independently ("map")
then combining chunk outputs ("reduce").
**How:** Split transcript into overlapping chunks → analyze each for flags/notes → a final LLM
call merges chunk results into one assessment. Trade-off: cross-chunk context is lost (an
objection raised in chunk 1, resolved in chunk 4).
**Example:** 3-hour recording → 6 chunks → 6 partial flag lists → merge call dedupes and scores.

### 2.5 Prompt / Prompt Engineering
**What:** The instructions + context you send the model. Engineering it = structuring the task so
output is consistent and correct.
**How (techniques used in this project):** role framing ("You are a sales-QA analyst"), the rubric
inline with concrete 0-and-5 anchors, the closed tag list, explicit output schema, "quote
verbatim" evidence rules, few-shot examples, and "if unsure, omit the flag" (precision over recall).
**Example anchor:** "Needs discovery = 5 only if the advisor asks ≥2 open questions about goals
AND references the answers later in the pitch."

### 2.6 Structured Output / JSON Schema / Tool Use
**What:** Forcing the model to reply in machine-parseable JSON matching a schema, instead of prose.
**How:** Modern APIs accept a JSON Schema (field names, types, enums, required fields). Under the
hood the API constrains token sampling so only schema-valid tokens can be produced ("tool use" /
"function calling" is the same mechanism framed as the-model-calls-a-function-with-typed-args).
Your code then re-validates with Pydantic — trust but verify.
**Example schema fragment:**
```json
{"flags": {"type": "array", "items": {"type": "object", "properties": {
  "tag": {"enum": ["over_promising", "pressure_tactics", ...]},
  "quote": {"type": "string"}, "confidence": {"type": "number"}},
  "required": ["tag", "quote", "confidence"]}}}
```
The model literally cannot output `"tag": "was_rude"` — the enum blocks it. That's the "closed
taxonomy" defense.

### 2.7 Temperature
**What:** A knob (0→~2) controlling randomness of token sampling.
**How:** The model outputs a probability for every possible next token. Temperature rescales those
probabilities before sampling: 0 = always pick the most likely token (deterministic-ish, ideal for
scoring — same call should get the same score), high = more diverse/creative.
**Example:** temp 0: "confidence": 0.85 every run. temp 1: might get 0.8, 0.9, different quotes —
useless for a QA system that must be consistent and auditable.

### 2.8 Hallucination
**What:** The model asserting things that aren't in the input — e.g., flagging "guaranteed
placement" when nobody said it.
**Why it happens:** The model is a plausibility machine, not a truth machine; if pushy sales calls
usually contain over-promising, it may "pattern-complete" a flag that fits the vibe.
**The plan's three-layer defense:** (1) closed enum — can't invent tags; (2) evidence quote
required — can't assert without citing; (3) **quote-verification gate** — your code checks the
quote actually exists in the transcript; missing → flag silently dropped and logged. Prompting
reduces hallucination; verification *eliminates* its impact.

### 2.9 Fuzzy String Matching (the quote gate's engine)
**What:** Checking whether two strings are "approximately equal," tolerating small differences.
**How:** Levenshtein/edit distance — the minimum number of single-character insertions, deletions,
substitutions to turn string A into B — normalized into a 0–1 similarity ratio
(`ratio = 1 − distance/max_len`, or SequenceMatcher's variant). The plan uses ≥0.85 against a
normalized transcript (lowercased, punctuation stripped) via a sliding window.
**Why fuzzy, not exact:** STT noise. The model quotes "guaranteed placement hai sir," the
transcript says "guranteed placment hai sir" (Whisper typos) — exact match fails, fuzzy passes.
**Example:** "book the trial" vs "book a trial" → 1 word off → ratio ≈ 0.93 → verified.
"we promise refunds" vs a transcript containing nothing similar → best window ratio 0.41 → dropped.

### 2.10 Confidence Score & Thresholding
**What:** The model self-reports 0–1 certainty per flag; you act differently by band.
**How:** It's in the output schema. Self-reported confidence isn't perfectly calibrated, but it
correlates: prompt-anchor it ("0.9+ = explicit verbatim violation; 0.6 = implied"). Plan rule:
< 0.6 → stored as `info` for human review rather than surfaced as a violation.
**Why:** False accusations destroy advisor trust faster than misses destroy QA value. This is a
precision-over-recall product decision — be ready to say that sentence in the interview.

### 2.11 Few-Shot Examples / Calibration Loop
**What:** Putting labeled examples inside the prompt so the model imitates the pattern —
"in-context learning," no training required.
**How in this project:** When a TL resolves a dispute, the (quote, verdict) pair is saved to
`calibration_examples`. The analysis prompt for that tag injects the latest N examples:
"‘prices go up Friday' → true pressure_tactics; ‘many students enrolled this week' → NOT
pressure_tactics (factual, no coercion)." The system's precision improves from human feedback
without any model training.
**Example effect:** after 10 dismissed false-positives on `pressure_tactics` for harmless urgency
phrases, the model stops flagging them.

### 2.12 Fine-Tuning (and why the plan defers it)
**What:** Actually updating a model's weights on your labeled data (vs prompting, which changes
only the input).
**How:** Collect thousands of (transcript → correct flags/scores) pairs, train — typically with
LoRA (train small low-rank adapter matrices instead of all weights; cheap, you did this in
LANGTRON). **Why deferred:** day one you have zero labeled data; prompting + validation reaches
high quality immediately; the dispute loop *generates* the training set that makes fine-tuning
worthwhile in month 3. This ordering — prompt → collect labels via product → fine-tune — is the
textbook-correct sequence; say it exactly like that.

### 2.13 NER (Named Entity Recognition)
**What:** An NLP model that tags spans of text as PERSON, PHONE, LOCATION, ORG, etc.
**How:** A trained sequence-labeling model (spaCy ships pretrained ones) classifies each token in
context — it catches "Rahul Sharma" as PERSON where regex can't (names have no pattern).
**Example:** "My name is Priya, I live in Indiranagar" → PERSON(Priya), LOC(Indiranagar) →
replaced with `[NAME]`, `[LOCATION]` in `redacted_text`.

### 2.14 PII & Redaction (regex + NER, before the LLM)
**What:** PII = Personally Identifiable Information (phones, card numbers, OTPs, Aadhaar, emails,
names, addresses). Redaction = masking it.
**How (two layers):** (1) **Regex** for patterned PII: `\b\d{10}\b` phones, `\b\d{4}\s?\d{4}\s?\d{4}\b`
Aadhaar, card numbers via format + Luhn checksum, emails. (2) **NER** (2.13) for unpatterned PII.
Order matters: redaction runs BEFORE the transcript is sent to any external LLM API — the privacy
boundary is architectural, not policy. Raw text is kept in a restricted column for authorized
audit only.
**Example:** "mera number 9876543210 hai, card ending 4242" → "mera number [PHONE] hai, card
ending [CARD]".
**Regex itself:** a mini-language for text patterns. `\b\d{10}\b` = word-boundary, exactly 10
digits, word-boundary. `\d` any digit, `{10}` repeat 10×, `\b` prevents matching inside a
14-digit number.

### 2.15 Classifier Pre-Stage (sales vs non-sales)
**What:** A cheap first-pass decision before expensive full analysis.
**How:** Send only the first ~40 turns to a small/cheap LLM: "Is this a sales conversation, a
wrong number, or an internal call? One word." Non-sales → tag, skip scoring, exclude from
averages. This is the "cascade" pattern: cheap model filters, expensive model only runs when
worth it — saves tokens AND keeps averages honest.
**Example:** "Hello? Sorry wrong number. — Oh, no problem." → `non_sales_call`, pipeline ends.

### 2.16 Golden Tests / Eval Set / Precision & Recall
**What:** A small hand-labeled benchmark to *measure* the LLM's judging quality instead of vibing it.
**How:** 5–10 fixture transcripts where YOU decided the correct flags and score bands. `make eval`
runs the live model on them and computes, per tag:
**Precision** = of the flags the model raised, how many were correct = TP/(TP+FP) — "when it
accuses, is it right?" **Recall** = of the real violations, how many did it catch = TP/(TP+FN) —
"does it miss things?" There's a tension: stricter thresholds raise precision, lower recall.
**Example:** golden set has 6 real `over_promising` instances; model raises 5 flags, 4 correct →
precision 4/5 = 0.80, recall 4/6 = 0.67. Report these numbers in the writeup — almost no other
candidate will.

### 2.17 Prompt Hash & Rubric Versioning
**What:** Stamping every stored score with `sha256(prompt_text)` and a rubric version string.
**How/Why:** Scores are only comparable if produced by the same prompt+rubric. When you improve
the prompt, old scores aren't wrong — they're a different version. The hash detects accidental
drift ("why did scores jump Tuesday?" → prompt hash changed Tuesday); the version enables
re-scoring history and A/B-ing rubric v1 vs v2. Cheap column, senior-engineer catnip.

---

# PART 3 · BACKEND & PIPELINE ENGINEERING

### 3.1 REST API
**What:** The convention for services talking over HTTP: URLs name resources, HTTP verbs name
actions, JSON carries data.
**How:** GET reads, POST creates, PATCH updates, DELETE removes; status codes signal outcome
(200 ok, 201 created, 404 missing, 422 invalid input). Stateless: every request carries all it needs.
**Example:** `POST /flags/17/dispute {"note": "customer asked for the discount themselves"}` →
201 + the created dispute object. The dashboard is just a pretty client of this API.

### 3.2 FastAPI
**What:** The modern Python web framework the API layer uses.
**How:** You declare a function with typed parameters; FastAPI generates routing, request parsing,
**validation** (via Pydantic — wrong types are rejected with a clear 422 before your code runs),
and interactive docs (`/docs`, Swagger UI) automatically. Built on async (3.3).
**Example:**
```python
@app.post("/ingest/upload")
async def upload(file: UploadFile, advisor_id: int): ...
```
A request missing `advisor_id` never reaches your logic.

### 3.3 Async / Await (asynchronous I/O)
**What:** Letting one process handle many simultaneous requests by not idling during waits.
**How:** Most web time is waiting (DB replies, LLM API replies). `await` yields control back to an
event loop, which runs other requests' code during the wait, resuming yours when the reply lands.
Concurrency without threads. Rule: `await` I/O; never run heavy CPU work (Whisper!) inside the
event loop — that's why transcription lives in a separate worker process, not in the API.
**Example:** 50 users load dashboards; each handler awaits its DB query; one process interleaves
all 50 instead of queueing them.

### 3.4 Pydantic
**What:** Python library for data validation via type-annotated classes. Used three ways here:
API request/response models, config loading (pydantic-settings), and **validating LLM output**.
**How:** Define `class Flag(BaseModel): tag: TagEnum; quote: str; confidence: float`. Feeding it a
dict checks/coerces every field or raises a precise error. Same tool guards the front door (HTTP)
and the side door (LLM) — the "one validation story" line in the plan.
**Example:** LLM returns `"confidence": "high"` → ValidationError → triggers the retry-with-error
path instead of corrupt data reaching Postgres.

### 3.5 Adapter Pattern & ABC (the source-agnostic ingestion answer)
**What:** A design pattern: define one interface your system speaks; write a thin translator
(adapter) per external source. ABC = Python's Abstract Base Class, the mechanism for declaring
that interface.
**How:**
```python
class SourceAdapter(ABC):
    @abstractmethod
    def fetch_new(self) -> list[CallEnvelope]: ...
```
FolderAdapter, RestAdapter, MockCrmAdapter each implement `fetch_new`, mapping their source's
quirks (file naming, webhook JSON, CRM fields) into the one canonical `CallEnvelope`. The pipeline
imports only the interface. Adding Exotel/Twilio later = one new file, zero pipeline changes —
which is literally the assignment's requirement "a new source can be mapped in without code
changes [to the core]."
**Example:** dialer's payload calls the advisor `"agent_ref": "AGT-9"` → adapter looks it up in
`advisors.external_ids` → envelope carries the internal advisor_id.

### 3.6 Canonical Schema (CallEnvelope)
**What:** The single normalized shape every call takes on entry, regardless of source.
**How:** `{audio_uri, source, source_call_id, advisor_external_id, called_at, channels,
raw_metadata}`. Everything downstream depends on this shape only. `raw_metadata JSONB` keeps the
untouched vendor payload so a mapping bug can be fixed and re-mapped later without re-fetching.
**Analogy:** international power sockets → one adapter per country → every device sees the same plug.

### 3.7 Webhook vs Polling
**What:** Two ways to learn about new data. Webhook: the source calls YOU (push). Polling: you
repeatedly ask the source "anything new?" (pull).
**How in the plan:** REST upload endpoint = webhook-style push; folder watcher & mock-CRM = polling.
Webhooks are instant but require you to be reachable and to handle *re-delivery* (vendors resend
on timeout — the idempotency key exists precisely for this). Polling is simpler but adds latency.
**Example:** telephony vendor POSTs `{"recording_url": ...}` when a call ends → your endpoint
enqueues it. Same call POSTed twice → second insert hits the UNIQUE key → ignored.

### 3.8 Idempotency & Idempotency Keys
**What:** An operation is idempotent if doing it twice has the same effect as once. Critical in
distributed systems because retries and re-deliveries are *normal*, not exceptional.
**How here (two levels):** (1) Ingest: `idempotency_key = sha256(audio_bytes) + source_id`,
UNIQUE column → duplicate delivery = DB conflict = no second call row. (2) Pipeline stages: each
stage first checks "does my output already exist for this call?" → a worker that crashed after
writing the transcript but before marking the job done will, on retry, skip re-transcribing.
**Example:** vendor webhook fires 3× for one call → one row. Worker killed mid-analysis → retry
resumes at analysis, transcript untouched.

### 3.9 sha256 (Cryptographic Hash)
**What:** A function mapping any input to a fixed 64-hex-char fingerprint; same input → same
output, always; different input → (effectively) always different output; irreversible.
**How it's used:** hashing the audio bytes gives a content-derived identity — the same recording
delivered under two filenames still collides to one key. Also used for prompt hashing (2.17).
**Example:** `sha256(b"...wav bytes...") = "a3f19c..."`. Change one byte → completely different hash.

### 3.10 Job Queue & Worker
**What:** Decoupling "a call arrived" from "a call was processed." The API only *enqueues* a job
row and returns instantly; a separate **worker** process loops: claim job → run stage → mark done.
**Why:** transcription takes minutes; HTTP requests must take milliseconds. Also gives you retries,
resumability, and horizontal scaling (run 5 workers) for free.
**Example flow:** upload → `processing_jobs(call_id=42, stage='transcribe', status='pending')` →
worker claims it → done → enqueues `stage='diarise'` → ... → `analyse` → dashboard shows the call.

### 3.11 `SELECT ... FOR UPDATE SKIP LOCKED` (the Postgres queue trick)
**What:** The SQL incantation that lets multiple workers safely share one job table without
grabbing the same job.
**How:** `FOR UPDATE` locks the selected row inside a transaction (others must wait) — but
`SKIP LOCKED` says "don't wait; skip rows someone else holds and take the next free one." Each
worker atomically claims a distinct job. This one clause is why you don't need Redis/Celery at
this scale.
**Example:**
```sql
SELECT * FROM processing_jobs WHERE status='pending' AND run_after <= now()
ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED;
```
Workers A and B run this simultaneously → A gets job 1, B gets job 2, never both job 1.

### 3.12 Retries, Exponential Backoff & Jitter
**What:** The failure-recovery policy: retry transient failures, wait longer each time, add
randomness.
**How:** attempt n waits ~`base × 2ⁿ` (2s, 4s, 8s) — exponential backoff gives a struggling
vendor API room to recover instead of hammering it. **Jitter** adds randomness (±50%) so 100
failed jobs don't all retry at the same instant and re-overload it (the "thundering herd").
Implemented via the `run_after` timestamp: a failed job's `run_after = now() + backoff`, and the
claim query ignores jobs whose time hasn't come.
**Example:** LLM API returns 529 → attempt 2 at +2.7s → 529 again → attempt 3 at +5.1s → success.

### 3.13 Dead-Letter State
**What:** Where a job goes after exhausting retries: parked as `dead` instead of retrying forever
or vanishing silently.
**How:** `attempts >= max_attempts` → status `dead`, `last_error` stored → visible in the `/ops/jobs`
view with a re-queue button. Failure is *visible and recoverable*, never silent — this is the
difference between a demo and a system.
**Example:** a corrupt-audio call fails transcription 3× → dead-lettered with the ffmpeg error →
you replace the file and re-queue.

### 3.14 State Machine (job & flag lifecycles)
**What:** Modeling an entity as a fixed set of states with allowed transitions.
**How here:** jobs: `pending → running → done | failed → pending(retry) | dead`. Flags:
`open → disputed → upheld | dismissed`. Enforcing transitions (you can't dismiss a flag that was
never disputed) prevents whole categories of bugs and makes the audit log meaningful.

---

# PART 4 · DATABASE

### 4.1 Relational Database / Postgres
**What:** Data as tables with typed columns, linked by keys, queried with SQL. Postgres = the
open-source gold standard.
**Why relational here:** the domain IS relations (org→teams→advisors→calls→flags), rollups are
native SQL aggregates, and **foreign keys** + transactions protect integrity (no score can point
at a nonexistent call).
**Example:** `SELECT t.name, AVG(cs.composite) FROM teams t JOIN advisors a ON a.team_id=t.id
JOIN calls c ON c.advisor_id=a.id JOIN call_scores cs ON cs.call_id=c.id GROUP BY t.name;`
— the entire Director dashboard in one query.

### 4.2 Primary Key / Foreign Key
**What:** PK = the unique identifier of a row. FK = a column that must equal some row's PK in
another table — a checked pointer.
**How:** `flags.call_id REFERENCES calls(id)` → inserting a flag for call 999 when call 999
doesn't exist = rejected by the DB itself. Data integrity enforced below the application layer.

### 4.3 UNIQUE Constraint & UPSERT (ON CONFLICT)
**What:** UNIQUE = the DB rejects duplicate values in a column (the idempotency enforcer).
UPSERT = "insert, or if it already exists, update/skip" in one atomic statement.
**Example:** `INSERT INTO calls (..., idempotency_key) VALUES (...) ON CONFLICT
(idempotency_key) DO NOTHING;` — duplicate webhook deliveries dissolve harmlessly. Advisor
external-ID mapping uses `DO UPDATE` to merge new dialer IDs.

### 4.4 JSONB
**What:** A Postgres column type storing arbitrary JSON, binary-encoded, indexable and queryable.
**How/Why:** Schema-flexible pockets inside a rigid schema. `raw_metadata JSONB` absorbs any
vendor's payload shape without migrations — the concrete mechanism behind "source-agnostic
without schema churn." Query inside it: `raw_metadata->>'campaign_id'`.
**Rule of thumb to say in interview:** relational columns for what you query/join/aggregate;
JSONB for what you merely preserve.

### 4.5 SQL Views & Materialized Views
**What:** A view = a saved query that acts like a virtual table, always computed fresh.
A materialized view = the same but with results physically stored, refreshed on demand.
**How here:** advisor/team/org averages are plain views → always consistent with underlying
scores, zero sync logic. At huge scale recomputing gets slow → `REFRESH MATERIALIZED VIEW`
nightly. The plan's stated threshold ("materialize past ~1M calls/quarter") shows you know the
trade-off: freshness vs read speed.

### 4.6 Window Functions
**What:** SQL functions that compute over a "window" of related rows *without collapsing them* —
unlike GROUP BY, every row survives, annotated.
**Example:** advisor leaderboard with rank and trend:
```sql
SELECT advisor_id, composite,
       AVG(composite) OVER (PARTITION BY advisor_id ORDER BY called_at
                            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS rolling_7,
       RANK() OVER (ORDER BY composite DESC) AS org_rank
FROM call_scores JOIN calls USING (call_id);
```
`PARTITION BY` = per-advisor windows; each call row gets its rolling average and rank attached.
This powers the sparklines.

### 4.7 Transactions & ACID
**What:** A transaction groups statements so they all commit or none do. ACID = Atomicity (all or
nothing), Consistency (constraints hold), Isolation (concurrent transactions don't see each
other's half-work), Durability (committed = survives crash).
**Why it matters here:** "write flags + write scores + mark job done" is one transaction — a crash
between them can't leave a call marked analyzed with half its flags missing. Also the foundation
of the SKIP LOCKED queue (3.11): the row lock lives inside the transaction.

### 4.8 ORM (SQLAlchemy 2)
**What:** Object-Relational Mapper — Python classes map to tables; queries are Python expressions;
results are objects.
**How:** `class Call(Base): id: Mapped[int]; advisor: Mapped["Advisor"] = relationship()` →
`session.get(Call, 42).advisor.name`. Benefits: type safety, composability, and it pairs with
Alembic. You still drop to raw SQL for views/window functions — knowing when to do that is the
senior move.

### 4.9 Migrations (Alembic)
**What:** Version control for the database schema — each change is a scripted, ordered, reversible
migration.
**How:** `alembic revision --autogenerate` diffs your models vs the DB and writes
upgrade()/downgrade() scripts; `alembic upgrade head` applies them. Why it impresses: it means
your schema can *evolve in production* without hand-run SQL on a live DB.
**Example:** v2 adds `flags.confidence` → a migration adds the column with a default → deployed
machines catch up automatically on start.

### 4.10 Audit Log
**What:** An append-only table recording every human action: who, did what, to which entity,
before/after values, when.
**Why:** disputes decide people's performance reviews — "who dismissed this mis-selling flag and
when" must be answerable. Also your compliance story. Append-only: never UPDATE or DELETE it.
**Example row:** `(actor='tl_meera', action='resolve_dispute', entity='flag', entity_id=17,
before={"state":"disputed"}, after={"state":"dismissed"}, at=...)`.

### 4.11 Indexes (implicit but you'll be asked)
**What:** A sorted lookup structure (B-tree) on a column so the DB finds rows without scanning
the whole table.
**How:** PKs and UNIQUE columns are auto-indexed; add indexes on FKs you join through
(`calls.advisor_id`, `flags.call_id`) and query filters (`processing_jobs(status, run_after)` —
the queue claim query). Trade-off: each index slows writes slightly and costs disk.
**Example:** leaderboard query on 1M calls: without index on advisor_id → full scan, seconds;
with → milliseconds.

---

# PART 5 · FRONTEND

### 5.1 Next.js
**What:** The dominant React framework — routing, server-side rendering, bundling out of the box.
**How:** File-system routing (`app/teams/[id]/page.tsx` = the URL `/teams/3`); components can
render on the server (fast first paint, fetch data close to the API) or the client (interactive
bits like the audio player). You've shipped it twice (portfolio, AlgoScope) — zero learning tax.

### 5.2 React (the model underneath)
**What:** UI as a function of state. You declare what the screen should look like for given data;
React updates the DOM when data changes.
**How:** Components are functions returning JSX; `useState` holds local state; changing state
re-renders. The call-detail page: `currentTime` state ← audio player events → the transcript
segment whose `start_s ≤ currentTime < end_s` gets a highlight class. That's the whole
"karaoke transcript" trick.

### 5.3 TypeScript
**What:** JavaScript + static types.
**How/Why:** Define `interface Flag { tag: string; start_s: number; ... }` mirroring the API's
Pydantic models — the compiler catches "you passed seconds where the component wants
milliseconds" before runtime. On a 48h build, types are speed, not ceremony.

### 5.4 Tailwind CSS
**What:** Styling via utility classes in the markup instead of separate CSS files.
**How:** `<div class="flex items-center gap-2 rounded-lg border p-4">` — each class is one CSS
property. Fast iteration, consistent spacing scale, no naming debates.

### 5.5 shadcn/ui
**What:** A collection of polished, accessible React components (Card, Table, Dialog, Tabs,
Badge...) that you copy into your repo rather than install as a dependency.
**Why it wins here:** instant professional SaaS aesthetic (the "Linear/Vercel look"), fully
customizable since you own the code. Severity badges, the dispute dialog, KPI cards — all
pre-built primitives.

### 5.6 Recharts
**What:** React charting library.
**How:** Declarative: `<LineChart data={scores}><Line dataKey="composite"/></LineChart>`.
Powers the org trend line, team bars, advisor radar. Keep charts few and meaningful — a
dashboard's quality is what it *omits*.

### 5.7 wavesurfer.js & Audio-Transcript Sync
**What:** Renders an audio waveform you can click/seek, with events for current playback time.
**How the money-feature works:** flags carry `start_s` → clicking a flag calls
`wavesurfer.seekTo(start_s / duration)` → playback jumps to the violation; meanwhile the
`timeupdate` event drives the highlighted transcript segment (5.2). Fallback if time burns:
a plain `<audio>` element has `.currentTime = start_s` — same effect, no waveform visuals.

### 5.8 Skeleton Loaders
**What:** Gray placeholder shapes shown while data loads, instead of spinners or layout jumps.
**Why mentioned in the plan:** it's a cheap polish signal — the app feels product-grade.
shadcn ships a `Skeleton` component; wrap each dashboard card's loading state.

### 5.9 Role Switcher (in lieu of auth)
**What:** A dropdown that sets "viewing as: Director / TL Meera / Advisor Arjun" and scopes every
API call accordingly.
**Why honest:** real auth (sessions, SSO) is out of scope; the switcher demonstrates the
*authorization model* (what each role may see) without the authentication plumbing. Say exactly
that when asked.

---

# PART 6 · INFRA, PACKAGING, OPS

### 6.1 Docker
**What:** Packages your app + OS-level dependencies (ffmpeg! specific Python! model files) into an
image that runs identically anywhere.
**How:** A Dockerfile scripts the build (`FROM python:3.11-slim`, `RUN apt install ffmpeg`,
`COPY . .`, `RUN pip install ...`); the image is a frozen filesystem; a container is a running
instance, isolated via Linux namespaces (not a VM — shares the host kernel, so it's light).
**Why critical here:** "we will run your code" — Docker removes every "works on my machine" risk,
especially ffmpeg and Whisper model paths.

### 6.2 Docker Compose
**What:** One YAML file declaring the whole system: postgres + api + worker + web, their networks,
env vars, volumes, startup order.
**How:** `docker compose up` builds and starts all four; services address each other by name
(`DATABASE_URL=postgresql://user:pass@postgres:5432/callsense`); `depends_on` +
**health checks** (`pg_isready`) make the API wait until the DB actually accepts connections,
not merely started.
**Example gotcha you'll hit:** the Whisper model download (~1.5GB for medium) — bake it into the
image or mount a volume, or the first demo run stalls; the plan's buffer hours exist for exactly this.

### 6.3 Makefile
**What:** Shortcut runner: named targets wrapping longer commands.
**How:** `make demo` = compose up + wait + run seed script + print the URL. `make test`, `make eval`.
Why: "runs from one clear command" is a grading criterion; the Makefile IS that command.

### 6.4 Environment Variables, .env, pydantic-settings
**What:** Config (API keys, DB URLs, MOCK_MODE) supplied from the environment, never hardcoded.
**How:** `.env` file (gitignored) holds local values; `.env.example` documents required keys;
`class Settings(BaseSettings): anthropic_api_key: str; mock_mode: bool = False` loads and
validates them at startup — a missing key fails loudly at boot, not cryptically mid-call.
**Why (twelve-factor principle):** same image runs in demo/prod with different config; secrets
never enter git history.

### 6.5 MOCK_MODE
**What:** A flag that swaps external dependencies (LLM API, optionally Whisper) for canned
fixture responses, so the FULL pipeline runs with zero keys and zero network.
**How:** the `LLM` interface (3.5's pattern again) has a `MockLLM` implementation returning a
stored, realistic JSON analysis keyed by fixture; the pre-transcribed fixture skips Whisper.
**Why it might save your submission:** a grader without an Anthropic key still sees ingestion →
storage → dashboard → dispute work end to end. Document it in the "real vs mocked" README table.

### 6.6 Health Checks & Structured Logging
**What:** Health check = an endpoint (`GET /health`) or command that answers "am I alive and are
my dependencies reachable?" Structured logging = logs as JSON key-value events, not prose.
**How/Why:** compose uses health checks for startup ordering; ops uses them for monitoring.
Structured logs (`{"event":"stage_done","call_id":42,"stage":"analyse","ms":8123}`) are
grep-able and aggregatable — when a grader asks "how would you debug a stuck call," the answer is
"filter logs by call_id, and the jobs table shows exactly which stage and error."

### 6.7 CI (GitHub Actions)
**What:** Continuous Integration — every push automatically runs your tests on a clean machine.
**How:** a YAML workflow: checkout → set up Python → start a Postgres service container →
`make test`. The green check on the repo silently proves "the tests pass somewhere other than
my laptop" — disproportionate credibility for ~20 lines of YAML.

### 6.8 Twelve-Factor / Stateless Workers (the "rollback" claim)
**What:** The design property that makes deployment boring: workers hold no local state — all
state lives in Postgres.
**Why it matters:** any worker can die anytime (crash test in §9 of the plan) and a new one
resumes from the jobs table; "rollback" = run the previous image, since data and code are
decoupled. This is the honest answer to "is this deployable?"

---

# PART 7 · THE THINGS YOU CHOSE *NOT* TO USE (know them anyway — they'll ask)

### 7.1 Celery + Redis
**What:** Celery = the standard Python distributed task queue; Redis = an in-memory data store
often used as its message broker (and as a cache).
**How it would work:** API calls `task.delay(call_id)` → task message goes to Redis → Celery
worker processes consume. **Why rejected:** adds a broker service + serialization + its own
failure modes, and its jobs aren't transactional with your Postgres data (a Celery task can fire
for a rolled-back insert). At hundreds of calls/day, SKIP LOCKED does the same job with zero new
infrastructure. Adopt when: multiple apps need the queue, or job throughput outgrows Postgres.

### 7.2 Kafka
**What:** A distributed, append-only event log for streaming data between many systems at massive
scale; consumers replay from any offset.
**Why rejected (your line):** Kafka shines when many producers/consumers exchange high-volume
streams and need replay; one producer → one consumer at hundreds of events/day is "cosplay."
You know Kafka (it's on your profile) — rejecting it *knowingly* reads senior; reaching for it
reads résumé-driven.

### 7.3 Kubernetes
**What:** Container orchestration — schedules containers across a fleet, restarts failures,
scales replicas, rolls out updates.
**Why rejected:** it manages fleet problems a 4-container single-host demo doesn't have; compose
expresses the same topology. The migration path (each service already containerized) costs
nothing later.

### 7.4 SQS
**What:** AWS's managed message queue — the natural production replacement for the Postgres queue.
**Why relevant:** your `JobQueue` interface means swapping to SQS touches one class; mentioning
this shows the abstraction was designed for the swap.

### 7.5 Cloud STT (Deepgram / AssemblyAI / Sarvam AI)
**What:** Hosted transcription APIs; you upload audio, get transcript + (often better)
diarization back. Sarvam = India-focused, strongest on Indic languages/Hinglish.
**Trade-off table in one line:** better accuracy + built-in diarization + zero compute management
vs per-minute cost + data leaves your infra (PII!) + vendor lock. The `Transcriber` interface is
the hedge; A/B with real calls decides.

### 7.6 Streamlit
**What:** Python library that turns scripts into web dashboards with almost no code.
**Why rejected for the deliverable:** speed of build, but it *looks* like a prototype; the
assignment explicitly awards "polished, clear dashboards," and your Next.js speed makes the
trade favorable. (Fine choice for internal one-offs — say that, don't trash it.)

### 7.7 MongoDB / SQLite
**Mongo (document DB):** stores JSON documents, flexible schema, but joins/aggregation across an
org hierarchy and FK integrity are weaker — the exact things this domain needs.
**SQLite (file-based SQL):** brilliant single-process DB, but the API and worker write
concurrently from different processes; SQLite's single-writer lock makes that painful. Postgres
costs one container and removes the ceiling.

---

# PART 8 · PRODUCT / SCORING CONCEPTS

### 8.1 Rubric & Behavioral Anchors
**What:** The fixed set of dimensions + a description of what each score level looks like in
observable behavior ("anchors").
**Why anchors matter:** "score discovery 0–5" is subjective; "5 = ≥2 open questions AND pitch
references the answers" is checkable — for the LLM *and* for a human auditing the LLM. Anchors
are what make scores consistent across calls and defensible in a dispute.

### 8.2 Weighted Composite Score
**What:** One 0–100 number per call from the five dimension scores.
**How:** `composite = Σ (dimension_i/5 × weight_i) × 100`, weights from the rubric table (they sum
to 1). Weights encode business priorities: discovery + compliance = 50% because they drive
SkilloVilla's conversion and risk.
**Example:** scores 4,3,5,2,4 with weights .25,.15,.20,.25,.15 → (.20+.09+.20+.10+.12)... → 71.

### 8.3 Compliance Cap
**What:** The rule that any critical compliance flag caps the composite at 40, regardless of other
dimensions.
**Why (the product argument):** averaging lets charm launder mis-selling — a smooth talker who
promises fake guarantees could still score 80. In edtech, one mis-sold customer costs more than
ten mediocre calls. A cap makes the org's values legible in the math. Expect pushback in the
interview ("isn't that harsh?") — the answer is: that's the point, and the dispute loop is the
safety valve for false positives.

### 8.4 Rollups & Averaging Choice
**What:** Advisor avg = mean of their call composites; **team avg = mean of advisor averages**
(not of all team calls); org = mean of team averages.
**Why that choice:** averaging over calls lets one high-volume advisor dominate a team's number;
averaging over advisors weights people equally — the fair unit for coaching comparisons. Know both
options; defending the choice matters more than the choice.

### 8.5 Precision-over-Recall as a Product Stance
**What:** Tuning the system to prefer missing a real violation over falsely accusing an advisor.
**Where it's implemented:** confidence threshold (2.10), quote gate (2.9), "omit if unsure"
prompt rule, and the dispute loop. One sentence for the interview: "A false accusation costs
trust and adoption; a miss costs one data point — so every ambiguous case degrades to `info`,
never to `critical`."

### 8.6 The Feedback Loop as a Data Flywheel
**What:** Dispute resolutions are simultaneously (a) due process, (b) calibration few-shots
(2.11), and (c) the future fine-tuning dataset (2.12).
**Why this is the deepest idea in the project:** the product's *human workflow* manufactures the
labeled data that improves the *model* — the loop the assignment calls "how humans correct the
system and how that loops back," closed literally.

---

# PART 9 · TESTING CONCEPTS

### 9.1 Unit Test
**What:** Tests one function in isolation, no network/DB. **Example:** feed the redactor
"card 4242 4242 4242 4242" → assert output contains `[CARD]` and not the digits.

### 9.2 Integration Test
**What:** Tests components together against real infrastructure (a real Postgres in a test
container). **Example:** enqueue a fixture call in MOCK_MODE → run worker loop → assert rows in
transcripts, segments, scores, flags; assert job states walked pending→done.

### 9.3 Fixtures, Stubs, Mocks
**Fixture:** known test data (the WAVs, hand-labeled transcripts). **Stub:** a fake dependency
with canned answers (a Transcriber that returns a fixed transcript instantly). **Mock:** a stub
that also records how it was called, so you can assert "the LLM was called exactly once with the
redacted text." The retry test uses a stub programmed to fail twice, succeed third.

### 9.4 Contract Test
**What:** Verifies the *shape* of an integration, not its content — here, that any LLM response
violating the schema is rejected-and-retried, and that an enum-violating tag never reaches the DB.
Protects you from silent model-side changes.

### 9.5 Golden / Regression Tests
**What:** Frozen expected outputs for frozen inputs; a diff means something changed — maybe your
prompt, maybe the model. **Example:** transcript #3 must always yield `over_promising` within
score band 25–45; if a prompt tweak breaks it, CI catches it before the demo does.

### 9.6 Smoke Test
**What:** The fastest possible "is it fundamentally alive" check — the README's manual checklist
(`make demo` → upload → flag → seek → dispute) is a scripted smoke test the graders execute.

### 9.7 Chaos-Style Checks (mini versions)
**What:** Deliberately injecting failure to prove recovery claims: `kill -9` the worker mid-stage
→ restart → assert the call still completes with no duplicate rows; upload the same file twice →
assert one call. Claim nothing in the README you don't have a test for — that consistency is
what senior engineers probe.

---

# PART 10 · ONE-LINERS (rapid-fire glossary of everything remaining)

- **Pipeline:** data flowing through ordered stages, each stage's output = next stage's input.
- **Stage:** one atomic, idempotent, retriable unit of the pipeline (transcribe, redact, analyse...).
- **Envelope:** a wrapper carrying the payload + metadata needed for routing/processing.
- **Batch vs real-time:** processing after the call ends vs during it; v1 is batch — simpler, and
  coaching doesn't need seconds-level latency.
- **Near-real-time:** batch, but within minutes — what this system actually delivers.
- **Horizontal scaling:** more worker copies; **vertical:** a bigger machine. Stateless workers →
  horizontal is trivial.
- **Backpressure:** when producers outpace consumers; the jobs table absorbs it as pending depth
  (and depth is a metric worth graphing).
- **Latency vs throughput:** time per call vs calls per hour; batch systems optimize throughput.
- **Interface / dependency inversion:** code depends on abstract contracts (Transcriber, LLM,
  JobQueue, SourceAdapter), not concrete vendors — the single principle behind every "swap path"
  claim in the plan.
- **Separation of concerns:** API serves, worker computes, DB stores, frontend renders — each
  replaceable alone.
- **RBAC:** Role-Based Access Control — permissions attached to roles (Director/TL/Advisor), not
  individuals; here expressed via role-scoped API queries.
- **Swagger / OpenAPI:** the machine-readable API description FastAPI auto-generates; `/docs` is
  its interactive UI — show it in the video for free credibility.
- **Sparkline:** a tiny inline trend chart in a table row (advisor leaderboard).
- **Radar chart:** multi-axis chart showing one advisor's five dimension scores as a shape —
  instantly shows "great closer, weak discovery."
- **KPI card:** a big-number tile with a delta ("Org score 72, ▲3 this week").
- **Talk ratio:** advisor speaking time ÷ total speaking time, computed from diarized segment
  durations; >75% triggers `talk_over_customer`.
- **Luhn checksum:** the mod-10 digit check valid card numbers satisfy — lets the card regex
  reject random 16-digit strings (fewer false redactions).
- **Gated model:** a model requiring license acceptance/token to download (pyannote) — the reason
  a fallback exists.
- **Vendor lock-in:** switching costs that trap you with a provider; every interface in the plan
  is an anti-lock-in device.
- **Thundering herd:** many clients retrying simultaneously and re-crashing a recovering service;
  jitter is the cure.
- **Append-only:** rows are only ever inserted (audit log) — history can't be rewritten.
- **Seed script:** code that populates a fresh DB with demo org/teams/advisors/calls so dashboards
  aren't empty on first run.
- **`.env.example`:** committed template of required env vars with fake values — documentation
  that can't go stale.
- **Monorepo:** backend + frontend + demo assets in one repository — right call for a single
  deliverable zip.

---

## How to study this before building
Read Parts 1–3 fully (they're the pipeline you'll write first). Skim 4–6, then return to each
section the hour you implement it. Part 7 + 8 are your interview ammunition — re-read them the
night before the interview, out loud. If you can explain 2.9 (quote gate), 3.11 (SKIP LOCKED),
3.8 (idempotency), and 8.3 (compliance cap) without notes, you can defend the entire project.
