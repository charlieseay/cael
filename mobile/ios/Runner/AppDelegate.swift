import Flutter
import Intents
import MapKit
import EventKit
import MessageUI
import UIKit
import Contacts
import CoreLocation
import AVFoundation
import MediaPlayer

@main
@objc class AppDelegate: FlutterAppDelegate, MFMessageComposeViewControllerDelegate, CLLocationManagerDelegate {
    private let siriBridgeChannelName = "cael/siri_intent_bridge"
    private let eventStore = EKEventStore()
    private let locationManager = CLLocationManager()

    // Retained across the async MFMessageComposeViewController flow.
    private var pendingMessageResult: FlutterResult?

    // Location manager state for async completion
    private var pendingLocationResult: FlutterResult?
    private var currentLocation: CLLocationCoordinate2D?

    override func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
    ) -> Bool {
        GeneratedPluginRegistrant.register(with: self)
        locationManager.delegate = self
        if let controller = window?.rootViewController as? FlutterViewController {
            let channel = FlutterMethodChannel(
                name: siriBridgeChannelName,
                binaryMessenger: controller.binaryMessenger
            )
            channel.setMethodCallHandler { [weak self] call, result in
                self?.handleCapability(call.method, arguments: call.arguments as? [String: Any] ?? [:], result: result)
            }
        }
        return super.application(application, didFinishLaunchingWithOptions: launchOptions)
    }

    private func handleCapability(_ name: String, arguments: [String: Any], result: @escaping FlutterResult) {
        switch name {
        case "reminder_create":
            dispatchReminder(arguments: arguments, result: result)
        case "directions_navigate":
            dispatchNavigation(arguments: arguments, result: result)
        case "calendar_query":
            dispatchCalendarQuery(arguments: arguments, result: result)
        case "message_send":
            dispatchMessage(arguments: arguments, result: result)
        case "contacts_query":
            dispatchContactsQuery(arguments: arguments, result: result)
        case "directions_query":
            dispatchDirectionsQuery(arguments: arguments, result: result)
        case "location_query":
            dispatchLocationQuery(arguments: arguments, result: result)
        case "phone_call":
            dispatchPhoneCall(arguments: arguments, result: result)
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

            // Maps is not opened here — the user stays in the conversation.
            // The agent reports the resolved destination; the user can start
            // navigation after the conversation ends.
            result([
                "success": true,
                "message": "Navigation ready for \(mapItem.name ?? destination). Open Maps when you're ready to go."
            ])
        }
    }

    private func dispatchCalendarQuery(arguments: [String: Any], result: @escaping FlutterResult) {
        let formatter = ISO8601DateFormatter()
        let startDate = (arguments["startDate"] as? String).flatMap { formatter.date(from: $0) } ?? Date()
        let endDate = (arguments["endDate"] as? String).flatMap { formatter.date(from: $0) }
            ?? startDate.addingTimeInterval(86400)

        let requestCalendarAccess: (@escaping (Bool) -> Void) -> Void = { completion in
            let status = EKEventStore.authorizationStatus(for: .event)
            if #available(iOS 17.0, *) {
                if status == .fullAccess {
                    completion(true)
                    return
                }
            } else if status == .authorized {
                completion(true)
                return
            }
            if status == .notDetermined {
                if #available(iOS 17.0, *) {
                    self.eventStore.requestFullAccessToEvents { granted, _ in
                        DispatchQueue.main.async { completion(granted) }
                    }
                } else {
                    self.eventStore.requestAccess(to: .event) { granted, _ in
                        DispatchQueue.main.async { completion(granted) }
                    }
                }
            } else {
                completion(false)
            }
        }

        requestCalendarAccess { [weak self] granted in
            guard granted, let self = self else {
                result(["success": false, "message": "Calendar permission denied."])
                return
            }

            let predicate = self.eventStore.predicateForEvents(
                withStart: startDate,
                end: endDate,
                calendars: nil
            )
            let events = self.eventStore.events(matching: predicate)
                .sorted { $0.startDate < $1.startDate }

            if events.isEmpty {
                let rangeDesc = self.formatDateRange(start: startDate, end: endDate)
                result(["success": true, "message": "No events found \(rangeDesc)."])
                return
            }

            let displayFmt = DateFormatter()
            displayFmt.dateStyle = .none
            displayFmt.timeStyle = .short

            let summary = events.enumerated().map { (i, e) in
                let time = displayFmt.string(from: e.startDate)
                return "(\(i + 1)) \(e.title ?? "Untitled") at \(time)"
            }.joined(separator: ", ")

            let rangeDesc = self.formatDateRange(start: startDate, end: endDate)
            result([
                "success": true,
                "message": "\(events.count) event\(events.count == 1 ? "" : "s") \(rangeDesc): \(summary)."
            ])
        }
    }

    private func formatDateRange(start: Date, end: Date) -> String {
        let cal = Calendar.current
        let fmt = DateFormatter()
        fmt.dateStyle = .medium
        fmt.timeStyle = .none
        if cal.isDateInToday(start) && cal.isDateInToday(end) {
            return "today"
        }
        if cal.isDateInTomorrow(start) && cal.isDateInTomorrow(end) {
            return "tomorrow"
        }
        return "from \(fmt.string(from: start)) to \(fmt.string(from: end))"
    }

    private func dispatchMessage(arguments: [String: Any], result: @escaping FlutterResult) {
        guard MFMessageComposeViewController.canSendText() else {
            result(["success": false, "message": "Messages is not available on this device."])
            return
        }

        let recipient = arguments["recipient"] as? String ?? ""
        let body = arguments["body"] as? String ?? ""

        guard let rootVC = window?.rootViewController else {
            result(["success": false, "message": "No root view controller available."])
            return
        }

        let composer = MFMessageComposeViewController()
        if !recipient.isEmpty { composer.recipients = [recipient] }
        composer.body = body
        composer.messageComposeDelegate = self
        // Hold onto the result callback — MFMessageComposeViewControllerDelegate
        // calls back asynchronously after the user sends or cancels.
        pendingMessageResult = result

        DispatchQueue.main.async {
            rootVC.present(composer, animated: true)
        }
    }

    // MFMessageComposeViewControllerDelegate
    func messageComposeViewController(
        _ controller: MFMessageComposeViewController,
        didFinishWith result: MessageComposeResult
    ) {
        controller.dismiss(animated: true)
        let (success, message): (Bool, String) = {
            switch result {
            case .sent:      return (true,  "Message sent.")
            case .cancelled: return (false, "Message cancelled.")
            case .failed:    return (false, "Failed to send message.")
            @unknown default: return (false, "Unknown compose result.")
            }
        }()
        pendingMessageResult?(["success": success, "message": message])
        pendingMessageResult = nil
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

    // MARK: - Contacts Lookup

    private func dispatchContactsQuery(arguments: [String: Any], result: @escaping FlutterResult) {
        guard let name = arguments["name"] as? String, !name.isEmpty else {
            result(["success": false, "message": "Contact name is required."])
            return
        }

        let status = CNContactStore.authorizationStatus(for: .contacts)
        if status == .denied || status == .restricted {
            result(["success": false, "message": "Contacts permission denied."])
            return
        }

        let store = CNContactStore()
        if status == .notDetermined {
            store.requestAccess(for: .contacts) { [weak self] granted, _ in
                guard granted else {
                    DispatchQueue.main.async {
                        result(["success": false, "message": "Contacts permission denied."])
                    }
                    return
                }
                DispatchQueue.main.async {
                    self?.queryContactsWithName(name, store: store, result: result)
                }
            }
        } else {
            queryContactsWithName(name, store: store, result: result)
        }
    }

    private func queryContactsWithName(_ name: String, store: CNContactStore, result: @escaping FlutterResult) {
        let predicate = CNContact.predicateForContacts(matching: CNContactFormatter.descriptorForRequiredKeys(for: .fullName))
        do {
            let contacts = try store.unifiedContacts(matching: predicate)
            let keysToFetch = [
                CNContactGivenNameKey,
                CNContactFamilyNameKey,
                CNContactPhoneNumbersKey,
                CNContactEmailAddressesKey
            ] as [CNKeyDescriptor]

            let filtered = contacts.filter { contact in
                let fullName = CNContactFormatter.string(from: contact, style: .fullName) ?? ""
                return fullName.lowercased().contains(name.lowercased())
            }

            let results = filtered.map { contact -> [String: Any] in
                let phones = contact.phoneNumbers.map { label, number in
                    [
                        "label": CNLabeledValue<CNPhoneNumber>.localizedString(forLabel: label) ?? "Phone",
                        "value": number.stringValue
                    ]
                }
                let emails = contact.emailAddresses.map { label, email in
                    [
                        "label": CNLabeledValue<NSString>.localizedString(forLabel: label) ?? "Email",
                        "value": email
                    ]
                }
                return [
                    "name": CNContactFormatter.string(from: contact, style: .fullName) ?? "Unknown",
                    "phoneNumbers": phones,
                    "emailAddresses": emails
                ]
            }

            result([
                "success": true,
                "message": "Found \(results.count) contact(s).",
                "contacts": results
            ])
        } catch {
            result([
                "success": false,
                "message": "Failed to query contacts: \(error.localizedDescription)"
            ])
        }
    }

    // MARK: - Directions Query (Travel Time & Distance)

    private func dispatchDirectionsQuery(arguments: [String: Any], result: @escaping FlutterResult) {
        guard let destination = arguments["destination"] as? String, !destination.isEmpty else {
            result(["success": false, "message": "Destination is required."])
            return
        }

        let transportType = (arguments["transport_type"] as? String ?? "driving").lowercased()
        let requestType: MKDirectionsTransportType = transportType.contains("walk") ? .walking : .automobile

        let request = MKLocalSearch.Request()
        request.naturalLanguageQuery = destination

        MKLocalSearch(request: request).start { [weak self] searchResponse, error in
            guard let self = self else {
                result(["success": false, "message": "Search handler unavailable."])
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
                result(["success": false, "message": "No destination found for '\(destination)'."])
                return
            }

            let directionsRequest = MKDirections.Request()
            directionsRequest.source = MKMapItem.forCurrentLocation()
            directionsRequest.destination = mapItem
            directionsRequest.transportType = requestType

            MKDirections(request: directionsRequest).calculateETA { [weak self] response, error in
                guard let self = self else {
                    result(["success": false, "message": "Directions handler unavailable."])
                    return
                }

                if let error = error {
                    result([
                        "success": false,
                        "message": "Failed to calculate directions: \(error.localizedDescription)"
                    ])
                    return
                }

                guard let response = response else {
                    result([
                        "success": false,
                        "message": "No route found."
                    ])
                    return
                }

                result([
                    "success": true,
                    "message": "Directions calculated.",
                    "destinationName": mapItem.name ?? destination,
                    "distanceMeters": Int(response.distance),
                    "travelTimeSeconds": Int(response.expectedTravelTime),
                    "transportType": transportType
                ])
            }
        }
    }

    // MARK: - Location Query

    private func dispatchLocationQuery(arguments: [String: Any], result: @escaping FlutterResult) {
        let status = CLLocationManager.authorizationStatus()
        if status == .denied || status == .restricted {
            result([
                "success": false,
                "message": "Location permission denied."
            ])
            return
        }

        if status == .notDetermined {
            pendingLocationResult = result
            locationManager.requestWhenInUseAuthorization()
            return
        }

        if let location = locationManager.location {
            reverseGeocodeLocation(location, result: result)
        } else {
            pendingLocationResult = result
            locationManager.startUpdatingLocation()
        }
    }

    private func reverseGeocodeLocation(_ location: CLLocation, result: @escaping FlutterResult) {
        let geocoder = CLGeocoder()
        geocoder.reverseGeocodeLocation(location) { placemarks, error in
            if let error = error {
                result([
                    "success": false,
                    "message": "Failed to reverse geocode: \(error.localizedDescription)"
                ])
                return
            }

            let address = placemarks?.first.map { placemark in
                var components = [String]()
                if let street = placemark.thoroughfare { components.append(street) }
                if let city = placemark.locality { components.append(city) }
                if let state = placemark.administrativeArea { components.append(state) }
                return components.joined(separator: ", ")
            } ?? "Unknown"

            result([
                "success": true,
                "message": "Location retrieved.",
                "latitude": location.coordinate.latitude,
                "longitude": location.coordinate.longitude,
                "address": address
            ])
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }
        manager.stopUpdatingLocation()

        if let result = pendingLocationResult {
            reverseGeocodeLocation(location, result: result)
            pendingLocationResult = nil
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        if let result = pendingLocationResult {
            result([
                "success": false,
                "message": "Location request failed: \(error.localizedDescription)"
            ])
            pendingLocationResult = nil
        }
    }

    // MARK: - Phone Call

    private func dispatchPhoneCall(arguments: [String: Any], result: @escaping FlutterResult) {
        guard let phoneNumber = arguments["phone_number"] as? String, !phoneNumber.isEmpty else {
            result(["success": false, "message": "Phone number is required."])
            return
        }

        guard let url = URL(string: "tel://\(phoneNumber)") else {
            result([
                "success": false,
                "message": "Invalid phone number format."
            ])
            return
        }

        UIApplication.shared.open(url) { success in
            result([
                "success": success,
                "message": success ? "Calling \(phoneNumber)." : "Failed to initiate call."
            ])
        }
    }
}
