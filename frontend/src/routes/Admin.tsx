/**
 * The admin console: the platform at a glance, the people on it, what has been
 * done (the audit log), and the health of its moving parts. Admin-only; the API
 * enforces that too (every /admin route needs the user.manage permission).
 *
 * Every figure is counted live from the database by the API. There is no
 * page-view tracking on the site, so the console says so instead of showing
 * traffic numbers it doesn't have.
 */
import { ArrowRight, Search, ShieldAlert, UserRound } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { ApiError } from "../api/client";
import {
  useAdminActivity,
  useAdminOverview,
  useAdminUser,
  useAdminUserAction,
  useAdminUsers,
  useUserAccount,
  type AdminUserAction,
  type AdminUserQuery,
} from "../api/queries";
import type { components } from "../api/schema";
import { PageHeader } from "../components/layout/AppShell";
import { Content, Page } from "../components/layout/Page";
import { Pagination } from "../components/ui/Pagination";
import { Sheet } from "../components/ui/Sheet";
import { EmptyState, ErrorState, Spinner } from "../components/ui/States";
import { STATUS_LABELS, formatDate, formatDateTime, plural } from "../lib/format";

type Schemas = components["schemas"];
type Overview = Schemas["AdminOverview"];
type NamedCount = Schemas["NamedCount"];
type UserRow = Schemas["AdminUserRow"];
type UserDetail = Schemas["AdminUserDetail"];
type AuditEntry = Schemas["AuditEntryRead"];

const TABS = [
  ["overview", "Overview"],
  ["users", "Users"],
  ["activity", "Activity"],
  ["system", "System"],
] as const;
type Tab = (typeof TABS)[number][0];

const humanise = (key: string) => (key.charAt(0).toUpperCase() + key.slice(1)).replace(/_/g, " ");
const verdictLabel = (key: string) => (STATUS_LABELS as Record<string, string>)[key] ?? humanise(key);
const ACTION_LABELS: Record<string, string> = {
  "user.role_changed": "Role changed",
  "user.suspended": "Account suspended",
  "user.reactivated": "Account reactivated",
  "user.sessions_revoked": "Signed out everywhere",
  "user.password_reset": "Password reset",
  "user.email_verified": "Email verified",
};
const actionLabel = (action: string) => ACTION_LABELS[action] ?? humanise(action.replace(/\./g, " · "));

function timeAgo(value: string | null | undefined): string {
  if (!value) return "Never";
  const seconds = Math.max(0, (Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 60) return "Just now";
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.floor(minutes)} min ago`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.floor(hours)} h ago`;
  const days = hours / 24;
  if (days < 30) return `${Math.floor(days)} d ago`;
  return formatDate(value);
}

const percent = (part: number, whole: number) => (whole ? `${Math.round((part / whole) * 100)}%` : "–");

/* ------------------------------------------------------------------------ */
/* Shell                                                                     */
/* ------------------------------------------------------------------------ */

export function Admin() {
  const account = useUserAccount();
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find(([key]) => key === params.get("tab"))?.[0] ?? "overview") as Tab;
  const [openUser, setOpenUser] = useState<string | null>(null);

  if (account.isPending) {
    return (
      <Page title="Admin">
        <Content width="wide">
          <div className="flex items-center gap-2 py-24 text-muted">
            <Spinner /> Checking your access…
          </div>
        </Content>
      </Page>
    );
  }
  if (account.data?.role !== "admin") {
    return (
      <Page title="Admin">
        <Content width="narrow">
          <EmptyState
            icon={ShieldAlert}
            title="Admins only"
            action={
              account.data?.role === "curator" ? (
                <Link to="/curate" className="btn btn-quiet">
                  Open the curator workspace
                </Link>
              ) : (
                <Link to="/discover" className="btn btn-quiet">
                  Back to Discover
                </Link>
              )
            }
          >
            The admin console is for administrators. Roles are granted by another admin.
          </EmptyState>
        </Content>
      </Page>
    );
  }

  return (
    <Page title="Admin">
      <Content width="wide">
        <PageHeader
          kicker="Administration"
          title="Admin console"
          description="Who is on the platform, what they do, and how the system is running. Every figure is counted live from the database."
          actions={
            <Link to="/curate" className="btn btn-quiet">
              Curator workspace
              <ArrowRight size={15} />
            </Link>
          }
        />
        <nav aria-label="Admin sections" className="mt-8 flex gap-7 overflow-x-auto border-b border-rule [scrollbar-width:none]">
          {TABS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              aria-pressed={tab === key}
              onClick={() => setParams(key === "overview" ? {} : { tab: key }, { replace: false })}
              className="index-tab shrink-0"
            >
              {label}
              {tab === key && <span className="absolute inset-x-0 -bottom-px h-[2px] bg-ink" aria-hidden="true" />}
            </button>
          ))}
        </nav>
        <div className="mt-8">
          {tab === "overview" && <OverviewTab />}
          {tab === "users" && <UsersTab onOpenUser={setOpenUser} />}
          {tab === "activity" && <ActivityTab onOpenUser={setOpenUser} />}
          {tab === "system" && <SystemTab />}
        </div>
      </Content>
      <UserSheet id={openUser} selfId={account.data.id} onClose={() => setOpenUser(null)} />
    </Page>
  );
}

