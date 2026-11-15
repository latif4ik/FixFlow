// OWNER: W3
import { PropertyDetailPage } from "@/features/dispatch/properties/property-detail";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <PropertyDetailPage propertyId={id} />;
}
