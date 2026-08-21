"use client";
import { useRouter } from "next/navigation";
import { QRScanner, type QRError } from "@/components/camera/QRScanner";
export default function ScanPage() {
 const router = useRouter();
 return <main className="min-h-screen px-5 py-12"><h1 className="font-display mb-8 text-center text-4xl text-[#c9a84c]">Verify authenticity</h1><QRScanner onSuccess={(data) => router.push(`/passport/${data.product.id}`)} onError={(error: QRError) => { if (error === "invalid") return; }} /></main>;
}
