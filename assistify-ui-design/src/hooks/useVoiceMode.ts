"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { computeEnergy, convertToPCM16, mergeFloat32, pcm16ToFloat32, resample } from "@/src/lib/audioUtils";
import { isRemoteVoiceSession } from "@/src/lib/networkProfile";
import type { WsControlAction } from "@/src/hooks/useChatWebSocket";
import type { AppLanguage } from "@/src/lib/types";

export type VoiceState =
  | "idle"
  | "listening"
  | "processing"
  | "transcribing"
  | "speaking"
  | "interrupted"
  | "error";

export type VoiceWsApi = {
  connected: boolean;
  sendBinary: (buf: ArrayBuffer) => void;
  sendControl: (action: WsControlAction, extra?: Record<string, unknown>) => void;
};

const STT_PENDING_WATCHDOG_LOCAL_MS = 3000;
const STT_PENDING_WATCHDOG_REMOTE_MS = 12_000;
const WS_PREBUFFER_LOCAL_SECS = 0.3;
const WS_PREBUFFER_REMOTE_SECS = 0.9;
const CAPTURE_POLL_MS = 50;
const CAPTURE_FLUSH_TICKS_REMOTE = 3;
const SPEAKING_WATCHDOG_REMOTE_MS = 12_000;
const SPEAKING_WATCHDOG_LOCAL_MS = 45_000;
const BROWSER_TTS_MAX_MS = 45_000;
const TTS_SAMPLE_RATE = 24000;
const CAPTURE_SAMPLE_RATE = 16000;

type UseVoiceModeOptions = {
  language: AppLanguage;
  wsApiRef: React.MutableRefObject<VoiceWsApi>;
  ttsEnabled?: boolean;
  /** Piper TTS over WebSocket; disabled on tunnel/mobile remote sessions. */
  useServerTts?: boolean;
  onUserTranscript?: (text: string) => void;
  onAssistantText?: (text: string) => void;
};

function statusLabel(state: VoiceState, language: AppLanguage, errorMsg?: string): string {
  const ar = language === "ar";
  if (errorMsg) return errorMsg;
  switch (state) {
    case "idle":
      return ar ? "جاهز — تحدث عندما تريد" : "Ready — speak when you want";
    case "listening":
      return ar ? "الاستماع..." : "Listening...";
    case "processing":
      return ar ? "جاري معالجة الصوت..." : "Processing speech...";
    case "transcribing":
      return ar ? "جاري التفكير..." : "Thinking...";
    case "speaking":
      return ar ? "يتحدث..." : "Speaking...";
    case "interrupted":
      return ar ? "تمت المقاطعة..." : "Interrupted...";
    case "error":
      return ar ? "خطأ" : "Error";
    default:
      return "";
  }
}

