import 'package:livekit_client/livekit_client.dart' as sdk;
import 'package:livekit_components/livekit_components.dart' as lk_components;

// Ext for Participant
extension ParticipantAgentExt on sdk.Participant {
  bool get isAgent {
    // Some sessions report AGENT via identity/attributes before kind settles.
    final identityLower = identity.toLowerCase();
    final role = (attributes['role'] ?? attributes['participant_role'] ?? '')
        .toString()
        .toLowerCase();
    final lkKind = (attributes['lk.kind'] ?? attributes['kind'] ?? '')
        .toString()
        .toLowerCase();
    return kind == sdk.ParticipantKind.AGENT ||
        identityLower.startsWith('agent-') ||
        role == 'agent' ||
        lkKind == 'agent';
  }

  sdk.AgentAttributes get agentAttributes => sdk.AgentAttributes.fromJson(attributes);
  sdk.AgentState? get agentState => agentAttributes.lkAgentState;
}

// Ext for RoomContext
extension RoomContextAgentExt on lk_components.RoomContext {
  sdk.Participant? get agentParticipant => participants.where((p) => p.isAgent).firstOrNull;
}

// Ext for ParticipantContext
extension ParticipantContextAgentExt on lk_components.ParticipantContext {
  sdk.AgentAttributes get agentAttributes => sdk.AgentAttributes.fromJson(attributes);
  sdk.AgentState? get agentState => agentAttributes.lkAgentState;
}
