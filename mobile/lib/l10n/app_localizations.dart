import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_da.dart';
import 'app_localizations_en.dart';
import 'app_localizations_fr.dart';
import 'app_localizations_it.dart';
import 'app_localizations_pt.dart';
import 'app_localizations_ro.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale) : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate = _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates = <LocalizationsDelegate<dynamic>>[
    delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
  ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('da'),
    Locale('en'),
    Locale('fr'),
    Locale('it'),
    Locale('pt'),
    Locale('ro')
  ];

  /// Subtitle on welcome screen
  ///
  /// In en, this message translates to:
  /// **'Chat live with your voice AI agent'**
  String get welcomeSubtitle;

  /// Button to start conversation
  ///
  /// In en, this message translates to:
  /// **'Talk to CAAL'**
  String get talkToAgent;

  /// Button text while connecting
  ///
  /// In en, this message translates to:
  /// **'Connecting'**
  String get connecting;

  /// Status when agent is listening
  ///
  /// In en, this message translates to:
  /// **'CAAL is listening'**
  String get agentListening;

  /// Placeholder when no messages
  ///
  /// In en, this message translates to:
  /// **'Agent is listening'**
  String get agentIsListening;

  /// Empty state subtitle
  ///
  /// In en, this message translates to:
  /// **'Start a conversation to see messages here.'**
  String get startConversation;

  /// Wake word prompt
  ///
  /// In en, this message translates to:
  /// **'Say \"Hey Jarvis\"'**
  String get sayWakeWord;

  /// Wake word waiting subtitle
  ///
  /// In en, this message translates to:
  /// **'Waiting for wake word...'**
  String get waitingForWakeWord;

  /// Screenshare placeholder
  ///
  /// In en, this message translates to:
  /// **'Screenshare View'**
  String get screenshareView;

  /// Settings button tooltip
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get settings;

  /// Settings screen title
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get settingsTitle;

  /// Setup screen title
  ///
  /// In en, this message translates to:
  /// **'Sonique Setup'**
  String get caalSetup;

  /// Save button
  ///
  /// In en, this message translates to:
  /// **'Save'**
  String get save;

  /// Save in progress
  ///
  /// In en, this message translates to:
  /// **'Saving...'**
  String get saving;

  /// Test button
  ///
  /// In en, this message translates to:
  /// **'Test'**
  String get test;

  /// Connect button on setup
  ///
  /// In en, this message translates to:
  /// **'CONNECT'**
  String get connect;

  /// Connection section header
  ///
  /// In en, this message translates to:
  /// **'Connection'**
  String get connection;

  /// Server URL field label
  ///
  /// In en, this message translates to:
  /// **'Server URL'**
  String get serverUrl;

  /// Server URL placeholder
  ///
  /// In en, this message translates to:
  /// **'http://192.168.1.100:3000'**
  String get serverUrlHint;

  /// Validation error
  ///
  /// In en, this message translates to:
  /// **'Server URL is required'**
  String get serverUrlRequired;

  /// Validation error
  ///
  /// In en, this message translates to:
  /// **'Enter a valid URL'**
  String get serverUrlInvalid;

  /// Server URL helper text
  ///
  /// In en, this message translates to:
  /// **'Your Sonique server address'**
  String get yourServerAddress;

  /// Connection success
  ///
  /// In en, this message translates to:
  /// **'Connected to CAAL server'**
  String get connectedToServer;

  /// Validation error
  ///
  /// In en, this message translates to:
  /// **'Enter a valid server URL first'**
  String get enterServerFirst;

  /// Server error with code
  ///
  /// In en, this message translates to:
  /// **'Server returned {code}'**
  String serverReturned(int code);

  /// Connection error
  ///
  /// In en, this message translates to:
  /// **'Could not connect to server'**
  String get couldNotConnect;

  /// Connection error
  ///
  /// In en, this message translates to:
  /// **'Could not reach server'**
  String get couldNotReach;

  /// Setup not complete message
  ///
  /// In en, this message translates to:
  /// **'Complete the first-start wizard in your browser first'**
  String get completeWizardFirst;

  /// Setup instruction
  ///
  /// In en, this message translates to:
  /// **'Enter your server address to get started'**
  String get enterServerToStart;

  /// Setup hint
  ///
  /// In en, this message translates to:
  /// **'Complete the first-start wizard in your browser, then connect here.'**
  String get completeWizardHint;

  /// Settings unavailable message
  ///
  /// In en, this message translates to:
  /// **'Connect to server to configure agent settings'**
  String get connectToServerFirst;

  /// Agent section header
  ///
  /// In en, this message translates to:
  /// **'Agent'**
  String get agent;

  /// Agent name field
  ///
  /// In en, this message translates to:
  /// **'Agent Name'**
  String get agentName;

  /// Wake greetings field
  ///
  /// In en, this message translates to:
  /// **'Wake Greetings'**
  String get wakeGreetings;

  /// Wake greetings hint
  ///
  /// In en, this message translates to:
  /// **'One greeting per line'**
  String get onePerLine;

  /// Providers section header
  ///
  /// In en, this message translates to:
  /// **'Providers'**
  String get providers;

  /// LLM provider label
  ///
  /// In en, this message translates to:
  /// **'LLM Provider'**
  String get llmProvider;

  /// Ollama subtitle
  ///
  /// In en, this message translates to:
  /// **'Local, private'**
  String get ollamaLocalPrivate;

  /// Groq subtitle
  ///
  /// In en, this message translates to:
  /// **'Fast cloud'**
  String get groqFastCloud;

  /// Ollama host field
  ///
  /// In en, this message translates to:
  /// **'Ollama Host'**
  String get ollamaHost;

  /// API key field
  ///
  /// In en, this message translates to:
  /// **'API Key'**
  String get apiKey;

  /// Model dropdown label
  ///
  /// In en, this message translates to:
  /// **'Model'**
  String get model;

  /// Model count
  ///
  /// In en, this message translates to:
  /// **'{count} models available'**
  String modelsAvailable(int count);

  /// Groq key configured hint
  ///
  /// In en, this message translates to:
  /// **'API key configured (enter new key to change)'**
  String get apiKeyConfigured;

  /// Connection error
  ///
  /// In en, this message translates to:
  /// **'Connection failed'**
  String get connectionFailed;

  /// Connection error
  ///
  /// In en, this message translates to:
  /// **'Failed to connect'**
  String get failedToConnect;

  /// Validation error
  ///
  /// In en, this message translates to:
  /// **'Failed to validate'**
  String get failedToValidate;

  /// API key error
  ///
  /// In en, this message translates to:
  /// **'Invalid API key'**
  String get invalidApiKey;

  /// TTS provider label
  ///
  /// In en, this message translates to:
  /// **'TTS Provider'**
  String get ttsProvider;

  /// Kokoro subtitle
  ///
  /// In en, this message translates to:
  /// **'GPU neural TTS'**
  String get kokoroGpuNeural;

  /// Piper subtitle
  ///
  /// In en, this message translates to:
  /// **'CPU lightweight'**
  String get piperCpuLightweight;

  /// Voice dropdown label
  ///
  /// In en, this message translates to:
  /// **'Voice'**
  String get voice;

  /// Integrations section header
  ///
  /// In en, this message translates to:
  /// **'Integrations'**
  String get integrations;

  /// Home Assistant toggle
  ///
  /// In en, this message translates to:
  /// **'Home Assistant'**
  String get homeAssistant;

  /// Host URL field
  ///
  /// In en, this message translates to:
  /// **'Host URL'**
  String get hostUrl;

  /// Access token field
  ///
  /// In en, this message translates to:
  /// **'Access Token'**
  String get accessToken;

  /// HASS connected status
  ///
  /// In en, this message translates to:
  /// **'Connected - {count} entities'**
  String connectedEntities(int count);

  /// Connected status
  ///
  /// In en, this message translates to:
  /// **'Connected'**
  String get connected;

  /// n8n URL note
  ///
  /// In en, this message translates to:
  /// **'/mcp-server/http will be appended automatically'**
  String get n8nMcpNote;

  /// LLM settings section
  ///
  /// In en, this message translates to:
  /// **'LLM Settings'**
  String get llmSettings;

  /// Temperature field
  ///
  /// In en, this message translates to:
  /// **'Temperature'**
  String get temperature;

  /// Context size field
  ///
  /// In en, this message translates to:
  /// **'Context Size'**
  String get contextSize;

  /// Max turns field
  ///
  /// In en, this message translates to:
  /// **'Max Turns'**
  String get maxTurns;

  /// Tool cache field
  ///
  /// In en, this message translates to:
  /// **'Tool Cache'**
  String get toolCache;

  /// Interruptions toggle
  ///
  /// In en, this message translates to:
  /// **'Allow Interruptions'**
  String get allowInterruptions;

  /// Interruptions description
  ///
  /// In en, this message translates to:
  /// **'Interrupt the agent while speaking'**
  String get interruptAgent;

  /// Endpointing delay field
  ///
  /// In en, this message translates to:
  /// **'Endpointing Delay (s)'**
  String get endpointingDelay;

  /// Endpointing delay description
  ///
  /// In en, this message translates to:
  /// **'How long to wait after you stop speaking'**
  String get endpointingDelayDesc;

  /// Wake word section
  ///
  /// In en, this message translates to:
  /// **'Wake Word'**
  String get wakeWord;

  /// Wake word toggle label
  ///
  /// In en, this message translates to:
  /// **'Server-Side Wake Word'**
  String get serverSideWakeWord;

  /// Wake word description
  ///
  /// In en, this message translates to:
  /// **'Activate with wake phrase'**
  String get activateWithWakePhrase;

  /// Wake word model dropdown
  ///
  /// In en, this message translates to:
  /// **'Wake Word Model'**
  String get wakeWordModel;

  /// Threshold field
  ///
  /// In en, this message translates to:
  /// **'Threshold'**
  String get threshold;

  /// Timeout field
  ///
  /// In en, this message translates to:
  /// **'Timeout (s)'**
  String get timeout;

  /// Language selector label
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get language;

  /// English option
  ///
  /// In en, this message translates to:
  /// **'English'**
  String get languageEnglish;

  /// French option
  ///
  /// In en, this message translates to:
  /// **'Francais'**
  String get languageFrench;

  /// Italian option
  ///
  /// In en, this message translates to:
  /// **'Italiano'**
  String get languageItalian;

  /// Portuguese option
  ///
  /// In en, this message translates to:
  /// **'Português'**
  String get languagePortuguese;

  /// Danish option
  ///
  /// In en, this message translates to:
  /// **'Dansk'**
  String get languageDanish;

  /// Romanian option
  ///
  /// In en, this message translates to:
  /// **'Română'**
  String get languageRomanian;

  /// Settings note
  ///
  /// In en, this message translates to:
  /// **'Note: Model, context size, and wake word changes take effect on next session.'**
  String get changesNote;

  /// Load error
  ///
  /// In en, this message translates to:
  /// **'Failed to load settings: {error}'**
  String failedToLoad(String error);

  /// Save error
  ///
  /// In en, this message translates to:
  /// **'Failed to save: {error}'**
  String failedToSave(String error);

  /// Agent save error
  ///
  /// In en, this message translates to:
  /// **'Failed to save agent settings: {code}'**
  String failedToSaveAgent(int code);

  /// Voice download status
  ///
  /// In en, this message translates to:
  /// **'Downloading voice model...'**
  String get downloadingVoice;

  /// Text input placeholder
  ///
  /// In en, this message translates to:
  /// **'Message...'**
  String get messageHint;

  /// Tool details sheet title
  ///
  /// In en, this message translates to:
  /// **'Tool Parameters'**
  String get toolParameters;

  /// STT provider label
  ///
  /// In en, this message translates to:
  /// **'STT Provider'**
  String get sttProvider;

  /// OpenAI-compatible provider label
  ///
  /// In en, this message translates to:
  /// **'OpenAI Compat.'**
  String get openaiCompatible;

  /// OpenAI-compatible subtitle
  ///
  /// In en, this message translates to:
  /// **'Any OpenAI API'**
  String get openaiCompatibleDesc;

  /// OpenRouter subtitle
  ///
  /// In en, this message translates to:
  /// **'200+ models'**
  String get openrouterDesc;

  /// Base URL field label
  ///
  /// In en, this message translates to:
  /// **'Base URL'**
  String get baseUrl;

  /// Optional hint for fields
  ///
  /// In en, this message translates to:
  /// **'optional'**
  String get optional;

  /// OpenAI API key note
  ///
  /// In en, this message translates to:
  /// **'Only needed if the server requires authentication'**
  String get openaiApiKeyNote;

  /// Model search placeholder
  ///
  /// In en, this message translates to:
  /// **'Search models...'**
  String get searchModels;

  /// Empty model search result
  ///
  /// In en, this message translates to:
  /// **'No models found'**
  String get noModelsFound;

  /// Hint to test before model selection
  ///
  /// In en, this message translates to:
  /// **'Test connection to see available models'**
  String get testConnectionToSee;

  /// Speaches STT subtitle
  ///
  /// In en, this message translates to:
  /// **'Local Whisper'**
  String get speachesLocalStt;

  /// Groq Whisper STT subtitle
  ///
  /// In en, this message translates to:
  /// **'Cloud Whisper'**
  String get groqWhisperCloud;

  /// STT Groq key shared info
  ///
  /// In en, this message translates to:
  /// **'Uses the same API key as LLM'**
  String get sttGroqKeyShared;

  /// STT Groq key needed info
  ///
  /// In en, this message translates to:
  /// **'Groq API key required for STT'**
  String get sttGroqKeyNeeded;

  /// Standby state title
  ///
  /// In en, this message translates to:
  /// **'Standby'**
  String get standbyMode;

  /// Standby wake instruction
  ///
  /// In en, this message translates to:
  /// **'Say \"Hey Cael\" to wake up'**
  String get sayCaelToWake;
}

class _AppLocalizationsDelegate extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) => <String>['da', 'en', 'fr', 'it', 'pt', 'ro'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'da':
      return AppLocalizationsDa();
    case 'en':
      return AppLocalizationsEn();
    case 'fr':
      return AppLocalizationsFr();
    case 'it':
      return AppLocalizationsIt();
    case 'pt':
      return AppLocalizationsPt();
    case 'ro':
      return AppLocalizationsRo();
  }

  throw FlutterError('AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
      'an issue with the localizations generation tool. Please file an issue '
      'on GitHub with a reproducible sample app and the gen-l10n configuration '
      'that was used.');
}
