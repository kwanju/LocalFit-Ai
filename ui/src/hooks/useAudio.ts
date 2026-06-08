// Audio I/O for voice modes (phase-5C, 2026-06-07 개정).
//  - Playback: WebAudio queue로 PCM chunk를 gap 없이 이어 재생.
//    GainNode로 볼륨 조절. AudioContext는 처음 chunk가 도착할 때 lazy 생성.
//  - Capture: mic → 16kHz mono PCM (STT 어댑터는 resample 안 함).
//
// 이전 구현은 chunk 마다 새 <audio> 엘리먼트 생성 + stopPlayback() 호출이라
// 코치 음성이 끊겨 들리는 문제가 있었음. WebAudio AudioBufferSourceNode를
// 순차 스케줄링해서 끊김 제거.

import { useCallback, useEffect, useRef, useState } from "react";

const TARGET_SAMPLE_RATE = 16000;
// Live streaming: emit ~128ms chunks (a few VAD windows' worth) to the backend.
const STREAM_CHUNK_MS = 128;
// 최소 lookahead — chunk를 너무 빨리 schedule하면 underrun이 일어날 수 있다.
const SCHEDULE_LOOKAHEAD_SEC = 0.05;

// Inline AudioWorklet: forwards each render quantum of mono PCM to the main
// thread. Inlined as a Blob so no separate static asset is needed.
const RECORDER_WORKLET = `
class RecorderProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) this.port.postMessage(channel.slice(0));
    return true;
  }
}
registerProcessor('localfit-recorder', RecorderProcessor);
`;

function base64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function pcm16ToFloat32(pcmBytes: Uint8Array): Float32Array {
  const view = new DataView(pcmBytes.buffer, pcmBytes.byteOffset, pcmBytes.byteLength);
  const samples = new Float32Array(pcmBytes.byteLength >> 1);
  for (let i = 0; i < samples.length; i += 1) {
    samples[i] = view.getInt16(i * 2, true) / 0x8000;
  }
  return samples;
}

function resampleLinear(input: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate === toRate) return input;
  const ratio = fromRate / toRate;
  const outLength = Math.floor(input.length / ratio);
  const output = new Float32Array(outLength);
  for (let i = 0; i < outLength; i += 1) {
    const pos = i * ratio;
    const left = Math.floor(pos);
    const right = Math.min(left + 1, input.length - 1);
    const frac = pos - left;
    output[i] = (input[left] ?? 0) * (1 - frac) + (input[right] ?? 0) * frac;
  }
  return output;
}

function mergeFrames(frames: Float32Array[], total: number): Float32Array {
  const merged = new Float32Array(total);
  let offset = 0;
  for (const f of frames) {
    merged.set(f, offset);
    offset += f.length;
  }
  return merged;
}

function floatToPcm16Bytes(samples: Float32Array): Uint8Array<ArrayBuffer> {
  const out = new Uint8Array(samples.length * 2);
  const view = new DataView(out.buffer);
  for (let i = 0; i < samples.length; i += 1) {
    const s = Math.max(-1, Math.min(1, samples[i] ?? 0));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return out;
}

function encodeWav(samples: Float32Array, sampleRate: number): Uint8Array {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i));
  };
  writeString(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true); // PCM chunk size
  view.setUint16(20, 1, true); // PCM format
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeString(36, "data");
  view.setUint32(40, samples.length * 2, true);
  let offset = 44;
  for (let i = 0; i < samples.length; i += 1) {
    const s = Math.max(-1, Math.min(1, samples[i] ?? 0));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }
  return new Uint8Array(buffer);
}

export interface RecordedAudio {
  audioB64: string;
  sampleRate: number;
}

/** Optional metadata that comes piggybacked on an audio chunk from the backend. */
export interface PlayPcmMeta {
  /** Called when this chunk actually starts playing (scheduled time fires). */
  onStart?: () => void;
}

interface UseAudio {
  playing: boolean;
  recording: boolean;
  streaming: boolean;
  micError: string | null;
  volume: number;
  setVolume: (v: number) => void;
  playWav: (b64: string) => Promise<void>;
  playPcm: (pcmB64: string, sampleRate: number, meta?: PlayPcmMeta) => void;
  stopPlayback: () => void;
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<RecordedAudio | null>;
  startStreaming: (onChunk: (pcmB64: string, sampleRate: number) => void) => Promise<boolean>;
  stopStreaming: () => Promise<void>;
}

