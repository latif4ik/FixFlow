import { Suspense } from "react";
import { LoadingState } from "@/components/ui";
import { MyRequestsPage } from "@/features/requester/my-requests-page";

// OWNER: W2. The screen lives in src/features/requester/.
export default function Page() {
  return (
    <Suspense fallback={<LoadingState label="Loading requests" />}>
      <MyRequestsPage />
    </Suspense>
  );
}