/* ------------------------------------------------------------------------ */
/* Overview                                                                  */
/* ------------------------------------------------------------------------ */

function Stat({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="border-t-2 border-ink pt-3">
      <p className="text-[12.5px] font-semibold uppercase tracking-[0.08em] text-muted">{label}</p>
      <p className="num mt-1.5 text-[34px] font-semibold leading-none tracking-[-0.02em] text-ink">{value}</p>
      {note && <p className="mt-2 text-[13px] text-ink-soft">{note}</p>}
    </div>
  );
}

function Panel({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="rounded-[14px] border border-rule bg-paper p-5 sm:p-6" aria-label={title}>
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="heading text-[18px] text-ink">{title}</h2>
        {aside}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

/** A single-series bar chart: one hue (the validated cobalt token), a tooltip per bar, and a table view. */
function SignupsChart({ days }: { days: Schemas["DayCount"][] }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...days.map((d) => d.count));
  const W = 600;
  const H = 150;
  const gap = 2;
  const bw = W / days.length - gap;
  const total = days.reduce((sum, d) => sum + d.count, 0);
  const bar = (x: number, h: number) => {
    const r = Math.min(3, bw / 2, h);
    const y = H - h;
    return h <= 0 ? "" : `M${x},${H} V${y + r} Q${x},${y} ${x + r},${y} H${x + bw - r} Q${x + bw},${y} ${x + bw},${y + r} V${H} Z`;
  };
  const active = hover === null ? null : days[hover];
  return (
    <div>
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H + 1}`} className="block h-[150px] w-full" role="img" aria-label={`Sign-ups per day over the last 30 days: ${total} in total, at most ${max} on one day.`} preserveAspectRatio="none" onMouseLeave={() => setHover(null)}>
          <line x1="0" x2={W} y1={H / 2} y2={H / 2} stroke="var(--color-rule)" strokeDasharray="3 4" vectorEffect="non-scaling-stroke" />
          {days.map((d, i) => {
            const x = i * (bw + gap);
            const h = (d.count / max) * (H - 6);
            return (
              <g key={d.day}>
                <path d={bar(x, h)} fill="var(--color-cobalt)" opacity={hover === null || hover === i ? 1 : 0.45} />
                <rect x={x - gap / 2} y={0} width={bw + gap} height={H} fill="transparent" onMouseEnter={() => setHover(i)} />
              </g>
            );
          })}
          <line x1="0" x2={W} y1={H + 0.5} y2={H + 0.5} stroke="var(--color-rule-strong)" vectorEffect="non-scaling-stroke" />
        </svg>
        {active && hover !== null && (
          <div
            className="pointer-events-none absolute top-0 -translate-x-1/2 -translate-y-[calc(100%+6px)] whitespace-nowrap rounded-[8px] border border-rule bg-paper px-2.5 py-1.5 text-[12.5px] text-ink shadow-[0_4px_14px_rgb(0_0_0/0.12)]"
            style={{ left: `${((hover + 0.5) / days.length) * 100}%` }}
          >
            <span className="font-semibold">{plural(active.count, "sign-up")}</span> · {formatDate(active.day)}
          </div>
        )}
      </div>
      <div className="mt-2 flex justify-between text-[12px] text-muted">
        <span>{formatDate(days[0]!.day)}</span>
        <span>Peak {max} a day</span>
        <span>{formatDate(days[days.length - 1]!.day)}</span>
      </div>
      <details className="mt-3 text-[13px]">
        <summary className="cursor-pointer text-ink-soft">Show as a table</summary>
        <table className="mt-2 w-full text-left">
          <thead>
            <tr className="text-muted">
              <th className="py-1 font-medium">Day</th>
              <th className="py-1 text-right font-medium">Sign-ups</th>
            </tr>
          </thead>
          <tbody>
            {days.map((d) => (
              <tr key={d.day} className="border-t border-rule">
                <td className="py-1">{formatDate(d.day)}</td>
                <td className="num py-1 text-right">{d.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

/** Horizontal bars for a breakdown: one hue, each bar labelled with its name and value (no legend needed). */
function Breakdown({ rows, label = humanise, empty = "Nothing yet." }: { rows: NamedCount[]; label?: (key: string) => string; empty?: string }) {
  const total = rows.reduce((sum, r) => sum + r.count, 0);
  const max = Math.max(1, ...rows.map((r) => r.count));
  if (!rows.length) return <p className="text-[14px] text-muted">{empty}</p>;
  return (
    <ul className="flex flex-col gap-3">
      {rows.map((row) => (
        <li key={row.key} title={`${label(row.key)}: ${row.count} (${percent(row.count, total)})`}>
          <div className="flex items-baseline justify-between gap-3 text-[13.5px]">
            <span className="text-ink">{label(row.key)}</span>
            <span className="num text-ink-soft">
              {row.count.toLocaleString()} <span className="text-muted">· {percent(row.count, total)}</span>
            </span>
          </div>
          <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-ink/[0.07]" aria-hidden="true">
            <div className="h-full rounded-full bg-cobalt" style={{ width: `${(row.count / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function TopList({ rows, unit }: { rows: Schemas["TopOpportunity"][]; unit: string }) {
  if (!rows.length) return <p className="text-[14px] text-muted">Nothing yet.</p>;
  return (
    <ol className="divide-y divide-rule">
      {rows.map((row, i) => (
        <li key={row.id} className="flex items-baseline gap-3 py-2.5">
          <span className="num w-5 shrink-0 text-[13px] text-muted">{i + 1}</span>
          <Link to={`/opportunities/${row.id}`} className="min-w-0 flex-1 truncate text-[14px] text-ink hover:underline">
            {row.title}
          </Link>
          <span className="num shrink-0 text-[13px] text-ink-soft">{plural(row.count, unit)}</span>
        </li>
      ))}
    </ol>
  );
}

function OverviewTab() {
  const overview = useAdminOverview();
  if (overview.isPending) return <OverviewSkeleton />;
  if (overview.isError) return <ErrorState message="The overview couldn’t load." onRetry={() => overview.refetch()} />;
  const o: Overview = overview.data;
  const published = o.catalogue.opportunities_by_status.find((r) => r.key === "published")?.count ?? 0;
  const awaiting = o.catalogue.candidates_by_state.find((r) => r.key === "needs_review")?.count ?? 0;
  return (
    <div className="flex flex-col gap-8">
      <div className="grid grid-cols-2 gap-x-6 gap-y-7 lg:grid-cols-3 xl:grid-cols-6">
        <Stat label="Users" value={o.users.total.toLocaleString()} note={`+${o.users.new_7d} this week · +${o.users.new_30d} in 30 days`} />
        <Stat label="Active, 7 days" value={o.activity.active_7d.toLocaleString()} note={`${percent(o.activity.active_7d, o.users.total)} of users · ${o.activity.active_1d} today`} />
        <Stat label="Profiles" value={o.users.with_profile.toLocaleString()} note={`${percent(o.users.with_profile, o.users.total)} of users finished onboarding`} />
        <Stat label="Eligibility checks" value={o.engagement.eligibility_checks.toLocaleString()} note={`for ${plural(o.engagement.profiles_checked, "profile")}`} />
        <Stat label="Applications tracked" value={o.engagement.applications.toLocaleString()} note={`${o.engagement.saved.toLocaleString()} saved by ${plural(o.engagement.profiles_saving, "person", "people")}`} />
        <Stat
          label="Published"
          value={published.toLocaleString()}
          note={
            awaiting ? (
              <Link to="/curate" className="underline underline-offset-2">
                {plural(awaiting, "candidate")} awaiting review
              </Link>
            ) : (
              "opportunities live"
            )
          }
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <Panel title="Sign-ups, last 30 days" aside={<span className="num text-[13px] text-muted">{o.activity.signups_30d.reduce((s, d) => s + d.count, 0)} total</span>}>
          <SignupsChart days={o.activity.signups_30d} />
        </Panel>
        <Panel title="Active people">
          <Breakdown
            rows={[
              { key: "Last 24 hours", count: o.activity.active_1d },
              { key: "Last 7 days", count: o.activity.active_7d },
              { key: "Last 30 days", count: o.activity.active_30d },
            ]}
            label={(k) => k}
          />
          <p className="mt-4 text-[12.5px] leading-relaxed text-muted">
            People with signed-in activity in each window. {o.activity.open_sessions} sessions are open now. Page views and anonymous visitors aren’t tracked on this site.
          </p>
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="Eligibility verdicts">
          <Breakdown rows={o.engagement.verdicts} label={verdictLabel} empty="No checks have run yet." />
        </Panel>
        <Panel title="Applications by stage">
          <Breakdown rows={o.engagement.applications_by_status} empty="No applications tracked yet." />
        </Panel>
        <Panel title="Accounts">
          <Breakdown
            rows={[
              ...o.users.by_role.map((r) => ({ key: `${humanise(r.key)}s`, count: r.count })),
              { key: "Signed in with Google", count: o.users.with_google },
              { key: "Email verified", count: o.users.verified_email },
              { key: "Suspended", count: o.users.suspended },
              { key: "Deletion requested", count: o.users.pending_deletion },
            ]}
            label={(k) => k}
          />
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Most saved">
          <TopList rows={o.engagement.most_saved} unit="save" />
        </Panel>
        <Panel title="Most tracked">
          <TopList rows={o.engagement.most_tracked} unit="application" />
        </Panel>
      </div>
      <p className="text-[12.5px] text-muted">Counted {formatDateTime(o.generated_at)}. Refreshes when you return to this tab.</p>
    </div>
  );
}

function OverviewSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading the overview" className="flex flex-col gap-8">
      <div className="grid grid-cols-2 gap-6 lg:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="border-t-2 border-rule pt-3">
            <div className="skeleton h-3 w-20" />
            <div className="skeleton mt-3 h-8 w-16" />
          </div>
        ))}
      </div>
      <div className="skeleton h-64 w-full rounded-[14px]" />
    </div>
  );
}

