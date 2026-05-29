// Audio I/O for voice modes (phase-5C).
//  - Playback: decode the coach's base64 WAV and play it (interruptible).
//  - Capture: record the mic and return a 16kHz mono WAV. The STT adapter does
//    NOT resample (known constraint), so we resample to 16kHz here before
//    sending — otherwise transcription is garbled.

import { useCallback, useRef, useState } from "react";

const TARGET_SAMPLE_RATE = 16000;
// Live streaming: emit ~128ms chunks (a few VAD windows' worth) to the backend.
const STREAM_CHUNK_MS = 128;

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

interface UseAudio {
  playing: boolean;
  recording: boolean;
  streaming: boolean;
  micError: string | null;
  playWav: (b64: string) => Promise<void>;
  stopPlayback: () => void;
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<RecordedAudio | null>;
  startStreaming: (onChunk: (pcmB64: string, sampleRate: number) => void) => Promise<boolean>;
  stopStreaming: () => Promise<void>;
}

export function useAudio(): UseAudio {
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const [playing, setPlaying] = useState(false);

  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
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
    const el = audioElRef.current;
    if (el) {
      el.pause();
      el.currentTime = 0;
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
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
    [stopPlayback],
  );

  const startRecording = useCallback(async () => {
    setMicError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;
      const ctx = new AudioContext();
      ctxRef.current = ctx;
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
    const ctx = ctxRef.current;
    nodeRef.current?.disconnect();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    if (ctx) await ctx.close();
    nodeRef.current = null;
    ctxRef.current = null;
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
        ctxRef.current = ctx;
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
    const ctx = ctxRef.current;
    nodeRef.current?.disconnect();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    if (ctx) await ctx.close();
    nodeRef.current = null;
    ctxRef.current = null;
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
    playWav,
    stopPlayback,
    startRecording,
    stopRecording,
    startStreaming,
    stopStreaming,
  };
}
