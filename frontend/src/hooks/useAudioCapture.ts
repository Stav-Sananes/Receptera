/**
 * useAudioCapture — captures microphone audio and streams PCM frames to the WS (FE-01).
 *
 * Wire contract (mirrors receptra.stt.vad constants):
 *   Sample rate : 16 000 Hz
 *   Channels    : 1 (mono)
 *   Frame bytes : 1 024  (512 int16 samples × 2 bytes)
 *   Encoding    : little-endian int16 (signed)
 *
 * Uses AudioWorklet with an inline Blob-URL processor to avoid Vite bundling complications.
 * The worklet accumulates float32 samples, flushes 512-sample chunks as Int16Array buffers,
 * and posts them to the main thread via MessagePort.
 *
 * Returns:
 *   isCapturing — true while microphone is active
 *   micError    — error message string or null
 *   start()     — request microphone permission + open WS + begin streaming
 *   stop()      — tear down audio pipeline + close WS
 */

import { useCallback, useRef, useState } from 'react'

const SAMPLE_RATE = 16_000
const FRAME_SAMPLES = 512 // 512 × 2 = 1024 bytes per frame

/** AudioWorklet processor source (inline to avoid Vite complication with AudioWorklet URLs). */
const PROCESSOR_SOURCE = /* javascript */ `
class PcmProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buf = new Float32Array(0);
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    const next = new Float32Array(this._buf.length + ch.length);
    next.set(this._buf);
    next.set(ch, this._buf.length);
    this._buf = next;
    while (this._buf.length >= ${FRAME_SAMPLES}) {
      const chunk = this._buf.slice(0, ${FRAME_SAMPLES});
      this._buf = this._buf.slice(${FRAME_SAMPLES});
      const i16 = new Int16Array(${FRAME_SAMPLES});
      for (let i = 0; i < ${FRAME_SAMPLES}; i++) {
        i16[i] = Math.max(-32768, Math.min(32767, Math.round(chunk[i] * 32768)));
      }
      this.port.postMessage(i16.buffer, [i16.buffer]);
    }
    return true;
  }
}
registerProcessor('pcm-processor', PcmProcessor);
`

export interface AudioCaptureState {
  isCapturing: boolean
  micError: string | null
  start: (sendBinary: (buf: ArrayBuffer) => void, onWsConnect: () => void) => Promise<void>
  stop: (onWsDisconnect: () => void) => void
}

export function useAudioCapture(): AudioCaptureState {
  const [isCapturing, setIsCapturing] = useState(false)
  const [micError, setMicError] = useState<string | null>(null)

  const contextRef = useRef<AudioContext | null>(null)
  const nodeRef = useRef<AudioWorkletNode | null>(null)
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const blobUrlRef = useRef<string | null>(null)

  const stop = useCallback((onWsDisconnect: () => void) => {
    nodeRef.current?.disconnect()
    sourceRef.current?.disconnect()
    streamRef.current?.getTracks().forEach((t) => t.stop())
    if (contextRef.current && contextRef.current.state !== 'closed') {
      void contextRef.current.close()
    }
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current)
      blobUrlRef.current = null
    }
    nodeRef.current = null
    sourceRef.current = null
    streamRef.current = null
    contextRef.current = null
    setIsCapturing(false)
    onWsDisconnect()
  }, [])

  const start = useCallback(
    async (sendBinary: (buf: ArrayBuffer) => void, onWsConnect: () => void) => {
      setMicError(null)
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            sampleRate: SAMPLE_RATE,
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
          },
        })
        streamRef.current = stream

        const ctx = new AudioContext({ sampleRate: SAMPLE_RATE })
        contextRef.current = ctx

        // Load inline worklet via Blob URL.
        const blob = new Blob([PROCESSOR_SOURCE], { type: 'application/javascript' })
        const url = URL.createObjectURL(blob)
        blobUrlRef.current = url
        await ctx.audioWorklet.addModule(url)

        const workletNode = new AudioWorkletNode(ctx, 'pcm-processor')
        nodeRef.current = workletNode

        workletNode.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
          sendBinary(e.data)
        }

        const source = ctx.createMediaStreamSource(stream)
        sourceRef.current = source
        source.connect(workletNode)
        // Do NOT connect workletNode to destination (we don't want echo).

        onWsConnect()
        setIsCapturing(true)
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        setMicError(msg)
        setIsCapturing(false)
      }
    },
    [],
  )

  return { isCapturing, micError, start, stop }
}
