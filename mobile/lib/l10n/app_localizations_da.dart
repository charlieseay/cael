// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Danish (`da`).
class AppLocalizationsDa extends AppLocalizations {
  AppLocalizationsDa([String locale = 'da']) : super(locale);

  @override
  String get welcomeSubtitle => 'Tal live med din stemme-AI-assistent';

  @override
  String get talkToAgent => 'Tal med CAAL';

  @override
  String get connecting => 'Forbinder';

  @override
  String get agentListening => 'CAAL lytter';

  @override
  String get agentIsListening => 'Agenten lytter';

  @override
  String get startConversation => 'Start en samtale for at se beskeder her.';

  @override
  String get sayWakeWord => 'Sig \"Hey Jarvis\"';

  @override
  String get waitingForWakeWord => 'Venter på aktiveringsord...';

  @override
  String get screenshareView => 'Skærmdelingsvisning';

  @override
  String get settings => 'Indstillinger';

  @override
  String get settingsTitle => 'Indstillinger';

  @override
  String get caalSetup => 'CAAL-opsætning';

  @override
  String get save => 'Gem';

  @override
  String get saving => 'Gemmer...';

  @override
  String get test => 'Test';

  @override
  String get connect => 'TILSLUT';

  @override
  String get connection => 'Forbindelse';

  @override
  String get serverUrl => 'Server-URL';

  @override
  String get serverUrlHint => 'http://192.168.1.100:3000';

  @override
  String get serverUrlRequired => 'Server-URL er påkrævet';

  @override
  String get serverUrlInvalid => 'Indtast en gyldig URL';

  @override
  String get yourServerAddress => 'Din CAAL-serveradresse';

  @override
  String get connectedToServer => 'Tilsluttet CAAL-server';

  @override
  String get enterServerFirst => 'Indtast først en gyldig server-URL';

  @override
  String serverReturned(int code) {
    return 'Server returnerede $code';
  }

  @override
  String get couldNotConnect => 'Kunne ikke oprette forbindelse til server';

  @override
  String get couldNotReach => 'Kunne ikke nå serveren';

  @override
  String get completeWizardFirst => 'Gennemfør først opsætningsguiden i din browser';

  @override
  String get enterServerToStart => 'Indtast din serveradresse for at komme i gang';

  @override
  String get completeWizardHint => 'Gennemfør opsætningsguiden i din browser, og tilslut derefter her.';

  @override
  String get connectToServerFirst => 'Tilslut til serveren for at konfigurere agentindstillinger';

  @override
  String get agent => 'Agent';

  @override
  String get agentName => 'Agentnavn';

  @override
  String get wakeGreetings => 'Aktiveringshilsner';

  @override
  String get onePerLine => 'Én hilsen pr. linje';

  @override
  String get providers => 'Udbydere';

  @override
  String get llmProvider => 'LLM-udbyder';

  @override
  String get ollamaLocalPrivate => 'Lokal, privat';

  @override
  String get groqFastCloud => 'Hurtig sky';

  @override
  String get ollamaHost => 'Ollama-host';

  @override
  String get apiKey => 'API-nøgle';

  @override
  String get model => 'Model';

  @override
  String modelsAvailable(int count) {
    return '$count modeller tilgængelige';
  }

  @override
  String get apiKeyConfigured => 'API-nøgle konfigureret (indtast ny nøgle for at ændre)';

  @override
  String get connectionFailed => 'Forbindelse mislykkedes';

  @override
  String get failedToConnect => 'Forbindelse mislykkedes';

  @override
  String get failedToValidate => 'Validering mislykkedes';

  @override
  String get invalidApiKey => 'Ugyldig API-nøgle';

  @override
  String get ttsProvider => 'TTS-udbyder';

  @override
  String get kokoroGpuNeural => 'GPU-neuralt TTS';

  @override
  String get piperCpuLightweight => 'Let CPU-TTS';

  @override
  String get voice => 'Stemme';

  @override
  String get integrations => 'Integrationer';

  @override
  String get homeAssistant => 'Home Assistant';

  @override
  String get hostUrl => 'Host-URL';

  @override
  String get accessToken => 'Adgangstoken';

  @override
  String connectedEntities(int count) {
    return 'Tilsluttet - $count enheder';
  }

  @override
  String get connected => 'Tilsluttet';

  @override
  String get n8nMcpNote => '/mcp-server/http tilføjes automatisk';

  @override
  String get llmSettings => 'LLM-indstillinger';

  @override
  String get temperature => 'Temperatur';

  @override
  String get contextSize => 'Kontekststørrelse';

  @override
  String get maxTurns => 'Maks. ture';

  @override
  String get toolCache => 'Værktøjscache';

  @override
  String get allowInterruptions => 'Tillad afbrydelser';

  @override
  String get interruptAgent => 'Afbryd agenten mens den taler';

  @override
  String get endpointingDelay => 'Slutpunktsforsinkelse (s)';

  @override
  String get endpointingDelayDesc => 'Hvor længe der skal ventes efter du stopper med at tale';

  @override
  String get wakeWord => 'Aktiveringsord';

  @override
  String get serverSideWakeWord => 'Serverside aktiveringsord';

  @override
  String get activateWithWakePhrase => 'Aktiver med aktiveringsfrase';

  @override
  String get wakeWordModel => 'Aktiveringsord-model';

  @override
  String get threshold => 'Tærskel';

  @override
  String get timeout => 'Timeout (s)';

  @override
  String get language => 'Sprog';

  @override
  String get languageEnglish => 'English';

  @override
  String get languageFrench => 'Français';

  @override
  String get languageItalian => 'Italiano';

  @override
  String get languagePortuguese => 'Português';

  @override
  String get languageDanish => 'Dansk';

  @override
  String get languageRomanian => 'Română';

  @override
  String get changesNote =>
      'Bemærk: Ændringer af model, kontekststørrelse og aktiveringsord træder i kraft ved næste session.';

  @override
  String failedToLoad(String error) {
    return 'Kunne ikke indlæse indstillinger: $error';
  }

  @override
  String failedToSave(String error) {
    return 'Kunne ikke gemme: $error';
  }

  @override
  String failedToSaveAgent(int code) {
    return 'Kunne ikke gemme agentindstillinger: $code';
  }

  @override
  String get downloadingVoice => 'Downloader stemmemodel...';

  @override
  String get messageHint => 'Besked...';

  @override
  String get toolParameters => 'Værktøjsparametre';

  @override
  String get sttProvider => 'STT-udbyder';

  @override
  String get openaiCompatible => 'OpenAI Compat.';

  @override
  String get openaiCompatibleDesc => 'Enhver OpenAI API';

  @override
  String get openrouterDesc => '200+ modeller';

  @override
  String get baseUrl => 'Basis-URL';

  @override
  String get optional => 'valgfri';

  @override
  String get openaiApiKeyNote => 'Kun nødvendig hvis serveren kræver autentificering';

  @override
  String get searchModels => 'Søg modeller...';

  @override
  String get noModelsFound => 'Ingen modeller fundet';

  @override
  String get testConnectionToSee => 'Test forbindelsen for at se tilgængelige modeller';

  @override
  String get speachesLocalStt => 'Lokal Whisper';

  @override
  String get groqWhisperCloud => 'Sky Whisper';

  @override
  String get sttGroqKeyShared => 'Bruger samme API-nøgle som LLM';

  @override
  String get sttGroqKeyNeeded => 'Groq API-nøgle påkrævet til STT';

  @override
  String get standbyMode => 'Standby';

  @override
  String get sayCaelToWake => 'Sig \"Hey Cael\" for at vågne';
}
