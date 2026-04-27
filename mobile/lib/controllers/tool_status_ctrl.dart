import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

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

/// Controller that listens for tool_status data packets from the backend
/// and handles iOS-specific tool dispatch (Siri intents, calendar, messages).
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
    // Backend requesting a calendar query — respond with EKEventStore data.
    // This is the response side of the query_ios_calendar request/response
    // pattern; it runs independently of the tool_status indicator.
    if (event.topic == 'request_ios_calendar') {
      unawaited(_handleCalendarRequest(event.data));
      return;
    }

    // Contacts query request/response
    if (event.topic == 'request_ios_contacts') {
      unawaited(_handleContactsRequest(event.data));
      return;
    }

    // Directions query request/response
    if (event.topic == 'request_ios_directions') {
      unawaited(_handleDirectionsRequest(event.data));
      return;
    }

    // Location query request/response
    if (event.topic == 'request_ios_location') {
      unawaited(_handleLocationRequest(event.data));
      return;
    }

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

  /// Respond to a `request_ios_calendar` packet from the backend.
  ///
  /// Queries EKEventStore on-device, then publishes the result back on the
  /// `ios_calendar_result` topic so the backend's [query_ios_calendar] tool
  /// can resolve and return event data to the LLM.
  Future<void> _handleCalendarRequest(Uint8List data) async {
    if (!SiriIntentBridge.isAvailable) return;

    try {
      final params = jsonDecode(utf8.decode(data)) as Map<String, dynamic>;
      final startStr = params['start_date'] as String?;
      final endStr = params['end_date'] as String?;

      final result = await SiriIntentBridge.dispatchCalendarQuery(
        startDate: (startStr?.isNotEmpty == true) ? DateTime.tryParse(startStr!) : null,
        endDate: (endStr?.isNotEmpty == true) ? DateTime.tryParse(endStr!) : null,
      );

      final payload = utf8.encode(jsonEncode({
        'success': result.success,
        'message': result.message,
        'events': result.events,
      }));

      await room.localParticipant?.publishData(
        payload,
        options: const sdk.DataPublishOptions(
          reliable: true,
          topic: 'ios_calendar_result',
        ),
      );

      _setExecutionMessage(result.message);
    } catch (error) {
      debugPrint('[ToolStatusCtrl] Calendar request failed: $error');
    }
  }

  /// Respond to a `request_ios_contacts` packet from the backend.
  Future<void> _handleContactsRequest(Uint8List data) async {
    if (!SiriIntentBridge.isAvailable) return;

    try {
      final params = jsonDecode(utf8.decode(data)) as Map<String, dynamic>;
      final name = params['name'] as String? ?? '';

      final result = await SiriIntentBridge.queryContacts(name: name);

      final payload = utf8.encode(jsonEncode({
        'success': result.success,
        'message': result.message,
      }));

      await room.localParticipant?.publishData(
        payload,
        options: const sdk.DataPublishOptions(
          reliable: true,
          topic: 'ios_contacts_result',
        ),
      );

      _setExecutionMessage(result.message);
    } catch (error) {
      debugPrint('[ToolStatusCtrl] Contacts request failed: $error');
    }
  }

  /// Respond to a `request_ios_directions` packet from the backend.
  Future<void> _handleDirectionsRequest(Uint8List data) async {
    if (!SiriIntentBridge.isAvailable) return;

    try {
      final params = jsonDecode(utf8.decode(data)) as Map<String, dynamic>;
      final destination = params['destination'] as String? ?? '';
      final transportType = params['transport_type'] as String? ?? 'driving';

      final result = await SiriIntentBridge.queryDirections(
        destination: destination,
        transportType: transportType,
      );

      final payload = utf8.encode(jsonEncode({
        'success': result.success,
        'message': result.message,
        'destinationName': result.success ? (result.message.contains('Directions') ? destination : null) : null,
      }));

      await room.localParticipant?.publishData(
        payload,
        options: const sdk.DataPublishOptions(
          reliable: true,
          topic: 'ios_directions_result',
        ),
      );

      _setExecutionMessage(result.message);
    } catch (error) {
      debugPrint('[ToolStatusCtrl] Directions request failed: $error');
    }
  }

  /// Respond to a `request_ios_location` packet from the backend.
  Future<void> _handleLocationRequest(Uint8List data) async {
    if (!SiriIntentBridge.isAvailable) return;

    try {
      final result = await SiriIntentBridge.queryLocation();

      final payload = utf8.encode(jsonEncode({
        'success': result.success,
        'message': result.message,
      }));

      await room.localParticipant?.publishData(
        payload,
        options: const sdk.DataPublishOptions(
          reliable: true,
          topic: 'ios_location_result',
        ),
      );

      _setExecutionMessage(result.message);
    } catch (error) {
      debugPrint('[ToolStatusCtrl] Location request failed: $error');
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
      } else if (_isMessageTool(toolName, toolParams)) {
        _handledIntentFingerprints.add(fingerprint);
        await _dispatchMessage(toolParams);
      } else if (_isPhoneCallTool(toolName, toolParams)) {
        _handledIntentFingerprints.add(fingerprint);
        await _dispatchPhoneCall(toolParams);
      }
      // Note: query_ios_calendar, query_ios_contacts, query_ios_directions,
      // and query_ios_location are handled via request/response data channels,
      // not through tool_status detection.
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

  bool _isMessageTool(String toolName, Map<String, dynamic> params) {
    return toolName.contains('message') ||
        toolName.contains('sms') ||
        toolName.contains('imessage') ||
        toolName.contains('text') && (params.containsKey('recipient') || params.containsKey('to')) ||
        params.containsKey('recipient');
  }

  bool _isPhoneCallTool(String toolName, Map<String, dynamic> params) {
    return toolName.contains('phone') ||
        toolName.contains('call') ||
        toolName.contains('dial') ||
        params.containsKey('phone_number') ||
        params.containsKey('phoneNumber');
  }

  Future<void> _dispatchMessage(Map<String, dynamic> params) async {
    final recipient = (params['recipient'] ?? params['to'] ?? params['phone'] ?? params['contact'] ?? '')
        .toString()
        .trim();
    final body = (params['body'] ?? params['message'] ?? params['text'] ?? '').toString().trim();

    if (recipient.isEmpty) {
      _setExecutionMessage('Message request skipped: missing recipient.');
      return;
    }
    if (body.isEmpty) {
      _setExecutionMessage('Message request skipped: missing body.');
      return;
    }

    final result = await SiriIntentBridge.dispatchMessage(recipient: recipient, body: body);
    _setExecutionMessage(result.message);
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

  Future<void> _dispatchPhoneCall(Map<String, dynamic> params) async {
    final phoneNumber = (params['phone_number'] ?? params['phoneNumber'] ?? params['number'] ?? '')
        .toString()
        .trim();
    if (phoneNumber.isEmpty) {
      _setExecutionMessage('Phone call request skipped: missing phone number.');
      return;
    }

    final result = await SiriIntentBridge.makePhoneCall(phoneNumber: phoneNumber);
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
