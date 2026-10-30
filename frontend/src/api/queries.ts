import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, unwrap } from "./client";
import type {
  EducationCreate,
  EducationUpdate,
  Match,
  Opportunity,
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
  profile: ["me", "profile"] as const,
  education: ["me", "education"] as const,
  testScores: ["me", "test-scores"] as const,
  mySkills: ["me", "skills"] as const,
  matches: ["me", "matches"] as const,
};

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
