import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'app.dart';
import 'providers/locale_provider.dart';
import 'services/config_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Hide status bar and navigation bar for full-screen experience
  await SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);

  // Initialize config service first
  final configService = ConfigService();
  await configService.init();

  // Initialize locale provider
  final localeProvider = LocaleProvider();

  // Check for deep link launch (e.g., Siri Shortcut opening cael://activate)
  final appLinks = AppLinks();
  Uri? initialLink;
  try {
    initialLink = await appLinks.getInitialLink();
  } catch (_) {
    // No initial link — normal launch
  }
  final autoConnect = initialLink?.scheme == 'cael' && initialLink?.host == 'activate';

  // Try to load .env as fallback for development (optional)
  try {
    await dotenv.load(fileName: '.env');
    // If .env exists and config isn't set, migrate server URL
    if (!configService.isConfigured) {
      final envUrl = dotenv.env['CAAL_SERVER_URL']?.replaceAll('"', '');
      if (envUrl != null && envUrl.isNotEmpty) {
        await configService.setServerUrl(envUrl);
      }
    }
  } catch (_) {
    // .env file not found - that's fine, we'll use ConfigService
  }

  // Load locale from backend if configured
  if (configService.isConfigured) {
    await localeProvider.loadFromSettings(configService.serverUrl);
  }

  runApp(CaalApp(
    configService: configService,
    localeProvider: localeProvider,
    autoConnect: autoConnect,
    appLinks: appLinks,
  ));
}
