# Hands-Free Activation

Cael supports hands-free activation using iOS Siri as the wake word trigger. After the initial Siri invocation, all conversation data stays local -- Siri is only used to launch the app.

## How It Works

1. **Siri hears "Hey Cael"** and runs an iOS Shortcut
2. The Shortcut opens `cael://activate`, which launches (or foregrounds) the Cael app
3. The app auto-connects to the desktop LiveKit session -- no tap required
4. Server-side OpenWakeWord handles all subsequent "Hey Cael" detection locally
5. After 30 seconds of idle (no speech, no wake word), Cael enters **standby**
6. Saying "Hey Cael" again reactivates -- detected locally, not through Siri

## Privacy Model

| Phase | Where it runs | Cloud involved? |
|-------|---------------|-----------------|
| Initial wake word ("Hey Siri, Hey Cael") | iOS on-device Siri | Apple processes "Hey Siri" only |
| App launch via URL scheme | iOS | No |
| Session connection (LiveKit) | LAN / Tailscale | No |
| Subsequent wake word detection | Server-side OpenWakeWord | No |
| Speech-to-text | Local Speaches (Whisper) | No (unless Groq fallback) |
| LLM inference | Local Ollama | No (unless cloud provider) |

After the Siri trigger, everything stays on your network.

## iOS Shortcut Setup

### Step 1: Create the Shortcut

1. Open the **Shortcuts** app on your iPhone
2. Tap **+** to create a new shortcut
3. Add the action: **Open URLs**
4. Set the URL to: `cael://activate`
5. Name the shortcut: **Hey Cael**

### Step 2: Set Up Siri Trigger

1. Tap the shortcut name at the top, then **Rename**
2. Name it exactly: `Hey Cael`
3. iOS automatically registers the shortcut name as a Siri voice command
4. You can also tap **...** > **Add to Siri** and record a custom phrase

### Step 3: Test It

1. Make sure the Cael server is running on your desktop
2. Say **"Hey Siri, Hey Cael"**
3. Siri should respond and launch the Cael app
4. The app auto-connects and Cael is ready to listen

### Troubleshooting

- **"I don't see that in your shortcuts"** -- Make sure the shortcut is named exactly "Hey Cael" and Siri Shortcuts sync is enabled
- **App opens but doesn't connect** -- Verify the server URL is configured in Settings
- **Connection fails** -- Check that your phone and desktop are on the same network (or connected via Tailscale)

## Standby Behavior

After a conversation ends:

1. **3 seconds** of silence: Cael returns to wake word listening (stops STT, saves resources)
2. **30 seconds** in listening with no wake word: Cael enters **standby** (UI dims, shows "Say Hey Cael to wake up")
3. Wake word detection continues running in standby -- say "Hey Cael" and it reactivates instantly
4. If the app is fully backgrounded, use Siri again: "Hey Siri, Hey Cael"

The standby timeout is configurable via `standby_timeout` in settings (default: 30 seconds).

## Configuration

In `settings.json`:

```json
{
  "wake_word_enabled": true,
  "wake_word_model": "models/hey_jarvis.onnx",
  "wake_word_threshold": 0.5,
  "wake_word_timeout": 3.0,
  "standby_timeout": 30.0
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| `wake_word_timeout` | 3.0s | Silence before returning to wake word listening |
| `standby_timeout` | 30.0s | Time in listening before entering standby mode |
| `wake_word_threshold` | 0.5 | Detection confidence (0-1, higher = stricter) |

## Technical Details

- **URL Scheme**: `cael://activate` registered in `Info.plist`
- **Deep link handling**: `app_links` Flutter package, detected in `main.dart`
- **Auto-connect**: `AppCtrl` receives `autoConnect: true` and calls `connect()` on init
- **Warm relaunch**: `AppLinks.uriLinkStream` listens for URLs while app is running
- **Standby state**: `WakeWordState.STANDBY` published via LiveKit data channel
- **Wake from standby**: OpenWakeWord continues detection in standby, transitions directly to ACTIVE
