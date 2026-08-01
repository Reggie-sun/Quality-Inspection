import { getJson, postForm, postJson } from "../../api/client";
import type {
  ProjectListItemTransport,
  ProjectListTransport,
  ProjectStatus,
} from "../../api/types";


export type ProjectListItem = {
  projectId: string;
  fileName: string;
  createdAt: string;
  lastOpenedAt: string;
};


export type ProjectApi = {
  createProject: (file: File, signal?: AbortSignal) => Promise<ProjectStatus>;
  getProjectStatus: (
    projectId: string,
    signal?: AbortSignal,
  ) => Promise<ProjectStatus>;
  listProjects: (signal?: AbortSignal) => Promise<ProjectListItem[]>;
  markProjectOpened: (
    projectId: string,
    signal?: AbortSignal,
  ) => Promise<ProjectListItem>;
};


function projectListItem(item: ProjectListItemTransport): ProjectListItem {
  return {
    projectId: item.project_id,
    fileName: item.file_name,
    createdAt: item.created_at,
    lastOpenedAt: item.last_opened_at,
  };
}


export function createProject(
  file: File,
  signal?: AbortSignal,
): Promise<ProjectStatus> {
  const body = new FormData();
  body.set("file", file);
  return postForm<ProjectStatus>("/api/v1/projects", body, signal);
}


export function getProjectStatus(
  projectId: string,
  signal?: AbortSignal,
): Promise<ProjectStatus> {
  const path = `/api/v1/projects/${encodeURIComponent(projectId)}/status`;
  return getJson<ProjectStatus>(path, signal);
}


export async function listProjects(
  signal?: AbortSignal,
): Promise<ProjectListItem[]> {
  const response = await getJson<ProjectListTransport>(
    "/api/v1/projects",
    signal,
  );
  return response.items.map(projectListItem);
}


export async function markProjectOpened(
  projectId: string,
  signal?: AbortSignal,
): Promise<ProjectListItem> {
  const path = `/api/v1/projects/${encodeURIComponent(projectId)}/open`;
  const response = await postJson<ProjectListItemTransport>(
    path,
    undefined,
    { Accept: "application/json" },
    signal,
  );
  return projectListItem(response);
}


export const projectApi: ProjectApi = {
  createProject,
  getProjectStatus,
  listProjects,
  markProjectOpened,
};
