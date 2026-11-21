import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, unwrap } from "./client";
import type {
  ApplicationCreate,
  ApplicationItemCreate,
  ApplicationItemUpdate,
  ApplicationUpdate,
  EducationCreate,
  EducationUpdate,
  Match,
  Opportunity,
  OpportunityUpdate,
  ProfileCreate,
  ProfileUpdate,
  TestScoreCreate,
} from "./types";
import type { components } from "./schema";
import { useAuth } from "../auth/AuthContext";

type Schemas = components["schemas"];

export const keys = {
  opportunities: ["opportunities"] as const,
  opportunity: (id: string) => ["opportunity", id] as const,
  skills: ["skills"] as const,
  account: ["me", "account"] as const,
  profile: ["me", "profile"] as const,
  education: ["me", "education"] as const,
  testScores: ["me", "test-scores"] as const,
  mySkills: ["me", "skills"] as const,
  matches: ["me", "matches"] as const,
  savedOpportunities: ["me", "saved-opportunities"] as const,
  applications: ["me", "applications"] as const,
  application: (id: string) => ["me", "applications", id] as const,
  curatorSources: ["curate", "sources"] as const,
  curatorOpportunities: (status?: string) => ["curate", "opportunities", status ?? "all"] as const,
  curatorCandidates: (state?: string, sourceId?: string) => ["curate", "candidates", state ?? "all", sourceId ?? "all"] as const,
  candidateDetail: (id: string) => ["curate", "candidates", id] as const,
  candidateRuns: ["curate", "candidates", "runs"] as const,
  auditLog: ["admin", "audit"] as const,
  adminOverview: ["admin", "overview"] as const,
  adminUsers: (query: AdminUserQuery) => ["admin", "users", query] as const,
  adminUser: (id: string) => ["admin", "user", id] as const,
  adminActivity: (filters: { action?: string; targetType?: string }) => ["admin", "activity", filters] as const,
  ingestionJobs: ["curate", "ingestion", "jobs"] as const,
};

export type AdminUserQuery = { q?: string; role?: "student" | "curator" | "admin"; state?: "active" | "suspended" | "pending_deletion"; sort?: "newest" | "oldest" | "last_active" | "email"; limit: number; offset: number };
export type AdminUserAction =
  | { kind: "role"; role: "student" | "curator" | "admin"; reason: string }
  | { kind: "status"; active: boolean; reason: string }
  | { kind: "signout"; reason: string };

const PAGE = 100;

/** Every published opportunity; the API pages at 100 rows. */
export const opportunitiesQuery = {
  queryKey: keys.opportunities,
  queryFn: async () => {
    const all: Opportunity[] = [];
    for (let offset = 0; ; offset += PAGE) {
      const page = await unwrap(api.GET("/opportunities", { params: { query: { limit: PAGE, offset } } }));
      all.push(...page);
      if (page.length < PAGE) return all;
    }
  },
  staleTime: 60_000,
};

export function useOpportunities() {
  return useQuery(opportunitiesQuery);
}

export function useOpportunity(id: string | undefined) {
  return useQuery({
    queryKey: keys.opportunity(id ?? ""),
    queryFn: () => unwrap(api.GET("/opportunities/{opportunity_id}", { params: { path: { opportunity_id: id! } } })),
    enabled: Boolean(id),
    staleTime: 60_000,
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
  });
}

export function useSkillCatalog() {
  return useQuery({
    queryKey: keys.skills,
    queryFn: () => unwrap(api.GET("/skills")),
    staleTime: 5 * 60_000,
  });
}

/** The signed-in user's profile, or ``null`` when they have not created one yet. */
export function useProfile() {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: keys.profile,
    queryFn: async () => {
      try {
        return await unwrap(api.GET("/me/profile"));
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
    enabled: isAuthenticated,
    staleTime: 30_000,
  });
}

function useProfileChild<T>(key: readonly unknown[], load: () => Promise<T>, enabled = true) {
  const { isAuthenticated } = useAuth();
  const profile = useProfile();
  return useQuery({
    queryKey: key,
    queryFn: load,
    enabled: isAuthenticated && Boolean(profile.data) && enabled,
    staleTime: 30_000,
  });
}

