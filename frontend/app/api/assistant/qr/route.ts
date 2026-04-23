import { NextRequest, NextResponse } from 'next/server';
import QRCode from 'qrcode';

const WEBHOOK_URL = process.env.WEBHOOK_URL || 'http://agent:8889';

export async function GET(request: NextRequest) {
  try {
    const settingsRes = await fetch(`${WEBHOOK_URL}/settings`);
    const settings = settingsRes.ok ? await settingsRes.json() : {};
    const localUrl: string = settings.client_connection_url || request.nextUrl.origin;
    const externalUrl: string = request.nextUrl.searchParams.get('external') ?? '';
    const apiKey: string = process.env.CAAL_API_KEY ?? '';

    const params = new URLSearchParams({ local: localUrl, key: apiKey });
    if (externalUrl) params.set('external', externalUrl);
    const qrData = `sonique://connect?${params.toString()}`;

    const dataUrl: string = await QRCode.toDataURL(qrData, {
      width: 300,
      margin: 2,
      color: { dark: '#000000', light: '#ffffff' },
    });

    const base64 = dataUrl.split(',')[1];
    const buffer = Buffer.from(base64, 'base64');

    return new Response(buffer, {
      headers: {
        'Content-Type': 'image/png',
        'Cache-Control': 'no-store',
      },
    });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