export function useVoiceMode({
  language,
  wsApiRef,
  ttsEnabled = true,
  useServerTts = true,
  onUserTranscript,
  onAssistantText,
}: UseVoiceModeOptions) {
  const [isOpen, setIsOpen] = useState(false);
  const [state, setState] = useState<VoiceState>("idle");
  const [statusText, setStatusText] = useState("");
  const [userText, setUserText] = useState("");
  const [assistantText, setAssistantText] = useState("");
  const [showRetry, setShowRetry] = useState(false);

  const isOpenRef = useRef(false);
  const stateRef = useRef<VoiceState>("idle");
  const isRecordingRef = useRef(false);
  const pauseSendRef = useRef(false);
  const ttsEnabledRef = useRef(ttsEnabled);
  const useServerTtsRef = useRef(useServerTts);
  const onUserTranscriptRef = useRef(onUserTranscript);
  const onAssistantTextRef = useRef(onAssistantText);

  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const capturePollRef = useRef<ReturnType<typeof setInterval> | number | null>(null);
  const captureBufferRef = useRef<Float32Array | null>(null);

  const ttsCtxRef = useRef<AudioContext | null>(null);
  const ttsGainRef = useRef<GainNode | null>(null);
  const ttsSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const wsAudioStateRef = useRef<"idle" | "buffering" | "playing">("idle");
  const wsScheduledTimeRef = useRef(0);
  const wsPendingChunksRef = useRef<Float32Array[]>([]);
  const wsPendingDurationRef = useRef(0);

  const sttWatchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const speakingWatchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const browserTtsTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const assistantBufferRef = useRef("");
  const startListeningRef = useRef<() => Promise<void>>(async () => {});
  const pendingCaptureRef = useRef<Float32Array[]>([]);
  const captureTickRef = useRef(0);
  const remoteSessionRef = useRef(false);

  useEffect(() => {
    remoteSessionRef.current = isRemoteVoiceSession();
  }, []);

  useEffect(() => {
    ttsEnabledRef.current = ttsEnabled;
    useServerTtsRef.current = useServerTts;
    onUserTranscriptRef.current = onUserTranscript;
    onAssistantTextRef.current = onAssistantText;
  });

  const setVoiceState = useCallback(
    (next: VoiceState, err?: string) => {
      stateRef.current = next;
      setState(next);
      setStatusText(statusLabel(next, language, err));
    },
    [language],
  );

  const getTtsContext = useCallback(() => {
    if (!ttsCtxRef.current || ttsCtxRef.current.state === "closed") {
      ttsCtxRef.current = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)({
        sampleRate: TTS_SAMPLE_RATE,
      });
      ttsGainRef.current = ttsCtxRef.current.createGain();
      ttsGainRef.current.connect(ttsCtxRef.current.destination);
    }
    if (ttsCtxRef.current.state === "suspended") void ttsCtxRef.current.resume();
    return ttsCtxRef.current;
  }, []);

  const stopTtsPlayback = useCallback(() => {
    for (const src of ttsSourcesRef.current) {
      try {
        src.stop();
        src.disconnect();
      } catch {
        /* ignore */
      }
    }
    ttsSourcesRef.current = [];
    wsAudioStateRef.current = "idle";
    wsPendingChunksRef.current = [];
    wsPendingDurationRef.current = 0;
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
  }, []);

  const scheduleAudioChunk = useCallback(
    (float32: Float32Array) => {
      const ctx = getTtsContext();
      const gain = ttsGainRef.current;
      if (!gain) return;
      const audioBuffer = ctx.createBuffer(1, float32.length, TTS_SAMPLE_RATE);
      audioBuffer.getChannelData(0).set(float32);
      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(gain);
      if (wsScheduledTimeRef.current < ctx.currentTime) {
        wsScheduledTimeRef.current = ctx.currentTime + 0.02;
      }
      source.start(wsScheduledTimeRef.current);
      ttsSourcesRef.current.push(source);
      wsScheduledTimeRef.current += audioBuffer.duration;
    },
    [getTtsContext],
  );

  const scheduleAllPending = useCallback(() => {
    while (wsPendingChunksRef.current.length > 0) {
      const chunk = wsPendingChunksRef.current.shift();
      if (chunk) scheduleAudioChunk(chunk);
    }
  }, [scheduleAudioChunk]);

  const handleTtsAudioStart = useCallback(() => {
    if (!ttsEnabledRef.current || !useServerTtsRef.current) return;
    const ctx = getTtsContext();
    if (wsAudioStateRef.current === "idle") {
      wsAudioStateRef.current = "buffering";
      wsPendingChunksRef.current = [];
      wsPendingDurationRef.current = 0;
      wsScheduledTimeRef.current = ctx.currentTime + 0.05;
    }
    setVoiceState("speaking");
    pauseSendRef.current = true;
  }, [getTtsContext, setVoiceState]);

  const ttsPrebufferSecs = useCallback(
    () => (remoteSessionRef.current ? WS_PREBUFFER_REMOTE_SECS : WS_PREBUFFER_LOCAL_SECS),
    [],
  );

  const handleWsAudioChunk = useCallback(
    (arrayBuffer: ArrayBuffer) => {
      if (!ttsEnabledRef.current || !useServerTtsRef.current || wsAudioStateRef.current === "idle") return;
      const float32 = pcm16ToFloat32(arrayBuffer);
      const prebufferSecs = ttsPrebufferSecs();
      if (wsAudioStateRef.current === "buffering") {
        wsPendingChunksRef.current.push(float32);
        wsPendingDurationRef.current += float32.length / TTS_SAMPLE_RATE;
        if (wsPendingDurationRef.current >= prebufferSecs) {
          wsAudioStateRef.current = "playing";
          scheduleAllPending();
        }
      } else if (wsAudioStateRef.current === "playing") {
        scheduleAudioChunk(float32);
      }
    },
    [scheduleAllPending, scheduleAudioChunk, ttsPrebufferSecs],
  );

  const clearSttWatchdog = useCallback(() => {
    if (sttWatchdogRef.current) {
      clearTimeout(sttWatchdogRef.current);
      sttWatchdogRef.current = null;
    }
  }, []);

  const armSttWatchdog = useCallback(() => {
    clearSttWatchdog();
    const watchdogMs = remoteSessionRef.current
      ? STT_PENDING_WATCHDOG_REMOTE_MS
      : STT_PENDING_WATCHDOG_LOCAL_MS;
    sttWatchdogRef.current = setTimeout(() => {
      sttWatchdogRef.current = null;
      if (!isOpenRef.current || stateRef.current !== "processing") return;
      const msg = language === "ar" ? "لم أسمعك بوضوح — حاول مرة أخرى" : "Didn't catch that — try again";
      setVoiceState("error", msg);
      setShowRetry(true);
    }, watchdogMs);
  }, [clearSttWatchdog, language, setVoiceState]);

  const releaseCapture = useCallback(() => {
    isRecordingRef.current = false;
    pauseSendRef.current = false;
    pendingCaptureRef.current = [];
    captureTickRef.current = 0;
    if (capturePollRef.current) {
      clearInterval(capturePollRef.current);
      capturePollRef.current = null;
    }
    if (analyserRef.current) {
      analyserRef.current.disconnect();
      analyserRef.current = null;
    }
    captureBufferRef.current = null;
    if (audioContextRef.current) {
      void audioContextRef.current.close();
      audioContextRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
  }, []);

  const resumeListening = useCallback(() => {
    assistantBufferRef.current = "";
    setAssistantText("");
    setUserText("");
    setShowRetry(false);
    stopTtsPlayback();
    if (isOpenRef.current) {
      void startListeningRef.current();
    } else {
      setVoiceState("idle");
    }
  }, [setVoiceState, stopTtsPlayback]);

  const completeVoiceTurn = useCallback(() => {
    clearSttWatchdog();
    if (speakingWatchdogRef.current) {
      clearTimeout(speakingWatchdogRef.current);
      speakingWatchdogRef.current = null;
    }
    if (browserTtsTimerRef.current) {
      clearTimeout(browserTtsTimerRef.current);
      browserTtsTimerRef.current = null;
    }
    const ctx = getTtsContext();
    const remaining = Math.max(0, wsScheduledTimeRef.current - ctx.currentTime);
    const afterPlayback = () => {
      wsAudioStateRef.current = "idle";
      pauseSendRef.current = false;
      if (isOpenRef.current) {
        setTimeout(() => {
          if (isOpenRef.current) void startListeningRef.current();
        }, 400);
      } else {
        setVoiceState("idle");
      }
    };
    if (remaining > 0.1 && wsAudioStateRef.current === "playing") {
      setTimeout(afterPlayback, remaining * 1000 + 200);
    } else {
      afterPlayback();
    }
  }, [clearSttWatchdog, getTtsContext, setVoiceState]);

  const clearSpeakingWatchdog = useCallback(() => {
    if (speakingWatchdogRef.current) {
      clearTimeout(speakingWatchdogRef.current);
      speakingWatchdogRef.current = null;
    }
  }, []);

  const armSpeakingWatchdog = useCallback(() => {
    clearSpeakingWatchdog();
    const ms = remoteSessionRef.current ? SPEAKING_WATCHDOG_REMOTE_MS : SPEAKING_WATCHDOG_LOCAL_MS;
    speakingWatchdogRef.current = setTimeout(() => {
      speakingWatchdogRef.current = null;
      if (!isOpenRef.current) return;
      if (stateRef.current !== "speaking" && stateRef.current !== "transcribing") return;
      stopTtsPlayback();
      completeVoiceTurn();
    }, ms);
  }, [clearSpeakingWatchdog, completeVoiceTurn, stopTtsPlayback]);

  const skipSpeaking = useCallback(() => {
    clearSpeakingWatchdog();
    stopTtsPlayback();
    completeVoiceTurn();
  }, [clearSpeakingWatchdog, completeVoiceTurn, stopTtsPlayback]);

  const unlockVoiceAudio = useCallback(() => {
    try {
      void getTtsContext().resume();
      if (typeof window !== "undefined" && window.speechSynthesis) {
        window.speechSynthesis.cancel();
        const unlock = new SpeechSynthesisUtterance(" ");
        unlock.volume = 0.01;
        window.speechSynthesis.speak(unlock);
      }
    } catch {
      /* ignore */
    }
  }, [getTtsContext]);

  const flushPendingCapture = useCallback(() => {
    if (pendingCaptureRef.current.length === 0) return;
    const merged = mergeFloat32(pendingCaptureRef.current);
    pendingCaptureRef.current = [];
    if (merged.length > 0 && wsApiRef.current.connected) {
      wsApiRef.current.sendBinary(convertToPCM16(merged));
    }
  }, [wsApiRef]);

  const waitForWsConnection = useCallback(async (timeoutMs = 15_000) => {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      if (wsApiRef.current.connected) return true;
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    return false;
  }, [wsApiRef]);

  const stopListening = useCallback(
    (discard = false) => {
      if (!isRecordingRef.current) return;
      if (!discard) flushPendingCapture();
      releaseCapture();
      wsApiRef.current.sendControl(discard ? "clear_audio_buffer" : "stop_recording");
      if (!discard) {
        setVoiceState("processing");
        armSttWatchdog();
      }
    },
    [armSttWatchdog, flushPendingCapture, releaseCapture, setVoiceState, wsApiRef],
  );

  const bargeIn = useCallback(() => {
    stopTtsPlayback();
    wsApiRef.current.sendControl("interrupt");
    wsApiRef.current.sendControl("clear_audio_buffer");
    setVoiceState("interrupted");
    pauseSendRef.current = false;
    setTimeout(() => {
      if (isOpenRef.current) void startListeningRef.current();
    }, 300);
  }, [setVoiceState, stopTtsPlayback, wsApiRef]);

  const startListening = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setVoiceState("error", "Voice not supported in this browser.");
      setShowRetry(true);
      return;
    }
    if (!wsApiRef.current.connected) {
      setVoiceState("error", "Not connected to server.");
      setShowRetry(true);
      return;
    }
    try {
      wsApiRef.current.sendControl("set_language", { language });
      const ctx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
      if (ctx.state === "suspended") await ctx.resume();
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 4096;
      source.connect(analyser);
      const buffer = new Float32Array(analyser.fftSize);
      captureBufferRef.current = buffer;
      pendingCaptureRef.current = [];
      captureTickRef.current = 0;
      capturePollRef.current = window.setInterval(() => {
        if (!isRecordingRef.current) return;
        analyser.getFloatTimeDomainData(buffer);
        if (pauseSendRef.current) {
          if (computeEnergy(buffer) > 0.09) bargeIn();
          return;
        }
        const resampled = resample(buffer, ctx.sampleRate, CAPTURE_SAMPLE_RATE);
        if (resampled) {
          pendingCaptureRef.current.push(resampled);
        }
        captureTickRef.current += 1;
        const flushEvery = remoteSessionRef.current ? CAPTURE_FLUSH_TICKS_REMOTE : 1;
        if (captureTickRef.current % flushEvery === 0) {
          flushPendingCapture();
        }
      }, CAPTURE_POLL_MS);
      audioContextRef.current = ctx;
      mediaStreamRef.current = stream;
      analyserRef.current = analyser;
      isRecordingRef.current = true;
      pauseSendRef.current = false;
      setVoiceState("listening");
    } catch (err) {
      setVoiceState("error", err instanceof Error ? err.message : "Mic access denied");
      setShowRetry(true);
    }
  }, [bargeIn, flushPendingCapture, language, setVoiceState, wsApiRef]);

  startListeningRef.current = startListening;

  const speakBrowserFallback = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) {
        completeVoiceTurn();
        return;
      }
      stopTtsPlayback();
      pauseSendRef.current = true;
      setVoiceState("speaking");
      armSpeakingWatchdog();

      if (!window.speechSynthesis) {
        completeVoiceTurn();
        return;
      }

      const synth = window.speechSynthesis;
      synth.cancel();
      if (synth.paused) synth.resume();

      const utter = new SpeechSynthesisUtterance(trimmed);
      utter.lang = language === "ar" ? "ar-SA" : "en-US";
      const finish = () => {
        if (browserTtsTimerRef.current) {
          clearTimeout(browserTtsTimerRef.current);
          browserTtsTimerRef.current = null;
        }
        completeVoiceTurn();
      };
      utter.onend = finish;
      utter.onerror = finish;
      browserTtsTimerRef.current = setTimeout(finish, BROWSER_TTS_MAX_MS);
      synth.speak(utter);
    },
    [armSpeakingWatchdog, completeVoiceTurn, language, setVoiceState, stopTtsPlayback],
  );

  const handleInboundMessage = useCallback(
    (msg: Record<string, unknown>) => {
      if (!isOpenRef.current) return;
      const type = String(msg.type ?? "");

      if (type === "transcript") {
        clearSttWatchdog();
        const text = String(msg.text ?? "").trim();
        if (msg.final && text) {
          setUserText(text);
          onUserTranscriptRef.current?.(text);
          setVoiceState("transcribing");
        }
      } else if (type === "thinking") {
        setVoiceState("transcribing");
      } else if (type === "aiResponseChunk" && msg.text) {
        assistantBufferRef.current += String(msg.text);
        setAssistantText(assistantBufferRef.current);
        onAssistantTextRef.current?.(assistantBufferRef.current);
        setVoiceState("transcribing");
        if (isRecordingRef.current) stopListening(true);
      } else if (type === "aiResponseDone") {
        const full = String(msg.fullText ?? assistantBufferRef.current ?? "");
        assistantBufferRef.current = full;
        setAssistantText(full);
        onAssistantTextRef.current?.(full);
        const serverTtsPending = msg.server_tts_pending === true;
        if (serverTtsPending && useServerTtsRef.current) {
          armSpeakingWatchdog();
          return;
        }
        if (!ttsEnabledRef.current) {
          completeVoiceTurn();
          return;
        }
        if (full) {
          speakBrowserFallback(full);
        } else {
          completeVoiceTurn();
        }
      } else if (type === "ttsAudioStart") {
        if (!useServerTtsRef.current) return;
        handleTtsAudioStart();
        armSpeakingWatchdog();
      } else if (type === "ttsAudioEnd") {
        if (!useServerTtsRef.current) return;
        if (wsAudioStateRef.current === "buffering" && wsPendingChunksRef.current.length > 0) {
          wsAudioStateRef.current = "playing";
          scheduleAllPending();
        }
        completeVoiceTurn();
      } else if (type === "ttsFallback") {
        const fb = String(msg.text ?? assistantBufferRef.current ?? "").trim();
        if (fb) speakBrowserFallback(fb);
        else completeVoiceTurn();
      } else if (type === "stt_failed") {
        clearSttWatchdog();
        setVoiceState("error", String(msg.message ?? "Speech recognition failed"));
        setShowRetry(true);
      } else if (type === "system_busy") {
        setVoiceState("error", String(msg.message ?? "System busy, try again"));
        setShowRetry(true);
      } else if (type === "error" || msg.error === true) {
        const recoverable = msg.voice_recoverable === true;
        setVoiceState("error", String(msg.message ?? "Voice error"));
        setShowRetry(true);
        if (recoverable) {
          releaseCapture();
          stopTtsPlayback();
        }
      }
    },
    [
      armSpeakingWatchdog,
      clearSttWatchdog,
      completeVoiceTurn,
      handleTtsAudioStart,
      scheduleAllPending,
      setVoiceState,
      speakBrowserFallback,
      stopListening,
      stopTtsPlayback,
      releaseCapture,
    ],
  );

  const handleBinaryMessage = useCallback(
    (chunk: ArrayBuffer) => {
      if (!isOpenRef.current) return;
      handleWsAudioChunk(chunk);
    },
    [handleWsAudioChunk],
  );

  const openVoiceMode = useCallback(async () => {
    isOpenRef.current = true;
    setIsOpen(true);
    setShowRetry(false);
    assistantBufferRef.current = "";
    setUserText("");
    setAssistantText("");
    setVoiceState(
      "idle",
      remoteSessionRef.current
        ? language === "ar"
          ? "جاري الاتصال..."
          : "Connecting..."
        : undefined,
    );
    const ready = wsApiRef.current.connected || (await waitForWsConnection());
    if (!ready) {
      setVoiceState("error", language === "ar" ? "تعذر الاتصال بالخادم" : "Not connected to server.");
      setShowRetry(true);
      return;
    }
    unlockVoiceAudio();
    void startListening();
  }, [language, setVoiceState, startListening, unlockVoiceAudio, waitForWsConnection, wsApiRef]);

  const closeVoiceMode = useCallback(() => {
    isOpenRef.current = false;
    setIsOpen(false);
    clearSttWatchdog();
    stopListening(true);
    releaseCapture();
    stopTtsPlayback();
    setVoiceState("idle");
    setShowRetry(false);
  }, [clearSttWatchdog, releaseCapture, setVoiceState, stopListening, stopTtsPlayback]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeVoiceMode();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [closeVoiceMode, isOpen]);

  useEffect(() => () => {
    releaseCapture();
    stopTtsPlayback();
    clearSttWatchdog();
    clearSpeakingWatchdog();
    if (browserTtsTimerRef.current) clearTimeout(browserTtsTimerRef.current);
  }, [clearSpeakingWatchdog, clearSttWatchdog, releaseCapture, stopTtsPlayback]);

  return {
    isOpen,
    state,
    statusText,
    userText,
    assistantText,
    showRetry,
    openVoiceMode,
    closeVoiceMode,
    stopListening: () => stopListening(false),
    skipSpeaking,
    retry: resumeListening,
    handleInboundMessage,
    handleBinaryMessage,
  };
}
