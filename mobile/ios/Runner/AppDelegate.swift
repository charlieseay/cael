import Flutter
import Intents
import MapKit
import EventKit
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate {
    private let siriBridgeChannelName = "cael/siri_intent_bridge"
    private let eventStore = EKEventStore()

    override func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
    ) -> Bool {
        GeneratedPluginRegistrant.register(with: self)
        if let controller = window?.rootViewController as? FlutterViewController {
            let channel = FlutterMethodChannel(
                name: siriBridgeChannelName,
                binaryMessenger: controller.binaryMessenger
            )
            channel.setMethodCallHandler { [weak self] call, result in
                self?.handleSiriBridgeMethodCall(call: call, result: result)
            }
        }
        return super.application(application, didFinishLaunchingWithOptions: launchOptions)
    }

    private func handleSiriBridgeMethodCall(call: FlutterMethodCall, result: @escaping FlutterResult) {
        guard let args = call.arguments as? [String: Any] else {
            result(["success": false, "message": "Invalid method arguments."])
            return
        }

        switch call.method {
        case "dispatchReminder":
            dispatchReminder(arguments: args, result: result)
        case "dispatchNavigation":
            dispatchNavigation(arguments: args, result: result)
        default:
            result(FlutterMethodNotImplemented)
        }
    }

    private func dispatchReminder(arguments: [String: Any], result: @escaping FlutterResult) {
        guard let title = arguments["title"] as? String, !title.isEmpty else {
            result(["success": false, "message": "Reminder title is required."])
            return
        }

        requestReminderAccessIfNeeded { [weak self] granted in
            guard granted, let self = self else {
                result(["success": false, "message": "Reminders permission denied."])
                return
            }

            let dueDateString = arguments["dueDate"] as? String
            let dueDate = dueDateString.flatMap { ISO8601DateFormatter().date(from: $0) }
            let notes = arguments["notes"] as? String

            let reminder = EKReminder(eventStore: self.eventStore)
            reminder.title = title
            reminder.notes = notes
            reminder.calendar = self.eventStore.defaultCalendarForNewReminders()
            if let dueDate = dueDate {
                reminder.dueDateComponents = Calendar.current.dateComponents(
                    [.year, .month, .day, .hour, .minute],
                    from: dueDate
                )
            }

            do {
                try self.eventStore.save(reminder, commit: true)

                // Donate the intent so Siri learns this in-app action.
                let intent = INAddTasksIntent(
                    targetTaskList: nil,
                    taskTitles: [INSpeakableString(spokenPhrase: title)],
                    spatialEventTrigger: nil,
                    temporalEventTrigger: nil,
                    priority: nil
                )
                let interaction = INInteraction(intent: intent, response: nil)
                interaction.donate(completion: nil)

                result([
                    "success": true,
                    "message": "Reminder created: \(title)."
                ])
            } catch {
                result([
                    "success": false,
                    "message": "Failed to create reminder: \(error.localizedDescription)"
                ])
            }
        }
    }

    private func dispatchNavigation(arguments: [String: Any], result: @escaping FlutterResult) {
        guard let destination = arguments["destination"] as? String, !destination.isEmpty else {
            result(["success": false, "message": "Navigation destination is required."])
            return
        }

        let request = MKLocalSearch.Request()
        request.naturalLanguageQuery = destination

        MKLocalSearch(request: request).start { [weak self] searchResponse, error in
            guard let self = self else {
                result(["success": false, "message": "Navigation handler unavailable."])
                return
            }
            if let error = error {
                result([
                    "success": false,
                    "message": "Unable to resolve destination: \(error.localizedDescription)"
                ])
                return
            }

            guard let mapItem = searchResponse?.mapItems.first else {
                result(["success": false, "message": "No matching destination found for \(destination)."])
                return
            }

            let intent = INGetDirectionsIntent(
                source: nil,
                destination: INPlacemark(
                    placemark: mapItem.placemark,
                    name: mapItem.name
                ),
                routeType: .driving
            )
            let interaction = INInteraction(intent: intent, response: nil)
            interaction.donate(completion: nil)

            mapItem.openInMaps(launchOptions: [
                MKLaunchOptionsDirectionsModeKey: MKLaunchOptionsDirectionsModeDriving
            ])

            result([
                "success": true,
                "message": "Navigation started to \(mapItem.name ?? destination)."
            ])
        }
    }

    private func requestReminderAccessIfNeeded(completion: @escaping (Bool) -> Void) {
        let status = EKEventStore.authorizationStatus(for: .reminder)
        if #available(iOS 17.0, *) {
            if status == .fullAccess || status == .writeOnly {
                completion(true)
                return
            }
        } else if status == .authorized {
            completion(true)
            return
        }

        switch status {
        case .notDetermined:
            if #available(iOS 17.0, *) {
                eventStore.requestFullAccessToReminders { granted, _ in
                    DispatchQueue.main.async {
                        completion(granted)
                    }
                }
            } else {
                eventStore.requestAccess(to: .reminder) { granted, _ in
                    DispatchQueue.main.async {
                        completion(granted)
                    }
                }
            }
        case .restricted, .denied:
            completion(false)
        default:
            completion(false)
        }
    }
}