export function useEducation() {
  return useProfileChild(keys.education, () => unwrap(api.GET("/me/profile/education")));
}

export function useTestScores() {
  return useProfileChild(keys.testScores, () => unwrap(api.GET("/me/profile/test-scores")));
}

export function useMySkills() {
  return useProfileChild(keys.mySkills, () => unwrap(api.GET("/me/profile/skills")));
}

/** All persisted matches for the profile (newest evaluation first). */
export function useMatches() {
  return useProfileChild(keys.matches, async () => {
    const all: Match[] = [];
    for (let offset = 0; ; offset += PAGE) {
      const page = await unwrap(api.GET("/me/matches", { params: { query: { limit: PAGE, offset } } }));
      all.push(...page.map(normalizeMatch));
      if (page.length < PAGE) return all;
    }
  });
}

/** Normalize at the boundary: a match without evidence rows has an empty list. */
export function normalizeMatch(match: Schemas["MatchRead"]): Match {
  return { ...match, requirements: match.requirements ?? [] };
}

export function useMatchMap(): Map<string, Match> {
  const matches = useMatches();
  const map = new Map<string, Match>();
  for (const match of matches.data ?? []) map.set(match.opportunity_id, match);
  return map;
}

/** Store one fresh evaluation in the shared matches cache. */
export function mergeMatch(previous: Match[] | undefined, match: Match): Match[] {
  const rest = (previous ?? []).filter((item) => item.opportunity_id !== match.opportunity_id);
  return [match, ...rest];
}

export async function evaluateOpportunity(opportunityId: string): Promise<Match> {
  const match = await unwrap(
    api.POST("/me/opportunities/{opportunity_id}/match", { params: { path: { opportunity_id: opportunityId } } }),
  );
  return normalizeMatch(match);
}

export async function batchEvaluateOpportunities(opportunityIds?: string[]): Promise<Match[]> {
  const matches = await unwrap(
    (api as any).POST("/me/matches/batch-evaluate", {
      body: { opportunity_ids: opportunityIds && opportunityIds.length > 0 ? opportunityIds : null },
    }),
  );
  return (matches as any[]).map(normalizeMatch);
}

// --- Profile mutations ----------------------------------------------------------------------

export function useCreateProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ProfileCreate) => unwrap(api.POST("/me/profile", { body })),
    onSuccess: (profile) => client.setQueryData(keys.profile, profile),
  });
}

export function useUpdateProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ProfileUpdate) => unwrap(api.PATCH("/me/profile", { body })),
    onSuccess: (profile) => client.setQueryData(keys.profile, profile),
  });
}

export function useSaveEducation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: EducationCreate | EducationUpdate }) =>
      id
        ? unwrap(
            api.PATCH("/me/profile/education/{education_id}", {
              params: { path: { education_id: id } },
              body: body as EducationUpdate,
            }),
          )
        : unwrap(api.POST("/me/profile/education", { body: body as EducationCreate })),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.education }),
  });
}

export function useDeleteEducation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/me/profile/education/{education_id}", { params: { path: { education_id: id } } })),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.education }),
  });
}

export function useAddTestScore() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: TestScoreCreate) => unwrap(api.POST("/me/profile/test-scores", { body })),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.testScores }),
  });
}

export function useDeleteTestScore() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.DELETE("/me/profile/test-scores/{test_score_id}", { params: { path: { test_score_id: id } } }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.testScores }),
  });
}

export function useToggleSkill() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ skillId, attached }: { skillId: string; attached: boolean }) =>
      attached
        ? unwrap(api.DELETE("/me/profile/skills/{skill_id}", { params: { path: { skill_id: skillId } } }))
        : unwrap(api.POST("/me/profile/skills", { body: { skill_id: skillId } })),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.mySkills }),
  });
}

export function useUserAccount() {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: keys.account,
    queryFn: () => unwrap(api.GET("/me")),
    enabled: isAuthenticated,
    staleTime: 60_000,
  });
}

