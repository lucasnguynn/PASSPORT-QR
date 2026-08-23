"use client";

import { BrowserQRCodeReader, type IScannerControls } from "@zxing/browser";
import { useCallback, useEffect, useRef, useState } from "react";

const PREFIX = "colora-secure://v1.";
const BASE85_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{|}~";

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
  if (!rawValue.startsWith(PREFIX)) throw new Error("Rejected: this is not a COLORA secure QR code");
  const token = decodeBase85(rawValue.slice(PREFIX.length));
  if (token.length < 1 + 12 + 16 + 64 || token[0] !== 1) throw new Error("Unsupported or truncated COLORA token");

  const signedPayload = token.slice(0, -64);
  const signature = token.slice(-64);
  const verificationKey = await crypto.subtle.importKey("jwk", publicKeyJwk, { name: "ECDSA", namedCurve: "P-256" }, false, ["verify"]);
  const authentic = await crypto.subtle.verify({ name: "ECDSA", hash: "SHA-256" }, verificationKey, signature, signedPayload);
  if (!authentic) throw new Error("Counterfeit QR: invalid COLORA signature");

  const decryptionKey = await crypto.subtle.importKey("raw", decodeBase64Url(aesKeyBase64Url), { name: "AES-GCM" }, false, ["decrypt"]);
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: signedPayload.slice(1, 13), additionalData: new TextEncoder().encode(PREFIX), tagLength: 128 },
    decryptionKey,
    signedPayload.slice(13),
  );
  const url = new TextDecoder("utf-8", { fatal: true }).decode(plaintext);
  const parsed = new URL(url);
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") throw new Error("Decrypted destination is unsafe");
  return parsed.href;
}

export function ColoraScanner({ aesKeyBase64Url, publicKeyJwk, onDecoded, autoRedirect = true }: ColoraScannerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const controlsRef = useRef<IScannerControls>();
  const handledRef = useRef(false);
  const [status, setStatus] = useState<ScannerStatus>("idle");
  const [message, setMessage] = useState("Ready to scan a COLORA secure QR code");

  const stop = useCallback(() => { controlsRef.current?.stop(); controlsRef.current = undefined; }, []);
  const start = useCallback(async () => {
    stop(); handledRef.current = false; setStatus("requesting"); setMessage("Requesting camera permission…");
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("No camera is available");
      const reader = new BrowserQRCodeReader();
      controlsRef.current = await reader.decodeFromConstraints(
        { video: { facingMode: { ideal: "environment" } }, audio: false }, videoRef.current ?? undefined,
        async (result) => {
          if (!result || handledRef.current) return;
          handledRef.current = true; stop(); setStatus("verifying"); setMessage("Verifying COLORA signature…");
          try {
            const url = await openToken(result.getText(), aesKeyBase64Url, publicKeyJwk);
            setStatus("success"); setMessage("Authentic COLORA code. Opening destination…"); onDecoded?.(url);
            if (autoRedirect) window.location.assign(url);
          } catch (error) {
            setStatus("error"); setMessage(error instanceof Error ? error.message : "The QR code could not be verified");
          }
        },
      );
      setStatus("scanning"); setMessage("Hold the QR code inside the frame");
    } catch (error) {
      setStatus("error"); setMessage(error instanceof Error ? error.message : "Camera access failed");
    }
  }, [aesKeyBase64Url, autoRedirect, onDecoded, publicKeyJwk, stop]);

  useEffect(() => stop, [stop]);
  return <section className="mx-auto max-w-lg text-center" aria-live="polite">
    <div className="relative aspect-square overflow-hidden rounded-3xl border-2 border-[#c9a84c] bg-black">
      <video ref={videoRef} muted playsInline className="size-full object-cover" aria-label="COLORA QR camera preview" />
      {status === "scanning" && <div className="scan-line absolute inset-x-6 top-6 h-0.5 bg-[#c9a84c]" />}
      {(status === "idle" || status === "error") && <div className="absolute inset-0 grid place-items-center bg-black/70">
        <button type="button" className="gold-button" onClick={start}>{status === "idle" ? "Start COLORA scanner" : "Try again"}</button>
      </div>}
    </div>
    <p className={status === "error" ? "mt-4 text-sm text-red-400" : "mt-4 text-sm text-zinc-400"}>{message}</p>
  </section>;
}

export { openToken as decodeColoraToken };
