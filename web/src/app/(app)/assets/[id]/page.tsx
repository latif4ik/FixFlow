// OWNER: W3
import { AssetDetailPage } from "@/features/dispatch/properties/asset-detail";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AssetDetailPage assetId={id} />;
}
