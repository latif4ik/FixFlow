// OWNER: W3
import { Suspense } from "react";
import { LoadingState } from "@/components/ui";
import { QueuePage } from "@/features/dispatch/queue/queue-page";

export default function Page() {
  return (
    <Suspense fallback={<LoadingState label="Loading queue" />}>
      <QueuePage />
    </Suspense>
  );
}
