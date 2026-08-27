export type SourceStatus = {
  name?: string;
  status: 'ok' | 'error' | 'disabled' | 'not_configured' | 'rate_limited';
  result_count?: number;
  detail?: string | null;
  enabled?: boolean;
  configured?: boolean;
  checked_at?: string;
};

export type Citation = {
  source_type: string;
  section?: string | null;
  page_start?: number | null;
  page_end?: number | null;
  chunk_id?: number | null;
};

export type RankingMetadata = {
  label: string;
  relevance: number;
  rank_score: number;
  relevance_band: number;
  position: number;
};

export type Paper = {
  id: number;
  title: string;
  normalized_title?: string;
  translated_title?: string | null;
  abstract?: string | null;
  publication_year?: number | null;
  publication_date?: string | null;
  authors: Array<{ name: string; orcid?: string | null }>;
  venue?: string | null;
  venue_type?: string | null;
  doi?: string | null;
  arxiv_id?: string | null;
  external_ids?: Record<string, string>;
  source_urls: string[];
  publisher_url?: string | null;
  pdf_url?: string | null;
  open_access_status?: string | null;
  citation_count?: number | null;
  reference_count?: number | null;
  fields_of_study?: string[];
  concepts?: string[];
  keywords: string[];
  source_provenance: Array<{ source: string; source_id: string; is_fixture: boolean }>;
  is_fixture: boolean;
  abstract_evidence_verified: boolean;
  ranking?: RankingMetadata | null;
};

export type SearchSession = {
  id: number;
  project_id?: number | null;
  query: string;
  filters: Record<string, unknown>;
  source_status: Record<string, SourceStatus>;
  result_ids: number[];
  result_count: number;
  search_mode: string;
  diversity_seed?: string | null;
  ranking_rule_version: string;
  composition: Record<string, unknown>;
  created_at: string;
};

export type PaperSet = {
  id: number;
  project_id?: number | null;
  purpose: 'compare' | 'gap' | 'manual';
  name: string;
  source_kind: 'explicit' | 'search_session' | 'favorites' | 'manual';
  paper_ids: number[];
  papers: Paper[];
  created_at: string;
};

export type Project = {
  id: number;
  name: string;
  description?: string | null;
  broad_direction?: string | null;
  status: string;
};

export type ScoreResult = {
  score: number;
  evidence_coverage: number;
  components?: Record<string, number | null>;
  reasons?: Record<string, string>;
  blocking_reasons?: string[];
  estimated_difficulty?: string;
};

export type TaskDefinition = {
  input?: string | null;
  output?: string | null;
  setting?: string | null;
};

export type PaperAnalysisBody = {
  evidence_level: string;
  executive_summary: string;
  summary: string;
  research_background?: string | null;
  research_problem?: string | null;
  task_definition: TaskDefinition;
  theoretical_contribution: string[];
  method_innovation: string[];
  research_route: string[];
  inputs: string[];
  outputs: string[];
  core_methods: string[];
  new_modules: string[];
  datasets: string[];
  baselines: string[];
  metrics: string[];
  experimental_protocol: string[];
  major_results: string[];
  claimed_contributions: string[];
  future_work_explicit: string[];
  limitations_author_stated: string[];
  limitations_inferred: string[];
  methods: string[];
  citations: Citation[];
  field_states: Record<string, 'evidenced' | 'insufficient_evidence' | 'unknown'>;
  field_citations: Record<string, Citation[]>;
  missing_fields: string[];
  warnings: string[];
};

export type PaperAnalysis = {
  id: number;
  paper_id: number;
  project_id?: number | null;
  analysis_version: string;
  analysis: PaperAnalysisBody;
  direction_similarity: ScoreResult;
  reproduction_assessment: ScoreResult;
  created_at?: string;
  analysis_mode?: string;
  provider?: string;
  model_name?: string | null;
  prompt_version?: string | null;
  fallback_reason?: string | null;
};

