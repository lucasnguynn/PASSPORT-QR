import { ColoraScanner } from "@/components/camera/ColoraScanner";

const aesKeyBase64Url = process.env.NEXT_PUBLIC_COLORA_AES_KEY ?? "";
const publicKeyJwk = JSON.parse(
  process.env.NEXT_PUBLIC_COLORA_PUBLIC_KEY_JWK ?? "{}",
) as JsonWebKey;

export default function ScanPage() {
  return (
    <main className="fixed inset-0 h-dvh w-full overflow-hidden overscroll-none bg-black">
      <ColoraScanner
        aesKeyBase64Url={aesKeyBase64Url}
        publicKeyJwk={publicKeyJwk}
      />
    </main>
  );
}