const VOLUME_KEY = "localfit:volume";

function readSavedVolume(): number {
  try {
    const raw = window.localStorage.getItem(VOLUME_KEY);
    if (raw == null) return 1;
    const n = Number(raw);
    return Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : 1;
  } catch {
    return 1;
  }
}

export function useAudio(): UseAudio {
  // -- WAV playback (legacy, used by sendAudio C2S path -- left untouched) -----
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);

  // -- WebAudio streaming queue (coach voice) ---------------------------------
  const audioCtxRef = useRef<AudioContext | null>(null);
  const gainRef = useRef<GainNode | null>(null);
  const nextStartTimeRef = useRef(0);
  const liveSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());
  const playingTimeoutRef = useRef<number | null>(null);

  const [playing, setPlaying] = useState(false);
  const [volume, setVolumeState] = useState<number>(() => readSavedVolume());

  // Volume persisted; whenever it changes, update the gain node too.
  useEffect(() => {
    try {
      window.localStorage.setItem(VOLUME_KEY, String(volume));
    } catch {
      /* ignore quota errors */
    }
    const g = gainRef.current;
    if (g) g.gain.value = volume;
  }, [volume]);

  const setVolume = useCallback((v: number) => {
    const clamped = Math.max(0, Math.min(1, v));
    setVolumeState(clamped);
  }, []);

  const ensureAudioContext = useCallback((sampleRateHint?: number): AudioContext => {
    if (audioCtxRef.current && audioCtxRef.current.state !== "closed") {
      return audioCtxRef.current;
    }
    // Match the incoming sample rate when possible to avoid resampling artefacts.
    type Ctor = new (opts?: AudioContextOptions) => AudioContext;
    const Ctx = (window.AudioContext ?? (window as { webkitAudioContext?: Ctor }).webkitAudioContext) as Ctor;
    const ctx = sampleRateHint
      ? new Ctx({ sampleRate: sampleRateHint })
      : new Ctx();
    const gain = ctx.createGain();
    gain.gain.value = volume;
    gain.connect(ctx.destination);
    audioCtxRef.current = ctx;
    gainRef.current = gain;
    nextStartTimeRef.current = ctx.currentTime;
    return ctx;
  }, [volume]);

  // -- Mic capture state ------------------------------------------------------
  const streamRef = useRef<MediaStream | null>(null);
  const captureCtxRef = useRef<AudioContext | null>(null);
  const nodeRef = useRef<AudioWorkletNode | null>(null);
  const chunksRef = useRef<Float32Array[]>([]);
  const captureRateRef = useRef(TARGET_SAMPLE_RATE);
  const [recording, setRecording] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);

  const streamFramesRef = useRef<Float32Array[]>([]);
  const streamLenRef = useRef(0);
  const onChunkRef = useRef<((pcmB64: string, sampleRate: number) => void) | null>(null);
  const [streaming, setStreaming] = useState(false);

  const stopPlayback = useCallback(() => {
    // Halt the legacy <audio> path (still used by playWav for full WAVs).
    const el = audioElRef.current;
    if (el) {
      el.pause();
      el.currentTime = 0;
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    // Halt the WebAudio queue.
    for (const src of liveSourcesRef.current) {
      try {
        src.stop(0);
      } catch {
        /* already stopped */
      }
      src.disconnect();
    }
    liveSourcesRef.current.clear();
    if (audioCtxRef.current) {
      nextStartTimeRef.current = audioCtxRef.current.currentTime;
    }
    if (playingTimeoutRef.current !== null) {
      window.clearTimeout(playingTimeoutRef.current);
      playingTimeoutRef.current = null;
    }
    setPlaying(false);
  }, []);

  const playWav = useCallback(
    async (b64: string) => {
      stopPlayback();
      const blob = new Blob([base64ToBytes(b64)], { type: "audio/wav" });
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      const el = audioElRef.current ?? new Audio();
      audioElRef.current = el;
      // Mirror the GainNode volume on the <audio> element as best we can.
      el.volume = volume;
      el.src = url;
      el.onended = () => {
        setPlaying(false);
        URL.revokeObjectURL(url);
        if (objectUrlRef.current === url) objectUrlRef.current = null;
      };
      try {
        await el.play();
        setPlaying(true);
      } catch (err) {
        console.warn("Audio playback failed", err);
        setPlaying(false);
      }
    },
    [stopPlayback, volume],
  );

  // Play raw PCM16LE audio from Pipecat TTS as a gap-less queue.
  //  - Schedules each chunk on a single WebAudio timeline so consecutive chunks
  //    play seamlessly (no <audio>-element restarts).
  //  - `meta.onStart` fires the moment the chunk actually starts playing —
  //    used by the counter UI to sync rep display with the spoken count.
  const playPcm = useCallback(
    (pcmB64: string, sampleRate: number, meta?: PlayPcmMeta) => {
      const ctx = ensureAudioContext(sampleRate);
      // AudioContext is "suspended" until first user gesture on most browsers.
      // We optimistically resume; if it fails (no user gesture yet), audio stays
      // queued but won't play until the next user click. That's a known
      // browser policy, not a bug.
      if (ctx.state === "suspended") {
        void ctx.resume();
      }

      const samples = pcm16ToFloat32(base64ToBytes(pcmB64));
      // The TTS may stream at a rate (faster-qwen3-tts = 24kHz) different from the
      // AudioContext's anchored rate. Use the chunk's declared rate when building
      // the AudioBuffer; WebAudio resamples on play.
      const buffer = ctx.createBuffer(1, samples.length, sampleRate);
      // `copyToChannel` 의 TS 시그니처가 `Float32Array<ArrayBuffer>` 만 받으므로
      // (`Float32Array<ArrayBufferLike>` 가 아닌) channelData.set() 으로 직접 복사.
      buffer.getChannelData(0).set(samples);

      const source = ctx.createBufferSource();
      source.buffer = buffer;
      const gain = gainRef.current ?? ctx.destination;
      source.connect(gain);

      const now = ctx.currentTime;
      const startTime = Math.max(now + SCHEDULE_LOOKAHEAD_SEC, nextStartTimeRef.current);
      source.start(startTime);
      nextStartTimeRef.current = startTime + buffer.duration;

      liveSourcesRef.current.add(source);
      setPlaying(true);

      if (meta?.onStart) {
        // Fire onStart at the scheduled playback time so the UI counter and the
        // spoken word land together. AudioContext.currentTime is monotonic, so
        // setTimeout against the wall clock is fine as a rough approximation.
        const delayMs = Math.max(0, (startTime - now) * 1000);
        window.setTimeout(meta.onStart, delayMs);
      }

      source.onended = () => {
        liveSourcesRef.current.delete(source);
        source.disconnect();
        // Defer the "stopped playing" flip slightly so back-to-back chunks
        // don't toggle `playing` off→on→off and confuse the half-duplex gate.
        if (playingTimeoutRef.current !== null) {
          window.clearTimeout(playingTimeoutRef.current);
        }
        playingTimeoutRef.current = window.setTimeout(() => {
          playingTimeoutRef.current = null;
          if (liveSourcesRef.current.size === 0) setPlaying(false);
        }, 50);
      };
    },
    [ensureAudioContext],
  );

  const startRecording = useCallback(async () => {
    setMicError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;
      const ctx = new AudioContext();
      captureCtxRef.current = ctx;
      captureRateRef.current = ctx.sampleRate;
      const blobUrl = URL.createObjectURL(
        new Blob([RECORDER_WORKLET], { type: "application/javascript" }),
      );
      await ctx.audioWorklet.addModule(blobUrl);
      URL.revokeObjectURL(blobUrl);
      const source = ctx.createMediaStreamSource(stream);
      const node = new AudioWorkletNode(ctx, "localfit-recorder");
      nodeRef.current = node;
      chunksRef.current = [];
      node.port.onmessage = (event) => {
        chunksRef.current.push(event.data as Float32Array);
      };
      source.connect(node);
      // Worklet must be in the graph to pull audio; route to a muted gain so it
      // doesn't echo to the speakers.
      const sink = ctx.createGain();
      sink.gain.value = 0;
      node.connect(sink).connect(ctx.destination);
      setRecording(true);
    } catch (err) {
      console.warn("Microphone capture failed", err);
      setMicError("마이크를 사용할 수 없습니다. 권한을 확인해 주세요.");
      setRecording(false);
    }
  }, []);

  const stopRecording = useCallback(async (): Promise<RecordedAudio | null> => {
    const ctx = captureCtxRef.current;
    nodeRef.current?.disconnect();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    if (ctx) await ctx.close();
    nodeRef.current = null;
    captureCtxRef.current = null;
    streamRef.current = null;
    setRecording(false);

    const chunks = chunksRef.current;
    chunksRef.current = [];
    if (chunks.length === 0) return null;

    const total = chunks.reduce((sum, c) => sum + c.length, 0);
    const merged = new Float32Array(total);
    let offset = 0;
    for (const c of chunks) {
      merged.set(c, offset);
      offset += c.length;
    }
    const resampled = resampleLinear(merged, captureRateRef.current, TARGET_SAMPLE_RATE);
    const wav = encodeWav(resampled, TARGET_SAMPLE_RATE);
    return { audioB64: bytesToBase64(wav), sampleRate: TARGET_SAMPLE_RATE };
  }, []);

  // Continuous capture for hands-free live S2S: emits ~128ms 16kHz PCM16 chunks.
  const startStreaming = useCallback(
    async (onChunk: (pcmB64: string, sampleRate: number) => void): Promise<boolean> => {
      if (streamRef.current) return false; // already capturing (recording or streaming)
      setMicError(null);
      onChunkRef.current = onChunk;
      streamFramesRef.current = [];
      streamLenRef.current = 0;
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
        });
        streamRef.current = stream;
        const ctx = new AudioContext();
        captureCtxRef.current = ctx;
        captureRateRef.current = ctx.sampleRate;
        const blobUrl = URL.createObjectURL(
          new Blob([RECORDER_WORKLET], { type: "application/javascript" }),
        );
        await ctx.audioWorklet.addModule(blobUrl);
        URL.revokeObjectURL(blobUrl);
        const source = ctx.createMediaStreamSource(stream);
        const node = new AudioWorkletNode(ctx, "localfit-recorder");
        nodeRef.current = node;
        const chunkSamples = Math.round((captureRateRef.current * STREAM_CHUNK_MS) / 1000);
        node.port.onmessage = (event) => {
          const frame = event.data as Float32Array;
          streamFramesRef.current.push(frame);
          streamLenRef.current += frame.length;
          if (streamLenRef.current < chunkSamples) return;
          const merged = mergeFrames(streamFramesRef.current, streamLenRef.current);
          streamFramesRef.current = [];
          streamLenRef.current = 0;
          const resampled = resampleLinear(merged, captureRateRef.current, TARGET_SAMPLE_RATE);
          onChunkRef.current?.(bytesToBase64(floatToPcm16Bytes(resampled)), TARGET_SAMPLE_RATE);
        };
        source.connect(node);
        const sink = ctx.createGain();
        sink.gain.value = 0;
        node.connect(sink).connect(ctx.destination);
        setStreaming(true);
        return true;
      } catch (err) {
        console.warn("Microphone streaming failed", err);
        setMicError("마이크를 사용할 수 없습니다. 권한을 확인해 주세요.");
        setStreaming(false);
        return false;
      }
    },
    [],
  );

  const stopStreaming = useCallback(async () => {
    const ctx = captureCtxRef.current;
    nodeRef.current?.disconnect();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    if (ctx) await ctx.close();
    nodeRef.current = null;
    captureCtxRef.current = null;
    streamRef.current = null;
    onChunkRef.current = null;
    streamFramesRef.current = [];
    streamLenRef.current = 0;
    setStreaming(false);
  }, []);

  return {
    playing,
    recording,
    streaming,
    micError,
    volume,
    setVolume,
    playWav,
    playPcm,
    stopPlayback,
    startRecording,
    stopRecording,
    startStreaming,
    stopStreaming,
  };
}
