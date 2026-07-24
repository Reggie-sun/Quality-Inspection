import { getJson, postForm } from "../../api/client";
import type { ProjectStatus } from "../../api/types";


export type ProjectApi = {
  createProject: (file: File, signal?: AbortSignal) => Promise<ProjectStatus>;
  getProjectStatus: (
    projectId: string,
    signal?: AbortSignal,
  ) => Promise<ProjectStatus>;
};


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


export const projectApi: ProjectApi = {
  createProject,
  getProjectStatus,
};
