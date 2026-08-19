"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { createContract, listContracts } from "@/api/contracts";
import { useAuth } from "@/hooks/useAuth";
import type { Contract, ContractType } from "@/types/contract";

const CONTRACT_TYPES: ContractType[] = ["service", "supply", "sale", "lease", "nda", "license", "other"];

export function ContractsView() {
  const { workspaceId } = useAuth();
  const [contracts, setContracts] = useState<Contract[] | null>(null);
  const [title, setTitle] = useState("");
  const [rawText, setRawText] = useState("");
  const [contractType, setContractType] = useState<ContractType>("service");
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  async function refresh() {
    if (!workspaceId) return;
    try {
      setContracts(await listContracts(workspaceId));
    } catch {
      setError("Не удалось загрузить договоры — backend доступен?");
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  async function handleUpload() {
    if (!title.trim() || !rawText.trim() || !workspaceId) return;
    setUploading(true);
    setError(null);
    try {
      await createContract(workspaceId, { title, raw_text: rawText, contract_type: contractType });
      setTitle("");
      setRawText("");
      await refresh();
    } catch {
      setError("Загрузка не удалась.");
    } finally {
      setUploading(false);
    }
  }

  if (!workspaceId) {
    return <div className="p-8 text-sm text-slate-500">Выберите рабочее пространство, чтобы увидеть договоры.</div>;
  }

  return (
    <div className="mx-auto max-w-3xl p-4 sm:p-8">
      <h1 className="text-2xl font-semibold">Договоры</h1>
      <p className="mt-1 text-sm text-slate-400">
        Анализ договоров — извлечение условий, поиск рисков, проверка через Юридическое исследование,
        двойная проверка юристами, редлайн. Есть два способа добавить договор: вставить текст вручную ниже,
        или загрузить файл (PDF/DOCX/TXT) на странице «Документы» и оттуда отправить его на проверку.
      </p>
      <Link
        href="/documents"
        className="mt-3 inline-block rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
      >
        Загрузить договор (файл)
      </Link>

      <div className="mt-6 space-y-3 rounded border border-slate-800 p-4">
        <h2 className="text-sm font-medium text-slate-300">Или вставить текст вручную</h2>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Название"
          className="w-full rounded border border-slate-700 bg-slate-900 p-2 text-sm"
        />
        <select
          value={contractType}
          onChange={(e) => setContractType(e.target.value as ContractType)}
          className="rounded border border-slate-700 bg-slate-900 p-2 text-sm"
        >
          {CONTRACT_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <textarea
          value={rawText}
          onChange={(e) => setRawText(e.target.value)}
          placeholder="Вставьте текст договора"
          rows={8}
          className="w-full rounded border border-slate-700 bg-slate-900 p-2 text-sm"
        />
        <button
          onClick={handleUpload}
          disabled={uploading || !title.trim() || !rawText.trim()}
          className="w-full rounded bg-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-600 disabled:opacity-50 sm:w-auto"
        >
          {uploading ? "Загрузка..." : "Загрузить договор"}
        </button>
      </div>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      <section className="mt-8">
        <h2 className="text-lg font-medium">Недавние договоры</h2>
        {contracts === null && <p className="mt-2 text-sm text-slate-500">Загрузка…</p>}
        {contracts?.length === 0 && <p className="mt-2 text-sm text-slate-500">Пока нет договоров.</p>}
        <ul className="mt-2 space-y-2">
          {contracts?.map((c) => (
            <li key={c.id} className="rounded border border-slate-800 p-3 text-sm">
              <Link href={`/contracts/${c.id}`} className="font-medium text-slate-200 hover:underline">
                {c.title}
              </Link>
              <div className="text-slate-500">
                {c.contract_type} · {c.status}
                {c.is_mock && <span className="ml-2 rounded bg-amber-900 px-1.5 py-0.5 text-xs text-amber-300">MOCK</span>}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
