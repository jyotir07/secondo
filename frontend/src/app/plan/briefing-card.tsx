"use client";

import { Volume2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, Card, ErrorState, Loading } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useApi } from "@/lib/use-api";

interface Briefing {
  text: string;
  voice_available: boolean;
}

export function BriefingCard({ planId }: { planId: string }) {
  const briefing = useApi<Briefing>(`/kitchen-plans/${planId}/briefing`);
  const [audioUrl, setAudioUrl] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();

  useEffect(() => () => { if (audioUrl) URL.revokeObjectURL(audioUrl); }, [audioUrl]);

  async function play() {
    setLoading(true);
    setError(undefined);
    try {
      const res = await fetch(`/api/kitchen-plans/${planId}/briefing/audio`, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new ApiError(body?.detail ?? `Voice briefing failed (${res.status}).`, res.status);
      }
      setAudioUrl(URL.createObjectURL(await res.blob()));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card
      title="Voice briefing"
      description="Read aloud for the kitchen. Only quantities and dietary labels are sent to ElevenLabs, never customer names or notes."
      actions={<Volume2 className="size-5 text-sage" aria-hidden />}
    >
      {briefing.loading && !briefing.data ? (
        <Loading />
      ) : briefing.error ? (
        <ErrorState message={briefing.error} onRetry={briefing.reload} />
      ) : briefing.data && (
        <>
          {briefing.data.voice_available ? (
            audioUrl ? (
              <audio controls autoPlay src={audioUrl} className="w-full" />
            ) : (
              <Button onClick={play} busy={loading} icon={<Volume2 className="size-4" />}>
                Play briefing
              </Button>
            )
          ) : (
            <p className="text-sm text-muted">
              Add <code>ELEVENLABS_API_KEY</code> on the server to hear this read aloud.
            </p>
          )}
          {error && <div className="mt-3"><ErrorState message={error} /></div>}
          <p className="mt-4 rounded-lg bg-cream px-3.5 py-3 text-sm leading-relaxed text-ink">
            {briefing.data.text}
          </p>
        </>
      )}
    </Card>
  );
}
