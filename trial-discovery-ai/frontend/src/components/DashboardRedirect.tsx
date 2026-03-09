import { useRouter } from "next/router";
import { useEffect, useMemo } from "react";

type DashboardRedirectProps = {
  message?: string;
};

export default function DashboardRedirect({
  message = "Redirecting to Acquittify dashboard...",
}: DashboardRedirectProps) {
  const router = useRouter();
  const matterId = useMemo(() => {
    const value = router.query.id;
    return Array.isArray(value) ? value[0] : value || "";
  }, [router.query.id]);

  useEffect(() => {
    if (!router.isReady) return;
    const nextHref = matterId ? `/?case_id=${encodeURIComponent(matterId)}` : "/";
    router.replace(nextHref);
  }, [matterId, router]);

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        background: "#0f0f0f",
        color: "#f3f3f3",
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      }}
    >
      {message}
    </main>
  );
}