export function useSavedOpportunities() {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: keys.savedOpportunities,
    queryFn: () => unwrap(api.GET("/me/saved-opportunities")),
    enabled: isAuthenticated,
    staleTime: 30_000,
  });
}

export function useSaveOpportunity() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ opportunityId, remindersEnabled = true }: { opportunityId: string; remindersEnabled?: boolean }) =>
      unwrap(api.POST("/me/saved-opportunities", { body: { opportunity_id: opportunityId, reminders_enabled: remindersEnabled } })),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.savedOpportunities });
    },
  });
}

export function useUnsaveOpportunity() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (opportunityId: string) =>
      unwrap(api.DELETE("/me/saved-opportunities/{opportunity_id}", { params: { path: { opportunity_id: opportunityId } } })),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.savedOpportunities });
    },
  });
}

export function useApplications() {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: keys.applications,
    queryFn: () => unwrap(api.GET("/me/applications")),
    enabled: isAuthenticated,
    staleTime: 30_000,
  });
}

export function useApplication(id: string | undefined) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: keys.application(id ?? ""),
    queryFn: () => unwrap(api.GET("/me/applications/{application_id}", { params: { path: { application_id: id! } } })),
    enabled: isAuthenticated && Boolean(id),
    staleTime: 30_000,
  });
}

export function useCreateApplication() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ApplicationCreate) => unwrap(api.POST("/me/applications", { body })),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.applications });
      client.invalidateQueries({ queryKey: keys.savedOpportunities });
    },
  });
}

export function useUpdateApplication() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ApplicationUpdate }) =>
      unwrap(api.PATCH("/me/applications/{application_id}", { params: { path: { application_id: id } }, body })),
    onSuccess: (_, variables) => {
      client.invalidateQueries({ queryKey: keys.applications });
      client.invalidateQueries({ queryKey: keys.application(variables.id) });
    },
  });
}

export function useDeleteApplication() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/me/applications/{application_id}", { params: { path: { application_id: id } } })),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.applications });
    },
  });
}

export function useCreateApplicationItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ applicationId, body }: { applicationId: string; body: ApplicationItemCreate }) =>
      unwrap(api.POST("/me/applications/{application_id}/items", { params: { path: { application_id: applicationId } }, body })),
    onSuccess: (_, variables) => {
      client.invalidateQueries({ queryKey: keys.application(variables.applicationId) });
      client.invalidateQueries({ queryKey: keys.applications });
    },
  });
}

export function useUpdateApplicationItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ applicationId, itemId, body }: { applicationId: string; itemId: string; body: ApplicationItemUpdate }) =>
      unwrap(
        api.PATCH("/me/applications/{application_id}/items/{item_id}", {
          params: { path: { application_id: applicationId, item_id: itemId } },
          body,
        }),
      ),
    onSuccess: (_, variables) => {
      client.invalidateQueries({ queryKey: keys.application(variables.applicationId) });
      client.invalidateQueries({ queryKey: keys.applications });
    },
  });
}

export function useDeleteApplicationItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ applicationId, itemId }: { applicationId: string; itemId: string }) =>
      unwrap(
        api.DELETE("/me/applications/{application_id}/items/{item_id}", {
          params: { path: { application_id: applicationId, item_id: itemId } },
        }),
      ),
    onSuccess: (_, variables) => {
      client.invalidateQueries({ queryKey: keys.application(variables.applicationId) });
      client.invalidateQueries({ queryKey: keys.applications });
    },
  });
}

export function useCuratorSources() {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: keys.curatorSources,
    queryFn: () => unwrap(api.GET("/curate/sources")),
    enabled: isAuthenticated,
    staleTime: 30_000,
  });
}

export function useCuratorOpportunities(status?: string) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: keys.curatorOpportunities(status),
    queryFn: () =>
      unwrap(
        api.GET("/curate/opportunities", {
          params: { query: status && status !== "all" ? { status: status as any } : {} },
        }),
      ),
    enabled: isAuthenticated,
    staleTime: 30_000,
  });
}

