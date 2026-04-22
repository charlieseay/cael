import { NextResponse } from 'next/server';

const WEBHOOK_URL = process.env.WEBHOOK_URL || 'http://agent:8889';

export async function GET() {
  try {
    const res = await fetch(`${WEBHOOK_URL}/assistant/avatar`);
    if (!res.ok) return NextResponse.json({ error: 'Not found' }, { status: 404 });
    const blob = await res.blob();
    return new Response(blob, {
      headers: { 'Content-Type': res.headers.get('Content-Type') ?? 'image/jpeg' },
    });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
