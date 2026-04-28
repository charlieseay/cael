// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for French (`fr`).
class AppLocalizationsFr extends AppLocalizations {
  AppLocalizationsFr([String locale = 'fr']) : super(locale);

  @override
  String get welcomeSubtitle => 'Discutez en direct avec votre assistant vocal IA';

  @override
  String get talkToAgent => 'Parler à CAAL';

  @override
  String get connecting => 'Connexion';

  @override
  String get agentListening => 'CAAL écoute';

  @override
  String get agentIsListening => 'L\'agent écoute';

  @override
  String get startConversation => 'Commencez une conversation pour voir les messages ici.';

  @override
  String get sayWakeWord => 'Dites \"Hey Jarvis\"';

  @override
  String get waitingForWakeWord => 'En attente du mot d\'activation...';

  @override
  String get screenshareView => 'Vue du partage d\'écran';

  @override
  String get settings => 'Paramètres';

  @override
  String get settingsTitle => 'Paramètres';

  @override
  String get caalSetup => 'Configuration CAAL';

  @override
  String get save => 'Enregistrer';

  @override
  String get saving => 'Enregistrement...';

  @override
  String get test => 'Tester';

  @override
  String get connect => 'CONNECTER';

  @override
  String get connection => 'Connexion';

  @override
  String get serverUrl => 'URL du serveur';

  @override
  String get serverUrlHint => 'http://192.168.1.100:3000';

  @override
  String get serverUrlRequired => 'L\'URL du serveur est requise';

  @override
  String get serverUrlInvalid => 'Entrez une URL valide';

  @override
  String get yourServerAddress => 'L\'adresse de votre serveur CAAL';

  @override
  String get connectedToServer => 'Connecté au serveur CAAL';

  @override
  String get enterServerFirst => 'Entrez d\'abord une URL de serveur valide';

  @override
  String serverReturned(int code) {
    return 'Le serveur a renvoyé $code';
  }

  @override
  String get couldNotConnect => 'Impossible de se connecter au serveur';

  @override
  String get couldNotReach => 'Impossible d\'atteindre le serveur';

  @override
  String get completeWizardFirst => 'Complétez d\'abord l\'assistant de démarrage dans votre navigateur';

  @override
  String get enterServerToStart => 'Entrez l\'adresse de votre serveur pour commencer';

  @override
  String get completeWizardHint =>
      'Complétez l\'assistant de démarrage dans votre navigateur, puis connectez-vous ici.';

  @override
  String get connectToServerFirst => 'Connectez-vous au serveur pour configurer les paramètres de l\'agent';

  @override
  String get agent => 'Agent';

  @override
  String get agentName => 'Nom de l\'agent';

  @override
  String get wakeGreetings => 'Messages d\'accueil';

  @override
  String get onePerLine => 'Un message par ligne';

  @override
  String get providers => 'Fournisseurs';

  @override
  String get llmProvider => 'Fournisseur LLM';

  @override
  String get ollamaLocalPrivate => 'Local, privé';

  @override
  String get groqFastCloud => 'Cloud rapide';

  @override
  String get ollamaHost => 'Hôte Ollama';

  @override
  String get apiKey => 'Clé API';

  @override
  String get model => 'Modèle';

  @override
  String modelsAvailable(int count) {
    return '$count modèles disponibles';
  }

  @override
  String get apiKeyConfigured => 'Clé API configurée (entrez une nouvelle clé pour changer)';

  @override
  String get connectionFailed => 'Échec de la connexion';

  @override
  String get failedToConnect => 'Échec de la connexion';

  @override
  String get failedToValidate => 'Échec de la validation';

  @override
  String get invalidApiKey => 'Clé API invalide';

  @override
  String get ttsProvider => 'Fournisseur TTS';

  @override
  String get kokoroGpuNeural => 'TTS neuronal GPU';

  @override
  String get piperCpuLightweight => 'Léger sur CPU';

  @override
  String get voice => 'Voix';

  @override
  String get integrations => 'Intégrations';

  @override
  String get homeAssistant => 'Home Assistant';

  @override
  String get hostUrl => 'URL de l\'hôte';

  @override
  String get accessToken => 'Jeton d\'accès';

  @override
  String connectedEntities(int count) {
    return 'Connecté - $count entités';
  }

  @override
  String get connected => 'Connecté';

  @override
  String get n8nMcpNote => '/mcp-server/http sera ajouté automatiquement';

  @override
  String get llmSettings => 'Paramètres LLM';

  @override
  String get temperature => 'Température';

  @override
  String get contextSize => 'Taille du contexte';

  @override
  String get maxTurns => 'Tours maximum';

  @override
  String get toolCache => 'Cache d\'outils';

  @override
  String get allowInterruptions => 'Autoriser les interruptions';

  @override
  String get interruptAgent => 'Interrompre l\'agent pendant qu\'il parle';

  @override
  String get endpointingDelay => 'Délai de fin (s)';

  @override
  String get endpointingDelayDesc => 'Temps d\'attente après que vous arrêtez de parler';

  @override
  String get wakeWord => 'Mot d\'activation';

  @override
  String get serverSideWakeWord => 'Mot d\'activation serveur';

  @override
  String get activateWithWakePhrase => 'Activer avec la phrase d\'activation';

  @override
  String get wakeWordModel => 'Modèle de mot d\'activation';

  @override
  String get threshold => 'Seuil';

  @override
  String get timeout => 'Délai (s)';

  @override
  String get language => 'Langue';

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
      'Note : Les changements de modèle, taille du contexte et mot d\'activation prennent effet à la prochaine session.';

  @override
  String failedToLoad(String error) {
    return 'Échec du chargement des paramètres : $error';
  }

  @override
  String failedToSave(String error) {
    return 'Échec de l\'enregistrement : $error';
  }

  @override
  String failedToSaveAgent(int code) {
    return 'Échec de l\'enregistrement des paramètres de l\'agent : $code';
  }

  @override
  String get downloadingVoice => 'Téléchargement du modèle vocal...';

  @override
  String get messageHint => 'Message...';

  @override
  String get toolParameters => 'Paramètres de l\'outil';

  @override
  String get sttProvider => 'Fournisseur STT';

  @override
  String get openaiCompatible => 'OpenAI Compat.';

  @override
  String get openaiCompatibleDesc => 'Toute API OpenAI';

  @override
  String get openrouterDesc => '200+ modèles';

  @override
  String get baseUrl => 'URL de base';

  @override
  String get optional => 'optionnel';

  @override
  String get openaiApiKeyNote => 'Nécessaire uniquement si le serveur requiert une authentification';

  @override
  String get searchModels => 'Rechercher des modèles...';

  @override
  String get noModelsFound => 'Aucun modèle trouvé';

  @override
  String get testConnectionToSee => 'Testez la connexion pour voir les modèles disponibles';

  @override
  String get speachesLocalStt => 'Whisper local';

  @override
  String get groqWhisperCloud => 'Whisper cloud';

  @override
  String get sttGroqKeyShared => 'Utilise la même clé API que le LLM';

  @override
  String get sttGroqKeyNeeded => 'Clé API Groq requise pour le STT';

  @override
  String get standbyMode => 'Veille';

  @override
  String get sayCaelToWake => 'Dites \"Hey Cael\" pour réactiver';
}
