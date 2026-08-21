"use client";
import { BrowserQRCodeReader } from "@zxing/library";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, verifyQR, type PassportData } from "@/lib/api";
import { QRWarning } from "./QRWarning";

export type QRScannerState = "idle" | "requesting_permission" | "scanning" | "verifying" | "success" | "error";
export type QRError = "permission_denied" | "no_camera" | "rate_limited" | "invalid" | "revoked";
export interface QRScannerProps { onSuccess: (passportData: PassportData) => void; onError: (error: QRError) => void; }

function fingerprint(): string {
  return typeof navigator === "undefined" ? "server" : btoa(`${navigator.userAgent}|${screen.width}x${screen.height}`).slice(0, 128);
}
export function QRScanner({ onSuccess, onError }: QRScannerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const readerRef = useRef<BrowserQRCodeReader | undefined>(undefined);
  const handledRef = useRef(false);
  const [state, setState] = useState<QRScannerState>("idle");
  const [externalCode, setExternalCode] = useState(false);
  const report = useCallback((error: QRError) => { setState("error"); onError(error); }, [onError]);
  const start = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) { report("no_camera"); return; }
    setState("requesting_permission"); setExternalCode(false); handledRef.current = false;
    const reader = new BrowserQRCodeReader(); readerRef.current = reader;
    try {
      setState("scanning");
      await reader.decodeFromConstraints({ video: { facingMode: "environment" } }, videoRef.current ?? undefined, async (result) => {
        if (!result || handledRef.current) return;
        handledRef.current = true; reader.stopContinuousDecode();
        const uri = result.getText();
        if (!uri.startsWith("dppassport://")) { setExternalCode(true); report("invalid"); return; }
        const token = uri.slice("dppassport://".length);
        if (!token) { report("invalid"); return; }
        setState("verifying");
        try { const data = await verifyQR(uri, fingerprint()); setState("success"); onSuccess(data); }
        catch (error) {
          if (error instanceof ApiError && error.problem.status === 429) report("rate_limited");
          else if (error instanceof ApiError && /revok/i.test(`${error.problem.title} ${error.problem.detail}`)) report("revoked");
          else report("invalid");
        }
      });
    } catch (error) {
      report(error instanceof DOMException && error.name === "NotAllowedError" ? "permission_denied" : "no_camera");
    }
  }, [onSuccess, report]);
  useEffect(() => () => { readerRef.current?.stopContinuousDecode(); readerRef.current?.reset(); }, []);
  if (externalCode) return <QRWarning />;
  return <section className="mx-auto max-w-lg text-center">
    <div className="relative aspect-square overflow-hidden rounded-3xl border-2 border-[#c9a84c]/70 bg-black">
      <video ref={videoRef} muted playsInline className="size-full object-cover" aria-label="QR camera preview" />
      {state === "scanning" && <div className="scan-line absolute inset-x-6 top-6 h-0.5 bg-[#c9a84c] shadow-[0_0_16px_#c9a84c]" />}
      {(state === "idle" || state === "error") && <div className="absolute inset-0 grid place-items-center bg-black/70"><button className="gold-button" onClick={start}>{state === "idle" ? "Start camera" : "Try again"}</button></div>}
      {(state === "requesting_permission" || state === "verifying") && <div className="absolute inset-0 grid place-items-center bg-black/60 text-[#c9a84c]">{state === "verifying" ? "Verifying signature…" : "Requesting camera…"}</div>}
    </div><p className="mt-4 text-sm capitalize text-zinc-400">{state.replaceAll("_", " ")}</p>
  </section>;
}
