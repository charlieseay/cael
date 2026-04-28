// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Italian (`it`).
class AppLocalizationsIt extends AppLocalizations {
  AppLocalizationsIt([String locale = 'it']) : super(locale);

  @override
  String get welcomeSubtitle => 'Chatta in diretta con il tuo assistente vocale IA';

  @override
  String get talkToAgent => 'Parla con CAAL';

  @override
  String get connecting => 'Connessione';

  @override
  String get agentListening => 'CAAL sta ascoltando';

  @override
  String get agentIsListening => 'L\'agente sta ascoltando';

  @override
  String get startConversation => 'Inizia una conversazione per vedere i messaggi qui.';

  @override
  String get sayWakeWord => 'Di\' \"Hey Jarvis\"';

  @override
  String get waitingForWakeWord => 'In attesa della parola di attivazione...';

  @override
  String get screenshareView => 'Vista condivisione schermo';

  @override
  String get settings => 'Impostazioni';

  @override
  String get settingsTitle => 'Impostazioni';

  @override
  String get caalSetup => 'Configurazione CAAL';

  @override
  String get save => 'Salva';

  @override
  String get saving => 'Salvataggio...';

  @override
  String get test => 'Testa';

  @override
  String get connect => 'CONNETTI';

  @override
  String get connection => 'Connessione';

  @override
  String get serverUrl => 'URL del server';

  @override
  String get serverUrlHint => 'http://192.168.1.100:3000';

  @override
  String get serverUrlRequired => 'L\'URL del server è richiesto';

  @override
  String get serverUrlInvalid => 'Inserisci un URL valido';

  @override
  String get yourServerAddress => 'L\'indirizzo del tuo server CAAL';

  @override
  String get connectedToServer => 'Connesso al server CAAL';

  @override
  String get enterServerFirst => 'Inserisci prima un URL del server valido';

  @override
  String serverReturned(int code) {
    return 'Il server ha restituito $code';
  }

  @override
  String get couldNotConnect => 'Impossibile connettersi al server';

  @override
  String get couldNotReach => 'Impossibile raggiungere il server';

  @override
  String get completeWizardFirst => 'Completa prima la configurazione guidata nel browser';

  @override
  String get enterServerToStart => 'Inserisci l\'indirizzo del tuo server per iniziare';

  @override
  String get completeWizardHint => 'Completa la configurazione guidata nel browser, poi connettiti qui.';

  @override
  String get connectToServerFirst => 'Connettiti al server per configurare le impostazioni dell\'agente';

  @override
  String get agent => 'Agente';

  @override
  String get agentName => 'Nome dell\'agente';

  @override
  String get wakeGreetings => 'Messaggi di benvenuto';

  @override
  String get onePerLine => 'Uno per riga';

  @override
  String get providers => 'Fornitori';

  @override
  String get llmProvider => 'Fornitore LLM';

  @override
  String get ollamaLocalPrivate => 'Locale, privato';

  @override
  String get groqFastCloud => 'Cloud veloce';

  @override
  String get ollamaHost => 'Host Ollama';

  @override
  String get apiKey => 'Chiave API';

  @override
  String get model => 'Modello';

  @override
  String modelsAvailable(int count) {
    return '$count modelli disponibili';
  }

  @override
  String get apiKeyConfigured => 'Chiave API configurata (inseriscine una nuova per cambiare)';

  @override
  String get connectionFailed => 'Connessione fallita';

  @override
  String get failedToConnect => 'Connessione fallita';

  @override
  String get failedToValidate => 'Validazione fallita';

  @override
  String get invalidApiKey => 'Chiave API non valida';

  @override
  String get ttsProvider => 'Fornitore TTS';

  @override
  String get kokoroGpuNeural => 'TTS neurale GPU';

  @override
  String get piperCpuLightweight => 'Leggero su CPU';

  @override
  String get voice => 'Voce';

  @override
  String get integrations => 'Integrazioni';

  @override
  String get homeAssistant => 'Home Assistant';

  @override
  String get hostUrl => 'URL dell\'host';

  @override
  String get accessToken => 'Token di accesso';

  @override
  String connectedEntities(int count) {
    return 'Connesso - $count entità';
  }

  @override
  String get connected => 'Connesso';

  @override
  String get n8nMcpNote => '/mcp-server/http verrà aggiunto automaticamente';

  @override
  String get llmSettings => 'Impostazioni LLM';

  @override
  String get temperature => 'Temperatura';

  @override
  String get contextSize => 'Dimensione del contesto';

  @override
  String get maxTurns => 'Turni massimi';

  @override
  String get toolCache => 'Cache strumenti';

  @override
  String get allowInterruptions => 'Consenti interruzioni';

  @override
  String get interruptAgent => 'Interrompi l\'agente mentre parla';

  @override
  String get endpointingDelay => 'Ritardo di fine turno (s)';

  @override
  String get endpointingDelayDesc => 'Tempo di attesa dopo che smetti di parlare';

  @override
  String get wakeWord => 'Parola di attivazione';

  @override
  String get serverSideWakeWord => 'Parola di attivazione lato server';

  @override
  String get activateWithWakePhrase => 'Attiva con la frase di attivazione';

  @override
  String get wakeWordModel => 'Modello della parola di attivazione';

  @override
  String get threshold => 'Soglia';

  @override
  String get timeout => 'Timeout (s)';

  @override
  String get language => 'Lingua';

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
      'Nota: Le modifiche al modello, dimensione del contesto e parola di attivazione avranno effetto alla prossima sessione.';

  @override
  String failedToLoad(String error) {
    return 'Caricamento delle impostazioni fallito: $error';
  }

  @override
  String failedToSave(String error) {
    return 'Salvataggio fallito: $error';
  }

  @override
  String failedToSaveAgent(int code) {
    return 'Salvataggio delle impostazioni dell\'agente fallito: $code';
  }

  @override
  String get downloadingVoice => 'Download del modello vocale...';

  @override
  String get messageHint => 'Messaggio...';

  @override
  String get toolParameters => 'Parametri dello strumento';

  @override
  String get sttProvider => 'Fornitore STT';

  @override
  String get openaiCompatible => 'OpenAI Compat.';

  @override
  String get openaiCompatibleDesc => 'Qualsiasi API OpenAI';

  @override
  String get openrouterDesc => '200+ modelli';

  @override
  String get baseUrl => 'URL di base';

  @override
  String get optional => 'opzionale';

  @override
  String get openaiApiKeyNote => 'Necessaria solo se il server richiede l\'autenticazione';

  @override
  String get searchModels => 'Cerca modelli...';

  @override
  String get noModelsFound => 'Nessun modello trovato';

  @override
  String get testConnectionToSee => 'Testa la connessione per vedere i modelli disponibili';

  @override
  String get speachesLocalStt => 'Whisper locale';

  @override
  String get groqWhisperCloud => 'Whisper cloud';

  @override
  String get sttGroqKeyShared => 'Usa la stessa chiave API del LLM';

  @override
  String get sttGroqKeyNeeded => 'Chiave API Groq richiesta per STT';

  @override
  String get standbyMode => 'Standby';

  @override
  String get sayCaelToWake => 'Di \"Hey Cael\" per riattivare';
}
