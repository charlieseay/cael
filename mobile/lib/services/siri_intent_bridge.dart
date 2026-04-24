import 'dart:io';

import 'package:flutter/services.dart';

enum SiriBridgeIntentType { reminder, navigation }

class SiriDispatchResult {
  final bool success;
  final String message;
  final SiriBridgeIntentType intentType;

  const SiriDispatchResult({
    required this.success,
    required this.message,
    required this.intentType,
  });
}

class SiriIntentBridge {
  static const MethodChannel _channel = MethodChannel('cael/siri_intent_bridge');

  static bool get isAvailable => Platform.isIOS;

  static Future<SiriDispatchResult> dispatchReminder({
    required String title,
    DateTime? dueDate,
    String? notes,
  }) async {
    if (!isAvailable) {
      return const SiriDispatchResult(
        success: false,
        message: 'Siri intent bridge is only available on iOS.',
        intentType: SiriBridgeIntentType.reminder,
      );
    }

    final result = await _channel.invokeMethod<Map<Object?, Object?>>(
      'dispatchReminder',
      {
        'title': title,
        'dueDate': dueDate?.toIso8601String(),
        'notes': notes,
      },
    );
    return _parseResult(result, SiriBridgeIntentType.reminder);
  }

  static Future<SiriDispatchResult> dispatchNavigation({
    required String destination,
  }) async {
    if (!isAvailable) {
      return const SiriDispatchResult(
        success: false,
        message: 'Siri intent bridge is only available on iOS.',
        intentType: SiriBridgeIntentType.navigation,
      );
    }

    final result = await _channel.invokeMethod<Map<Object?, Object?>>(
      'dispatchNavigation',
      {
        'destination': destination,
      },
    );
    return _parseResult(result, SiriBridgeIntentType.navigation);
  }

  static SiriDispatchResult _parseResult(
    Map<Object?, Object?>? result,
    SiriBridgeIntentType intentType,
  ) {
    final map = (result ?? <Object?, Object?>{}).cast<Object?, Object?>();
    final success = map['success'] as bool? ?? false;
    final message = map['message'] as String? ?? 'Intent dispatch completed.';
    return SiriDispatchResult(
      success: success,
      message: message,
      intentType: intentType,
    );
  }
}
