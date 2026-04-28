import { NextResponse } from 'next/server';
import { AccessToken, type AccessTokenOptions, type VideoGrant } from 'livekit-server-sdk';
import { RoomConfiguration } from '@livekit/protocol';

type ConnectionDetails = {
  serverUrl: string;
  roomName: string;
  participantName: string;
  participantToken: string;
};

// NOTE: you are expected to define the following environment variables in `.env.local`:
const API_KEY = process.env.LIVEKIT_API_KEY;
const API_SECRET = process.env.LIVEKIT_API_SECRET;
// Internal URL for token generation (Docker network or localhost)
const LIVEKIT_URL = process.env.LIVEKIT_URL;
// External URL for browser connection (set to 'auto' for dynamic detection)
const LIVEKIT_PUBLIC_URL = process.env.NEXT_PUBLIC_LIVEKIT_URL;

// don't cache the results
export const revalidate = 0;

// Optional pre-shared key for iOS/external clients — set CAAL_API_KEY env var to enable
const CAAL_API_KEY = process.env.CAAL_API_KEY;

export async function POST(req: Request) {
  try {
    if (LIVEKIT_URL === undefined) {
      throw new Error('LIVEKIT_URL is not defined');
    }
    if (API_KEY === undefined) {
      throw new Error('LIVEKIT_API_KEY is not defined');
    }
    if (API_SECRET === undefined) {
      throw new Error('LIVEKIT_API_SECRET is not defined');
    }

    // API key check — only enforced when CAAL_API_KEY is set
    if (CAAL_API_KEY) {
      const provided = req.headers.get('x-api-key');
      if (provided !== CAAL_API_KEY) {
        return new NextResponse('Unauthorized', { status: 401 });
      }
    }

    // Parse agent configuration from request body
    const body = await req.json().catch(() => ({}));
    const agentName: string = body?.room_config?.agents?.[0]?.agent_name;
    // extended_session: true → 4-hour token TTL (for Siri/wake-word triggered sessions)
    const extendedSession: boolean = body?.extended_session === true;

    // Generate participant token
    // Fixed room name - all devices share the same room/agent session
    // This prevents orphaned agent jobs from accumulating on reconnect
    const participantName = 'user';
    const participantIdentity = `voice_assistant_user_${Math.floor(Math.random() * 10_000)}`;
    const roomName = 'voice_assistant_room';

    const participantToken = await createParticipantToken(
      { identity: participantIdentity, name: participantName },
      roomName,
      agentName,
      extendedSession,
    );

    // Determine the WebSocket URL for the client.
    // If NEXT_PUBLIC_LIVEKIT_URL is configured, always honor it so
    // Tailscale/distributed clients do not get downgraded to ws://host:7880.
    // Otherwise derive ws:// from request host for local LAN/dev.
    let serverUrl: string;
    const configuredPublicUrl =
      LIVEKIT_PUBLIC_URL && LIVEKIT_PUBLIC_URL !== 'auto' ? LIVEKIT_PUBLIC_URL : '';
    if (configuredPublicUrl) {
      serverUrl = configuredPublicUrl;
    } else {
      // Derive ws:// from request host for LAN/mobile access
      const host = req.headers.get('host') || 'localhost';
      const hostname = host.split(':')[0]; // Remove port if present
      serverUrl = `ws://${hostname}:7880`;
    }

    // Return connection details
    const data: ConnectionDetails = {
      serverUrl,
      roomName,
      participantToken: participantToken,
      participantName,
    };
    const headers = new Headers({
      'Cache-Control': 'no-store',
    });
    return NextResponse.json(data, { headers });
  } catch (error) {
    if (error instanceof Error) {
      console.error(error);
      return new NextResponse(error.message, { status: 500 });
    }
  }
}

function createParticipantToken(
  userInfo: AccessTokenOptions,
  roomName: string,
  agentName?: string,
  extendedSession = false,
): Promise<string> {
  const at = new AccessToken(API_KEY, API_SECRET, {
    ...userInfo,
    ttl: extendedSession ? '4h' : '15m',
  });
  const grant: VideoGrant = {
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canPublishData: true,
    canSubscribe: true,
  };
  at.addGrant(grant);

  // Keep the room alive long enough for mobile network jitter/reconnect.
  // 1s caused room teardown before agent replies finished.
  at.roomConfig = new RoomConfiguration({
    departureTimeout: 45,
    ...(agentName && { agents: [{ agentName }] }),
  });

  return at.toJwt();
}
