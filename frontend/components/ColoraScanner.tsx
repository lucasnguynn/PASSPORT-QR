"use client";

import { BrowserQRCodeReader } from "@zxing/browser";
import { useCallback, useEffect, useRef, useState } from "react";

const PREFIX = "colora-secure://v1.";
const BASE85_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{|}~";
const DECODE_INTERVAL_MS = 150; // 6.67 attempts/second: fast enough to feel instant without cooking the device.

export interface ColoraScannerProps {
  aesKeyBase64Url: string;
  publicKeyJwk: JsonWebKey;
  onDecoded?: (url: string) => void;
  autoRedirect?: boolean;
}

type ScannerStatus = "idle" | "requesting" | "scanning" | "verifying" | "success" | "error";

function decodeBase85(value: string): Uint8Array {
  if (!value || value.length % 5 === 1) throw new Error("Malformed Base85 payload");
  const output: number[] = [];
  for (let offset = 0; offset < value.length; offset += 5) {
    const chunk = value.slice(offset, offset + 5);
    let accumulator = 0;
    for (const character of chunk.padEnd(5, "~")) {
      const digit = BASE85_ALPHABET.indexOf(character);
      if (digit < 0) throw new Error("Malformed Base85 payload");
      accumulator = accumulator * 85 + digit;
      if (accumulator > 0xffffffff) throw new Error("Malformed Base85 payload");
    }
    const bytes = [(accumulator >>> 24) & 255, (accumulator >>> 16) & 255, (accumulator >>> 8) & 255, accumulator & 255];
    output.push(...bytes.slice(0, chunk.length - 1));
  }
  return new Uint8Array(output);
}

function decodeBase64Url(value: string): Uint8Array {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  return Uint8Array.from(atob(normalized), (character) => character.charCodeAt(0));
}

async function openToken(rawValue: string, aesKeyBase64Url: string, publicKeyJwk: JsonWebKey): Promise<string> {
  if (!rawValue.startsWith(PREFIX)) throw new Error("This is not a COLORA secure code");
  const token = decodeBase85(rawValue.slice(PREFIX.length));
  if (token.length < 1 + 12 + 16 + 64 || token[0] !== 1) throw new Error("Unsupported or incomplete COLORA code");

  const signedPayload = token.slice(0, -64);
  const signature = token.slice(-64);
  const verificationKey = await crypto.subtle.importKey(
    "jwk", publicKeyJwk, { name: "ECDSA", namedCurve: "P-256" }, false, ["verify"],
  );
  const authentic = await crypto.subtle.verify(
    { name: "ECDSA", hash: "SHA-256" }, verificationKey, signature, signedPayload,
  );
  if (!authentic) throw new Error("Counterfeit code: signature verification failed");

  const keyBytes = decodeBase64Url(aesKeyBase64Url);
  if (keyBytes.byteLength !== 32) throw new Error("Scanner configuration is invalid");
  const decryptionKey = await crypto.subtle.importKey("raw", keyBytes, { name: "AES-GCM" }, false, ["decrypt"]);
  const plaintext = await crypto.subtle.decrypt(
    {
      name: "AES-GCM",
      iv: signedPayload.slice(1, 13),
      additionalData: new TextEncoder().encode(PREFIX),
      tagLength: 128,
    },
    decryptionKey,
    signedPayload.slice(13),
  );
  const url = new TextDecoder("utf-8", { fatal: true }).decode(plaintext);
  const parsed = new URL(url);
  if (!["https:", "http:"].includes(parsed.protocol) || parsed.username || parsed.password) {
    throw new Error("Decrypted destination is unsafe");
  }
  return parsed.href;
}

