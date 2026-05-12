import 'dart:async';

import 'package:flutter/material.dart';
import 'package:livekit_client/livekit_client.dart' as sdk;
import 'package:provider/provider.dart';

import '../controllers/app_ctrl.dart' as ctrl;
import '../l10n/app_localizations.dart';
import '../services/config_service.dart';
import '../widgets/button.dart' as buttons;
import 'settings_screen.dart';
import 'setup_screen.dart';

class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key});

  void _openSettings(BuildContext context) {
    final configService = context.read<ConfigService>();
    final appCtrl = context.read<ctrl.AppCtrl>();

    // If first start (not configured), show simple URL setup
    // Otherwise show full settings page
    if (!configService.isConfigured) {
      unawaited(Navigator.of(context).push(
        MaterialPageRoute(
          builder: (context) => SetupScreen(
            configService: configService,
            onConfigured: () {
              Navigator.of(context).pop();
              unawaited(appCtrl.updateConfig(serverUrl: configService.serverUrl));
            },
          ),
        ),
      ));
    } else {
      unawaited(Navigator.of(context).push(
        MaterialPageRoute(
          builder: (context) => SettingsScreen(
            configService: configService,
            onSave: () {
              Navigator.of(context).pop();
              unawaited(appCtrl.updateConfig(serverUrl: configService.serverUrl));
            },
          ),
        ),
      ));
    }
  }

  @override
  Widget build(BuildContext ctx) {
    final l10n = AppLocalizations.of(ctx);

    return Material(
      child: Stack(
        children: [
          // Main content
          Center(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 36),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                spacing: 30,
                children: [
                  // Audio waveform icon to match web frontend
                  Icon(
                    Icons.graphic_eq,
                    size: 80,
                    color: Colors.white,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    l10n.welcomeSubtitle,
                    style: const TextStyle(
                      fontSize: 18,
                      color: Colors.white,
                    ),
                    textAlign: TextAlign.center,
                  ),
                  // Agent listening indicator
                  Consumer<sdk.Session>(
                    builder: (ctx, session, child) => AnimatedOpacity(
                      opacity: session.agent.canListen ? 1.0 : 0.0,
                      duration: const Duration(milliseconds: 300),
                      child: Container(
                        padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              Icons.mic,
                              color: Colors.green,
                              size: 18,
                            ),
                            const SizedBox(width: 8),
                            Text(
                              l10n.agentListening,
                              style: const TextStyle(
                                color: Colors.green,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  Consumer2<ctrl.AppCtrl, sdk.Session>(
                    builder: (ctx, appCtrl, session, child) {
                      final isProgressing =
                          appCtrl.isSessionStarting || session.connectionState != sdk.ConnectionState.disconnected;
                      return buttons.Button(
                        text: isProgressing ? l10n.connecting : l10n.talkToAgent,
                        isProgressing: isProgressing,
                        onPressed: () => appCtrl.connect(),
                      );
                    },
                  ),
                  Consumer<ctrl.AppCtrl>(
                    builder: (ctx, appCtrl, _) {
                      final err = appCtrl.lastConnectionError;
                      if (err == null || err.isEmpty) {
                        return const SizedBox.shrink();
                      }
                      return Padding(
                        padding: const EdgeInsets.only(top: 16),
                        child: Text(
                          '${l10n.couldNotConnect}\n$err',
                          style: const TextStyle(
                            color: Colors.orangeAccent,
                            fontSize: 14,
                            height: 1.35,
                          ),
                          textAlign: TextAlign.center,
                        ),
                      );
                    },
                  ),
                ],
              ),
            ),
          ),
          // Settings button in top right
          Positioned(
            top: 16,
            right: 16,
            child: SafeArea(
              child: IconButton(
                icon: const Icon(Icons.settings, color: Colors.white54),
                onPressed: () => _openSettings(ctx),
                tooltip: l10n.settings,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
