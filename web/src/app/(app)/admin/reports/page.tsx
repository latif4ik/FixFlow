import { Suspense } from "react";
import { ReportsPage } from "@/features/admin/reports-page";

export default function Page() {
  return (
    <Suspense>
      <ReportsPage />
    </Suspense>
  );
}