export function ColoraScanner({ aesKeyBase64Url, publicKeyJwk, onDecoded, autoRedirect = true }: ColoraScannerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>();
  const streamRef = useRef<MediaStream>();
  const animationRef = useRef<number>();
  const readerRef = useRef<BrowserQRCodeReader>();
  const handledRef = useRef(false);
  const decodingRef = useRef(false);
  const lastDecodeRef = useRef(0);
  const mountedRef = useRef(true);
  const [status, setStatus] = useState<ScannerStatus>("idle");
  const [message, setMessage] = useState("Ready to discover your COLORA piece");

  const stop = useCallback(() => {
    if (animationRef.current !== undefined) cancelAnimationFrame(animationRef.current);
    animationRef.current = undefined;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = undefined;
    if (videoRef.current) videoRef.current.srcObject = null;
    readerRef.current?.reset();
    decodingRef.current = false;
  }, []);

  const start = useCallback(async () => {
    stop();
    handledRef.current = false;
    lastDecodeRef.current = 0;
    setStatus("requesting");
    setMessage("Opening the rear camera…");

    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("Camera scanning is not supported on this device");
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { exact: "environment" },
          width: { ideal: 1280, max: 1280 },
          height: { ideal: 720, max: 720 },
        },
      });
      if (!mountedRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }

      streamRef.current = stream;
      const video = videoRef.current;
      if (!video) throw new Error("Camera preview is unavailable");
      video.srcObject = stream;
      await video.play();

      const reader = new BrowserQRCodeReader();
      const canvas = document.createElement("canvas");
      const context = canvas.getContext("2d", { alpha: false, willReadFrequently: true });
      if (!context) throw new Error("This browser cannot process camera frames");
      readerRef.current = reader;
      canvasRef.current = canvas;
      setStatus("scanning");
      setMessage("Align the secure code within the frame");

      const scan = async (timestamp: number) => {
        if (handledRef.current || !mountedRef.current) return;
        animationRef.current = requestAnimationFrame(scan);
        if (decodingRef.current || timestamp - lastDecodeRef.current < DECODE_INTERVAL_MS || video.readyState < 2) return;
        lastDecodeRef.current = timestamp;
        decodingRef.current = true;

        try {
          // Convert the visible, central viewfinder back into source-video coordinates.
          // This avoids decoding the obscured pixels and substantially reduces ZXing work.
          const frame = frameRef.current?.getBoundingClientRect();
          const scale = Math.max(window.innerWidth / video.videoWidth, window.innerHeight / video.videoHeight);
          const sourceSide = Math.min((frame?.width ?? 320) / scale, video.videoWidth, video.videoHeight);
          const sourceX = (video.videoWidth - sourceSide) / 2;
          const sourceY = (video.videoHeight - sourceSide) / 2;
          const decodeSide = Math.min(480, Math.max(240, Math.round(sourceSide)));
          if (canvas.width !== decodeSide) canvas.width = decodeSide;
          if (canvas.height !== decodeSide) canvas.height = decodeSide;
          context.drawImage(video, sourceX, sourceY, sourceSide, sourceSide, 0, 0, decodeSide, decodeSide);

          const result = reader.decodeFromCanvas(canvas);
          if (!result || handledRef.current) return;
          handledRef.current = true;
          setStatus("verifying");
          setMessage("Authenticating and decrypting…");
          const url = await openToken(result.getText(), aesKeyBase64Url, publicKeyJwk);
          if (!mountedRef.current) return;
          setStatus("success");
          setMessage("Authentic COLORA piece");
          stop();
          onDecoded?.(url);
          if (autoRedirect) window.setTimeout(() => window.location.assign(url), 450);
        } catch (error) {
          // NotFoundException is ZXing's normal "nothing in this frame" signal.
          if (handledRef.current) {
            handledRef.current = false;
            setStatus("error");
            setMessage(error instanceof Error ? error.message : "The COLORA code could not be verified");
            stop();
          }
        } finally {
          decodingRef.current = false;
        }
      };
      animationRef.current = requestAnimationFrame(scan);
    } catch (error) {
      stop();
      const denied = error instanceof DOMException && error.name === "NotAllowedError";
      const unavailable = error instanceof DOMException && error.name === "OverconstrainedError";
      setStatus("error");
      setMessage(denied ? "Camera access was denied" : unavailable ? "A rear camera is required" : error instanceof Error ? error.message : "Camera access failed");
    }
  }, [aesKeyBase64Url, autoRedirect, onDecoded, publicKeyJwk, stop]);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; stop(); };
  }, [stop]);

  const inactive = status === "idle" || status === "error";
  return (
    <section className="fixed inset-0 isolate overflow-hidden bg-[#020817] text-white" aria-live="polite">
      <video ref={videoRef} muted playsInline className="absolute inset-0 size-full object-cover" aria-label="COLORA secure QR camera preview" />

      <div className="pointer-events-none absolute inset-x-0 top-0 h-[calc(50%-min(39vw,13rem))] bg-[#020817]/65 backdrop-blur-[3px]" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[calc(50%-min(39vw,13rem))] bg-[#020817]/65 backdrop-blur-[3px]" />
      <div className="pointer-events-none absolute left-0 top-1/2 h-[min(78vw,26rem)] w-[calc(50%-min(39vw,13rem))] -translate-y-1/2 bg-[#020817]/65 backdrop-blur-[3px]" />
      <div className="pointer-events-none absolute right-0 top-1/2 h-[min(78vw,26rem)] w-[calc(50%-min(39vw,13rem))] -translate-y-1/2 bg-[#020817]/65 backdrop-blur-[3px]" />

      <header className="pointer-events-none absolute inset-x-0 top-0 z-20 flex flex-col items-center px-6 pt-[max(2rem,env(safe-area-inset-top))] text-center">
        <span className="text-[0.65rem] font-semibold uppercase tracking-[0.5em] text-white/60">Authenticity scanner</span>
        <h1 className="mt-2 text-2xl font-light tracking-[0.35em] text-white">COLORA</h1>
      </header>

      <div
        ref={frameRef}
        className="absolute left-1/2 top-1/2 z-10 size-[min(78vw,26rem)] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-[2rem] ring-1 ring-white/15"
      >
        {(["left-5 top-5 border-l-2 border-t-2", "right-5 top-5 border-r-2 border-t-2", "bottom-5 left-5 border-b-2 border-l-2", "bottom-5 right-5 border-b-2 border-r-2"] as const).map((position) => (
          <span key={position} className={`absolute z-20 size-12 rounded-[0.9rem] border-[#082756] ${position}`} />
        ))}
        {status === "scanning" && <span className="colora-laser absolute inset-x-7 top-7 z-10 h-px bg-cyan-100 shadow-[0_0_5px_1px_#fff,0_0_16px_4px_#1687b8]" />}
      </div>

      {(status === "requesting" || status === "verifying") && (
        <div className="absolute inset-0 z-30 grid place-items-center bg-[#020817]/45 backdrop-blur-sm">
          <span className="size-9 animate-spin rounded-full border border-white/20 border-t-white" aria-hidden="true" />
        </div>
      )}
      {status === "success" && <div className="colora-flash pointer-events-none absolute inset-0 z-40 bg-white" />}

      <footer className="absolute inset-x-0 bottom-0 z-20 flex flex-col items-center px-8 pb-[max(2rem,env(safe-area-inset-bottom))] text-center">
        <p className={`min-h-6 text-sm tracking-wide ${status === "error" ? "text-red-300" : "text-white/75"}`}>{message}</p>
        {inactive && (
          <button type="button" onClick={start} className="mt-5 rounded-full border border-white/20 bg-white px-8 py-3 text-xs font-semibold uppercase tracking-[0.2em] text-[#082756] shadow-2xl transition hover:scale-[1.02] hover:bg-white/90 focus:outline-none focus:ring-2 focus:ring-white/70">
            {status === "idle" ? "Open scanner" : "Try again"}
          </button>
        )}
        <p className="mt-4 text-[0.65rem] uppercase tracking-[0.18em] text-white/35">Encrypted · Verified · Private</p>
      </footer>

      <style jsx>{`
        .colora-laser { animation: colora-scan 2.2s ease-in-out infinite; }
        .colora-flash { animation: colora-flash 480ms ease-out forwards; }
        @keyframes colora-scan { 0%, 100% { top: 1.75rem; opacity: .35; } 50% { top: calc(100% - 1.75rem); opacity: 1; } }
        @keyframes colora-flash { 0% { opacity: .9; } 100% { opacity: 0; } }
        @media (prefers-reduced-motion: reduce) { .colora-laser { animation-duration: 5s; } }
      `}</style>
    </section>
  );
}

export { openToken as decodeColoraToken };
