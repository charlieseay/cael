import 'dart:io';

import 'package:flutter/services.dart';

enum SiriBridgeIntentType { reminder, navigation, calendarQuery, message, contactsQuery, directionsQuery, locationQuery, phoneCall }

class SiriDispatchResult {
  final bool success;
  final String message;
  final SiriBridgeIntentType intentType;

  /// Structured event data for calendarQuery results.
  /// Each map contains: title, start, end, calendar, isAllDay, and
  /// optionally location — matching the keys returned by AppDelegate.
  final List<Map<String, dynamic>> events;

  /// Structured contact data for contactsQuery results.
  /// Each map contains: name, phoneNumbers, emailAddresses.
  final List<Map<String, dynamic>> contacts;

  /// Additional data from capability response (directions, location, etc).
  final Map<String, dynamic> data;

  const SiriDispatchResult({
    required this.success,
    required this.message,
    required this.intentType,
    this.events = const [],
    this.contacts = const [],
    this.data = const {},
  });
}

class SiriIntentBridge {
  static const MethodChannel _channel = MethodChannel('cael/siri_intent_bridge');

  static bool get isAvailable => Platform.isIOS;

  /// Generic capability invoker — add new capabilities without changing the channel.
  static Future<Map<String, dynamic>> invokeCapability(
    String capability,
    Map<String, dynamic> params,
  ) async {
    if (!isAvailable) {
      return {
        'success': false,
        'message': 'Capability is only available on iOS.',
      };
    }
    try {
      final result = await _channel.invokeMethod<Map>(capability, params);
      return Map<String, dynamic>.from(result ?? {});
    } on PlatformException catch (e) {
      return {
        'success': false,
        'message': 'Platform exception: ${e.message}',
      };
    }
  }

  // Typed convenience wrappers — all call invokeCapability internally

  static Future<SiriDispatchResult> createReminder({
    required String title,
    DateTime? dueDate,
    String? notes,
  }) async {
    final result = await invokeCapability('reminder_create', {
      'title': title,
      'dueDate': dueDate?.toIso8601String(),
      'notes': notes,
    });
    return _parseResult(result, SiriBridgeIntentType.reminder);
  }

  static Future<SiriDispatchResult> navigateTo({
    required String destination,
  }) async {
    final result = await invokeCapability('directions_navigate', {
      'destination': destination,
    });
    return _parseResult(result, SiriBridgeIntentType.navigation);
  }

  /// Query calendar events in a date range. [startDate] defaults to now,
  /// [endDate] defaults to 24 hours from now when not provided.
  static Future<SiriDispatchResult> queryCalendar({
    DateTime? startDate,
    DateTime? endDate,
  }) async {
    final result = await invokeCapability('calendar_query', {
      'startDate': (startDate ?? DateTime.now()).toIso8601String(),
      'endDate': (endDate ?? DateTime.now().add(const Duration(hours: 24))).toIso8601String(),
    });
    return _parseResult(result, SiriBridgeIntentType.calendarQuery);
  }

  /// Open the Messages app with a pre-filled recipient and body.
  /// The user must tap Send — iOS provides no silent background send API.
  static Future<SiriDispatchResult> sendMessage({
    required String recipient,
    required String body,
  }) async {
    final result = await invokeCapability('message_send', {
      'recipient': recipient,
      'body': body,
    });
    return _parseResult(result, SiriBridgeIntentType.message);
  }

  /// Query contacts by name. Returns matching contacts with phone numbers and email addresses.
  static Future<SiriDispatchResult> queryContacts({
    required String name,
  }) async {
    final result = await invokeCapability('contacts_query', {
      'name': name,
    });
    return _parseResult(result, SiriBridgeIntentType.contactsQuery);
  }

  /// Query travel time and distance to a destination.
  /// [transportType] can be "driving" (default) or "walking".
  static Future<SiriDispatchResult> queryDirections({
    required String destination,
    String transportType = 'driving',
  }) async {
    final result = await invokeCapability('directions_query', {
      'destination': destination,
      'transport_type': transportType,
    });
    return _parseResult(result, SiriBridgeIntentType.directionsQuery);
  }

  /// Get the user's current location as coordinates and address.
  static Future<SiriDispatchResult> queryLocation() async {
    final result = await invokeCapability('location_query', {});
    return _parseResult(result, SiriBridgeIntentType.locationQuery);
  }

  /// Initiate a phone call on the user's iPhone.
  static Future<SiriDispatchResult> makePhoneCall({
    required String phoneNumber,
  }) async {
    final result = await invokeCapability('phone_call', {
      'phone_number': phoneNumber,
    });
    return _parseResult(result, SiriBridgeIntentType.phoneCall);
  }

  // Legacy method names for backward compatibility
  static Future<SiriDispatchResult> dispatchReminder({
    required String title,
    DateTime? dueDate,
    String? notes,
  }) => createReminder(title: title, dueDate: dueDate, notes: notes);

  static Future<SiriDispatchResult> dispatchNavigation({
    required String destination,
  }) => navigateTo(destination: destination);

  static Future<SiriDispatchResult> dispatchCalendarQuery({
    DateTime? startDate,
    DateTime? endDate,
  }) => queryCalendar(startDate: startDate, endDate: endDate);

  static Future<SiriDispatchResult> dispatchMessage({
    required String recipient,
    required String body,
  }) => sendMessage(recipient: recipient, body: body);

  static Future<SiriDispatchResult> dispatchContactsQuery({
    required String name,
  }) => queryContacts(name: name);

  static Future<SiriDispatchResult> dispatchDirectionsQuery({
    required String destination,
    String transportType = 'driving',
  }) => queryDirections(destination: destination, transportType: transportType);

  static Future<SiriDispatchResult> dispatchLocationQuery() => queryLocation();

  static Future<SiriDispatchResult> dispatchPhoneCall({
    required String phoneNumber,
  }) => makePhoneCall(phoneNumber: phoneNumber);

  static SiriDispatchResult _parseResult(
    Map<String, dynamic> result,
    SiriBridgeIntentType intentType,
  ) {
    final success = result['success'] as bool? ?? false;
    final message = result['message'] as String? ?? 'Intent dispatch completed.';

    final events = <Map<String, dynamic>>[];
    final rawEvents = result['events'];
    if (rawEvents is List) {
      for (final item in rawEvents) {
        if (item is Map) {
          events.add(Map<String, dynamic>.from(item));
        }
      }
    }

    final contacts = <Map<String, dynamic>>[];
    final rawContacts = result['contacts'];
    if (rawContacts is List) {
      for (final item in rawContacts) {
        if (item is Map) {
          contacts.add(Map<String, dynamic>.from(item));
        }
      }
    }

    final data = Map<String, dynamic>.from(result);
    data.removeWhere((k, _) => ['success', 'message', 'events', 'contacts'].contains(k));

    return SiriDispatchResult(
      success: success,
      message: message,
      intentType: intentType,
      events: events,
      contacts: contacts,
      data: data,
    );
  }
}
