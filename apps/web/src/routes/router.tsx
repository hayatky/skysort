import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "@/components/layout";
import { DeleteCandidatesRoute } from "@/routes/delete-candidates-route";
import { ExportRoute } from "@/routes/export-route";
import { GroupDetailRoute } from "@/routes/group-detail-route";
import { GroupsRoute } from "@/routes/groups-route";
import { ImportRoute } from "@/routes/import-route";
import { ProgressRoute } from "@/routes/progress-route";
import { ProjectsRoute } from "@/routes/projects-route";
import { ReviewRoute } from "@/routes/review-route";
import { SettingsRoute } from "@/routes/settings-route";

export function AppRouter() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<ProjectsRoute />} />
        <Route path="/import" element={<ImportRoute />} />
        <Route path="/progress" element={<ProgressRoute />} />
        <Route path="/groups" element={<GroupsRoute />} />
        <Route path="/groups/:groupId" element={<GroupDetailRoute />} />
        <Route path="/review" element={<ReviewRoute />} />
        <Route path="/delete-candidates" element={<DeleteCandidatesRoute />} />
        <Route path="/export" element={<ExportRoute />} />
        <Route path="/settings" element={<SettingsRoute />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppLayout>
  );
}
