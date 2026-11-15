// OWNER: W3
import { Suspense } from "react";
import { LoadingState } from "@/components/ui";
import { PropertiesPage } from "@/features/dispatch/properties/properties-page";

export default function Page() {
  return (
    <Suspense fallback={<LoadingState label="Loading properties" />}>
      <PropertiesPage />
    </Suspense>
  );
}
