// Typed client for /documents — LEGAL-API.md §Documents. Phase 9.2 added
// real processing/ask/analyze/delete endpoints.

import { apiClient, withWorkspace } from "@/lib/api-client";
import type { Document, DocumentAnalyzeResponse, DocumentAskResponse } from "@/types/document";

export async function listDocuments(workspaceId: string): Promise<Document[]> {
  const { data } = await apiClient.get<Document[]>("/api/v1/legal/documents", withWorkspace(workspaceId));
  return data;
}

export async function getDocument(workspaceId: string, documentId: string): Promise<Document> {
  const { data } = await apiClient.get<Document>(`/api/v1/legal/documents/${documentId}`, withWorkspace(workspaceId));
  return data;
}

export async function uploadDocument(workspaceId: string, file: File): Promise<Document> {
  const form = new FormData();
  form.append("file", file);
  const config = withWorkspace(workspaceId);
  const { data } = await apiClient.post<Document>("/api/v1/legal/documents", form, {
    ...config,
    headers: { ...config.headers, "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deleteDocument(workspaceId: string, documentId: string): Promise<void> {
  await apiClient.delete(`/api/v1/legal/documents/${documentId}`, withWorkspace(workspaceId));
}

export async function reprocessDocument(workspaceId: string, documentId: string): Promise<Document> {
  const { data } = await apiClient.post<Document>(
    `/api/v1/legal/documents/${documentId}/process`,
    {},
    withWorkspace(workspaceId)
  );
  return data;
}

export async function getDocumentText(workspaceId: string, documentId: string): Promise<string> {
  const { data } = await apiClient.get<{ document_id: string; text: string }>(
    `/api/v1/legal/documents/${documentId}/text`,
    withWorkspace(workspaceId)
  );
  return data.text;
}

export async function askDocument(workspaceId: string, documentId: string, question: string): Promise<DocumentAskResponse> {
  const { data } = await apiClient.post<DocumentAskResponse>(
    `/api/v1/legal/documents/${documentId}/ask`,
    { question },
    withWorkspace(workspaceId)
  );
  return data;
}

export async function analyzeDocument(workspaceId: string, documentId: string): Promise<DocumentAnalyzeResponse> {
  const { data } = await apiClient.post<DocumentAnalyzeResponse>(
    `/api/v1/legal/documents/${documentId}/analyze`,
    {},
    withWorkspace(workspaceId)
  );
  return data;
}