export type EvidenceAcquisition = {
  run_id: string;
  outcome: 'abstract_acquired' | 'no_matching_evidence' | 'no_eligible_source' | 'source_unavailable' | 'already_sufficient';
  evidence_level_before: 'metadata_only' | 'abstract_only' | 'open_fulltext' | 'user_uploaded_fulltext' | 'publisher_authorized_fulltext';
  evidence_level_after: 'metadata_only' | 'abstract_only' | 'open_fulltext' | 'user_uploaded_fulltext' | 'publisher_authorized_fulltext';
  queried_sources: string[];
  source_status: Record<string, SourceStatus>;
  paper: Paper;
  analysis: PaperAnalysis;
};



export type EvidenceWorkflowEvent = {
  id: number;
  event_type: string;
  detail: Record<string, unknown>;
  created_at: string;
};

export type EvidenceWorkflow = {
  id: number;
  paper_id: number;
  project_id?: number | null;
  status: 'pending' | 'running' | 'succeeded' | 'partial' | 'failed' | 'cancelled' | string;
  payload: Record<string, unknown>;
  result: Record<string, unknown>;
  error?: string | null;
  strongest_evidence: 'metadata_only' | 'abstract_only' | 'open_fulltext' | 'user_uploaded_fulltext' | 'publisher_authorized_fulltext' | string;
  attempt_count: number;
  max_attempts: number;
  started_at?: string | null;
  finished_at?: string | null;
  cancelled_at?: string | null;
  created_at: string;
  terminal: boolean;
  events: EvidenceWorkflowEvent[];
};

export type AuthorCard = {
  id: number;
  canonical_name: string;
  orcid?: string | null;
  openalex_id?: string | null;
  semantic_scholar_id?: string | null;
  affiliations: string[];
  topics: string[];
  works_count?: number | null;
  citation_count?: number | null;
  homepage?: string | null;
  identity_status: string;
  provenance: Array<Record<string, unknown>>;
  position?: number | null;
  credit_roles: string[];
};

export type DatasetCard = {
  id: number;
  canonical_name: string;
  access_url?: string | null;
  license?: string | null;
  domain?: string | null;
  identity_status: string;
  provenance: Array<Record<string, unknown>>;
  mention_id?: number | null;
  paper_id?: number | null;
  analysis_id?: number | null;
  raw_mention?: string | null;
  role?: string | null;
  task?: string | null;
  train_split?: string | null;
  validation_split?: string | null;
  test_split?: string | null;
  metrics: string[];
  evidence_level?: string | null;
  field_citations: Record<string, Citation[]>;
};

export type DirectionCluster = {
  id: number;
  cluster_key: string;
  label: string;
  terms: string[];
  evidence_distribution: Record<string, number>;
};

export type DirectionClusterMember = {
  paper_id: number;
  cluster_id?: number | null;
  cluster_key?: string | null;
  similarity: number;
  is_unclustered: boolean;
};

export type DirectionClusterRun = {
  id: number;
  project_id: number;
  algorithm_version: string;
  parameters: Record<string, unknown>;
  input_hash: string;
  status: string;
  disclaimer: string;
  clusters: DirectionCluster[];
  members: DirectionClusterMember[];
};

export type EvaluationVariant = {
  label: 'A' | 'B';
  payload: Record<string, unknown>;
};


export type EvaluationTask = {
  id: number;
  task_key: string;
  paper_id?: number | null;
  position: number;
};

export type EvaluationStudy = {
  id: number;
  name: string;
  description?: string | null;
  status: string;
  study_version: string;
  frozen_input_hash?: string | null;
  expert_outcome_validation: string;
  randomized_seed: string;
  protocol: Record<string, unknown>;
  tasks: EvaluationTask[];
};

export type EvaluationAssignment = {
  id: number;
  study_id: number;
  task_id: number;
  task_key: string;
  status: string;
  is_simulated: boolean;
  variants: EvaluationVariant[];
  assigned_at: string;
  started_at?: string | null;
  completed_at?: string | null;
};

