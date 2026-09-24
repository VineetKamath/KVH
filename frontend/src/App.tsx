import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Skeleton } from "./components/ui";
import TravellerLayout from "./pages/traveller/TravellerLayout";
import Search from "./pages/traveller/Search";
import PricePass from "./pages/traveller/PricePass";

const Desk = lazy(() => import("./pages/admin/Desk"));

export default function App() {
  return (
    <Routes>
      <Route element={<TravellerLayout />}>
        <Route index element={<Search />} />
        <Route path="pass/:roomId" element={<PricePass />} />
      </Route>
      <Route path="desk/*" element={<Suspense fallback={<div className="p-10"><Skeleton lines={6} /></div>}><Desk /></Suspense>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
