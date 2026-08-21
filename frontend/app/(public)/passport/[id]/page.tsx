export default async function PassportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <h1 className="text-2xl font-semibold">Passport {id}</h1>;
}
