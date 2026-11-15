import { motion } from "motion/react";
import { useEffect, type ReactNode } from "react";

/** Sets the document title and gives route changes one quiet, shared entrance. */
export function Page({ title, children, className = "" }: { title: string; children: ReactNode; className?: string }) {
  useEffect(() => {
    document.title = title === "Opportunity Hub" ? title : `${title} — Opportunity Hub`;
  }, [title]);
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/** Standard application content column. */
export function Content({ children, width = "default" }: { children: ReactNode; width?: "default" | "narrow" | "wide" }) {
  const max = width === "narrow" ? "max-w-[760px]" : width === "wide" ? "max-w-[1240px]" : "max-w-[1080px]";
  return <div className={`mx-auto w-full ${max} px-4 py-6 sm:px-8 sm:py-10`}>{children}</div>;
}
