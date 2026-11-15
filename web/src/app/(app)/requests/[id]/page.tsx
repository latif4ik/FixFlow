import { RequestDetailPage } from "@/features/request-detail/request-detail-page";

// Owner: W1 (shared by requester and staff). Role-specific actions plug in via src/features/request-actions/.
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <RequestDetailPage requestId={id} />;
}
