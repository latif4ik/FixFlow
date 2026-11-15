// OWNER: W3
import { Suspense } from "react";
import { LoadingState } from "@/components/ui";
import { EstimatesPage } from "@/features/dispatch/estimates/estimates-page";

export default function Page() {
  return (
    <Suspense fallback={<LoadingState label="Loading estimates" />}>
      <EstimatesPage />
    </Suspense>
  );
}
