import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:livekit_client/livekit_client.dart' as sdk;
import '../services/siri_intent_bridge.dart';

/// Represents the current tool usage status from the agent.
class ToolStatus {
  final bool toolUsed;
  final List<String> toolNames;
  final List<Map<String, dynamic>> toolParams;

  const ToolStatus({
    this.toolUsed = false,
    this.toolNames = const [],
    this.toolParams = const [],
  });

  factory ToolStatus.fromJson(Map<String, dynamic> json) {
    return ToolStatus(
      toolUsed: json['tool_used'] as bool? ?? false,
      toolNames: (json['tool_names'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          [],
      toolParams: (json['tool_params'] as List<dynamic>?)
              ?.map((e) => e as Map<String, dynamic>)
              .toList() ??
          [],
    );
  }

  @override
  String toString() => 'ToolStatus(toolUsed: $toolUsed, toolNames: $toolNames)';
}

/// Controller that listens for tool_status data packets from the backend.
class ToolStatusCtrl extends ChangeNotifier {
  final sdk.Room room;
  late final sdk.EventsListener<sdk.RoomEvent> _listener;
  final Set<String> _handledIntentFingerprints = <String>{};

  ToolStatus _status = const ToolStatus();
  ToolStatus get status => _status;
  String? _lastSiriExecutionMessage;
  String? get lastSiriExecutionMessage => _lastSiriExecutionMessage;

  ToolStatusCtrl({required this.room}) {
    _listener = room.createListener();
    _listener.on<sdk.DataReceivedEvent>(_handleDataReceived);
  }

  void _handleDataReceived(sdk.DataReceivedEvent event) {
    // Only handle tool_status messages
    if (event.topic != 'tool_status') return;

    try {
      final jsonString = utf8.decode(event.data);
      final data = jsonDecode(jsonString) as Map<String, dynamic>;
      _status = ToolStatus.fromJson(data);
      notifyListeners();
      unawaited(_dispatchSiriIntentIfRequested(_status));
    } catch (error) {
      debugPrint('[ToolStatusCtrl] Failed to parse tool status: $error');
    }
  }

  Future<void> _dispatchSiriIntentIfRequested(ToolStatus status) async {
    if (!SiriIntentBridge.isAvailable || !status.toolUsed) return;

    for (int i = 0; i < status.toolNames.length; i++) {
      final toolName = status.toolNames[i].toLowerCase();
      final toolParams = i < status.toolParams.length ? status.toolParams[i] : <String, dynamic>{};
      final fingerprint = '$toolName:${jsonEncode(toolParams)}';
      if (_handledIntentFingerprints.contains(fingerprint)) continue;

      if (_isReminderTool(toolName, toolParams)) {
        _handledIntentFingerprints.add(fingerprint);
        await _dispatchReminder(toolParams);
      } else if (_isNavigationTool(toolName, toolParams)) {
        _handledIntentFingerprints.add(fingerprint);
        await _dispatchNavigation(toolParams);
      }
    }
  }

  bool _isReminderTool(String toolName, Map<String, dynamic> params) {
    return toolName.contains('reminder') || params.containsKey('reminder') || params.containsKey('due_date');
  }

  bool _isNavigationTool(String toolName, Map<String, dynamic> params) {
    return toolName.contains('navigation') ||
        toolName.contains('directions') ||
        toolName.contains('maps') ||
        params.containsKey('destination') ||
        params.containsKey('address');
  }

  Future<void> _dispatchReminder(Map<String, dynamic> params) async {
    final title = (params['title'] ?? params['task'] ?? params['reminder'] ?? '').toString().trim();
    if (title.isEmpty) {
      _setExecutionMessage('Reminder request skipped: missing title.');
      return;
    }

    DateTime? dueDate;
    final dueDateRaw = params['due_date'] ?? params['dueDate'] ?? params['when'];
    if (dueDateRaw is String && dueDateRaw.isNotEmpty) {
      dueDate = DateTime.tryParse(dueDateRaw);
    }

    final result = await SiriIntentBridge.dispatchReminder(
      title: title,
      dueDate: dueDate,
      notes: params['notes']?.toString(),
    );
    _setExecutionMessage(result.message);
  }

  Future<void> _dispatchNavigation(Map<String, dynamic> params) async {
    final destination = (params['destination'] ?? params['address'] ?? params['query'] ?? '').toString().trim();
    if (destination.isEmpty) {
      _setExecutionMessage('Navigation request skipped: missing destination.');
      return;
    }

    final result = await SiriIntentBridge.dispatchNavigation(destination: destination);
    _setExecutionMessage(result.message);
  }

  void _setExecutionMessage(String message) {
    _lastSiriExecutionMessage = message;
    debugPrint('[ToolStatusCtrl] Siri bridge: $message');
    notifyListeners();
  }

  /// Reset status (e.g., when disconnecting)
  void reset() {
    _status = const ToolStatus();
    _lastSiriExecutionMessage = null;
    _handledIntentFingerprints.clear();
    notifyListeners();
  }

  @override
  void dispose() {
    unawaited(_listener.dispose());
    super.dispose();
  }
}
