// OWNER: W3
import { Suspense } from "react";
import { LoadingState } from "@/components/ui";
import { SchedulePage } from "@/features/dispatch/schedule/schedule-page";

export default function Page() {
  return (
    <Suspense fallback={<LoadingState label="Loading schedule" />}>
      <SchedulePage />
    </Suspense>
  );
}