/* ------------------------------------------------------------------------ */
/* Users                                                                     */
/* ------------------------------------------------------------------------ */

const PAGE_SIZE = 25;

function RoleBadge({ role }: { role: string }) {
  const tone = role === "admin" ? "bg-ink text-ivory" : role === "curator" ? "bg-cobalt/12 text-cobalt-deep" : "bg-ink/[0.06] text-ink-soft";
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11.5px] font-semibold ${tone}`}>{humanise(role)}</span>;
}

function StatusText({ user }: { user: Pick<UserRow, "is_active" | "deletion_due_at"> }) {
  if (!user.is_active) return <span className="text-[13px] font-medium text-ineligible-ink">● Suspended</span>;
  if (user.deletion_due_at) return <span className="text-[13px] font-medium text-potential-ink">◐ Deletion pending</span>;
  return <span className="text-[13px] text-ink-soft">○ Active</span>;
}

function UsersTab({ onOpenUser }: { onOpenUser: (id: string) => void }) {
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [role, setRole] = useState<AdminUserQuery["role"]>();
  const [state, setState] = useState<AdminUserQuery["state"]>();
  const [sort, setSort] = useState<NonNullable<AdminUserQuery["sort"]>>("newest");
  const [page, setPage] = useState(1);
  // Search as you type, once typing pauses.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQ(search.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search]);
  const query = useMemo<AdminUserQuery>(() => ({ q: q || undefined, role, state, sort, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }), [q, role, state, sort, page]);
  const users = useAdminUsers(query);
  const pageCount = Math.max(1, Math.ceil((users.data?.total ?? 0) / PAGE_SIZE));

  return (
    <div>
      <div className="flex flex-col gap-3 md:flex-row md:items-end">
        <div className="relative flex-1">
          <label htmlFor="user-search" className="field-label">
            Search
          </label>
          <Search size={16} className="pointer-events-none absolute bottom-3.5 left-3 text-muted" aria-hidden="true" />
          <input id="user-search" type="search" className="input pl-9" placeholder="Name or email" value={search} onChange={(event) => setSearch(event.target.value)} />
        </div>
        <Select id="user-role" label="Role" value={role ?? ""} onChange={(value) => { setRole((value || undefined) as AdminUserQuery["role"]); setPage(1); }} options={[["", "All roles"], ["student", "Students"], ["curator", "Curators"], ["admin", "Admins"]]} />
        <Select id="user-state" label="Status" value={state ?? ""} onChange={(value) => { setState((value || undefined) as AdminUserQuery["state"]); setPage(1); }} options={[["", "Any status"], ["active", "Active"], ["suspended", "Suspended"], ["pending_deletion", "Deletion pending"]]} />
        <Select id="user-sort" label="Sort" value={sort} onChange={(value) => { setSort(value as typeof sort); setPage(1); }} options={[["newest", "Newest first"], ["oldest", "Oldest first"], ["last_active", "Recently active"], ["email", "Email A–Z"]]} />
      </div>

      <p className="mt-5 text-[13.5px] text-muted" aria-live="polite">
        {users.data ? `${plural(users.data.total, "account")}${q ? ` matching “${q}”` : ""}` : "Loading…"}
      </p>

      {users.isError ? (
        <div className="mt-4">
          <ErrorState message="The user list couldn’t load." onRetry={() => users.refetch()} />
        </div>
      ) : users.data && users.data.items.length === 0 ? (
        <div className="mt-6">
          <EmptyState icon={UserRound} title="No accounts match">
            Try a different search or clear the filters.
          </EmptyState>
        </div>
      ) : (
        <div className={`mt-3 transition-opacity ${users.isPlaceholderData ? "opacity-60" : ""}`}>
          <table className="w-full border-separate border-spacing-0 text-left">
            <thead className="hidden md:table-header-group">
              <tr className="text-[12px] uppercase tracking-[0.08em] text-muted">
                <th className="border-b border-ink py-2.5 pr-3 font-semibold">Person</th>
                <th className="border-b border-ink py-2.5 pr-3 font-semibold">Role</th>
                <th className="border-b border-ink py-2.5 pr-3 font-semibold">Status</th>
                <th className="border-b border-ink py-2.5 pr-3 font-semibold">Joined</th>
                <th className="border-b border-ink py-2.5 pr-3 font-semibold">Last active</th>
                <th className="border-b border-ink py-2.5 pr-3 text-right font-semibold">Saved</th>
                <th className="border-b border-ink py-2.5 text-right font-semibold">Applications</th>
              </tr>
            </thead>
            <tbody>
              {(users.data?.items ?? []).map((user) => (
                <tr key={user.id} className="group block border-b border-rule py-3 md:table-row md:py-0">
                  <td className="block md:table-cell md:border-b md:border-rule md:py-3 md:pr-3">
                    <button type="button" onClick={() => onOpenUser(user.id)} className="text-left">
                      <span className="block text-[14.5px] font-semibold text-ink group-hover:underline">{user.full_name || user.email}</span>
                      {user.full_name && <span className="block text-[13px] text-muted">{user.email}</span>}
                    </button>
                  </td>
                  <td className="mt-1.5 inline-block md:mt-0 md:table-cell md:border-b md:border-rule md:py-3 md:pr-3">
                    <RoleBadge role={user.role} />
                  </td>
                  <td className="ml-3 inline-block md:ml-0 md:table-cell md:border-b md:border-rule md:py-3 md:pr-3">
                    <StatusText user={user} />
                  </td>
                  <td className="hidden text-[13.5px] text-ink-soft md:table-cell md:border-b md:border-rule md:py-3 md:pr-3">{formatDate(user.created_at)}</td>
                  <td className="mt-1 block text-[13px] text-ink-soft md:mt-0 md:table-cell md:border-b md:border-rule md:py-3 md:pr-3 md:text-[13.5px]">
                    <span className="md:hidden">Last active </span>
                    {timeAgo(user.last_active_at)}
                  </td>
                  <td className="num hidden text-right text-[13.5px] text-ink-soft md:table-cell md:border-b md:border-rule md:py-3 md:pr-3">{user.saved_count}</td>
                  <td className="num hidden text-right text-[13.5px] text-ink-soft md:table-cell md:border-b md:border-rule md:py-3">{user.applications_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {pageCount > 1 && (
            <div className="mt-6">
              <Pagination page={page} pageCount={pageCount} onChange={setPage} label="User pages" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Select({ id, label, value, onChange, options }: { id: string; label: string; value: string; onChange: (value: string) => void; options: [string, string][] }) {
  return (
    <div className="md:w-44">
      <label htmlFor={id} className="field-label">
        {label}
      </label>
      <select id={id} className="input" value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map(([v, text]) => (
          <option key={v} value={v}>
            {text}
          </option>
        ))}
      </select>
    </div>
  );
}

/* ------------------------------------------------------------------------ */
/* One user                                                                  */
/* ------------------------------------------------------------------------ */

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-rule py-2 text-[13.5px]">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right text-ink">{children}</dd>
    </div>
  );
}

function UserSheet({ id, selfId, onClose }: { id: string | null; selfId: string; onClose: () => void }) {
  const user = useAdminUser(id || null);
  const data = user.data;
  return (
    <Sheet open={Boolean(id)} onClose={onClose} title={data ? data.full_name || data.email : "Account"} placement="right">
      {!id ? null : user.isPending ? (
        <div className="flex items-center gap-2 py-10 text-muted">
          <Spinner /> Loading the account…
        </div>
      ) : user.isError || !data ? (
        <ErrorState message="This account couldn’t load." onRetry={() => user.refetch()} />
      ) : (
        <UserDetailView user={data} isSelf={data.id === selfId} />
      )}
    </Sheet>
  );
}

function UserDetailView({ user, isSelf }: { user: UserDetail; isSelf: boolean }) {
  return (
    <div className="flex flex-col gap-7">
      <div>
        {user.full_name && <p className="text-[14px] text-ink-soft">{user.email}</p>}
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <RoleBadge role={user.role} />
          <StatusText user={user} />
        </div>
      </div>

      <dl>
        <Fact label="Joined">{formatDateTime(user.created_at)}</Fact>
        <Fact label="Last active">{timeAgo(user.last_active_at)}</Fact>
        <Fact label="Email verified">{user.email_verified_at ? formatDate(user.email_verified_at) : "No"}</Fact>
        <Fact label="Signs in with">{[user.has_password && "Password", user.google_linked && `Google${user.google_email ? ` (${user.google_email})` : ""}`].filter(Boolean).join(" · ") || "No method set"}</Fact>
        <Fact label="Profile">{user.has_profile ? "Completed" : "Not started"}</Fact>
        <Fact label="Eligibility checks">{user.matches_count}</Fact>
        <Fact label="Saved · Applications">
          {user.saved_count} · {user.applications_count}
        </Fact>
        {user.deletion_due_at && <Fact label="Deletion due">{formatDate(user.deletion_due_at)}</Fact>}
      </dl>

      {isSelf ? (
        <p className="rounded-[10px] border border-rule bg-cream px-4 py-3 text-[13.5px] text-ink-soft">This is your account. Role and status changes to it have to be made by another admin.</p>
      ) : (
        <AccountActions user={user} />
      )}

      <section aria-labelledby="sessions-heading">
        <h3 id="sessions-heading" className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted">
          Open sessions
        </h3>
        {user.sessions.length === 0 ? (
          <p className="mt-2 text-[13.5px] text-muted">Not signed in anywhere.</p>
        ) : (
          <ul className="mt-2 divide-y divide-rule">
            {user.sessions.map((session) => (
              <li key={session.id} className="flex items-baseline justify-between gap-3 py-2 text-[13.5px]">
                <span className="text-ink">{session.device ?? "Unknown device"}</span>
                <span className="text-right text-muted">
                  {timeAgo(session.last_seen_at)}
                  {session.network ? ` · ${session.network}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-[12px] text-muted">Networks are shown, never full IP addresses.</p>
      </section>

      <section aria-labelledby="history-heading">
        <h3 id="history-heading" className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted">
          Account history
        </h3>
        {user.history.length === 0 ? <p className="mt-2 text-[13.5px] text-muted">Nothing recorded yet.</p> : <AuditList entries={user.history} />}
      </section>
    </div>
  );
}