export function useCreateOpportunity() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["OpportunityCreate"]) => unwrap(api.POST("/opportunities", { body })),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["curate", "opportunities"] });
      client.invalidateQueries({ queryKey: keys.opportunities });
    },
  });
}

export function useUpdateOpportunity() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: OpportunityUpdate }) =>
      unwrap(api.PATCH("/curate/opportunities/{opportunity_id}", { params: { path: { opportunity_id: id } }, body })),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["curate", "opportunities"] });
      client.invalidateQueries({ queryKey: keys.opportunities });
    },
  });
}

export function usePublishOpportunity() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.POST("/curate/opportunities/{opportunity_id}/publish", { params: { path: { opportunity_id: id } } })),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["curate", "opportunities"] });
      client.invalidateQueries({ queryKey: keys.opportunities });
    },
  });
}

export function useCloseOpportunity() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.POST("/curate/opportunities/{opportunity_id}/close", { params: { path: { opportunity_id: id } } })),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["curate", "opportunities"] });
      client.invalidateQueries({ queryKey: keys.opportunities });
    },
  });
}

export function useAuditLog(targetType?: string, action?: string) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: keys.auditLog,
    queryFn: () =>
      unwrap(
        api.GET("/admin/audit", {
          params: { query: { target_type: targetType, action } },
        }),
      ),
    enabled: isAuthenticated,
    staleTime: 15_000,
  });
}

export function useCuratorCandidates(state?: string, sourceId?: string) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: keys.curatorCandidates(state, sourceId),
    queryFn: () =>
      unwrap(
        api.GET("/curate/candidates", {
          params: { query: { state: state === "all" ? undefined : (state as any), source_id: sourceId } },
        }),
      ),
    enabled: isAuthenticated,
    staleTime: 15_000,
  });
}

export function useCandidateDetail(candidateId?: string | null) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: keys.candidateDetail(candidateId ?? ""),
    queryFn: () =>
      unwrap(
        api.GET("/curate/candidates/{candidate_id}", {
          params: { path: { candidate_id: candidateId! } },
        }),
      ),
    enabled: isAuthenticated && Boolean(candidateId),
    staleTime: 15_000,
  });
}

export function useCandidateRuns(limit = 20) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: keys.candidateRuns,
    queryFn: () =>
      unwrap(
        api.GET("/curate/candidates/runs", {
          params: { query: { limit } },
        }),
      ),
    enabled: isAuthenticated,
    staleTime: 30_000,
  });
}

export function useReviewCandidate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Schemas["ReviewRequest"] }) =>
      unwrap(
        api.POST("/curate/candidates/{candidate_id}/review", {
          params: { path: { candidate_id: id } },
          body,
        }),
      ),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["curate", "candidates"] });
      client.invalidateQueries({ queryKey: ["curate", "opportunities"] });
      client.invalidateQueries({ queryKey: keys.opportunities });
    },
  });
}

export function useRequeueCandidate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.POST("/curate/candidates/{candidate_id}/requeue", {
          params: { path: { candidate_id: id } },
        }),
      ),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["curate", "candidates"] });
    },
  });
}


/* Admin console ---------------------------------------------------------- */

export function useAdminOverview() {
  return useQuery({
    queryKey: keys.adminOverview,
    queryFn: () => unwrap(api.GET("/admin/overview")),
    staleTime: 30_000,
  });
}

export function useAdminUsers(query: AdminUserQuery) {
  return useQuery({
    queryKey: keys.adminUsers(query),
    queryFn: () => unwrap(api.GET("/admin/users", { params: { query } })),
    placeholderData: (previous) => previous, // keep the current page on screen while the next loads
    staleTime: 15_000,
  });
}

export function useAdminUser(id: string | null) {
  return useQuery({
    queryKey: keys.adminUser(id ?? ""),
    queryFn: () => unwrap(api.GET("/admin/users/{user_id}", { params: { path: { user_id: id! } } })),
    enabled: Boolean(id),
  });
}

