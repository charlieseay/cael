// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Romanian Moldavian Moldovan (`ro`).
class AppLocalizationsRo extends AppLocalizations {
  AppLocalizationsRo([String locale = 'ro']) : super(locale);

  @override
  String get welcomeSubtitle => 'Vorbește live cu asistentul tău vocal AI';

  @override
  String get talkToAgent => 'Vorbește cu CAAL';

  @override
  String get connecting => 'Se conectează';

  @override
  String get agentListening => 'CAAL ascultă';

  @override
  String get agentIsListening => 'Agentul ascultă';

  @override
  String get startConversation => 'Începe o conversație pentru a vedea mesajele aici.';

  @override
  String get sayWakeWord => 'Spune \"Hey Jarvis\"';

  @override
  String get waitingForWakeWord => 'Se așteaptă cuvântul de activare...';

  @override
  String get screenshareView => 'Vizualizare partajare ecran';

  @override
  String get settings => 'Setări';

  @override
  String get settingsTitle => 'Setări';

  @override
  String get caalSetup => 'Configurare CAAL';

  @override
  String get save => 'Salvează';

  @override
  String get saving => 'Se salvează...';

  @override
  String get test => 'Testează';

  @override
  String get connect => 'CONECTARE';

  @override
  String get connection => 'Conexiune';

  @override
  String get serverUrl => 'URL server';

  @override
  String get serverUrlHint => 'http://192.168.1.100:3000';

  @override
  String get serverUrlRequired => 'URL-ul serverului este necesar';

  @override
  String get serverUrlInvalid => 'Introdu un URL valid';

  @override
  String get yourServerAddress => 'Adresa serverului tău CAAL';

  @override
  String get connectedToServer => 'Conectat la serverul CAAL';

  @override
  String get enterServerFirst => 'Introdu mai întâi un URL de server valid';

  @override
  String serverReturned(int code) {
    return 'Serverul a returnat $code';
  }

  @override
  String get couldNotConnect => 'Nu s-a putut conecta la server';

  @override
  String get couldNotReach => 'Nu s-a putut contacta serverul';

  @override
  String get completeWizardFirst => 'Completează mai întâi asistentul de pornire în browser';

  @override
  String get enterServerToStart => 'Introdu adresa serverului tău pentru a începe';

  @override
  String get completeWizardHint => 'Completează asistentul de pornire în browser, apoi conectează-te aici.';

  @override
  String get connectToServerFirst => 'Conectează-te la server pentru a configura setările agentului';

  @override
  String get agent => 'Agent';

  @override
  String get agentName => 'Numele agentului';

  @override
  String get wakeGreetings => 'Salutări de activare';

  @override
  String get onePerLine => 'Un salut pe linie';

  @override
  String get providers => 'Furnizori';

  @override
  String get llmProvider => 'Furnizor LLM';

  @override
  String get ollamaLocalPrivate => 'Local, privat';

  @override
  String get groqFastCloud => 'Cloud rapid';

  @override
  String get ollamaHost => 'Gazdă Ollama';

  @override
  String get apiKey => 'Cheie API';

  @override
  String get model => 'Model';

  @override
  String modelsAvailable(int count) {
    return '$count modele disponibile';
  }

  @override
  String get apiKeyConfigured => 'Cheie API configurată (introdu o cheie nouă pentru a schimba)';

  @override
  String get connectionFailed => 'Conexiunea a eșuat';

  @override
  String get failedToConnect => 'Conectarea a eșuat';

  @override
  String get failedToValidate => 'Validarea a eșuat';

  @override
  String get invalidApiKey => 'Cheie API invalidă';

  @override
  String get ttsProvider => 'Furnizor TTS';

  @override
  String get kokoroGpuNeural => 'TTS neuronal GPU';

  @override
  String get piperCpuLightweight => 'TTS ușor CPU';

  @override
  String get voice => 'Voce';

  @override
  String get integrations => 'Integrări';

  @override
  String get homeAssistant => 'Home Assistant';

  @override
  String get hostUrl => 'URL gazdă';

  @override
  String get accessToken => 'Token de acces';

  @override
  String connectedEntities(int count) {
    return 'Conectat - $count entități';
  }

  @override
  String get connected => 'Conectat';

  @override
  String get n8nMcpNote => '/mcp-server/http va fi adăugat automat';

  @override
  String get llmSettings => 'Setări LLM';

  @override
  String get temperature => 'Temperatură';

  @override
  String get contextSize => 'Dimensiune context';

  @override
  String get maxTurns => 'Ture maxime';

  @override
  String get toolCache => 'Cache instrumente';

  @override
  String get allowInterruptions => 'Permite întreruperi';

  @override
  String get interruptAgent => 'Întrerupe agentul în timp ce vorbește';

  @override
  String get endpointingDelay => 'Întârziere punct final (s)';

  @override
  String get endpointingDelayDesc => 'Cât timp să aștepte după ce te oprești din vorbit';

  @override
  String get wakeWord => 'Cuvânt de activare';

  @override
  String get serverSideWakeWord => 'Cuvânt de activare server';

  @override
  String get activateWithWakePhrase => 'Activează cu frază de activare';

  @override
  String get wakeWordModel => 'Model cuvânt de activare';

  @override
  String get threshold => 'Prag';

  @override
  String get timeout => 'Timeout (s)';

  @override
  String get language => 'Limbă';

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
      'Notă: Modificările de model, dimensiune context și cuvânt de activare au efect la sesiunea următoare.';

  @override
  String failedToLoad(String error) {
    return 'Încărcarea setărilor a eșuat: $error';
  }

  @override
  String failedToSave(String error) {
    return 'Salvarea a eșuat: $error';
  }

  @override
  String failedToSaveAgent(int code) {
    return 'Salvarea setărilor agentului a eșuat: $code';
  }

  @override
  String get downloadingVoice => 'Se descarcă modelul vocal...';

  @override
  String get messageHint => 'Mesaj...';

  @override
  String get toolParameters => 'Parametri instrument';

  @override
  String get sttProvider => 'Furnizor STT';

  @override
  String get openaiCompatible => 'OpenAI Compat.';

  @override
  String get openaiCompatibleDesc => 'Orice API OpenAI';

  @override
  String get openrouterDesc => '200+ modele';

  @override
  String get baseUrl => 'URL de bază';

  @override
  String get optional => 'opțional';

  @override
  String get openaiApiKeyNote => 'Necesar doar dacă serverul necesită autentificare';

  @override
  String get searchModels => 'Caută modele...';

  @override
  String get noModelsFound => 'Niciun model găsit';

  @override
  String get testConnectionToSee => 'Testează conexiunea pentru a vedea modelele disponibile';

  @override
  String get speachesLocalStt => 'Whisper local';

  @override
  String get groqWhisperCloud => 'Whisper cloud';

  @override
  String get sttGroqKeyShared => 'Folosește aceeași cheie API ca LLM';

  @override
  String get sttGroqKeyNeeded => 'Cheie API Groq necesară pentru STT';

  @override
  String get standbyMode => 'Standby';

  @override
  String get sayCaelToWake => 'Spune \"Hey Cael\" pentru a reactiva';
}