function AccountActions({ user }: { user: UserDetail }) {
  const action = useAdminUserAction(user.id);
  const [reason, setReason] = useState("");
  const [role, setRole] = useState(user.role as "student" | "curator" | "admin");
  const [confirmSuspend, setConfirmSuspend] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  useEffect(() => setRole(user.role as typeof role), [user.role]);
  const reasonOk = reason.trim().length >= 3;
  const error = action.error instanceof ApiError ? action.error.message : action.error ? "That didn’t go through. Try again." : null;

  async function run(next: AdminUserAction, message: string) {
    setDone(null);
    try {
      await action.mutateAsync(next);
      setDone(message);
      setReason("");
      setConfirmSuspend(false);
    } catch {
      /* shown below */
    }
  }

  return (
    <section aria-labelledby="actions-heading" className="rounded-[12px] border border-rule p-4">
      <h3 id="actions-heading" className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted">
        Account actions
      </h3>
      <label htmlFor="action-reason" className="field-label mt-3">
        Reason <span className="font-normal text-muted">(required, saved in the audit log)</span>
      </label>
      <textarea id="action-reason" className="input" rows={2} maxLength={500} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="e.g. Joining the review team" />

      <div className="mt-4 flex flex-wrap items-end gap-2">
        <div className="min-w-[10rem] flex-1">
          <label htmlFor="action-role" className="field-label">
            Role
          </label>
          <select id="action-role" className="input" value={role} onChange={(event) => setRole(event.target.value as typeof role)}>
            <option value="student">Student</option>
            <option value="curator">Curator</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <button type="button" className="btn btn-ink" disabled={!reasonOk || role === user.role || action.isPending} onClick={() => run({ kind: "role", role, reason: reason.trim() }, `Role changed to ${role}.`)}>
          Change role
        </button>
      </div>

      <div className="mt-4 flex flex-wrap gap-2 border-t border-rule pt-4">
        {user.is_active ? (
          confirmSuspend ? (
            <>
              <button type="button" className="btn btn-sm bg-ineligible text-white" disabled={!reasonOk || action.isPending} onClick={() => run({ kind: "status", active: false, reason: reason.trim() }, "Account suspended and signed out everywhere.")}>
                Confirm suspension
              </button>
              <button type="button" className="btn btn-sm btn-ghost" onClick={() => setConfirmSuspend(false)}>
                Cancel
              </button>
            </>
          ) : (
            <button type="button" className="btn btn-sm btn-quiet" disabled={!reasonOk || action.isPending} onClick={() => setConfirmSuspend(true)}>
              Suspend account…
            </button>
          )
        ) : (
          <button type="button" className="btn btn-sm btn-quiet" disabled={!reasonOk || action.isPending} onClick={() => run({ kind: "status", active: true, reason: reason.trim() }, "Account reactivated.")}>
            Reactivate account
          </button>
        )}
        <button type="button" className="btn btn-sm btn-quiet" disabled={!reasonOk || action.isPending || user.sessions.length === 0} onClick={() => run({ kind: "signout", reason: reason.trim() }, "Signed out of every device.")}>
          Sign out everywhere
        </button>
      </div>
      {!reasonOk && <p className="mt-3 text-[12.5px] text-muted">Write a reason to enable these actions.</p>}
      {confirmSuspend && <p className="mt-3 text-[12.5px] text-ineligible-ink">Suspending signs them out at once and blocks sign-in until reactivated.</p>}
      <p className="mt-2 text-[13px]" role="status" aria-live="polite">
        {action.isPending ? "Saving…" : done ? <span className="text-eligible-ink">✓ {done}</span> : null}
      </p>
      {error && (
        <p role="alert" className="mt-1 text-[13px] text-ineligible-ink">
          {error}
        </p>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------------ */
/* Activity                                                                  */
/* ------------------------------------------------------------------------ */

function describeChanges(changes: Record<string, unknown>): string {
  return Object.entries(changes)
    .map(([key, value]) => {
      if (value && typeof value === "object" && "from" in value && "to" in value) {
        const v = value as { from: unknown; to: unknown };
        return `${humanise(key)}: ${String(v.from)} → ${String(v.to)}`;
      }
      return `${humanise(key)}: ${typeof value === "object" ? JSON.stringify(value) : String(value)}`;
    })
    .join(" · ");
}

function AuditList({ entries, onOpenUser }: { entries: AuditEntry[]; onOpenUser?: (id: string) => void }) {
  return (
    <ul className="divide-y divide-rule">
      {entries.map((entry) => (
        <li key={entry.id} className="grid gap-1 py-3 text-[13.5px] sm:grid-cols-[150px_minmax(0,1fr)] sm:gap-4">
          <span className="num text-[12.5px] text-muted">{formatDateTime(entry.occurred_at)}</span>
          <div className="min-w-0">
            <p className="font-semibold text-ink">{actionLabel(entry.action)}</p>
            <p className="mt-0.5 text-ink-soft">
              {entry.target_type === "user" && onOpenUser ? (
                <button type="button" className="underline underline-offset-2" onClick={() => onOpenUser(entry.target_id)}>
                  Open the account
                </button>
              ) : (
                <span>
                  {humanise(entry.target_type)} <span className="num text-muted">{entry.target_id.slice(0, 8)}</span>
                </span>
              )}
              <span className="text-muted">
                {" "}
                · by {entry.actor_kind === "user" ? "a signed-in user" : entry.actor_kind === "cli" ? "an operator command" : "the system"}
              </span>
              {entry.actor_user_id && onOpenUser && (
                <>
                  {" "}
                  <button type="button" className="text-muted underline underline-offset-2" onClick={() => onOpenUser(entry.actor_user_id!)}>
                    (who)
                  </button>
                </>
              )}
            </p>
            {Object.keys(entry.changes).length > 0 && <p className="mt-0.5 break-words text-[12.5px] text-muted">{describeChanges(entry.changes)}</p>}
            {entry.reason && <p className="mt-0.5 text-[12.5px] text-ink-soft">“{entry.reason}”</p>}
          </div>
        </li>
      ))}
    </ul>
  );
}

function ActivityTab({ onOpenUser }: { onOpenUser: (id: string) => void }) {
  const [targetType, setTargetType] = useState("");
  const [action, setAction] = useState("");
  const activity = useAdminActivity({ action, targetType });
  const entries = activity.data?.pages.flat() ?? [];
  return (
    <div>
      <div className="flex flex-col gap-3 md:flex-row md:items-end">
        <Select id="activity-target" label="About" value={targetType} onChange={setTargetType} options={[["", "Everything"], ["user", "Accounts"], ["opportunity", "Opportunities"], ["acquisition_source", "Sources"], ["ingestion_candidate", "Candidates"]]} />
        <Select id="activity-action" label="Action" value={action} onChange={setAction} options={[["", "Any action"], ...Object.entries(ACTION_LABELS)]} />
        <p className="text-[13px] text-muted md:ml-auto md:pb-3">The audit log is append-only: entries can’t be edited or deleted.</p>
      </div>
      <div className="mt-5">
        {activity.isPending ? (
          <div className="flex items-center gap-2 py-10 text-muted">
            <Spinner /> Loading activity…
          </div>
        ) : activity.isError ? (
          <ErrorState message="The activity log couldn’t load." onRetry={() => activity.refetch()} />
        ) : entries.length === 0 ? (
          <EmptyState icon={ShieldAlert} title="Nothing recorded">
            No audit entries match these filters.
          </EmptyState>
        ) : (
          <>
            <AuditList entries={entries} onOpenUser={onOpenUser} />
            {activity.hasNextPage && (
              <button type="button" className="btn btn-quiet mt-5" onClick={() => activity.fetchNextPage()} disabled={activity.isFetchingNextPage}>
                {activity.isFetchingNextPage ? <Spinner size={14} /> : null} Load older entries
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------------ */
/* System                                                                    */
/* ------------------------------------------------------------------------ */

function SystemTab() {
  const overview = useAdminOverview();
  if (overview.isPending) return <OverviewSkeleton />;
  if (overview.isError) return <ErrorState message="System status couldn’t load." onRetry={() => overview.refetch()} />;
  const o = overview.data;
  const failedEmail = o.email.by_status.find((r) => r.key === "failed")?.count ?? 0;
  const skew = Math.round((new Date(o.system.database_time).getTime() - Date.now()) / 1000);
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Panel title="Platform">
        <dl>
          <Fact label="Environment">{humanise(o.system.environment)}</Fact>
          <Fact label="Database schema">
            <span className="num">{o.system.schema_revision ?? "Unknown"}</span>
          </Fact>
          <Fact label="Database clock">{Math.abs(skew) < 60 ? "In sync with your device" : `${skew > 0 ? "+" : ""}${skew} s from your device`}</Fact>
          <Fact label="Open sessions">{o.activity.open_sessions}</Fact>
        </dl>
      </Panel>
      <Panel title="Email delivery" aside={failedEmail ? <span className="text-[13px] font-semibold text-ineligible-ink">● {failedEmail} failed</span> : <span className="text-[13px] text-eligible-ink">✓ No failures</span>}>
        <Breakdown rows={o.email.by_status} empty="No email has been queued yet." />
        {o.email.oldest_pending && <p className="mt-3 text-[13px] text-ink-soft">Oldest waiting since {formatDateTime(o.email.oldest_pending)}.</p>}
      </Panel>
      <Panel title="Catalogue" aside={<Link to="/curate" className="text-[13px] font-semibold text-ink underline underline-offset-4">Manage</Link>}>
        <Breakdown rows={o.catalogue.opportunities_by_status} />
      </Panel>
      <Panel title="Ingestion pipeline">
        <h3 className="text-[12.5px] font-semibold uppercase tracking-[0.08em] text-muted">Sources</h3>
        <div className="mt-2">
          <Breakdown rows={o.catalogue.sources_by_status} empty="No sources registered." />
        </div>
        <h3 className="mt-5 text-[12.5px] font-semibold uppercase tracking-[0.08em] text-muted">Candidates</h3>
        <div className="mt-2">
          <Breakdown rows={o.catalogue.candidates_by_state} empty="No candidates yet." />
        </div>
      </Panel>
    </div>
  );
}
