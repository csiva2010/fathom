import { EmptyState } from "@/components/feedback/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";

/** Placeholder for tabs that ship later in the build plan. */
export function ComingSoonPage({ title, description }: { title: string; description: string }) {
  return (
    <section>
      <PageHeader title={title} />
      <EmptyState title="Coming soon">{description}</EmptyState>
    </section>
  );
}