export type EvaluationResult = {
  study_id: number;
  metrics: Record<string, unknown>;
  real_expert_count: number;
  simulated_count: number;
  validation_status: string;
  claim_boundary: string;
};

export type PaperDocument = {
  id: number;
  paper_id: number;
  original_filename: string;
  evidence_level: string;
  source_type: string;
  sha256: string;
  size_bytes: number;
  page_count: number;
  chunk_count: number;
  source_url?: string | null;
  source_record_id?: string | null;
  rights_basis?: string | null;
  license?: string | null;
  retrieved_at?: string | null;
  response_hash?: string | null;
  acquisition_run_id?: string | null;
  created_at: string;
};

export type ComparisonCell = {
  paper_id: number;
  value: unknown;
  evidence_state: 'evidenced' | 'insufficient_evidence' | 'unknown';
  citations: Citation[];
};

export type ComparisonRow = {
  key: string;
  label: string;
  cells: ComparisonCell[];
};

export type ComparisonRun = {
  id: number;
  project_id: number;
  paper_set_id: number;
  direction_snapshot: Record<string, unknown>;
  papers: Array<{ id: number; title: string; publication_year?: number | null; venue?: string | null; evidence_level: string }>;
  rows: ComparisonRow[];
  analysis_version: string;
  evidence_hash: string;
  created_at: string;
};

export type GapExplanation = {
  version: number;
  provider: string;
  direct_evidence: Array<Record<string, unknown>>;
  inferences: string[];
  supporting_papers: number[];
  weakening_papers: number[];
  absent_evidence: string[];
  direction_relation: Record<string, unknown>;
  novelty_risk_factors: string[];
  challenge_queries: string[];
  minimum_validation: string[];
  confidence_rationale: string;
  not_novelty_proof: boolean;
  evidence_hash: string;
};

export type GapCandidate = {
  id: number;
  project_id: number;
  paper_set_id?: number | null;
  direction_snapshot: Record<string, unknown>;
  gap_type: string;
  claim: string;
  scope: string;
  status: string;
  workflow_stage: string;
  evidence_matrix: Array<Record<string, unknown>>;
  supporting_evidence: number[];
  adjacent_work: number[];
  counter_evidence: Array<Record<string, unknown>>;
  challenge_queries: string[];
  data_sources: string[];
  coverage: Record<string, unknown>;
  confidence: string;
  risk_factors: string[];
  minimal_validation: string[];
  suggested_research_question: string;
  not_novelty_proof: boolean;
  explanation?: GapExplanation | null;
  challenge_completed_at?: string | null;
  confirmed_at?: string | null;
  human_confirmation_note?: string | null;
};

export type PlanItem = {
  id: number;
  category: string;
  title: string;
  description: string;
  sequence: number;
  status: string;
  notes?: string | null;
};

export type ResearchPlan = {
  id: number;
  project_id: number;
  gap_id?: number | null;
  title: string;
  objective: string;
  status: string;
  items: PlanItem[];
};

export type LibraryItem = {
  paper: Paper;
  favorite: boolean;
  notes: Array<{ id: number; paper_id: number; content: string; note_type: string; created_at?: string; updated_at?: string }>;
  tags: Array<{ id: number; name: string }>;
  reading_status?: { id: number; paper_id: number; status: string; progress: number; updated_at: string } | null;
};

export type UserSettings = {
  default_result_count: 10 | 20 | 50 | number;
  default_page_size: number;
  preferred_sources: string[];
  default_open_access_only: boolean;
  display_language: string;
  analysis_execution_preference: 'synchronous' | 'queued';
};

export type Job = {
  id: number;
  project_id?: number | null;
  job_type: string;
  status: string;
  payload: Record<string, unknown>;
  result: Record<string, unknown>;
  error?: string | null;
  attempt_count: number;
  max_attempts: number;
  terminal: boolean;
  started_at?: string | null;
  finished_at?: string | null;
  cancelled_at?: string | null;
  created_at: string;
};