/** Role, suspension and sign-out-everywhere: each needs a reason and is audited by the API. */
export function useAdminUserAction(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (action: AdminUserAction) => {
      const path = { params: { path: { user_id: id } } };
      if (action.kind === "role") return unwrap(api.POST("/admin/users/{user_id}/role", { ...path, body: { role: action.role, reason: action.reason } }));
      if (action.kind === "status") return unwrap(api.POST("/admin/users/{user_id}/status", { ...path, body: { active: action.active, reason: action.reason } }));
      return unwrap(api.POST("/admin/users/{user_id}/sessions/revoke", { ...path, body: { reason: action.reason } }));
    },
    onSuccess: (detail) => {
      client.setQueryData(keys.adminUser(id), detail);
      void client.invalidateQueries({ queryKey: ["admin", "users"] });
      void client.invalidateQueries({ queryKey: keys.adminOverview });
      void client.invalidateQueries({ queryKey: ["admin", "activity"] });
    },
  });
}

/** The audit log, newest first, fifty at a time. */
export function useAdminActivity(filters: { action?: string; targetType?: string }) {
  return useInfiniteQuery({
    queryKey: keys.adminActivity(filters),
    initialPageParam: undefined as number | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(api.GET("/admin/audit", { params: { query: { action: filters.action || undefined, target_type: filters.targetType || undefined, limit: 50, before_id: pageParam } } })),
    getNextPageParam: (last) => (last.length === 50 ? last[last.length - 1]!.id : undefined),
    staleTime: 15_000,
  });
}


/* Running the pipeline from the site ----------------------------------- */

/** The current ingestion job and the last few; polls every 2 s only while one runs. */
export function useIngestionJobs() {
  return useQuery({
    queryKey: keys.ingestionJobs,
    queryFn: () => unwrap(api.GET("/curate/ingestion/jobs")),
    refetchInterval: (query) => (query.state.data?.current ? 2000 : false),
  });
}

export function useIngestionActions() {
  const client = useQueryClient();
  const refresh = () => {
    void client.invalidateQueries({ queryKey: keys.ingestionJobs });
    void client.invalidateQueries({ queryKey: keys.curatorSources });
    void client.invalidateQueries({ queryKey: ["curate", "candidates"] });
  };
  const onSuccess = refresh;
  return {
    refresh,
    importStarter: useMutation({ mutationFn: () => unwrap(api.POST("/curate/ingestion/jobs/starter-sources")), onSuccess }),
    startPipeline: useMutation({
      mutationFn: (sourceId?: string) => unwrap(api.POST("/curate/ingestion/jobs/pipeline", { body: { source_id: sourceId ?? null, limit: 50 } })),
      onSuccess,
    }),
    testSource: useMutation({
      mutationFn: (sourceId: string) => unwrap(api.POST("/curate/ingestion/jobs/source-test/{source_id}", { params: { path: { source_id: sourceId } } })),
      onSuccess,
    }),
    reviewTerms: useMutation({
      mutationFn: (input: { sourceId: string; status: "acceptable" | "restricted"; notes: string }) =>
        unwrap(api.POST("/curate/sources/{source_id}/terms-review", { params: { path: { source_id: input.sourceId } }, body: { status: input.status, notes: input.notes } })),
      onSuccess,
    }),
    setPublishMode: useMutation({
      mutationFn: (input: { sourceId: string; mode: "off" | "shadow" | "listing_only" | "full"; reason: string }) =>
        unwrap(api.POST("/curate/sources/{source_id}/publish-mode", { params: { path: { source_id: input.sourceId } }, body: { mode: input.mode, reason: input.reason } })),
      onSuccess,
    }),
    changeStatus: useMutation({
      mutationFn: (input: { sourceId: string; status: "approved" | "paused" | "testing"; reason?: string }) =>
        unwrap(api.POST("/curate/sources/{source_id}/status", { params: { path: { source_id: input.sourceId } }, body: { status: input.status, reason: input.reason ?? null } })),
      onSuccess,
    }),
  };
}
