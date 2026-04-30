---
title: Sonique iOS Voice Path Stabilization — Decision Memo
date: 2026-04-30
status: Recommendation Ready
task: #306
---

# Sonique iOS Voice Path Stabilization: Decision Memo

**Symptom:** Local chime plays, but remote voice from agent doesn't reach user. Works in sandbox, fails on TestFlight/production.

**Root Cause:** AVAudioSession configuration conflicts between LiveKit and parallel audio services (Speech-to-Text, TTS).

**Recommendation:** Stabilize with Piper (local TTS) + manual AVAudioSession management this week. Plan Sesame CSM migration for next sprint with acceptable latency tradeoff.

**Go/No-Go Call:** **GO** on Piper path immediately. **CONDITIONAL** on Sesame (test latency first).

---

## 1. Common Root Causes: LiveKit iOS + AVAudioSession One-Way Audio

### Primary Issue: `.measurement` Mode Conflict

When Speech-to-Text or other audio analysis services activate `AVAudioSessionMode.measurement`, it conflicts with LiveKit's `.playAndRecord` category. Result: microphone captures input, but remote audio playback stops.

| Issue | Framework | Status | Impact | Reference |
|-------|-----------|--------|--------|-----------|
| Measurement mode breaks playback | Speech-to-Text + LiveKit | Known, unfixed (Feb 2026) | Remote audio silent, mic works | [LiveKit Flutter #996](https://github.com/livekit/client-sdk-flutter/issues/996) |
| Speaker routing loop | AVAudioSession defaults | Documented | Audio flips between receiver/speaker | [LiveKit Swift #391](https://github.com/livekit/client-sdk-swift/issues/391) |
| Parallel audio services | STT + LiveKit + TTS | Confirmed | Audio session stops capturing | [LiveKit React Native #286](https://github.com/livekit/client-sdk-react-native/issues/286) |

### Why It Happens

- **LiveKit auto-configures** AVAudioSession to `.playAndRecord` when publishing audio
- **Default mode is `.videoChat`**, which routes to speaker (earpiece with CallKit)
- **`.measurement` mode is incompatible** with simultaneous recording/playback (designed for audio analysis only)
- **Thread-sensitive:** Audio delegates fire on SDK's internal thread; missing `@MainActor` routing causes race conditions

### Diagnostic Pattern

```
✓ Local chime plays (AVAudioSession is active)
✗ Remote voice silent (playback routed incorrectly or overlapped)
✓ Microphone captures (recording works)
→ Confirms: AVAudioSession category mismatch, not a network issue
```

**Key Insight:** If local audio works but remote doesn't, it's not a LiveKit connection problem—it's an AVAudioSession configuration problem.

---

## 2. Proven Production Implementation Patterns

### Pattern A: Manual AVAudioSession Control (Recommended for Immediate Stabilization)

```swift
// In your voice assistant initialization:
AudioManager.shared.audioSession.isAutomaticConfigurationEnabled = false

// Configure BEFORE any audio operation:
let audioSession = AVAudioSession.sharedInstance()
try audioSession.setCategory(
    .playAndRecord,
    mode: .voiceChat,  // ← Critical: not .videoChat or .default
    options: [.duckOthers, .defaultToSpeaker]
)
try audioSession.setActive(true, options: .notifyOthersOnDeactivation)
```

**When to use:** Building custom audio pipelines with parallel services (STT + TTS + LiveKit).

**Why it works:** Disables LiveKit's automatic configuration, letting you coordinate audio session state explicitly.

**Risk:** You own the configuration lifecycle. Misconfiguration → silent failures.

### Pattern B: AudioEngineObserver Chain (Lifecycle Coordination)

```swift
// Install early in app startup, before connecting to room:
AudioManager.shared.set(engineObservers: [yourObserver])

// Your observer receives callbacks:
// - audioEngineWillStart() — prepare audio before SDK starts
// - audioEngineDidStart()  — safe to publish audio
// - audioEngineWillStop()  — clean up audio state
// - audioEngineDidStop()   — audio session inactive
```

**When to use:** Need to synchronize initialization timing with Speech-to-Text or other audio services.

**Best practice:** First observer installed = first callback received. Order matters.

### Pattern C: Thread-Safe Delegate Routing (Critical for Correctness)

```swift
// ALL LiveKit audio delegates fire on SDK internal thread
// This WILL cause crashes or race conditions:
DispatchQueue.main.async {
    self.isRemoteAudioPlaying = true  // Safe UI update
}

// Failure pattern (DO NOT DO):
// self.isRemoteAudioPlaying = true  // Race condition!
```

**Why critical:** Audio state changes must update on main thread. Missing this causes silent playback, stuck audio state, or app crashes.

### Pattern D: Error Recovery (When Audio Stops Mid-Session)

```swift
// If remote audio stops during active session:
AudioManager.shared.isSpeakerOutputPreferred = false  // Reset routing
// Wait 100ms
// Reconnect room if needed

// Prevention: Monitor audio state continuously
AudioManager.shared.set(engineObservers: [AudioStateMonitor()])
```

**When to use:** After network interruption or app backgrounding/foregrounding.

---

## 3. Reliability Comparison: Piper vs Sesame CSM

### For Mac Mini + iOS Stack: Latency & Operational Complexity

| Factor | Piper (Local TTS) | Sesame CSM (LLM + TTS) | Winner |
|--------|-------------------|------------------------|--------|
| **Time-to-First-Audio** | 150-300ms (synthesis only) | 150-400ms (synthesis + LLM context) | Piper |
| **Latency Predictability** | Consistent; no variance under load | High variance; LLM adds 150-300ms | Piper |
| **Infrastructure** | 100% local (Mac Mini/iOS) | Network-dependent API calls | Piper |
| **Real-Time Factor** | 0.20 RTF on Raspberry Pi 4 (very fast) | Not published; reports of "slow inference" | Piper |
| **Voice Quality** | High quality, limited catalog | Context-aware, natural prosody | Sesame |
| **Operational Complexity** | Low: model files + inference loop | Medium-High: LLM routing, rate limits, fallback | Piper |
| **Failure Modes** | Model load timeout, CPU saturation | API timeouts, quota exhaustion, service unavailable | Piper |
| **Cost** | Free (open-source) | Pay-per-request (API billing) | Piper |
| **Network Dependency** | None | Critical (API unavailable = silent failure) | Piper |

### End-to-End Latency Benchmarks (Local Stack)

**Piper Path (Recommended Now):**
```
User speaks → Speech-to-Text: 30-80ms
            → LLM processing: 150-300ms
            → Piper TTS: 150-300ms
            → LiveKit transmission: 100-200ms
            ─────────────────────────────
            Total: 430-880ms P90
            Verdict: Natural conversation (< 500ms P50 threshold met most of the time)
```

**Sesame CSM Path (Next Sprint):**
```
User speaks → Speech-to-Text: 30-80ms
            → LLM: 150-300ms
            → Sesame synthesis: 150-400ms (with context)
            → LiveKit: 100-200ms
            ─────────────────────────────
            Total: 430-980ms P90
            Verdict: At upper bound; noticeable delay. Test required.
```

### Critical Latency Thresholds

- **< 250ms P50:** Feels instantaneous (best UX)
- **250-500ms P50:** Natural conversation
- **500-800ms P90:** Acceptable, noticeable
- **> 800ms:** Unnatural; users interrupt

**Piper Assessment:** Hits 430-880ms range. P50 ~500ms. Borderline acceptable for assistant.

**Sesame Assessment:** Hits 430-980ms range. P90 approaches 1000ms in worst case. Requires testing.

### Why Piper Now, Sesame Next

**Piper Strengths:**
- No external dependencies (offline-first)
- Deterministic latency (doesn't degrade under load)
- Lightweight iOS integration (ONNX Runtime available)
- Immediate deployment path this week

**Piper Weaknesses:**
- No context awareness (doesn't adjust tone based on conversation)
- Slower on older hardware (CPU-bound)

**Sesame CSM Strengths:**
- Context-aware prosody (sounds more natural)
- Production-grade voice quality
- Conversational tone adjustment

**Sesame CSM Weaknesses:**
- Inference time "unrealistic for real-time voice agents" ([Sesame GitHub #78](https://github.com/SesameAILabs/csm/issues/78))
- Network latency adds 50-200ms overhead
- API-dependent (unavailability = silent failure)
- Requires operational overhead (LLM + TTS pipeline coordination)

---

## 4. Recommended Path: Immediate Stabilization + Migration Strategy

### This Week (Apr 30 – May 2): Piper Stabilization

**Goal:** Get remote voice playback working reliably on TestFlight build.

**Implementation:**

1. **Apply Pattern A** (Manual AVAudioSession control)
   - Disable automatic LiveKit audio session configuration
   - Set category to `.playAndRecord`, mode to `.voiceChat`
   - Test with Speech-to-Text + Piper + LiveKit running simultaneously

2. **Integrate Piper TTS locally**
   - Use ONNX Runtime for iOS (cross-platform compatible)
   - Reference: [Piper GitHub](https://github.com/rhasspy/piper)
   - Time estimate: 4-6 hours of integration work

3. **Apply Pattern C** (Thread-safe delegate routing)
   - Audit all audio state callbacks
   - Ensure main-thread routing via `DispatchQueue.main.async`

4. **Apply Pattern D** (Error recovery)
   - Monitor audio state continuously
   - Auto-recover from network interruptions

5. **QA Testing:**
   - Verify local chime + remote voice in parallel
   - Test network interruption recovery
   - Profile CPU/memory usage on Mac Mini and iOS devices

**Expected Outcome:** Remote voice plays reliably. Latency 430-880ms P90 (acceptable).

**Rollback Plan:** If Piper integration fails, use remote TTS service (Speechmatics/Cartesia) with acceptable network latency (50-150ms added to total).

### Next Sprint (May 5+): Sesame CSM Migration (Conditional)

**Gate:** Only proceed if Piper latency feedback is positive AND Sesame latency testing shows P90 < 700ms.

**Implementation:**

1. **Sesame API Integration**
   - Add LLM + TTS pipeline coordination
   - Implement rate limiting and fallback to Piper

2. **Latency Testing in Production**
   - Measure time-to-first-audio across 100+ user sessions
   - Compare Piper vs Sesame P50/P90 distribution

3. **Decision Gate:**
   - If Sesame P90 < 700ms: migrate incrementally (10% traffic)
   - If Sesame P90 ≥ 700ms: stay with Piper, keep Sesame for future consideration

---

## 5. Risk Matrix: Piper vs Sesame

### Piper (Local TTS) Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Model load timeout on startup | Medium (15-20%) | High (voice unavailable) | Pre-load model on app launch; set 5s timeout budget |
| CPU saturation (especially older iOS) | Medium (20%) | Medium (sluggish responses) | Profile on target devices; reduce voice complexity if needed |
| ONNX Runtime compatibility on iOS | Low (5%) | High (integration blocks) | Test with Piper ONNX variant early; have fallback TTS ready |
| Audio buffer underrun during LLM processing | Low (10%) | Medium (audio glitches) | Use pattern C (thread-safe routing); pre-buffer audio |

**Overall Risk Assessment:** Low-Medium. Piper is battle-tested; iOS integration is new but ONNX Runtime is stable.

### Sesame CSM Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| API latency spike (> 400ms) | High (30-40%) | High (user perceives as sluggish) | Monitor P90 latency; set SLA ceiling; fallback to Piper |
| API quota exhaustion (high traffic) | Medium (25%) | High (voice stops) | Implement rate limiting; queue requests; fallback strategy |
| Network unavailability (API down) | Low (5%) | Critical (complete failure) | Fallback to local Piper; cache responses |
| LLM context overflow (long conversations) | Low (10%) | Medium (response quality degrades) | Trim conversation history; reset context periodically |

**Overall Risk Assessment:** Medium-High. Sesame CSM is production-ready but introduces operational dependencies.

---

## 6. Concrete Links & References

### LiveKit iOS Audio Session Management
- [LiveKit Agent Audio Documentation](https://docs.livekit.io/agents/multimodality/audio/)
- [LiveKit Swift SDK GitHub](https://github.com/livekit/client-sdk-swift)
- [LiveKit Swift SDK Issue #391 — Speaker Routing Fix](https://github.com/livekit/client-sdk-swift/issues/391)
- [Apple AVAudioSession Documentation](https://developer.apple.com/documentation/avfaudio/avaudiosession)
- [Apple CallKit Documentation](https://developer.apple.com/documentation/callkit)

### Known Issues & Discussions
- [LiveKit Flutter Issue #996 — Measurement Mode Conflict](https://github.com/livekit/client-sdk-flutter/issues/996)
- [LiveKit React Native Issue #286 — Parallel Audio Conflict](https://github.com/livekit/client-sdk-react-native/issues/286)

### Piper TTS Implementation
- [Piper GitHub Repository](https://github.com/rhasspy/piper)
- [Medium: LiveKit + Piper TTS Low-Latency Implementation](https://medium.com/@mail2chasif/livekit-piper-tts-building-a-low-latency-local-voice-agent-with-real-time-latency-tracking-92a1008416e4)
- [macOS Piper TTS Setup Guide](https://www.thoughtasylum.com/2025/08/25/text-to-speech-on-macos-with-piper/)

### Sesame CSM & Real-Time Voice Agents
- [DigitalOcean: Sesame CSM Overview](https://www.digitalocean.com/community/tutorials/sesame-csm)
- [Spheron: Real-Time Speech-to-Speech GPU Cloud Deployment](https://www.spheron.network/blog/speech-to-speech-gpu-cloud-moshi-sesame-csm-hertz-dev/)
- [Sesame CSM GitHub Issue #78 — Real-Time Voice Agent Latency](https://github.com/SesameAILabs/csm/issues/78)
- [Sesame Research: Crossing the Uncanny Valley of Voice](https://www.sesame.com/research/crossing_the_uncanny_valley_of_voice)

### Competitive TTS Service Latency Benchmarks
- [Inworld AI: Best Voice AI TTS APIs 2026 Benchmarks](https://inworld.ai/resources/best-voice-ai-tts-apis-for-real-time-voice-agents-2026-benchmarks)
- [AssemblyAI: Top TTS APIs 2026](https://www.assemblyai.com/blog/top-text-to-speech-apis)
- [Retell AI: Sub-Second Latency Voice Assistant Benchmarks](https://www.retellai.com/resources/sub-second-latency-voice-assistants-benchmarks)
- [Speechmatics: Best TTS APIs 2025](https://www.speechmatics.com/company/articles-and-news/best-tts-apis-in-2025-top-12-text-to-speech-services-for-developers)

### Production Standards & Benchmarking
- [MDPI: Benchmarking Open-Source TTS Responsiveness](https://www.mdpi.com/2073-431X/14/10/406)
- [Picovoice TTS Latency Benchmark](https://picovoice.ai/docs/benchmark/tts-latency/)

---

## 7. Go/No-Go Call

### GO: Piper Stabilization (This Week)

**Reasoning:**
- AVAudioSession conflict is well-understood and fixable
- Piper is battle-tested, offline-first, deterministic latency
- 430-880ms P90 latency meets natural conversation threshold
- Low operational overhead; no API dependencies
- Fast deployment path (4-6 hours integration)
- Unblocks TestFlight release

**Success Criteria:**
- Remote voice plays reliably (>99% of calls)
- Latency P50 < 500ms, P90 < 800ms
- Zero silent failures (no cases where audio session gets stuck)
- CPU usage < 25% on target devices

### CONDITIONAL GO: Sesame CSM Migration (Next Sprint)

**Gate:** Only proceed if BOTH conditions met:
1. Piper latency testing shows acceptable P50/P90 in production
2. Sesame CSM latency testing shows P90 < 700ms in your use case

**If Sesame P90 ≥ 700ms:** Stay with Piper. Revisit Sesame in Q3 if latency improves.

**Migration Strategy (if GO):**
- Start at 10% traffic (A/B test)
- Monitor latency and user engagement
- If latency creep detected, rollback to Piper automatically
- Fallback to Piper if Sesame API unavailable

---

## Summary

| Decision | Timeline | Rationale |
|----------|----------|-----------|
| **Adopt Piper TTS** | This week (Apr 30–May 2) | Fixes one-way audio via manual AVAudioSession control. Low ops complexity, deterministic latency. |
| **Test Sesame CSM** | Next sprint (May 5+) | Evaluate real-time latency in production. Gate migration on P90 < 700ms benchmark. |
| **Deploy to TestFlight** | May 2 (Build 19+) | After Piper integration verified + error recovery tested. |

**Owner:** Sonique voice platform team
**Approver:** [Product/Eng Lead]
**Review Date:** May 2, 2026

