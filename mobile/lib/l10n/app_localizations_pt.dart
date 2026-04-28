// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Portuguese (`pt`).
class AppLocalizationsPt extends AppLocalizations {
  AppLocalizationsPt([String locale = 'pt']) : super(locale);

  @override
  String get welcomeSubtitle => 'Converse ao vivo com seu assistente vocal IA';

  @override
  String get talkToAgent => 'Falar com o CAAL';

  @override
  String get connecting => 'Conectando';

  @override
  String get agentListening => 'CAAL está ouvindo';

  @override
  String get agentIsListening => 'O agente está ouvindo';

  @override
  String get startConversation => 'Inicie uma conversa para ver as mensagens aqui.';

  @override
  String get sayWakeWord => 'Diga \"Hey Jarvis\"';

  @override
  String get waitingForWakeWord => 'Aguardando palavra de ativação...';

  @override
  String get screenshareView => 'Visualização de compartilhamento de tela';

  @override
  String get settings => 'Configurações';

  @override
  String get settingsTitle => 'Configurações';

  @override
  String get caalSetup => 'Configuração CAAL';

  @override
  String get save => 'Salvar';

  @override
  String get saving => 'Salvando...';

  @override
  String get test => 'Testar';

  @override
  String get connect => 'CONECTAR';

  @override
  String get connection => 'Conexão';

  @override
  String get serverUrl => 'URL do servidor';

  @override
  String get serverUrlHint => 'http://192.168.1.100:3000';

  @override
  String get serverUrlRequired => 'A URL do servidor é obrigatória';

  @override
  String get serverUrlInvalid => 'Insira uma URL válida';

  @override
  String get yourServerAddress => 'O endereço do seu servidor CAAL';

  @override
  String get connectedToServer => 'Conectado ao servidor CAAL';

  @override
  String get enterServerFirst => 'Insira primeiro uma URL de servidor válida';

  @override
  String serverReturned(int code) {
    return 'O servidor retornou $code';
  }

  @override
  String get couldNotConnect => 'Não foi possível conectar ao servidor';

  @override
  String get couldNotReach => 'Não foi possível alcançar o servidor';

  @override
  String get completeWizardFirst => 'Complete primeiro o assistente de configuração no navegador';

  @override
  String get enterServerToStart => 'Insira o endereço do seu servidor para começar';

  @override
  String get completeWizardHint => 'Complete o assistente de configuração no navegador, depois conecte-se aqui.';

  @override
  String get connectToServerFirst => 'Conecte-se ao servidor para configurar as opções do agente';

  @override
  String get agent => 'Agente';

  @override
  String get agentName => 'Nome do agente';

  @override
  String get wakeGreetings => 'Saudações de ativação';

  @override
  String get onePerLine => 'Uma por linha';

  @override
  String get providers => 'Provedores';

  @override
  String get llmProvider => 'Provedor LLM';

  @override
  String get ollamaLocalPrivate => 'Local, privado';

  @override
  String get groqFastCloud => 'Nuvem rápida';

  @override
  String get ollamaHost => 'Host Ollama';

  @override
  String get apiKey => 'Chave API';

  @override
  String get model => 'Modelo';

  @override
  String modelsAvailable(int count) {
    return '$count modelos disponíveis';
  }

  @override
  String get apiKeyConfigured => 'Chave API configurada (insira uma nova para alterar)';

  @override
  String get connectionFailed => 'Falha na conexão';

  @override
  String get failedToConnect => 'Falha ao conectar';

  @override
  String get failedToValidate => 'Falha na validação';

  @override
  String get invalidApiKey => 'Chave API inválida';

  @override
  String get ttsProvider => 'Provedor TTS';

  @override
  String get kokoroGpuNeural => 'TTS neural GPU';

  @override
  String get piperCpuLightweight => 'Leve em CPU';

  @override
  String get voice => 'Voz';

  @override
  String get integrations => 'Integrações';

  @override
  String get homeAssistant => 'Home Assistant';

  @override
  String get hostUrl => 'URL do host';

  @override
  String get accessToken => 'Token de acesso';

  @override
  String connectedEntities(int count) {
    return 'Conectado - $count entidades';
  }

  @override
  String get connected => 'Conectado';

  @override
  String get n8nMcpNote => '/mcp-server/http será adicionado automaticamente';

  @override
  String get llmSettings => 'Configurações LLM';

  @override
  String get temperature => 'Temperatura';

  @override
  String get contextSize => 'Tamanho do contexto';

  @override
  String get maxTurns => 'Turnos máximos';

  @override
  String get toolCache => 'Cache de ferramentas';

  @override
  String get allowInterruptions => 'Permitir interrupções';

  @override
  String get interruptAgent => 'Interromper o agente enquanto fala';

  @override
  String get endpointingDelay => 'Atraso de fim de fala (s)';

  @override
  String get endpointingDelayDesc => 'Quanto tempo esperar após você parar de falar';

  @override
  String get wakeWord => 'Palavra de ativação';

  @override
  String get serverSideWakeWord => 'Palavra de ativação no servidor';

  @override
  String get activateWithWakePhrase => 'Ativar com frase de ativação';

  @override
  String get wakeWordModel => 'Modelo da palavra de ativação';

  @override
  String get threshold => 'Limiar';

  @override
  String get timeout => 'Tempo limite (s)';

  @override
  String get language => 'Idioma';

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
      'Nota: Alterações no modelo, tamanho do contexto e palavra de ativação terão efeito na próxima sessão.';

  @override
  String failedToLoad(String error) {
    return 'Falha ao carregar configurações: $error';
  }

  @override
  String failedToSave(String error) {
    return 'Falha ao salvar: $error';
  }

  @override
  String failedToSaveAgent(int code) {
    return 'Falha ao salvar configurações do agente: $code';
  }

  @override
  String get downloadingVoice => 'Baixando modelo de voz...';

  @override
  String get messageHint => 'Mensagem...';

  @override
  String get toolParameters => 'Parâmetros da ferramenta';

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
  String get sayCaelToWake => 'Diga \"Hey Cael\" para reativar';
}
