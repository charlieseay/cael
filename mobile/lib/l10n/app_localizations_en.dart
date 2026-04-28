// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get welcomeSubtitle => 'Chat live with your voice AI agent';

  @override
  String get talkToAgent => 'Talk to CAAL';

  @override
  String get connecting => 'Connecting';

  @override
  String get agentListening => 'CAAL is listening';

  @override
  String get agentIsListening => 'Agent is listening';

  @override
  String get startConversation => 'Start a conversation to see messages here.';

  @override
  String get sayWakeWord => 'Say \"Hey Jarvis\"';

  @override
  String get waitingForWakeWord => 'Waiting for wake word...';

  @override
  String get screenshareView => 'Screenshare View';

  @override
  String get settings => 'Settings';

  @override
  String get settingsTitle => 'Settings';

  @override
  String get caalSetup => 'Sonique Setup';

  @override
  String get save => 'Save';

  @override
  String get saving => 'Saving...';

  @override
  String get test => 'Test';

  @override
  String get connect => 'CONNECT';

  @override
  String get connection => 'Connection';

  @override
  String get serverUrl => 'Server URL';

  @override
  String get serverUrlHint => 'http://192.168.1.100:3000';

  @override
  String get serverUrlRequired => 'Server URL is required';

  @override
  String get serverUrlInvalid => 'Enter a valid URL';

  @override
  String get yourServerAddress => 'Your Sonique server address';

  @override
  String get connectedToServer => 'Connected to CAAL server';

  @override
  String get enterServerFirst => 'Enter a valid server URL first';

  @override
  String serverReturned(int code) {
    return 'Server returned $code';
  }

  @override
  String get couldNotConnect => 'Could not connect to server';

  @override
  String get couldNotReach => 'Could not reach server';

  @override
  String get completeWizardFirst => 'Complete the first-start wizard in your browser first';

  @override
  String get enterServerToStart => 'Enter your server address to get started';

  @override
  String get completeWizardHint => 'Complete the first-start wizard in your browser, then connect here.';

  @override
  String get connectToServerFirst => 'Connect to server to configure agent settings';

  @override
  String get agent => 'Agent';

  @override
  String get agentName => 'Agent Name';

  @override
  String get wakeGreetings => 'Wake Greetings';

  @override
  String get onePerLine => 'One greeting per line';

  @override
  String get providers => 'Providers';

  @override
  String get llmProvider => 'LLM Provider';

  @override
  String get ollamaLocalPrivate => 'Local, private';

  @override
  String get groqFastCloud => 'Fast cloud';

  @override
  String get ollamaHost => 'Ollama Host';

  @override
  String get apiKey => 'API Key';

  @override
  String get model => 'Model';

  @override
  String modelsAvailable(int count) {
    return '$count models available';
  }

  @override
  String get apiKeyConfigured => 'API key configured (enter new key to change)';

  @override
  String get connectionFailed => 'Connection failed';

  @override
  String get failedToConnect => 'Failed to connect';

  @override
  String get failedToValidate => 'Failed to validate';

  @override
  String get invalidApiKey => 'Invalid API key';

  @override
  String get ttsProvider => 'TTS Provider';

  @override
  String get kokoroGpuNeural => 'GPU neural TTS';

  @override
  String get piperCpuLightweight => 'CPU lightweight';

  @override
  String get voice => 'Voice';

  @override
  String get integrations => 'Integrations';

  @override
  String get homeAssistant => 'Home Assistant';

  @override
  String get hostUrl => 'Host URL';

  @override
  String get accessToken => 'Access Token';

  @override
  String connectedEntities(int count) {
    return 'Connected - $count entities';
  }

  @override
  String get connected => 'Connected';

  @override
  String get n8nMcpNote => '/mcp-server/http will be appended automatically';

  @override
  String get llmSettings => 'LLM Settings';

  @override
  String get temperature => 'Temperature';

  @override
  String get contextSize => 'Context Size';

  @override
  String get maxTurns => 'Max Turns';

  @override
  String get toolCache => 'Tool Cache';

  @override
  String get allowInterruptions => 'Allow Interruptions';

  @override
  String get interruptAgent => 'Interrupt the agent while speaking';

  @override
  String get endpointingDelay => 'Endpointing Delay (s)';

  @override
  String get endpointingDelayDesc => 'How long to wait after you stop speaking';

  @override
  String get wakeWord => 'Wake Word';

  @override
  String get serverSideWakeWord => 'Server-Side Wake Word';

  @override
  String get activateWithWakePhrase => 'Activate with wake phrase';

  @override
  String get wakeWordModel => 'Wake Word Model';

  @override
  String get threshold => 'Threshold';

  @override
  String get timeout => 'Timeout (s)';

  @override
  String get language => 'Language';

  @override
  String get languageEnglish => 'English';

  @override
  String get languageFrench => 'Francais';

  @override
  String get languageItalian => 'Italiano';

  @override
  String get languagePortuguese => 'Português';

  @override
  String get languageDanish => 'Dansk';

  @override
  String get languageRomanian => 'Română';

  @override
  String get changesNote => 'Note: Model, context size, and wake word changes take effect on next session.';

  @override
  String failedToLoad(String error) {
    return 'Failed to load settings: $error';
  }

  @override
  String failedToSave(String error) {
    return 'Failed to save: $error';
  }

  @override
  String failedToSaveAgent(int code) {
    return 'Failed to save agent settings: $code';
  }

  @override
  String get downloadingVoice => 'Downloading voice model...';

  @override
  String get messageHint => 'Message...';

  @override
  String get toolParameters => 'Tool Parameters';

  @override
  String get sttProvider => 'STT Provider';

  @override
  String get openaiCompatible => 'OpenAI Compat.';

  @override
  String get openaiCompatibleDesc => 'Any OpenAI API';

  @override
  String get openrouterDesc => '200+ models';

  @override
  String get baseUrl => 'Base URL';

  @override
  String get optional => 'optional';

  @override
  String get openaiApiKeyNote => 'Only needed if the server requires authentication';

  @override
  String get searchModels => 'Search models...';

  @override
  String get noModelsFound => 'No models found';

  @override
  String get testConnectionToSee => 'Test connection to see available models';

  @override
  String get speachesLocalStt => 'Local Whisper';

  @override
  String get groqWhisperCloud => 'Cloud Whisper';

  @override
  String get sttGroqKeyShared => 'Uses the same API key as LLM';

  @override
  String get sttGroqKeyNeeded => 'Groq API key required for STT';

  @override
  String get standbyMode => 'Standby';

  @override
  String get sayCaelToWake => 'Say \"Hey Cael\" to wake up';
}
